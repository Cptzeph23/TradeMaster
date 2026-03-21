# ============================================================
# Mobile-optimised API — lightweight condensed payloads
# All endpoints return only what a mobile screen needs
# ============================================================
import logging
from datetime import datetime, timezone, timedelta
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.trading.models import TradingBot, Trade, BotLog
from utils.constants import TradeStatus, BotStatus

logger = logging.getLogger('trading')


def ok(data, code=status.HTTP_200_OK):
    return Response({'success': True, **data}, status=code)

def err(msg, code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': msg}, status=code)


class MobileDashboardView(APIView):
    """
    GET /api/v1/mobile/dashboard/
    Single endpoint that returns everything the mobile home screen needs.
    Designed for one-shot loading — no waterfall requests.

    Returns:
      - Account summary (balance, equity, total P&L)
      - All bots (condensed — id, name, status, pnl, win_rate)
      - Open trades (condensed)
      - Today's stats (trades, wins, pnl)
      - Recent 5 alerts/logs
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # ── Bots ────────────────────────────────────────────
        bots = TradingBot.objects.filter(
            user=user, is_active=True
        ).select_related('trading_account', 'strategy')

        bots_data = [{
            'id':        str(b.id),
            'name':      b.name,
            'status':    b.status,
            'strategy':  b.strategy.name if b.strategy else '—',
            'symbols':   b.symbols[:2] if b.symbols else [],  # max 2 for mobile
            'timeframe': b.timeframe,
            'pnl':       round(float(b.total_profit_loss or 0), 2),
            'win_rate':  round(b.win_rate or 0, 1),
            'drawdown':  round(float(b.current_drawdown or 0), 2),
            'trades':    b.total_trades or 0,
        } for b in bots]

        running = sum(1 for b in bots_data if b['status'] == BotStatus.RUNNING)

        # ── Open trades ──────────────────────────────────────
        open_trades = Trade.objects.filter(
            bot__user=user, status=TradeStatus.OPEN
        ).select_related('bot').order_by('-opened_at')[:10]

        open_data = [{
            'id':         str(t.id),
            'bot':        t.bot.name,
            'symbol':     t.symbol,
            'type':       t.order_type,
            'entry':      round(float(t.entry_price or 0), 5),
            'pnl':        round(float(t.profit_loss or 0), 2),
            'opened_ago': _time_ago(t.opened_at),
        } for t in open_trades]

        # ── Today's stats ─────────────────────────────────────
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_trades = Trade.objects.filter(
            bot__user=user,
            status=TradeStatus.CLOSED,
            closed_at__gte=today,
        )
        pnl_list   = [float(t.profit_loss or 0) for t in today_trades]
        today_pnl  = round(sum(pnl_list), 2)
        today_wins = sum(1 for p in pnl_list if p > 0)
        today_wr   = round(today_wins / len(pnl_list) * 100, 1) if pnl_list else 0

        # ── Account balance ───────────────────────────────────
        total_balance = 0.0
        for bot in bots:
            try:
                total_balance += float(bot.trading_account.balance or 0)
            except Exception:
                pass

        # ── Recent logs ───────────────────────────────────────
        recent_logs = BotLog.objects.filter(
            bot__user=user
        ).order_by('-timestamp')[:5]

        logs_data = [{
            'bot':     log.bot.name,
            'level':   log.level,
            'message': log.message[:80],
            'time':    _time_ago(log.timestamp),
        } for log in recent_logs]

        return ok({
            'summary': {
                'balance':      round(total_balance, 2),
                'total_pnl':    round(sum(b['pnl'] for b in bots_data), 2),
                'running_bots': running,
                'total_bots':   len(bots_data),
                'open_trades':  len(open_data),
            },
            'today': {
                'trades':   len(pnl_list),
                'wins':     today_wins,
                'win_rate': today_wr,
                'pnl':      today_pnl,
            },
            'bots':        bots_data,
            'open_trades': open_data,
            'recent_logs': logs_data,
        })


class MobileBotsView(APIView):
    """
    GET  /api/v1/mobile/bots/           — condensed bot list
    POST /api/v1/mobile/bots/<id>/start — start a bot
    POST /api/v1/mobile/bots/<id>/stop  — stop a bot
    POST /api/v1/mobile/bots/<id>/pause — pause a bot
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        bots = TradingBot.objects.filter(
            user=request.user, is_active=True
        ).select_related('strategy')

        return ok({'bots': [{
            'id':       str(b.id),
            'name':     b.name,
            'status':   b.status,
            'strategy': b.strategy.name if b.strategy else '—',
            'symbols':  b.symbols or [],
            'pnl':      round(float(b.total_profit_loss or 0), 2),
            'win_rate': round(b.win_rate or 0, 1),
            'trades':   b.total_trades or 0,
        } for b in bots]})


class MobileBotControlView(APIView):
    """POST /api/v1/mobile/bots/<bot_id>/<action>/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, bot_id, action):
        try:
            bot = TradingBot.objects.get(
                pk=bot_id, user=request.user, is_active=True
            )
        except TradingBot.DoesNotExist:
            return err('Bot not found.', code=status.HTTP_404_NOT_FOUND)

        if action == 'start':
            if bot.status == BotStatus.RUNNING:
                return err('Bot is already running.')
            if not bot.trading_account.is_verified:
                return err('Trading account not verified.')
            from workers.tasks import run_trading_bot
            from django.utils import timezone as dj_tz
            task           = run_trading_bot.apply_async(args=[str(bot.id)], queue='trading')
            bot.celery_task_id = task.id
            bot.status         = BotStatus.RUNNING
            bot.started_at     = dj_tz.now()
            bot.save(update_fields=['celery_task_id', 'status', 'started_at'])
            return ok({'message': f'{bot.name} started.', 'status': bot.status})

        elif action == 'stop':
            if bot.celery_task_id:
                from config.celery import app as celery_app
                try:
                    celery_app.control.revoke(bot.celery_task_id, terminate=True)
                except Exception:
                    pass
            from django.utils import timezone as dj_tz
            bot.status     = BotStatus.STOPPED
            bot.stopped_at = dj_tz.now()
            bot.save(update_fields=['status', 'stopped_at'])
            return ok({'message': f'{bot.name} stopped.', 'status': bot.status})

        elif action == 'pause':
            bot.status = BotStatus.PAUSED
            bot.save(update_fields=['status'])
            return ok({'message': f'{bot.name} paused.', 'status': bot.status})

        elif action == 'resume':
            bot.status = BotStatus.RUNNING
            bot.save(update_fields=['status'])
            return ok({'message': f'{bot.name} resumed.', 'status': bot.status})

        return err(f'Unknown action: {action}')


class MobileTradesView(APIView):
    """
    GET /api/v1/mobile/trades/
    ?status=open|closed  ?bot_id=<uuid>  ?limit=20
    Condensed trade list for mobile trade history screen.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        trade_status = request.query_params.get('status', 'open')
        bot_id       = request.query_params.get('bot_id')
        limit        = min(int(request.query_params.get('limit', 20)), 100)

        qs = Trade.objects.filter(
            bot__user=request.user
        ).select_related('bot').order_by('-opened_at')

        if trade_status in ('open', 'closed'):
            qs = qs.filter(status=trade_status)
        if bot_id:
            qs = qs.filter(bot_id=bot_id)

        trades = qs[:limit]
        return ok({
            'trades': [{
                'id':        str(t.id),
                'bot':       t.bot.name,
                'symbol':    t.symbol,
                'type':      t.order_type,
                'entry':     round(float(t.entry_price or 0), 5),
                'exit':      round(float(t.exit_price or 0), 5) if t.exit_price else None,
                'sl':        round(float(t.stop_loss or 0), 5) if t.stop_loss else None,
                'tp':        round(float(t.take_profit or 0), 5) if t.take_profit else None,
                'pnl':       round(float(t.profit_loss or 0), 2),
                'lots':      float(t.lot_size or 0),
                'status':    t.status,
                'opened':    t.opened_at.isoformat() if t.opened_at else None,
                'closed':    t.closed_at.isoformat() if t.closed_at else None,
                'opened_ago':_time_ago(t.opened_at),
            } for t in trades],
            'count': len(trades),
        })


class MobileStatsView(APIView):
    """
    GET /api/v1/mobile/stats/
    ?period=today|week|month|all
    Performance summary for mobile analytics screen.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        period = request.query_params.get('period', 'today')
        now    = datetime.now(timezone.utc)

        periods = {
            'today': now.replace(hour=0, minute=0, second=0, microsecond=0),
            'week':  now - timedelta(days=7),
            'month': now - timedelta(days=30),
            'all':   None,
        }
        since = periods.get(period)

        qs = Trade.objects.filter(
            bot__user=request.user, status=TradeStatus.CLOSED
        )
        if since:
            qs = qs.filter(closed_at__gte=since)

        pnl_list = [float(t.profit_loss or 0) for t in qs]
        wins     = sum(1 for p in pnl_list if p > 0)
        losses   = sum(1 for p in pnl_list if p < 0)
        total    = len(pnl_list)
        gross_w  = sum(p for p in pnl_list if p > 0)
        gross_l  = abs(sum(p for p in pnl_list if p < 0))

        return ok({
            'period': period,
            'stats': {
                'total_trades':  total,
                'wins':          wins,
                'losses':        losses,
                'win_rate':      round(wins / total * 100, 1) if total else 0,
                'total_pnl':     round(sum(pnl_list), 2),
                'gross_profit':  round(gross_w, 2),
                'gross_loss':    round(gross_l, 2),
                'profit_factor': round(gross_w / gross_l, 2) if gross_l else 0,
                'avg_win':       round(gross_w / wins, 2)   if wins else 0,
                'avg_loss':      round(gross_l / losses, 2) if losses else 0,
                'expectancy':    round(
                    (wins/total * gross_w/max(wins,1)) -
                    (losses/total * gross_l/max(losses,1)), 2
                ) if total else 0,
            },
        })


class MobileNLPView(APIView):
    """
    POST /api/v1/mobile/command/
    Body: {"command": "set stop loss to 30 pips", "bot_id": "optional-uuid"}
    Same as the main NLP endpoint but returns a simpler mobile-friendly response.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        command = request.data.get('command', '').strip()
        bot_id  = request.data.get('bot_id')

        if not command:
            return err('Command cannot be empty.')
        if len(command) > 500:
            return err('Command too long (max 500 characters).')

        from workers.tasks import process_nlp_command
        from django.utils import timezone as dj_tz

        task = process_nlp_command.apply_async(
            args=[str(request.user.id), command, bot_id],
            queue='commands',
        )

        return ok({
            'message': 'Command received.',
            'task_id': task.id,
            'command': command,
        }, code=status.HTTP_202_ACCEPTED)


class MobilePriceView(APIView):
    """
    GET /api/v1/mobile/prices/
    ?symbols=EUR_USD,GBP_USD,USD_JPY
    Quick price check — last known price for requested symbols.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        symbols_param = request.query_params.get('symbols', 'EUR_USD,GBP_USD,USD_JPY,AUD_USD')
        symbols       = [s.strip().upper() for s in symbols_param.split(',')][:8]  # max 8

        from apps.market_data.models import LiveTick

        prices = {}
        for symbol in symbols:
            tick = LiveTick.objects.filter(
                symbol=symbol
            ).order_by('-timestamp').first()

            if tick:
                prices[symbol] = {
                    'bid':       float(tick.bid),
                    'ask':       float(tick.ask),
                    'mid':       round((float(tick.bid) + float(tick.ask)) / 2, 5),
                    'spread':    float(tick.spread),
                    'updated':   _time_ago(tick.timestamp),
                }
            else:
                prices[symbol] = None

        return ok({'prices': prices})


# ── Utility ───────────────────────────────────────────────────
def _time_ago(dt) -> str:
    """Human-readable relative time — '2m ago', '1h ago', 'just now'."""
    if not dt:
        return '—'
    try:
        now   = datetime.now(timezone.utc)
        delta = now - dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else now - dt
        secs  = int(delta.total_seconds())
        if secs < 60:
            return 'just now'
        elif secs < 3600:
            return f"{secs // 60}m ago"
        elif secs < 86400:
            return f"{secs // 3600}h ago"
        else:
            return f"{secs // 86400}d ago"
    except Exception:
        return '—'