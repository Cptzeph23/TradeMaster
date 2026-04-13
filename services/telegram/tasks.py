# ============================================================
# UPDATED — all tasks now pull pip/RRR/account data from Trade
# Full replacement of Phase O tasks.py
# ============================================================
import logging
from celery import shared_task

logger = logging.getLogger('telegram_bot')


# ── Helper: build full trade data dict from Trade model ───────

def _trade_to_data(trade) -> dict:
    """
    Extract all fields the new message formatters need.
    Works even if Phase 3b fields are None (backwards-compatible).
    """
    bot  = trade.bot
    acct = bot.trading_account

    return {
        # Core trade fields
        'symbol':       trade.symbol,
        'order_type':   trade.order_type,
        'entry_price':  float(trade.entry_price or 0),
        'exit_price':   float(trade.exit_price  or 0) if trade.exit_price else None,
        'stop_loss':    float(trade.stop_loss   or 0) if trade.stop_loss  else None,
        'take_profit':  float(trade.take_profit or 0) if trade.take_profit else None,
        'lot_size':     float(trade.lot_size    or 0),
        'profit_loss':  float(trade.profit_loss or 0),
        'exit_reason':  getattr(trade, 'exit_reason', ''),

        # Phase 3b pip/RRR fields
        'sl_pips':       getattr(trade, 'sl_pips',      None),
        'tp_pips':       getattr(trade, 'tp_pips',      None),
        'profit_pips':   getattr(trade, 'profit_pips',  None),
        'rrr_used':      getattr(trade, 'rrr_used',     None),
        'rrr_achieved':  getattr(trade, 'rrr_achieved', None),
        'account_label': getattr(trade, 'account_label', '') or acct.name,

        # Phase 3a account type fields
        'account_type':  getattr(acct, 'account_type', ''),
        'funded_firm':   getattr(acct, 'funded_firm',  ''),

        # Bot metadata
        'bot_name': bot.name,

        # Risk info (from bot risk_settings if available)
        'risk_percent': float(
            (getattr(bot, 'risk_settings', {}) or {}).get('risk_percent', 1.0)
        ),
        'risk_amount': _estimate_risk_amount(trade, acct),
    }


def _estimate_risk_amount(trade, acct) -> float:
    """
    Estimate risk amount in USD from trade fields.
    Uses sl_pips × lot_size × pip_value if available,
    otherwise falls back to risk_percent × balance.
    """
    try:
        sl_pips = getattr(trade, 'sl_pips', None)
        if sl_pips and trade.lot_size:
            from utils.pip_calculator import get_pip_value
            pip_val = get_pip_value(trade.symbol, float(trade.lot_size))
            return round(float(sl_pips) * pip_val, 2)
    except Exception:
        pass
    try:
        risk_pct = float(
            (getattr(trade.bot, 'risk_settings', {}) or {}).get('risk_percent', 1.0)
        )
        balance = float(acct.balance or 10000)
        return round(balance * risk_pct / 100, 2)
    except Exception:
        return 0.0


# ── Alert tasks ───────────────────────────────────────────────

@shared_task(name='telegram.send_trade_opened_alert', ignore_result=True)
def send_trade_opened_alert(trade_id: str):
    """
    Send Telegram alert when a trade opens.
    Message includes: symbol, direction, entry, SL/TP in pips,
    RRR, account name, funded firm, risk amount.
    """
    try:
        from apps.trading.models import Trade
        from services.telegram.bot import get_bot
        from services.telegram import messages

        trade = Trade.objects.select_related(
            'bot', 'bot__trading_account'
        ).get(pk=trade_id)

        data = _trade_to_data(trade)
        text = messages.trade_opened(data)
        get_bot().send_to_user(trade.bot.user, text)

    except Exception as e:
        logger.error(f"send_trade_opened_alert failed: {e}", exc_info=True)


