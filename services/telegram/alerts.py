# ============================================================
# Alert formatters — called by signals.py and Celery tasks
# ============================================================
import logging
from typing import Optional
from .bot import get_telegram_bot

logger = logging.getLogger('telegram_bot')


def _send(text: str) -> bool:
    """Fire-and-forget Telegram send — never raises."""
    try:
        return get_telegram_bot().send(text)
    except Exception as e:
        logger.debug(f"Telegram alert skipped: {e}")
        return False


# ── Trade alerts ──────────────────────────────────────────────
def alert_trade_opened(trade) -> bool:
    """Called when a new trade is opened."""
    bot_name   = trade.bot.name if trade.bot else '?'
    order_icon = '🟢' if trade.order_type == 'buy' else '🔴'
    text = (
        f"{order_icon} <b>Trade Opened</b>\n\n"
        f"Bot:    {bot_name}\n"
        f"Pair:   <b>{trade.symbol}</b>\n"
        f"Type:   {trade.order_type.upper()}\n"
        f"Entry:  {trade.entry_price}\n"
        f"SL:     {trade.stop_loss or '—'}\n"
        f"TP:     {trade.take_profit or '—'}\n"
        f"Lots:   {trade.lot_size}\n"
    )
    return _send(text)


def alert_trade_closed(trade) -> bool:
    """Called when a trade closes."""
    pnl   = float(trade.profit_loss or 0)
    icon  = '✅' if pnl >= 0 else '❌'
    sign  = '+' if pnl >= 0 else ''
    pips  = float(trade.profit_pips or 0)
    pip_sign = '+' if pips >= 0 else ''
    bot_name = trade.bot.name if trade.bot else '?'

    duration = ''
    if trade.opened_at and trade.closed_at:
        delta = trade.closed_at - trade.opened_at
        hours = int(delta.total_seconds() // 3600)
        mins  = int((delta.total_seconds() % 3600) // 60)
        duration = f"Duration: {hours}h {mins}m\n" if hours > 0 else f"Duration: {mins}m\n"

    text = (
        f"{icon} <b>Trade Closed</b>\n\n"
        f"Bot:    {bot_name}\n"
        f"Pair:   <b>{trade.symbol}</b>\n"
        f"Type:   {trade.order_type.upper()}\n"
        f"Entry:  {trade.entry_price} → Exit: {trade.exit_price}\n"
        f"P&amp;L:    <b>{sign}{pnl:.2f} USD</b> ({pip_sign}{pips:.1f} pips)\n"
        f"{duration}"
        f"Reason: {trade.close_reason or 'signal'}\n"
    )
    return _send(text)


# ── Risk alerts ───────────────────────────────────────────────
def alert_drawdown_warning(bot_name: str, drawdown_pct: float,
                            max_pct: float) -> bool:
    """Called when drawdown approaches the limit."""
    pct_of_max = round(drawdown_pct / max_pct * 100, 1)
    icon = '🚨' if pct_of_max >= 90 else '⚠️'
    text = (
        f"{icon} <b>Drawdown Warning</b>\n\n"
        f"Bot:      {bot_name}\n"
        f"Drawdown: <b>{drawdown_pct:.2f}%</b> "
        f"({pct_of_max}% of {max_pct}% limit)\n"
    )
    return _send(text)


def alert_bot_halted(bot_name: str, drawdown_pct: float,
                      reason: str = '') -> bool:
    """Called when a bot is auto-halted by the risk engine."""
    text = (
        f"🛑 <b>Bot HALTED</b>\n\n"
        f"Bot:      <b>{bot_name}</b>\n"
        f"Drawdown: {drawdown_pct:.2f}%\n"
        f"Reason:   {reason or 'Max drawdown exceeded'}\n\n"
        f"Use /start {bot_name} to restart."
    )
    return _send(text)


def alert_daily_loss_limit(bot_name: str, loss_pct: float,
                             limit_pct: float) -> bool:
    text = (
        f"🚫 <b>Daily Loss Limit Reached</b>\n\n"
        f"Bot:   {bot_name}\n"
        f"Loss:  {loss_pct:.2f}% (limit: {limit_pct}%)\n"
        f"No more trades today."
    )
    return _send(text)


# ── Bot status alerts ─────────────────────────────────────────
def alert_bot_started(bot_name: str, symbols: list,
                       timeframe: str, strategy: str) -> bool:
    text = (
        f"🚀 <b>Bot Started</b>\n\n"
        f"Name:     {bot_name}\n"
        f"Strategy: {strategy}\n"
        f"Pairs:    {', '.join(symbols or [])}\n"
        f"TF:       {timeframe}\n"
    )
    return _send(text)


def alert_bot_stopped(bot_name: str, reason: str = 'Manual') -> bool:
    text = (
        f"⏹ <b>Bot Stopped</b>\n\n"
        f"Name:   {bot_name}\n"
        f"Reason: {reason}\n"
    )
    return _send(text)


def alert_bot_error(bot_name: str, error: str) -> bool:
    text = (
        f"❌ <b>Bot Error</b>\n\n"
        f"Bot:   {bot_name}\n"
        f"Error: {error[:200]}\n\n"
        f"Check logs for details."
    )
    return _send(text)


# ── Daily report ──────────────────────────────────────────────
def send_daily_report(date_str: str, stats: dict) -> bool:
    """
    Sends end-of-day performance summary.
    stats dict keys: total_trades, winners, losers, total_pnl,
                     win_rate, best_trade, worst_trade, running_bots
    """
    total_pnl = float(stats.get('total_pnl', 0))
    pnl_icon  = '📈' if total_pnl >= 0 else '📉'
    sign      = '+' if total_pnl >= 0 else ''

    text = (
        f"{pnl_icon} <b>Daily Report — {date_str}</b>\n\n"
        f"Trades:     {stats.get('total_trades', 0)} "
        f"(✅{stats.get('winners', 0)} ❌{stats.get('losers', 0)})\n"
        f"Win Rate:   {stats.get('win_rate', 0):.1f}%\n"
        f"Total P&amp;L:  <b>{sign}{total_pnl:.2f} USD</b>\n"
    )

    best = stats.get('best_trade')
    if best:
        text += f"Best Trade: +{best:.2f} USD\n"

    worst = stats.get('worst_trade')
    if worst:
        text += f"Worst:      {worst:.2f} USD\n"

    text += f"\nRunning Bots: {stats.get('running_bots', 0)}"
    return _send(text)


# ── NLP command result ────────────────────────────────────────
def alert_nlp_result(command: str, action: str,
                      success: bool, explanation: str) -> bool:
    icon = '✅' if success else '❌'
    text = (
        f"{icon} <b>NLP Command Result</b>\n\n"
        f"Command: <i>{command[:80]}</i>\n"
        f"Action:  {action}\n"
        f"Result:  {explanation[:150]}\n"
    )
    return _send(text)