# ============================================================
# PerformanceService — recalculates AccountPerformance after
# every trade close. Called from Django signals or Celery tasks.
# ============================================================
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger('trading.performance')


class PerformanceService:
    """
    Recalculates and persists AccountPerformance for a
    TradingAccount after every trade close.

    Usage (from Django signal or Celery task):
        svc = PerformanceService(account)
        svc.update()

    Or via the class method:
        PerformanceService.update_for_trade(trade)
    """

    def __init__(self, account):
        self.account = account

    # ── Primary API ───────────────────────────────────────────

    def update(self) -> 'AccountPerformance':
        """
        Recalculate all metrics for self.account and save.
        Returns the updated AccountPerformance record.
        """
        from apps.accounts.performance_models import AccountPerformance
        from apps.trading.models import Trade
        from utils.constants import TradeStatus

        trades = Trade.objects.filter(
            bot__trading_account = self.account,
            status               = TradeStatus.CLOSED,
        ).order_by('closed_at')

        perf, _ = AccountPerformance.objects.get_or_create(
            account=self.account
        )

        if not trades.exists():
            logger.debug(
                f"No closed trades for {self.account.name} — resetting"
            )
            self._reset(perf)
            perf.save()
            return perf

        self._compute(perf, list(trades))
        perf.save()
        logger.info(
            f"Performance updated: {self.account.name} | "
            f"trades={perf.total_trades} WR={perf.win_rate:.1f}% "
            f"pips={perf.total_pips:+.1f} PF={perf.profit_factor:.2f}"
        )
        return perf

    @classmethod
    def update_for_trade(cls, trade) -> Optional['AccountPerformance']:
        """
        Convenience — update performance for the account linked to a trade.
        Call this from Django signals after a trade is closed.
        """
        try:
            account = trade.bot.trading_account
            svc     = cls(account)
            return svc.update()
        except Exception as e:
            logger.error(
                f"PerformanceService.update_for_trade failed: {e}",
                exc_info=True
            )
            return None

    def take_daily_snapshot(self) -> Optional['AccountPerformanceHistory']:
        """
        Save today's equity/P&L snapshot to AccountPerformanceHistory.
        Called daily by Celery beat.
        """
        from apps.accounts.performance_models import AccountPerformanceHistory
        from apps.trading.models import Trade
        from utils.constants import TradeStatus

        today       = datetime.now(timezone.utc).date()
        today_start = datetime.combine(today, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )

        today_trades = Trade.objects.filter(
            bot__trading_account = self.account,
            status               = TradeStatus.CLOSED,
            closed_at__date      = today,
        )

        pnl_list  = [float(t.profit_loss or 0) for t in today_trades]
        pip_list  = [float(t.profit_pips  or 0) for t in today_trades]
        wins      = sum(1 for p in pnl_list if p > 0)
        daily_wr  = round(wins / len(pnl_list) * 100, 1) if pnl_list else 0.0

        try:
            perf = self.account.performance
        except Exception:
            perf = None

        snap, created = AccountPerformanceHistory.objects.update_or_create(
            account       = self.account,
            snapshot_date = today,
            defaults={
                'balance':       float(self.account.balance or 0),
                'equity':        float(self.account.equity  or 0),
                'daily_pnl':     round(sum(pnl_list), 2),
                'daily_pips':    round(sum(pip_list), 1),
                'daily_trades':  len(pnl_list),
                'daily_win_rate':daily_wr,
                'drawdown_pct':  perf.current_drawdown if perf else 0.0,
            }
        )
        action = 'Created' if created else 'Updated'
        logger.info(
            f"{action} daily snapshot {self.account.name} "
            f"{today}: pnl={snap.daily_pnl:+.2f} pips={snap.daily_pips:+.1f}"
        )
        return snap

    # ── Core calculation ──────────────────────────────────────

    def _compute(self, perf, trades: list):
        """Recalculate all metrics from full trade history."""
        pnl_list  = [float(t.profit_loss  or 0) for t in trades]
        pip_list  = [float(t.profit_pips  or 0) for t in trades]
        rrr_used  = [float(t.rrr_used     or 0) for t in trades if t.rrr_used]
        rrr_achvd = [float(t.rrr_achieved or 0) for t in trades if t.rrr_achieved]

        wins   = [p for p in pnl_list if p > 0]
        losses = [p for p in pnl_list if p < 0]
        evens  = [p for p in pnl_list if p == 0]

        win_pips  = [p for p in pip_list if p > 0]
        loss_pips = [abs(p) for p in pip_list if p < 0]

        gross_profit = sum(wins)
        gross_loss   = abs(sum(losses))
        total_trades = len(trades)

        # ── Counts ───────────────────────────────────────────
        perf.total_trades     = total_trades
        perf.winning_trades   = len(wins)
        perf.losing_trades    = len(losses)
        perf.breakeven_trades = len(evens)

        # ── Win rate ─────────────────────────────────────────
        perf.win_rate = round(
            len(wins) / total_trades * 100, 2
        ) if total_trades else 0.0

        # ── Monetary ─────────────────────────────────────────
        perf.total_profit = round(sum(pnl_list), 2)
        perf.gross_profit = round(gross_profit, 2)
        perf.gross_loss   = round(gross_loss, 2)
        perf.avg_win      = round(sum(wins)   / len(wins),   2) if wins   else 0.0
        perf.avg_loss     = round(sum(losses) / len(losses), 2) if losses else 0.0
        perf.largest_win  = round(max(wins),   2) if wins   else 0.0
        perf.largest_loss = round(abs(min(losses)), 2) if losses else 0.0

        # ── Profit factor ─────────────────────────────────────
        perf.profit_factor = (
            round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0.0
        )

        # ── Expectancy ────────────────────────────────────────
        wr  = len(wins)   / total_trades if total_trades else 0
        lr  = len(losses) / total_trades if total_trades else 0
        perf.expectancy = round(
            (wr * perf.avg_win) + (lr * perf.avg_loss), 2
        )

        # ── Pip metrics ───────────────────────────────────────
        perf.total_pips       = round(sum(pip_list), 1)
        perf.total_pips_won   = round(sum(win_pips),  1)
        perf.total_pips_lost  = round(sum(loss_pips), 1)
        perf.avg_win_pips     = round(sum(win_pips)  / len(win_pips),  1) if win_pips  else 0.0
        perf.avg_loss_pips    = round(sum(loss_pips) / len(loss_pips), 1) if loss_pips else 0.0
        perf.largest_win_pips = round(max(win_pips),  1) if win_pips  else 0.0
        perf.largest_loss_pips= round(max(loss_pips), 1) if loss_pips else 0.0

        # ── RRR averages ──────────────────────────────────────
        perf.avg_rrr_used     = round(
            sum(rrr_used) / len(rrr_used), 2
        ) if rrr_used else 0.0
        perf.avg_rrr_achieved = round(
            sum(rrr_achvd) / len(rrr_achvd), 2
        ) if rrr_achvd else 0.0

        # ── Drawdown ──────────────────────────────────────────
        self._compute_drawdown(perf, pnl_list)

        # ── Streak ───────────────────────────────────────────
        self._compute_streak(perf, pnl_list)

        # ── Symbol stats ──────────────────────────────────────
        self._compute_symbol_stats(perf, trades)

        # ── Timestamps ───────────────────────────────────────
        if trades:
            first = trades[0]
            last  = trades[-1]
            perf.first_trade_at = getattr(first, 'opened_at', None) or \
                                   getattr(first, 'closed_at', None)
            perf.last_trade_at  = getattr(last, 'closed_at', None)

    def _compute_drawdown(self, perf, pnl_list: list):
        """Calculate max drawdown from P&L series."""
        if not pnl_list:
            perf.max_drawdown_pct = 0.0
            perf.max_drawdown_usd = 0.0
            perf.current_drawdown = 0.0
            return

        # Starting balance from account or estimate
        start_balance = float(self.account.balance or 0) - sum(pnl_list)
        if start_balance <= 0:
            start_balance = 10000.0  # fallback

        equity    = start_balance
        peak      = start_balance
        max_dd    = 0.0
        max_dd_usd= 0.0

        for pnl in pnl_list:
            equity += pnl
            if equity > peak:
                peak = equity
            dd_usd = peak - equity
            dd_pct = (dd_usd / peak * 100) if peak > 0 else 0
            if dd_pct > max_dd:
                max_dd     = dd_pct
                max_dd_usd = dd_usd

        current_balance = float(self.account.balance or equity)
        current_dd = max(0, (peak - current_balance) / peak * 100) if peak > 0 else 0

        perf.peak_balance     = round(peak, 2)
        perf.max_drawdown_pct = round(max_dd, 2)
        perf.max_drawdown_usd = round(max_dd_usd, 2)
        perf.current_drawdown = round(current_dd, 2)

    def _compute_streak(self, perf, pnl_list: list):
        """Calculate win/loss streaks."""
        if not pnl_list:
            return

        cur_streak = 0
        max_win    = 0
        max_loss   = 0

        for pnl in pnl_list:
            if pnl > 0:
                cur_streak = max(1, cur_streak + 1)
                max_win    = max(max_win, cur_streak)
            elif pnl < 0:
                cur_streak = min(-1, cur_streak - 1)
                max_loss   = max(max_loss, abs(cur_streak))
            # breakeven resets streak
            else:
                cur_streak = 0

        perf.current_streak       = cur_streak
        perf.longest_win_streak   = max_win
        perf.longest_loss_streak  = max_loss

    def _compute_symbol_stats(self, perf, trades: list):
        """Build per-symbol breakdown dict."""
        from collections import defaultdict

        stats = defaultdict(lambda: {
            'trades': 0, 'wins': 0,
            'pnl': 0.0, 'pips': 0.0,
        })

        for t in trades:
            sym  = t.symbol
            pnl  = float(t.profit_loss  or 0)
            pips = float(t.profit_pips  or 0)
            stats[sym]['trades'] += 1
            stats[sym]['pnl']    += pnl
            stats[sym]['pips']   += pips
            if pnl > 0:
                stats[sym]['wins'] += 1

        result = {}
        for sym, s in stats.items():
            t = s['trades']
            result[sym] = {
                'trades':    t,
                'wins':      s['wins'],
                'win_rate':  round(s['wins'] / t * 100, 1) if t else 0,
                'pnl':       round(s['pnl'],  2),
                'pips':      round(s['pips'], 1),
            }
        perf.symbol_stats = result

    def _reset(self, perf):
        """Zero out all metrics."""
        fields = [
            'total_trades','winning_trades','losing_trades','breakeven_trades',
            'total_pips','total_pips_won','total_pips_lost',
            'avg_win_pips','avg_loss_pips','largest_win_pips','largest_loss_pips',
            'total_profit','gross_profit','gross_loss',
            'largest_win','largest_loss','avg_win','avg_loss',
            'win_rate','profit_factor','expectancy',
            'avg_rrr_used','avg_rrr_achieved',
            'max_drawdown_pct','max_drawdown_usd','current_drawdown','peak_balance',
            'current_streak','longest_win_streak','longest_loss_streak',
        ]
        for f in fields:
            setattr(perf, f, 0)
        perf.symbol_stats = {}
        perf.first_trade_at = None
        perf.last_trade_at  = None