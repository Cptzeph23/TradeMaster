# ============================================================
# UPDATED — adds Telegram alerts to every trade/bot event
# Replaces the Phase K version
# ============================================================
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from utils.constants import TradeStatus, BotStatus

logger = logging.getLogger('trading')


@receiver(post_save, sender='trading.Trade')
def update_bot_drawdown(sender, instance, **kwargs):
    """Recalculate bot drawdown after every trade save."""
    if not instance.bot_id:
        return
    try:
        bot = instance.bot
        if float(bot.peak_balance or 0) > 0:
            current = float(bot.trading_account.balance or 0)
            peak    = float(bot.peak_balance)
            dd      = round((peak - current) / peak * 100, 2)
            bot.__class__.objects.filter(pk=bot.pk).update(
                current_drawdown=max(0, dd)
            )
    except Exception:
        pass


@receiver(post_save, sender='trading.Trade')
def broadcast_and_alert_trade(sender, instance, created, **kwargs):
    """
    On trade open/close:
      1. Broadcast to WebSocket (dashboard live update)
      2. Send Telegram alert
    """
    try:
        from services.realtime.broadcaster import notify_trade_event
        from services.telegram.alerts import alert_trade_opened, alert_trade_closed

        if created and instance.status == TradeStatus.OPEN:
            notify_trade_event(instance, 'opened')
            alert_trade_opened(instance)

        elif not created and instance.status == TradeStatus.CLOSED:
            notify_trade_event(instance, 'closed')
            alert_trade_closed(instance)

    except Exception as e:
        logger.warning(f"broadcast_and_alert_trade failed: {e}")


@receiver(post_save, sender='trading.BotLog')
def broadcast_bot_log(sender, instance, created, **kwargs):
    """Stream new bot log entries to WebSocket clients."""
    if not created:
        return
    try:
        from services.realtime.broadcaster import broadcast_bot_log
        broadcast_bot_log(str(instance.bot_id), {
            'id':         instance.id,
            'level':      instance.level,
            'event_type': instance.event_type,
            'message':    instance.message,
            'timestamp':  instance.timestamp.isoformat(),
        })
    except Exception:
        pass


@receiver(post_save, sender='trading.TradingBot')
def broadcast_and_alert_bot_status(sender, instance, created, **kwargs):
    """
    On bot status change:
      1. Broadcast to WebSocket
      2. Send Telegram status alert (only on significant changes)
    """
    try:
        from services.realtime.broadcaster import broadcast_bot_status
        broadcast_bot_status(str(instance.id), {
            'id':       str(instance.id),
            'name':     instance.name,
            'status':   instance.status,
            'pnl':      float(instance.total_profit_loss or 0),
            'win_rate': instance.win_rate,
            'drawdown': float(instance.current_drawdown or 0),
        })
    except Exception:
        pass

    # Telegram alerts for significant status changes
    try:
        from services.telegram import alerts as tg

        if instance.status == BotStatus.RUNNING and not created:
            tg.alert_bot_started(
                bot_name = instance.name,
                symbols  = instance.symbols or [],
                timeframe= instance.timeframe,
                strategy = instance.strategy.name if instance.strategy_id else '—',
            )
        elif instance.status == BotStatus.STOPPED and not created:
            tg.alert_bot_stopped(instance.name)
        elif instance.status == BotStatus.ERROR and not created:
            tg.alert_bot_error(instance.name, instance.error_message or 'Unknown error')

    except Exception as e:
        logger.debug(f"Telegram bot status alert skipped: {e}")