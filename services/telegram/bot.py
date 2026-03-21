# ============================================================
# Telegram bot — handles incoming commands from traders
# ============================================================
import logging
from django.conf import settings

logger = logging.getLogger('telegram_bot')


class ForexTelegramBot:
    """
    Telegram bot that accepts trader commands and sends alerts.

    Setup:
      1. Message @BotFather on Telegram → /newbot
      2. Copy the token to .env: TELEGRAM_BOT_TOKEN=...
      3. Get your chat ID: message @userinfobot → copy ID
      4. Add to .env: TELEGRAM_CHAT_ID=...
      5. Optionally set a webhook or run in polling mode

    Commands supported:
      /status         — show all bot statuses + P&L
      /pause <name>   — pause a bot by name or 'all'
      /resume <name>  — resume a bot
      /stop <name>    — stop a bot
      /start <name>   — start a bot
      /pnl            — today's P&L summary
      /trades         — last 5 trades
      /risk <name>    — show risk settings for a bot
      /help           — show all commands
    """

    def __init__(self):
        self.token   = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        self.chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
        self._bot    = None

    def _get_bot(self):
        """Lazy init — only import telegram if token is set."""
        if not self.token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN not set in .env. "
                "Create a bot via @BotFather and add the token."
            )
        if self._bot is None:
            import telegram
            self._bot = telegram.Bot(token=self.token)
        return self._bot

    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    # ── Send messages ─────────────────────────────────────────
    def send(self, text: str, chat_id: str = None, parse_mode: str = 'HTML') -> bool:
        """Send a message. Returns True on success."""
        if not self.is_configured():
            logger.debug(f"Telegram not configured — skipping: {text[:60]}")
            return False
        try:
            bot  = self._get_bot()
            cid  = chat_id or self.chat_id
            bot.send_message(chat_id=cid, text=text, parse_mode=parse_mode)
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def send_photo(self, photo_path: str, caption: str = '',
                   chat_id: str = None) -> bool:
        """Send an image (e.g. equity curve chart)."""
        if not self.is_configured():
            return False
        try:
            bot = self._get_bot()
            cid = chat_id or self.chat_id
            with open(photo_path, 'rb') as f:
                bot.send_photo(chat_id=cid, photo=f, caption=caption)
            return True
        except Exception as e:
            logger.error(f"Telegram send_photo failed: {e}")
            return False

    # ── Command handler (webhook or polling) ──────────────────
    def handle_update(self, update_data: dict):
        """
        Process an incoming Telegram update.
        Called by the webhook view or polling loop.
        """
        try:
            import telegram
            update = telegram.Update.de_json(update_data, self._get_bot())
            if not update.message or not update.message.text:
                return

            text    = update.message.text.strip()
            chat_id = str(update.message.chat_id)
            user    = update.message.from_user

            logger.info(
                f"Telegram command from {user.username or user.id}: {text}"
            )

            # Authorisation — only accept from configured chat_id
            if self.chat_id and chat_id != str(self.chat_id):
                self.send(
                    "⛔ Unauthorised. This bot is private.",
                    chat_id=chat_id
                )
                return

            self._dispatch_command(text, chat_id)

        except Exception as e:
            logger.error(f"Telegram handle_update failed: {e}", exc_info=True)

    def _dispatch_command(self, text: str, chat_id: str):
        """Route command text to the correct handler."""
        parts   = text.split()
        command = parts[0].lower().lstrip('/')
        args    = parts[1:] if len(parts) > 1 else []

        handlers = {
            'status':  self._cmd_status,
            'pnl':     self._cmd_pnl,
            'trades':  self._cmd_trades,
            'pause':   self._cmd_pause,
            'resume':  self._cmd_resume,
            'stop':    self._cmd_stop,
            'start':   self._cmd_start,
            'risk':    self._cmd_risk,
            'help':    self._cmd_help,
            'start@forexbot': self._cmd_help,   # Telegram sends /start on first use
        }

        handler = handlers.get(command, self._cmd_unknown)
        response = handler(args)
        self.send(response, chat_id=chat_id)

    # ── Command implementations ───────────────────────────────
    def _cmd_status(self, args: list) -> str:
        from apps.trading.models import TradingBot, Trade
        from utils.constants import TradeStatus

        bots = TradingBot.objects.filter(is_active=True).select_related('strategy')
        if not bots.exists():
            return "📊 <b>Bot Status</b>\n\nNo bots configured yet."

        lines = ["📊 <b>Bot Status</b>\n"]
        for bot in bots:
            icon  = {'running':'🟢','paused':'🟡','stopped':'🔴','error':'❌'}.get(bot.status, '⚪')
            pnl   = float(bot.total_profit_loss or 0)
            psign = '+' if pnl >= 0 else ''
            open_count = Trade.objects.filter(bot=bot, status=TradeStatus.OPEN).count()
            lines.append(
                f"{icon} <b>{bot.name}</b>\n"
                f"   Status: {bot.status} | P&amp;L: {psign}{pnl:.2f}\n"
                f"   Open trades: {open_count} | Win rate: {bot.win_rate:.1f}%\n"
                f"   Pairs: {', '.join(bot.symbols or [])}\n"
            )
        return '\n'.join(lines)

    def _cmd_pnl(self, args: list) -> str:
        from apps.trading.models import Trade
        from utils.constants import TradeStatus
        from datetime import datetime, timezone, timedelta

        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        week  = today - timedelta(days=7)

        today_trades = Trade.objects.filter(
            status=TradeStatus.CLOSED, closed_at__gte=today
        )
        week_trades = Trade.objects.filter(
            status=TradeStatus.CLOSED, closed_at__gte=week
        )
        all_trades = Trade.objects.filter(status=TradeStatus.CLOSED)

        def stats(qs):
            pnl  = sum(float(t.profit_loss or 0) for t in qs)
            wins = sum(1 for t in qs if float(t.profit_loss or 0) > 0)
            n    = qs.count()
            wr   = round(wins/n*100, 1) if n else 0
            sign = '+' if pnl >= 0 else ''
            return f"{sign}{pnl:.2f} USD ({n} trades, {wr}% win)"

        return (
            f"💰 <b>P&amp;L Summary</b>\n\n"
            f"Today:    {stats(today_trades)}\n"
            f"7 Days:   {stats(week_trades)}\n"
            f"All Time: {stats(all_trades)}"
        )

    def _cmd_trades(self, args: list) -> str:
        from apps.trading.models import Trade
        from utils.constants import TradeStatus

        trades = Trade.objects.filter(
            status=TradeStatus.CLOSED
        ).order_by('-closed_at')[:5]

        if not trades.exists():
            return "📋 <b>Recent Trades</b>\n\nNo closed trades yet."

        lines = ["📋 <b>Last 5 Trades</b>\n"]
        for t in trades:
            pnl   = float(t.profit_loss or 0)
            icon  = '✅' if pnl >= 0 else '❌'
            sign  = '+' if pnl >= 0 else ''
            time  = t.closed_at.strftime('%m/%d %H:%M') if t.closed_at else '?'
            lines.append(
                f"{icon} <b>{t.symbol}</b> {t.order_type.upper()} "
                f"@ {t.entry_price} → {t.exit_price}\n"
                f"   P&amp;L: {sign}{pnl:.2f} | {time}\n"
            )
        return '\n'.join(lines)

    def _cmd_pause(self, args: list) -> str:
        return self._bot_control('pause', args)

    def _cmd_resume(self, args: list) -> str:
        return self._bot_control('resume', args)

    def _cmd_stop(self, args: list) -> str:
        return self._bot_control('stop', args)

    def _cmd_start(self, args: list) -> str:
        return self._bot_control('start', args)

    def _bot_control(self, action: str, args: list) -> str:
        from apps.trading.models import TradingBot
        from utils.constants import BotStatus

        name = ' '.join(args).strip() if args else 'all'
        bots = TradingBot.objects.filter(is_active=True)
        if name.lower() != 'all':
            bots = bots.filter(name__icontains=name)

        if not bots.exists():
            return f"❓ No bot found matching '<b>{name}</b>'"

        results = []
        for bot in bots:
            try:
                if action == 'pause' and bot.status == BotStatus.RUNNING:
                    bot.status = BotStatus.PAUSED
                    bot.save(update_fields=['status'])
                    results.append(f"⏸ <b>{bot.name}</b> paused")
                elif action == 'resume' and bot.status == BotStatus.PAUSED:
                    bot.status = BotStatus.RUNNING
                    bot.save(update_fields=['status'])
                    results.append(f"▶️ <b>{bot.name}</b> resumed")
                elif action == 'stop' and bot.status in (BotStatus.RUNNING, BotStatus.PAUSED):
                    if bot.celery_task_id:
                        from config.celery import app as celery_app
                        celery_app.control.revoke(bot.celery_task_id, terminate=True)
                    bot.status = BotStatus.STOPPED
                    bot.save(update_fields=['status'])
                    results.append(f"⏹ <b>{bot.name}</b> stopped")
                elif action == 'start' and bot.status != BotStatus.RUNNING:
                    from workers.tasks import run_trading_bot
                    task = run_trading_bot.apply_async(args=[str(bot.id)], queue='trading')
                    bot.celery_task_id = task.id
                    bot.status = BotStatus.RUNNING
                    bot.save(update_fields=['celery_task_id', 'status'])
                    results.append(f"🚀 <b>{bot.name}</b> started")
                else:
                    results.append(f"⚠️ <b>{bot.name}</b> already {bot.status}")
            except Exception as e:
                results.append(f"❌ <b>{bot.name}</b> error: {e}")

        return '\n'.join(results) if results else f"No action taken for '{name}'"

    def _cmd_risk(self, args: list) -> str:
        from apps.trading.models import TradingBot
        name = ' '.join(args).strip() if args else ''
        if not name:
            return "Usage: /risk <bot name>"
        try:
            bot = TradingBot.objects.filter(
                name__icontains=name, is_active=True
            ).first()
            if not bot:
                return f"❓ No bot matching '{name}'"
            rs = bot.risk_settings or {}
            return (
                f"⚙️ <b>Risk Settings — {bot.name}</b>\n\n"
                f"Risk per trade:  {rs.get('risk_percent', 1.0)}%\n"
                f"Stop loss:       {rs.get('stop_loss_pips', 50)} pips\n"
                f"Take profit:     {rs.get('take_profit_pips', 100)} pips\n"
                f"Max trades/day:  {rs.get('max_trades_per_day', 10)}\n"
                f"Max open:        {rs.get('max_open_trades', 3)}\n"
                f"Max drawdown:    {rs.get('max_drawdown_percent', 20)}%\n"
            )
        except Exception as e:
            return f"❌ Error: {e}"

    def _cmd_help(self, args: list) -> str:
        return (
            "🤖 <b>ForexBot Commands</b>\n\n"
            "/status        — all bot statuses &amp; P&amp;L\n"
            "/pnl           — today/week/all-time P&amp;L\n"
            "/trades        — last 5 closed trades\n"
            "/risk &lt;name&gt;  — risk settings for a bot\n"
            "/start &lt;name&gt; — start a bot (or 'all')\n"
            "/stop &lt;name&gt;  — stop a bot (or 'all')\n"
            "/pause &lt;name&gt; — pause a bot (or 'all')\n"
            "/resume &lt;name&gt;— resume a bot (or 'all')\n"
            "/help          — this message\n\n"
            "💡 <i>Example: /pause EUR USD Bot</i>"
        )

    def _cmd_unknown(self, args: list) -> str:
        return "❓ Unknown command. Type /help for a list of commands."


# Module-level singleton
_bot_instance = None

def get_telegram_bot() -> ForexTelegramBot:
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = ForexTelegramBot()
    return _bot_instance