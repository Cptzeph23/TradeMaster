# ============================================================
# Utility functions to push events to WebSocket clients
# Called from trading engine, signals, and Celery tasks
# ============================================================
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger('trading')


def _send(group: str, message_type: str, data: dict):
    """
    Fire-and-forget helper to send a message to a channel group.
    Converts sync → async safely.
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.debug("Channel layer not available — skip broadcast")
            return
        async_to_sync(channel_layer.group_send)(
            group,
            {'type': message_type, 'data': data},
        )
    except Exception as e:
        # Never let a broadcast failure crash the trading engine
        logger.warning(f"Broadcast failed [{group}/{message_type}]: {e}")


# ── Bot-specific broadcasts ───────────────────────────────────
def broadcast_bot_status(bot_id: str, status_data: dict):
    """Push bot status update to all clients watching this bot."""
    _send(f"bot_{bot_id}", 'bot_status', status_data)


def broadcast_signal(bot_id: str, signal_data: dict):
    """Push a strategy signal to bot watchers."""
    _send(f"bot_{bot_id}", 'signal', signal_data)


def broadcast_trade_opened(bot_id: str, trade_data: dict):
    """Notify watchers that a new trade was opened."""
    _send(f"bot_{bot_id}", 'trade_opened', trade_data)
    # Also push to user's dashboard
    if 'user_id' in trade_data:
        _send(f"dashboard_{trade_data['user_id']}", 'trade_alert', {
            **trade_data, 'event': 'trade_opened'
        })


def broadcast_trade_closed(bot_id: str, trade_data: dict):
    """Notify watchers that a trade was closed."""
    _send(f"bot_{bot_id}", 'trade_closed', trade_data)
    if 'user_id' in trade_data:
        _send(f"dashboard_{trade_data['user_id']}", 'trade_alert', {
            **trade_data, 'event': 'trade_closed'
        })


def broadcast_bot_log(bot_id: str, log_data: dict):
    """Stream a bot log entry to watchers."""
    _send(f"bot_{bot_id}", 'bot_log', log_data)


def broadcast_nlp_result(bot_id: str, user_id: str, result_data: dict):
    """Push NLP command execution result to both bot and dashboard."""
    if bot_id:
        _send(f"bot_{bot_id}", 'nlp_result', result_data)
    _send(f"dashboard_{user_id}", 'nlp_result', result_data)


# ── Price broadcasts ──────────────────────────────────────────
def broadcast_price_tick(symbol: str, price_data: dict):
    """
    Push a live price tick to all clients subscribed to this symbol.
    Called every time a new tick arrives from the broker feed.
    """
    _send(f"prices_{symbol}", 'price_tick', price_data)


# ── Dashboard broadcasts ──────────────────────────────────────
def broadcast_dashboard_update(user_id: str, data: dict):
    """Push a dashboard refresh to a specific user."""
    _send(f"dashboard_{user_id}", 'dashboard_update', data)


def broadcast_notification(user_id: str, level: str,
                            message: str, bot_name: str = ''):
    """Push a toast notification to a user's dashboard."""
    _send(f"dashboard_{user_id}", 'notification', {
        'level':    level,    # 'info' | 'success' | 'warning' | 'error'
        'message':  message,
        'bot_name': bot_name,
    })


# ── Convenience function used by trading signals ──────────────
def notify_trade_event(trade, event_type: str):
    """
    Build and broadcast a trade event from a Trade model instance.
    Called from apps/trading/signals.py post_save handler.
    """
    try:
        user_id = str(trade.bot.user_id)
        bot_id  = str(trade.bot_id)

        trade_data = {
            'trade_id':    str(trade.id),
            'bot_id':      bot_id,
            'user_id':     user_id,
            'symbol':      trade.symbol,
            'order_type':  trade.order_type,
            'lot_size':    float(trade.lot_size or 0),
            'entry_price': float(trade.entry_price or 0),
            'exit_price':  float(trade.exit_price or 0) if trade.exit_price else None,
            'pnl':         float(trade.profit_loss or 0),
            'status':      trade.status,
        }

        if event_type == 'opened':
            broadcast_trade_opened(bot_id, trade_data)
            broadcast_notification(
                user_id, 'info',
                f"Trade opened: {trade.order_type.upper()} "
                f"{trade.symbol} @ {trade.entry_price}",
                bot_name=trade.bot.name,
            )
        elif event_type == 'closed':
            broadcast_trade_closed(bot_id, trade_data)
            pnl     = float(trade.profit_loss or 0)
            level   = 'success' if pnl >= 0 else 'warning'
            sign    = '+' if pnl >= 0 else ''
            broadcast_notification(
                user_id, level,
                f"Trade closed: {trade.symbol} P&L={sign}{pnl:.2f}",
                bot_name=trade.bot.name,
            )

    except Exception as e:
        logger.warning(f"notify_trade_event failed: {e}")