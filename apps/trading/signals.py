# ============================================================
# UPDATED — adds realtime broadcast on every trade save
# ============================================================
from django.db.models.signals import post_save
from django.dispatch import receiver
from utils.constants import TradeStatus


@receiver(post_save, sender='trading.Trade')
def update_bot_drawdown(sender, instance, **kwargs):
    """Recalculate the bot's current drawdown after every trade save."""
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
def broadcast_trade_update(sender, instance, created, **kwargs):
    """
    Broadcast trade events to WebSocket clients in real time.
    - New trade (created=True, status=OPEN)  → trade_opened event
    - Closed trade (status=CLOSED)           → trade_closed event
    """
    try:
        from services.realtime.broadcaster import notify_trade_event

        if created and instance.status == TradeStatus.OPEN:
            notify_trade_event(instance, 'opened')

        elif not created and instance.status == TradeStatus.CLOSED:
            notify_trade_event(instance, 'closed')

    except Exception as e:
        import logging
        logging.getLogger('trading').warning(
            f"broadcast_trade_update failed: {e}"
        )


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
def broadcast_bot_status_change(sender, instance, **kwargs):
    """Broadcast bot status changes immediately."""
    try:
        from services.realtime.broadcaster import broadcast_bot_status
        broadcast_bot_status(str(instance.id), {
            'id':        str(instance.id),
            'name':      instance.name,
            'status':    instance.status,
            'pnl':       float(instance.total_profit_loss or 0),
            'win_rate':  instance.win_rate,
            'drawdown':  float(instance.current_drawdown or 0),
        })
    except Exception:
        pass