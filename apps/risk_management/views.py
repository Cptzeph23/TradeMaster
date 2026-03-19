# ============================================================
# Risk management REST API endpoints
# ============================================================
import logging
from datetime import datetime, timezone
from rest_framework import status, permissions, generics
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import RiskRule, DrawdownEvent
from .calculator import RiskCalculator
from .serializers import (
    RiskRuleSerializer, RiskRuleUpdateSerializer,
    DrawdownEventSerializer, LotSizeCalculatorSerializer,
)
from apps.trading.models import TradingBot, Trade
from utils.constants import TradeStatus, BotStatus

logger = logging.getLogger('risk_management')


def ok(data, code=status.HTTP_200_OK):
    return Response({'success': True, **data}, status=code)

def err(msg, code=status.HTTP_400_BAD_REQUEST, errors=None):
    r = {'success': False, 'message': msg}
    if errors: r['errors'] = errors
    return Response(r, status=code)


# ── Risk Rules CRUD ───────────────────────────────────────────
class RiskRuleView(APIView):
    """
    GET   /api/v1/risk/bots/<bot_id>/rules/   → get risk rules
    PUT   /api/v1/risk/bots/<bot_id>/rules/   → replace all rules
    PATCH /api/v1/risk/bots/<bot_id>/rules/   → partial update
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_bot(self, bot_id, user):
        try:
            return TradingBot.objects.get(
                pk=bot_id, user=user, is_active=True
            )
        except TradingBot.DoesNotExist:
            return None

    def get(self, request, bot_id):
        bot = self._get_bot(bot_id, request.user)
        if not bot:
            return err('Bot not found.', code=status.HTTP_404_NOT_FOUND)

        rule, created = RiskRule.objects.get_or_create(
            bot=bot,
            defaults={
                'risk_percent':       bot.risk_settings.get('risk_percent', 1.0),
                'stop_loss_pips':     bot.risk_settings.get('stop_loss_pips', 50),
                'take_profit_pips':   bot.risk_settings.get('take_profit_pips', 100),
                'max_drawdown_percent': bot.risk_settings.get('max_drawdown_percent', 20.0),
                'max_trades_per_day': bot.risk_settings.get('max_trades_per_day', 10),
                'max_open_trades':    bot.risk_settings.get('max_open_trades', 3),
            }
        )
        return ok({'rules': RiskRuleSerializer(rule).data})

    def put(self, request, bot_id):
        return self._update(request, bot_id, partial=False)

    def patch(self, request, bot_id):
        return self._update(request, bot_id, partial=True)

    def _update(self, request, bot_id, partial):
        bot = self._get_bot(bot_id, request.user)
        if not bot:
            return err('Bot not found.', code=status.HTTP_404_NOT_FOUND)

        if bot.status == BotStatus.RUNNING:
            return err(
                'Stop the bot before changing risk rules.',
                code=status.HTTP_409_CONFLICT
            )

        rule, _ = RiskRule.objects.get_or_create(bot=bot)
        s = RiskRuleUpdateSerializer(rule, data=request.data, partial=partial)
        if not s.is_valid():
            return err('Validation failed.', errors=s.errors)

        rule = s.save()
        # Signal in risk_management/signals.py syncs to bot.risk_settings
        return ok({
            'message': 'Risk rules updated.',
            'rules':   RiskRuleSerializer(rule).data,
        })


# ── Risk Analysis Dashboard ───────────────────────────────────
class RiskAnalysisView(APIView):
    """
    GET /api/v1/risk/bots/<bot_id>/analysis/
    Returns a full risk summary for a bot including:
    - Current drawdown, daily P&L, open trades
    - All performance metrics
    - Active risk rule violations / alerts
    - Recent drawdown events
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, bot_id):
        try:
            bot = TradingBot.objects.get(
                pk=bot_id, user=request.user, is_active=True
            )
        except TradingBot.DoesNotExist:
            return err('Bot not found.', code=status.HTTP_404_NOT_FOUND)

        # ── Closed trade P&L list ─────────────────────────────
        all_pnl = list(
            Trade.objects.filter(bot=bot, status=TradeStatus.CLOSED)
            .values_list('profit_loss', flat=True)
        )
        pnl_floats = [float(p) for p in all_pnl]

        # ── Today's stats ─────────────────────────────────────
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_trades = Trade.objects.filter(
            bot=bot, opened_at__gte=today_start
        )
        today_pnl = sum(
            float(t.profit_loss or 0)
            for t in today_trades.filter(status=TradeStatus.CLOSED)
        )
        open_count = Trade.objects.filter(
            bot=bot, status=TradeStatus.OPEN
        ).count()

        # ── Metrics ───────────────────────────────────────────
        win_rate      = RiskCalculator.win_rate(pnl_floats)
        pf            = RiskCalculator.profit_factor(pnl_floats)
        expectancy    = RiskCalculator.expectancy(pnl_floats)
        current_dd    = float(bot.current_drawdown or 0)
        peak_bal      = float(bot.peak_balance or 0)
        current_bal   = float(bot.trading_account.balance or 0)

        # ── Alerts ────────────────────────────────────────────
        alerts = self._build_alerts(bot, current_dd, today_pnl,
                                     today_trades.count(), open_count)

        # ── Drawdown events ───────────────────────────────────
        dd_events = DrawdownEvent.objects.filter(
            bot=bot
        ).order_by('-timestamp')[:10]

        # ── Risk rule ─────────────────────────────────────────
        try:
            rule = bot.risk_rule
            rule_data = RiskRuleSerializer(rule).data
        except Exception:
            rule_data = {}

        return ok({
            'bot_id':          str(bot.id),
            'bot_name':        bot.name,
            'status':          bot.status,
            'current_drawdown': current_dd,
            'peak_balance':    peak_bal,
            'current_balance': current_bal,
            'daily_pnl':       round(today_pnl, 2),
            'daily_trades':    today_trades.count(),
            'open_trades':     open_count,
            'total_trades':    bot.total_trades,
            'win_rate':        win_rate,
            'profit_factor':   pf,
            'expectancy':      expectancy,
            'total_pnl':       round(sum(pnl_floats), 2),
            'rules':           rule_data,
            'drawdown_events': DrawdownEventSerializer(dd_events, many=True).data,
            'alerts':          alerts,
        })

    def _build_alerts(
        self, bot, current_dd, today_pnl, today_count, open_count
    ) -> list:
        alerts = []
        rs     = bot.risk_settings or {}

        max_dd     = float(rs.get('max_drawdown_percent', 20))
        pause_dd   = float(rs.get('drawdown_pause_percent', 10))
        max_daily  = float(rs.get('max_daily_loss', 5))
        max_trades = int(rs.get('max_trades_per_day', 10))
        max_open   = int(rs.get('max_open_trades', 3))

        if current_dd >= max_dd * 0.9:
            alerts.append({
                'level':   'critical',
                'rule':    'max_drawdown',
                'message': f"Drawdown {current_dd:.1f}% approaching max {max_dd}%",
            })
        elif current_dd >= pause_dd * 0.8:
            alerts.append({
                'level':   'warning',
                'rule':    'drawdown_pause',
                'message': f"Drawdown {current_dd:.1f}% approaching pause threshold {pause_dd}%",
            })

        if max_daily > 0 and today_pnl < 0:
            daily_loss_pct = abs(today_pnl) / max(
                float(bot.trading_account.balance or 10000), 1
            ) * 100
            if daily_loss_pct >= max_daily * 0.8:
                alerts.append({
                    'level':   'warning',
                    'rule':    'daily_loss',
                    'message': f"Daily loss {daily_loss_pct:.1f}% approaching limit {max_daily}%",
                })

        if today_count >= max_trades * 0.8:
            alerts.append({
                'level':   'info',
                'rule':    'max_trades_per_day',
                'message': f"Trade count {today_count}/{max_trades} today",
            })

        if open_count >= max_open:
            alerts.append({
                'level':   'info',
                'rule':    'max_open_trades',
                'message': f"Max open trades reached ({open_count}/{max_open})",
            })

        return alerts


