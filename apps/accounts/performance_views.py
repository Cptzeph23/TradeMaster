# ============================================================
# Performance REST API — per-account metrics endpoints
# ============================================================
import logging
from datetime import datetime, timezone, timedelta
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

logger = logging.getLogger('trading.performance')


def ok(data, code=status.HTTP_200_OK):
    return Response({'success': True, **data}, status=code)

def err(msg, code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': msg}, status=code)


class AccountPerformanceView(APIView):
    """
    GET /api/v1/performance/accounts/
        List performance summary for all user accounts.

    GET /api/v1/performance/accounts/<account_id>/
        Full performance detail for one account.

    POST /api/v1/performance/accounts/<account_id>/recalculate/
        Force recalculate metrics from all closed trades.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, account_id=None):
        from apps.accounts.models import TradingAccount
        from apps.accounts.performance_models import AccountPerformance
        from apps.accounts.performance_service import PerformanceService

        if account_id:
            # Single account detail
            try:
                acct = TradingAccount.objects.get(
                    pk=account_id, user=request.user, is_active=True
                )
            except TradingAccount.DoesNotExist:
                return err('Account not found.', status.HTTP_404_NOT_FOUND)

            perf, created = AccountPerformance.objects.get_or_create(
                account=acct
            )
            if created:
                # First time — calculate now
                svc  = PerformanceService(acct)
                perf = svc.update()

            return ok({'performance': perf.to_dict()})

        # All accounts for this user
        accounts = TradingAccount.objects.filter(
            user=request.user, is_active=True
        )
        result = []
        for acct in accounts:
            perf, _ = AccountPerformance.objects.get_or_create(account=acct)
            result.append({
                'account_id':   str(acct.id),
                'account_name': acct.name,
                'broker_type':  getattr(acct, 'broker_type', ''),
                'account_type': getattr(acct, 'account_type', ''),
                'funded_firm':  getattr(acct, 'funded_firm', ''),
                'balance':      float(acct.balance or 0),
                'total_trades': perf.total_trades,
                'win_rate':     round(perf.win_rate, 2),
                'total_pips':   round(perf.total_pips, 1),
                'total_profit': round(perf.total_profit, 2),
                'profit_factor':round(perf.profit_factor, 2),
                'max_drawdown': round(perf.max_drawdown_pct, 2),
                'avg_rrr_used': round(perf.avg_rrr_used, 2),
                'updated_at':   perf.updated_at.isoformat(),
            })

        return ok({'accounts': result, 'count': len(result)})

    def post(self, request, account_id):
        """Force recalculate — POST /accounts/<id>/recalculate/"""
        from apps.accounts.models import TradingAccount
        from apps.accounts.performance_service import PerformanceService

        try:
            acct = TradingAccount.objects.get(
                pk=account_id, user=request.user, is_active=True
            )
        except TradingAccount.DoesNotExist:
            return err('Account not found.', status.HTTP_404_NOT_FOUND)

        svc  = PerformanceService(acct)
        perf = svc.update()
        return ok({
            'message':     'Performance recalculated.',
            'performance': perf.to_dict(),
        })


class PerformanceHistoryView(APIView):
    """
    GET /api/v1/performance/accounts/<account_id>/history/
        Daily equity/P&L history for charting.
        Query params:
          ?days=30      (default 30, max 365)
          ?period=week|month|quarter|year
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, account_id):
        from apps.accounts.models import TradingAccount
        from apps.accounts.performance_models import AccountPerformanceHistory

        try:
            acct = TradingAccount.objects.get(
                pk=account_id, user=request.user, is_active=True
            )
        except TradingAccount.DoesNotExist:
            return err('Account not found.', status.HTTP_404_NOT_FOUND)

        period = request.query_params.get('period', '')
        days   = {
            'week':    7,
            'month':   30,
            'quarter': 90,
            'year':    365,
        }.get(period, int(request.query_params.get('days', 30)))
        days = min(days, 365)

        since = datetime.now(timezone.utc).date() - timedelta(days=days)
        snaps = AccountPerformanceHistory.objects.filter(
            account       = acct,
            snapshot_date__gte = since,
        ).order_by('snapshot_date')

        history = [{
            'date':        s.snapshot_date.isoformat(),
            'balance':     round(s.balance, 2),
            'equity':      round(s.equity,  2),
            'daily_pnl':   round(s.daily_pnl, 2),
            'daily_pips':  round(s.daily_pips, 1),
            'daily_trades':s.daily_trades,
            'win_rate':    round(s.daily_win_rate, 1),
            'drawdown':    round(s.drawdown_pct, 2),
        } for s in snaps]

        # Build equity curve from history
        equity_curve = [h['equity'] for h in history]
        dates        = [h['date']   for h in history]

        return ok({
            'account_id':   str(acct.id),
            'account_name': acct.name,
            'period_days':  days,
            'history':      history,
            'equity_curve': equity_curve,
            'dates':        dates,
            'count':        len(history),
        })


