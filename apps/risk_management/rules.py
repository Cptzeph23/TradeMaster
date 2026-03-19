# ============================================================
# RiskRuleChecker — validates every tick and every trade
# against the bot's configured risk rules
# ============================================================
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Tuple

from apps.trading.models import TradingBot, Trade
from utils.constants import TradeStatus
from .calculator import RiskCalculator

logger = logging.getLogger('risk_management')


class RiskRuleChecker:
    """
    Enforces all risk rules for a TradingBot before:
      - Each tick  (pre_tick_check)
      - Each trade (pre_trade_check)

    All checks return {'allowed': bool, 'reason': str, 'rule': str}

    Rules checked:
      1.  Max drawdown halt        — stop bot permanently
      2.  Drawdown pause           — pause bot temporarily
      3.  Daily loss limit         — stop trading for the day
      4.  Daily profit target      — stop trading for the day
      5.  Max trades per day       — count today's trades
      6.  Max open trades total    — count currently open trades
      7.  Max trades per symbol    — per-symbol position limit
      8.  Trading hours filter     — UTC hour window
      9.  Spread filter            — checked in SignalProcessor
      10. Allow buy / allow sell   — directional flags on bot
    """

    def __init__(
        self,
        bot: TradingBot,
        account_info: dict,
        position_tracker=None,
    ):
        self.bot      = bot
        self.rs       = bot.risk_settings or {}   # shorthand
        self.account  = account_info
        self.tracker  = position_tracker

    # ── Pre-tick check (runs before every strategy evaluation) ─
    def pre_tick_check(self) -> Dict:
        """
        Checks that run once per tick before any symbols are processed.
        These can pause or halt the bot entirely.
        """
        balance = float(self.account.get('balance', 0))
        equity  = float(self.account.get('equity',  balance))

        # ── 1. Max drawdown halt ──────────────────────────────
        peak_balance = float(self.bot.peak_balance or balance)
        if peak_balance > 0:
            current_dd = RiskCalculator.drawdown_percent(peak_balance, equity)
            max_dd     = float(self.rs.get('max_drawdown_percent', 20.0))

            if current_dd >= max_dd:
                self._trigger_halt(current_dd, peak_balance, equity)
                return self._block(
                    f"Max drawdown {current_dd:.2f}% ≥ {max_dd}% — bot halted",
                    rule='max_drawdown'
                )

            # ── 2. Drawdown pause ─────────────────────────────
            pause_dd = float(self.rs.get('drawdown_pause_percent', 10.0))
            if current_dd >= pause_dd and self.bot.status == 'running':
                self._trigger_pause(current_dd, peak_balance, equity)
                return self._block(
                    f"Drawdown pause threshold {current_dd:.2f}% ≥ {pause_dd}% — bot paused",
                    rule='drawdown_pause'
                )

        # ── 3. Daily loss limit ───────────────────────────────
        max_daily_loss = float(self.rs.get('max_daily_loss', 5.0))
        if max_daily_loss > 0:
            daily_loss_pct = self._get_daily_loss_pct(balance)
            if daily_loss_pct >= max_daily_loss:
                return self._block(
                    f"Daily loss {daily_loss_pct:.2f}% ≥ {max_daily_loss}% — no more trades today",
                    rule='daily_loss'
                )

        # ── 4. Daily profit target ────────────────────────────
        max_daily_profit = float(self.rs.get('max_daily_profit', 0.0))
        if max_daily_profit > 0:
            daily_profit_pct = self._get_daily_profit_pct(balance)
            if daily_profit_pct >= max_daily_profit:
                return self._block(
                    f"Daily profit target {daily_profit_pct:.2f}% ≥ {max_daily_profit}% — done for today",
                    rule='daily_profit'
                )

        # ── 5. Max trades per day ─────────────────────────────
        max_trades = int(self.rs.get('max_trades_per_day', 10))
        if max_trades > 0:
            today_count = self._count_trades_today()
            if today_count >= max_trades:
                return self._block(
                    f"Daily trade limit reached ({today_count}/{max_trades})",
                    rule='max_trades_per_day'
                )

        # ── 6. Trading hours filter ───────────────────────────
        start_h = int(self.rs.get('trade_start_hour', 0))
        end_h   = int(self.rs.get('trade_end_hour',  23))
        if start_h != 0 or end_h != 23:
            current_hour = datetime.now(timezone.utc).hour
            if not (start_h <= current_hour <= end_h):
                return self._block(
                    f"Outside trading hours (UTC {start_h}:00–{end_h}:00, now={current_hour}:00)",
                    rule='trading_hours'
                )

        return {'allowed': True, 'reason': '', 'rule': ''}

    # ── Pre-trade check (runs before each individual order) ───
    def pre_trade_check(self, processed_signal) -> Dict:
        """
        Final validation before placing a single order.
        Checks position limits and directional flags.
        """
        signal = processed_signal.signal
        symbol = signal.symbol

        # ── Max open trades total ─────────────────────────────
        max_open = int(self.rs.get('max_open_trades', 3))
        if self.tracker:
            open_count = self.tracker.get_open_count()
            if open_count >= max_open:
                return self._block(
                    f"Max open trades reached ({open_count}/{max_open})",
                    rule='max_open_trades'
                )

        # ── Max trades per symbol ─────────────────────────────
        max_per_sym = int(self.rs.get('max_trades_per_symbol', 1))
        if self.tracker:
            sym_count = self.tracker.get_open_count_for_symbol(symbol)
            if sym_count >= max_per_sym:
                return self._block(
                    f"Max trades per symbol reached for {symbol} ({sym_count}/{max_per_sym})",
                    rule='max_trades_per_symbol'
                )

        # ── Directional flags ─────────────────────────────────
        if signal.action == 'buy' and not self.bot.allow_buy:
            return self._block("Buy trades are disabled on this bot", rule='allow_buy')
        if signal.action == 'sell' and not self.bot.allow_sell:
            return self._block("Sell trades are disabled on this bot", rule='allow_sell')

        # ── Minimum risk amount sanity check ──────────────────
        balance = float(self.account.get('balance', 0))
        if balance < 10:
            return self._block(
                f"Account balance too low (${balance:.2f})",
                rule='min_balance'
            )

        return {'allowed': True, 'reason': '', 'rule': ''}

    # ── Helpers ───────────────────────────────────────────────
    def _count_trades_today(self) -> int:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return Trade.objects.filter(
            bot      = self.bot,
            opened_at__gte = today_start,
        ).count()

    def _get_daily_loss_pct(self, current_balance: float) -> float:
        """
        Compare today's starting balance to current balance.
        Starting balance = balance at midnight UTC.
        We approximate using closed trade P&L today.
        """
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_pnl = Trade.objects.filter(
            bot        = self.bot,
            status     = TradeStatus.CLOSED,
            closed_at__gte = today_start,
        ).values_list('profit_loss', flat=True)

        total_today = sum(float(p) for p in today_pnl)
        if total_today >= 0 or current_balance <= 0:
            return 0.0
        return round(abs(total_today) / current_balance * 100, 4)

    def _get_daily_profit_pct(self, current_balance: float) -> float:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_pnl = Trade.objects.filter(
            bot        = self.bot,
            status     = TradeStatus.CLOSED,
            closed_at__gte = today_start,
        ).values_list('profit_loss', flat=True)

        total_today = sum(float(p) for p in today_pnl)
        if total_today <= 0 or current_balance <= 0:
            return 0.0
        return round(total_today / current_balance * 100, 4)

    def _trigger_halt(self, dd_pct: float, peak: float, current: float):
        """Permanently stop the bot due to max drawdown breach."""
        from utils.constants import BotStatus
        from django.utils import timezone as dj_tz

        logger.critical(
            f"Bot {self.bot.name} HALTED — drawdown {dd_pct:.2f}% "
            f"(peak={peak}, current={current})"
        )
        self.bot.status    = BotStatus.STOPPED
        self.bot.stopped_at = dj_tz.now()
        self.bot.error_message = f"Auto-halted: drawdown {dd_pct:.2f}% exceeded max"
        self.bot.save(update_fields=['status', 'stopped_at', 'error_message'])
        self._record_drawdown_event('halt', dd_pct, peak, current)

    def _trigger_pause(self, dd_pct: float, peak: float, current: float):
        """Temporarily pause the bot due to drawdown pause threshold."""
        from utils.constants import BotStatus
        from django.utils import timezone as dj_tz

        logger.warning(
            f"Bot {self.bot.name} PAUSED — drawdown {dd_pct:.2f}%"
        )
        self.bot.status = BotStatus.PAUSED
        self.bot.save(update_fields=['status'])
        self._record_drawdown_event('pause', dd_pct, peak, current)

    def _record_drawdown_event(
        self, event_type: str, dd_pct: float,
        peak: float, current: float
    ):
        try:
            from apps.risk_management.models import DrawdownEvent
            DrawdownEvent.objects.create(
                bot               = self.bot,
                event_type        = event_type,
                drawdown_percent  = dd_pct,
                balance_at_event  = current,
                peak_balance      = peak,
            )
        except Exception as e:
            logger.error(f"DrawdownEvent record failed: {e}")

    @staticmethod
    def _block(reason: str, rule: str) -> Dict:
        logger.warning(f"Risk block [{rule}]: {reason}")
        return {'allowed': False, 'reason': reason, 'rule': rule}