# ── Lot Size Calculator ───────────────────────────────────────
class LotSizeCalculatorView(APIView):
    """
    POST /api/v1/risk/calculate/lot-size/
    Body: {account_balance, risk_percent, stop_loss_pips, symbol}
    Returns: {lot_size, risk_amount, units}
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = LotSizeCalculatorSerializer(data=request.data)
        if not s.is_valid():
            return err('Invalid input.', errors=s.errors)
        result = s.calculate()
        return ok({'result': result})


# ── Drawdown Event History ────────────────────────────────────
class DrawdownEventListView(generics.ListAPIView):
    """
    GET /api/v1/risk/bots/<bot_id>/drawdown-events/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = DrawdownEventSerializer

    def get_queryset(self):
        return DrawdownEvent.objects.filter(
            bot__user=self.request.user,
            bot_id=self.kwargs['bot_id'],
        ).order_by('-timestamp')

    def list(self, request, *args, **kwargs):
        qs   = self.get_queryset()
        data = DrawdownEventSerializer(qs, many=True).data
        return ok({'events': data, 'count': len(data)})


# ── Performance Metrics ───────────────────────────────────────
class PerformanceMetricsView(APIView):
    """
    GET /api/v1/risk/bots/<bot_id>/performance/
    Full performance breakdown for a bot.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, bot_id):
        try:
            bot = TradingBot.objects.get(
                pk=bot_id, user=request.user, is_active=True
            )
        except TradingBot.DoesNotExist:
            return err('Bot not found.', code=status.HTTP_404_NOT_FOUND)

        trades = Trade.objects.filter(bot=bot, status=TradeStatus.CLOSED)
        pnl    = [float(t.profit_loss or 0) for t in trades]
        equity_curve = self._build_equity_curve(bot, trades)

        if not pnl:
            return ok({
                'bot_id':   str(bot.id),
                'message':  'No closed trades yet.',
                'metrics':  {},
            })

        initial_bal = float(bot.trading_account.balance or 10000)
        final_bal   = initial_bal + sum(pnl)

        metrics = {
            'total_trades':          len(pnl),
            'winning_trades':        sum(1 for p in pnl if p > 0),
            'losing_trades':         sum(1 for p in pnl if p < 0),
            'win_rate':              RiskCalculator.win_rate(pnl),
            'profit_factor':         RiskCalculator.profit_factor(pnl),
            'expectancy':            RiskCalculator.expectancy(pnl),
            'total_pnl':             round(sum(pnl), 2),
            'avg_win':               round(
                sum(p for p in pnl if p > 0) / max(sum(1 for p in pnl if p > 0), 1), 2
            ),
            'avg_loss':              round(
                sum(p for p in pnl if p < 0) / max(sum(1 for p in pnl if p < 0), 1), 2
            ),
            'total_return_pct':      round((final_bal - initial_bal) / initial_bal * 100, 4),
            'max_drawdown_pct':      RiskCalculator.max_drawdown(equity_curve),
            'sharpe_ratio':          RiskCalculator.sharpe_ratio(
                [p / initial_bal for p in pnl]
            ),
            'sortino_ratio':         RiskCalculator.sortino_ratio(
                [p / initial_bal for p in pnl]
            ),
        }

        return ok({
            'bot_id':       str(bot.id),
            'bot_name':     bot.name,
            'metrics':      metrics,
            'equity_curve': equity_curve[-100:],   # last 100 points
        })

    def _build_equity_curve(self, bot, trades) -> list:
        balance = float(bot.trading_account.balance or 10000)
        # Reverse to oldest first
        sorted_trades = sorted(trades, key=lambda t: t.closed_at or t.created_at)
        running = balance - sum(float(t.profit_loss or 0) for t in sorted_trades)
        curve   = [round(running, 2)]
        for t in sorted_trades:
            running += float(t.profit_loss or 0)
            curve.append(round(running, 2))
        return curve