@shared_task(name='telegram.send_trade_closed_alert', ignore_result=True)
def send_trade_closed_alert(trade_id: str):
    """
    Send Telegram alert when a trade closes.
    Message includes: pips gained/lost, RRR achieved vs planned,
    TP HIT / SL HIT label, account name.
    """
    try:
        from apps.trading.models import Trade
        from services.telegram.bot import get_bot
        from services.telegram import messages

        trade = Trade.objects.select_related(
            'bot', 'bot__trading_account'
        ).get(pk=trade_id)

        data = _trade_to_data(trade)
        text = messages.trade_closed(data)
        get_bot().send_to_user(trade.bot.user, text)

    except Exception as e:
        logger.error(f"send_trade_closed_alert failed: {e}", exc_info=True)


@shared_task(name='telegram.send_bot_status_alert', ignore_result=True)
def send_bot_status_alert(bot_id: str, status: str, reason: str = ''):
    """Send bot started/stopped/paused alerts with account info."""
    try:
        from apps.trading.models import TradingBot
        from services.telegram.bot import get_bot
        from services.telegram import messages

        bot     = TradingBot.objects.select_related('trading_account').get(pk=bot_id)
        tg_bot  = get_bot()
        user    = bot.user
        acct    = bot.trading_account
        label   = getattr(acct, 'name', '')
        acct_t  = getattr(acct, 'account_type', '')

        if status == 'running':
            text = messages.bot_started(
                bot.name,
                bot.symbols or [],
                bot.timeframe or 'H1',
                account_label = label,
                account_type  = acct_t,
            )
        elif status == 'stopped':
            text = messages.bot_stopped(bot.name, reason, account_label=label)
        elif status == 'paused':
            text = messages.bot_paused(bot.name, reason, account_label=label)
        else:
            return

        tg_bot.send_to_user(user, text)

    except Exception as e:
        logger.error(f"send_bot_status_alert failed: {e}", exc_info=True)


@shared_task(name='telegram.send_drawdown_alert', ignore_result=True)
def send_drawdown_alert(
    bot_id:    str,
    drawdown:  float,
    threshold: float,
):
    """Send drawdown warning with funded firm name if applicable."""
    try:
        from apps.trading.models import TradingBot
        from services.telegram.bot import get_bot
        from services.telegram import messages

        bot    = TradingBot.objects.select_related('trading_account').get(pk=bot_id)
        acct   = bot.trading_account
        text   = messages.drawdown_warning(
            bot_name     = bot.name,
            drawdown     = drawdown,
            threshold    = threshold,
            account_label= getattr(acct, 'name', ''),
            funded_firm  = getattr(acct, 'funded_firm', ''),
        )
        get_bot().send_to_user(bot.user, text)

    except Exception as e:
        logger.error(f"send_drawdown_alert failed: {e}", exc_info=True)