class PerformanceSymbolView(APIView):
    """
    GET /api/v1/performance/accounts/<account_id>/symbols/
        Per-symbol breakdown — wins, losses, pips, P&L per symbol.
        Optional: ?symbol=XAUUSD for one symbol detail.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, account_id):
        from apps.accounts.models import TradingAccount
        from apps.accounts.performance_models import AccountPerformance
        from apps.trading.models import Trade
        from utils.constants import TradeStatus

        try:
            acct = TradingAccount.objects.get(
                pk=account_id, user=request.user, is_active=True
            )
        except TradingAccount.DoesNotExist:
            return err('Account not found.', status.HTTP_404_NOT_FOUND)

        filter_sym = request.query_params.get('symbol', '').upper()

        try:
            perf = acct.performance
        except Exception:
            return err('No performance data yet — close a trade first.')

        stats = perf.symbol_stats or {}

        if filter_sym:
            sym_data = stats.get(filter_sym)
            if not sym_data:
                return err(f"No data for symbol '{filter_sym}'.")

            # Enrich with recent trades for this symbol
            recent = Trade.objects.filter(
                bot__trading_account = acct,
                symbol               = filter_sym,
                status               = TradeStatus.CLOSED,
            ).order_by('-closed_at')[:20]

            trades_detail = [{
                'id':           str(t.id),
                'order_type':   t.order_type,
                'entry':        float(t.entry_price or 0),
                'exit':         float(t.exit_price  or 0),
                'pnl':          round(float(t.profit_loss  or 0), 2),
                'pips':         round(float(t.profit_pips  or 0), 1),
                'sl_pips':      t.sl_pips,
                'tp_pips':      t.tp_pips,
                'rrr_used':     t.rrr_used,
                'rrr_achieved': t.rrr_achieved,
                'closed_at':    t.closed_at.isoformat() if t.closed_at else None,
            } for t in recent]

            return ok({
                'symbol':  filter_sym,
                'stats':   sym_data,
                'recent_trades': trades_detail,
            })

        # All symbols — sort by most trades
        sorted_stats = sorted(
            [{'symbol': k, **v} for k, v in stats.items()],
            key=lambda x: x['trades'],
            reverse=True,
        )
        return ok({
            'account_id':   str(acct.id),
            'symbol_stats': sorted_stats,
            'count':        len(sorted_stats),
        })


class PerformanceCompareView(APIView):
    """
    GET /api/v1/performance/compare/
        Compare metrics across all user accounts side by side.
        Useful for FTMO vs personal vs demo comparison.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.accounts.models import TradingAccount
        from apps.accounts.performance_models import AccountPerformance

        accounts = TradingAccount.objects.filter(
            user=request.user, is_active=True
        ).prefetch_related('performance')

        comparison = []
        for acct in accounts:
            try:
                perf = acct.performance
            except Exception:
                perf = None

            comparison.append({
                'account_id':    str(acct.id),
                'account_name':  acct.name,
                'broker_type':   getattr(acct, 'broker_type', ''),
                'account_type':  getattr(acct, 'account_type', ''),
                'funded_firm':   getattr(acct, 'funded_firm', ''),
                'balance':       float(acct.balance or 0),
                'metrics': {
                    'total_trades':  perf.total_trades    if perf else 0,
                    'win_rate':      round(perf.win_rate, 2)      if perf else 0,
                    'total_pips':    round(perf.total_pips, 1)    if perf else 0,
                    'total_profit':  round(perf.total_profit, 2)  if perf else 0,
                    'profit_factor': round(perf.profit_factor, 2) if perf else 0,
                    'expectancy':    round(perf.expectancy, 2)    if perf else 0,
                    'max_drawdown':  round(perf.max_drawdown_pct, 2) if perf else 0,
                    'avg_rrr_used':  round(perf.avg_rrr_used, 2)  if perf else 0,
                    'avg_rrr_achieved': round(perf.avg_rrr_achieved, 2) if perf else 0,
                    'current_streak': perf.current_streak          if perf else 0,
                } if perf else {},
            })

        # Sort by total profit descending
        comparison.sort(
            key=lambda x: x['metrics'].get('total_profit', 0),
            reverse=True
        )
        return ok({
            'accounts':    comparison,
            'count':       len(comparison),
            'best_account': comparison[0]['account_name'] if comparison else None,
        })


class PerformanceSummaryView(APIView):
    """
    GET /api/v1/performance/summary/
        Aggregated summary across ALL user accounts.
        Same as portfolio view but focused on performance metrics.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.accounts.models import TradingAccount
        from apps.accounts.performance_models import AccountPerformance
        from apps.trading.models import Trade
        from utils.constants import TradeStatus
        from datetime import date

        accounts = TradingAccount.objects.filter(
            user=request.user, is_active=True
        )

        total_balance = 0.0
        all_perfs     = []
        for acct in accounts:
            total_balance += float(acct.balance or 0)
            try:
                all_perfs.append(acct.performance)
            except Exception:
                pass

        # Aggregate
        total_trades  = sum(p.total_trades   for p in all_perfs)
        total_pips    = sum(p.total_pips     for p in all_perfs)
        total_profit  = sum(p.total_profit   for p in all_perfs)
        gross_profit  = sum(p.gross_profit   for p in all_perfs)
        gross_loss    = sum(p.gross_loss     for p in all_perfs)
        total_wins    = sum(p.winning_trades for p in all_perfs)

        win_rate = round(
            total_wins / total_trades * 100, 2
        ) if total_trades else 0.0
        pf = round(
            gross_profit / gross_loss, 2
        ) if gross_loss > 0 else 0.0

        # Today's P&L
        today = date.today()
        today_trades = Trade.objects.filter(
            bot__trading_account__user = request.user,
            status   = TradeStatus.CLOSED,
            closed_at__date = today,
        )
        today_pnl  = sum(float(t.profit_loss or 0) for t in today_trades)
        today_pips = sum(float(t.profit_pips or 0) for t in today_trades)

        return ok({
            'summary': {
                'total_accounts': accounts.count(),
                'total_balance':  round(total_balance, 2),
                'total_trades':   total_trades,
                'total_wins':     total_wins,
                'win_rate':       win_rate,
                'total_pips':     round(total_pips, 1),
                'total_profit':   round(total_profit, 2),
                'profit_factor':  pf,
                'today_pnl':      round(today_pnl, 2),
                'today_pips':     round(today_pips, 1),
                'today_trades':   today_trades.count(),
            }
        })