@shared_task(name='telegram.send_daily_report_alert', ignore_result=True)
def send_daily_report_alert(user_id: str):
    """
    Send the daily P&L report to a user.
    Now includes: total pips, avg RRR, best symbol.
    """
    try:
        from apps.accounts.models import User, TradingAccount
        from apps.trading.models import TradingBot, Trade
        from services.telegram.bot import get_bot
        from services.telegram import messages
        from utils.constants import TradeStatus, BotStatus
        from django.db.models import Sum, Avg
        from datetime import datetime, timezone

        user        = User.objects.get(pk=user_id)
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        today_trades = Trade.objects.filter(
            bot__user    = user,
            status       = TradeStatus.CLOSED,
            closed_at__gte = today_start,
        )

        pnl_list  = [float(t.profit_loss  or 0) for t in today_trades]
        pip_list  = [float(t.profit_pips  or 0) for t in today_trades
                     if t.profit_pips is not None]
        rrr_list  = [float(t.rrr_used or 0) for t in today_trades
                     if t.rrr_used]

        total_pnl   = round(sum(pnl_list), 2)
        total_pips  = round(sum(pip_list), 1)
        wins        = sum(1 for p in pnl_list if p > 0)
        wr          = round(wins / len(pnl_list) * 100, 1) if pnl_list else 0
        avg_rrr     = round(sum(rrr_list) / len(rrr_list), 1) if rrr_list else 0.0

        running = TradingBot.objects.filter(
            user=user, status=BotStatus.RUNNING, is_active=True
        ).count()

        open_trades = Trade.objects.filter(
            bot__user=user, status=TradeStatus.OPEN
        ).count()

        # Best bot today
        best_bot = ''
        from collections import defaultdict
        bot_pnl = defaultdict(float)
        for t in today_trades:
            bot_pnl[t.bot.name] += float(t.profit_loss or 0)
        if bot_pnl:
            best = max(bot_pnl.items(), key=lambda x: x[1])
            best_bot = f"{best[0]} ({best[1]:+.2f})"

        # Best symbol today
        sym_pips = defaultdict(float)
        for t in today_trades:
            if t.profit_pips is not None:
                sym_pips[t.symbol] += float(t.profit_pips)
        best_symbol = max(sym_pips, key=sym_pips.get) if sym_pips else ''

        text = messages.daily_report(
            date_str     = today_start.strftime('%Y-%m-%d'),
            total_trades = len(pnl_list),
            win_rate     = wr,
            total_pnl    = total_pnl,
            running_bots = running,
            top_bot      = best_bot,
            open_trades  = open_trades,
            total_pips   = total_pips,
            best_symbol  = best_symbol,
            avg_rrr      = avg_rrr,
        )

        get_bot().send_to_user(user, text)

    except Exception as e:
        logger.error(f"send_daily_report_alert failed: {e}", exc_info=True)


# ── Command polling task (unchanged from Phase O) ─────────────

@shared_task(name='telegram.poll_commands', ignore_result=True)
def poll_commands():
    """
    Poll Telegram for new /commands every 10 seconds.
    Uses offset stored in Redis to avoid duplicate processing.
    """
    try:
        from services.telegram.bot import get_bot
        from django.core.cache import cache

        tg_bot = get_bot()
        if not tg_bot.enabled:
            return

        offset_key = 'telegram:poll_offset'
        offset     = int(cache.get(offset_key, 0))
        updates    = tg_bot.get_updates(offset=offset, timeout=5)

        for update in updates:
            update_id = update.get('update_id', 0)
            message   = update.get('message', {})
            text      = message.get('text', '').strip()
            chat_id   = str(message.get('chat', {}).get('id', ''))
            username  = message.get('from', {}).get('username', '')

            if text.startswith('/'):
                _handle_command(text, chat_id, username, tg_bot)

            cache.set(offset_key, update_id + 1, timeout=86400)

    except Exception as e:
        logger.error(f"poll_commands failed: {e}", exc_info=True)


def _handle_command(text: str, chat_id: str, username: str, tg_bot):
    """Resolve user from chat_id and dispatch the command."""
    from apps.accounts.models import UserProfile

    user = None
    try:
        profile = UserProfile.objects.filter(
            telegram_chat_id=chat_id
        ).select_related('user').first()
        if profile:
            user = profile.user
    except Exception:
        pass

    parts   = text.split()
    command = parts[0].lstrip('/')
    args    = parts[1:] if len(parts) > 1 else []

    if not user and command == 'start':
        try:
            profile = UserProfile.objects.filter(
                telegram_username=username
            ).select_related('user').first()
            if profile:
                user = profile.user
        except Exception:
            pass

    if not user:
        tg_bot.send_message(
            chat_id,
            "❌ Account not linked.\n\n"
            "Go to dashboard → Profile → Settings "
            "and enter your Telegram username."
        )
        return

    from services.telegram.commander import TelegramCommander
    response = TelegramCommander(user).handle(command, args, chat_id)
    tg_bot.send_message(chat_id, response)
    logger.info(f"Telegram /{command} handled for {user.email}")