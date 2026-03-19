# ============================================================
# Core trading engine — orchestrates one full bot tick cycle
# ============================================================
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from django.utils import timezone as dj_tz
from apps.trading.models import TradingBot, BotLog
from utils.constants import BotStatus

logger = logging.getLogger('trading')


class TradingEngine:
    """
    Orchestrates a single bot's trading cycle.

    One cycle:
      1.  Load bot + strategy + risk settings from DB
      2.  Connect to broker API
      3.  Fetch account info (balance, equity, margin)
      4.  Sync open positions with broker
      5.  Run risk checks (daily limits, drawdown)
      6.  Fetch latest candles (cache → DB → broker)
      7.  Run strategy → generate Signal
      8.  Process signal (lot size, SL/TP calculation)
      9.  Run pre-trade risk validation
      10. Execute order (if signal is actionable)
      11. Update trailing stops on open positions
      12. Write heartbeat log
      13. Sleep until next candle close

    The engine runs inside a Celery worker task.
    It loops until the bot's status changes to STOPPED/PAUSED/ERROR.
    """

    SLEEP_SECONDS = {
        'M1': 60,   'M5': 300,  'M15': 900,
        'M30': 1800,'H1': 3600, 'H4': 14400,
        'D1': 86400,'W1': 604800,
    }

    def __init__(self, bot_id: str):
        self.bot_id  = bot_id
        self.bot     = None
        self.broker  = None
        self._running = False

    def run(self):
        """
        Main entry point called by the Celery worker.
        Loads bot, marks it running, loops until stopped.
        """
        self.bot = self._load_bot()
        if not self.bot:
            logger.error(f"TradingEngine: bot {self.bot_id} not found")
            return

        self._set_status(BotStatus.RUNNING)
        self._log(BotLog.EventType.STATUS_CHANGE, BotLog.Level.INFO,
                  f"Bot '{self.bot.name}' started")
        self._running = True

        try:
            self.broker = self._connect_broker()
        except Exception as e:
            self._set_status(BotStatus.ERROR, str(e))
            self._log(BotLog.EventType.ERROR, BotLog.Level.ERROR,
                      f"Broker connection failed: {e}")
            return

        logger.info(f"TradingEngine: bot '{self.bot.name}' running "
                    f"| strategy={self.bot.strategy.name} "
                    f"| symbols={self.bot.symbols}")

        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"TradingEngine tick error: {e}", exc_info=True)
                self._log(BotLog.EventType.ERROR, BotLog.Level.ERROR,
                          f"Tick error: {e}")

            # Refresh bot status from DB (may have been changed via API/NLP)
            self.bot.refresh_from_db()
            if self.bot.status in (
                BotStatus.STOPPED, BotStatus.PAUSED, BotStatus.ERROR
            ):
                self._running = False
                break

            sleep_secs = self.SLEEP_SECONDS.get(self.bot.timeframe, 3600)
            logger.debug(f"Bot sleeping {sleep_secs}s until next candle...")
            self._interruptible_sleep(sleep_secs)

        self._log(BotLog.EventType.STATUS_CHANGE, BotLog.Level.INFO,
                  f"Bot '{self.bot.name}' stopped (status={self.bot.status})")
        logger.info(f"TradingEngine: bot '{self.bot.name}' exited run loop")

    def _tick(self):
        """Execute one full trading cycle."""
        tick_start = time.monotonic()
        bot        = self.bot

        # ── Step 1: Account info ──────────────────────────────
        account_info = self._get_account_info()
        if not account_info:
            self._log(BotLog.EventType.ERROR, BotLog.Level.ERROR,
                      "Could not fetch account info — skipping tick")
            return

        # ── Step 2: Sync positions ────────────────────────────
        from services.trading_engine.position_tracker import PositionTracker
        tracker = PositionTracker(bot, self.broker)
        sync    = tracker.sync_with_broker()
        if sync['closed'] > 0:
            logger.info(f"Position sync: {sync['closed']} trades closed by broker")

        # ── Step 3: Risk checks ───────────────────────────────
        from apps.risk_management.rules import RiskRuleChecker
        checker    = RiskRuleChecker(bot, account_info, tracker)
        risk_check = checker.pre_tick_check()

        if not risk_check['allowed']:
            self._log(
                BotLog.EventType.RISK_BLOCK, BotLog.Level.WARNING,
                f"Tick blocked by risk rule: {risk_check['reason']}"
            )
            return

        # ── Step 4: Loop each symbol ──────────────────────────
        for symbol in (bot.symbols or []):
            self._process_symbol(symbol, account_info, tracker, checker)

        # ── Step 5: Update trailing stops ────────────────────
        if bot.risk_settings.get('trailing_stop_enabled', False):
            prices = {
                s: self.broker.get_price(s)
                for s in (bot.symbols or [])
            }
            tracker.check_trailing_stops(prices)

        # ── Step 6: Heartbeat ─────────────────────────────────
        elapsed = round((time.monotonic() - tick_start) * 1000, 1)
        self._log(
            BotLog.EventType.HEARTBEAT, BotLog.Level.INFO,
            f"Tick complete in {elapsed}ms | "
            f"open={tracker.get_open_count()} trades | "
            f"balance={account_info.get('balance', '?')}",
            data={'elapsed_ms': elapsed, 'account': account_info},
        )
        bot.last_signal_at = dj_tz.now()
        bot.save(update_fields=['last_signal_at'])

    def _process_symbol(self, symbol, account_info, tracker, checker):
        """Run strategy + execute for one symbol."""
        bot = self.bot

        # Check per-symbol position limit
        if tracker.get_open_count_for_symbol(symbol) >= \
                bot.risk_settings.get('max_trades_per_symbol', 1):
            logger.debug(f"Symbol {symbol}: max open trades reached — skipping")
            return

        # ── Fetch candles ──────────────────────────────────────
        from apps.market_data.cache import get_cached_candles
        df = get_cached_candles(
            symbol, bot.timeframe,
            count  = bot.strategy.get_plugin_class()().get_required_candles() + 50,
            broker = bot.broker,
        )
        if df is None or df.empty:
            logger.warning(f"No candle data for {symbol}/{bot.timeframe}")
            return

        # ── Run strategy ───────────────────────────────────────
        try:
            strategy_instance = bot.strategy.instantiate()
            signal = strategy_instance.generate_signal(df, symbol)
        except Exception as e:
            logger.error(f"Strategy error for {symbol}: {e}", exc_info=True)
            self._log(BotLog.EventType.ERROR, BotLog.Level.ERROR,
                      f"Strategy error on {symbol}: {e}")
            return

        self._log(
            BotLog.EventType.SIGNAL, BotLog.Level.INFO,
            f"Signal [{symbol}]: {signal.action.upper()} — {signal.reason}",
            data=signal.to_dict(),
        )

        if signal.is_hold:
            return

        # ── Respect bot direction flags ────────────────────────
        if signal.action == 'buy'  and not bot.allow_buy:
            logger.debug(f"Buy signal on {symbol} blocked — allow_buy=False")
            return
        if signal.action == 'sell' and not bot.allow_sell:
            logger.debug(f"Sell signal on {symbol} blocked — allow_sell=False")
            return

        # ── Get live price ─────────────────────────────────────
        current_price = self.broker.get_price(symbol)
        if not current_price:
            logger.warning(f"Cannot get live price for {symbol}")
            return

        # ── Process signal (lot size + SL/TP) ─────────────────
        from services.trading_engine.signal_processor import SignalProcessor
        processor        = SignalProcessor(bot, account_info, current_price)
        processed_signal = processor.process(signal)

        if not processed_signal.valid:
            self._log(
                BotLog.EventType.RISK_BLOCK, BotLog.Level.WARNING,
                f"Signal rejected [{symbol}]: {processed_signal.reject_reason}",
            )
            return

        # ── Pre-trade risk check ───────────────────────────────
        trade_check = checker.pre_trade_check(processed_signal)
        if not trade_check['allowed']:
            from utils.logger import TradingActivityLogger
            TradingActivityLogger.log_risk_block(
                bot_id  = bot.id,
                rule    = trade_check.get('rule', 'unknown'),
                details = trade_check['reason'],
            )
            self._log(
                BotLog.EventType.RISK_BLOCK, BotLog.Level.WARNING,
                f"Trade blocked by risk rule [{symbol}]: {trade_check['reason']}",
            )
            return

        # ── Execute order ──────────────────────────────────────
        from services.trading_engine.executor import OrderExecutor
        executor = OrderExecutor(bot, self.broker)
        result   = executor.execute(processed_signal)

        if result['success']:
            logger.info(
                f"Trade executed: {signal.action.upper()} {symbol} "
                f"@ {result.get('fill_price')} lot={result.get('lot_size')}"
            )
        else:
            logger.warning(
                f"Trade failed: {symbol} — {result.get('reason')}"
            )

    # ── Internal helpers ──────────────────────────────────────
    def _load_bot(self) -> Optional[TradingBot]:
        try:
            return TradingBot.objects.select_related(
                'strategy', 'trading_account', 'user'
            ).get(pk=self.bot_id, is_active=True)
        except TradingBot.DoesNotExist:
            return None

    def _connect_broker(self):
        """Instantiate and connect the correct broker."""
        bot     = self.bot
        account = bot.trading_account
        api_key = account.get_api_key()

        if bot.broker == 'oanda':
            from services.broker_api.oanda import OandaBroker
            broker = OandaBroker(
                api_key     = api_key,
                account_id  = account.account_id,
                environment = account.account_type,
            )
        elif bot.broker == 'metatrader5':
            from services.broker_api.metatrader5 import MT5Broker
            broker = MT5Broker(
                login    = account.account_id,
                password = api_key,
                server   = account.get_api_secret(),
            )
        else:
            raise ValueError(f"Unsupported broker: {bot.broker}")

        broker.connect()
        return broker

    def _get_account_info(self) -> Optional[dict]:
        try:
            return self.broker.get_account_info()
        except Exception as e:
            logger.error(f"get_account_info failed: {e}")
            return None

    def _set_status(self, status: str, error_msg: str = ''):
        try:
            self.bot.status = status
            if error_msg:
                self.bot.error_message = error_msg
            if status == BotStatus.RUNNING:
                self.bot.started_at = dj_tz.now()
            elif status in (BotStatus.STOPPED, BotStatus.ERROR):
                self.bot.stopped_at = dj_tz.now()
            self.bot.save(update_fields=[
                'status', 'error_message', 'started_at', 'stopped_at'
            ])
        except Exception as e:
            logger.error(f"_set_status failed: {e}")

    def _log(self, event_type, level, message, data=None):
        try:
            BotLog.objects.create(
                bot        = self.bot,
                level      = level,
                event_type = event_type,
                message    = message,
                data       = data or {},
            )
        except Exception as e:
            logger.error(f"BotLog write failed: {e}")

    def _interruptible_sleep(self, seconds: int):
        """Sleep in small chunks so status changes are detected quickly."""
        chunk = 10
        for _ in range(0, seconds, chunk):
            time.sleep(min(chunk, seconds))
            self.bot.refresh_from_db()
            if self.bot.status in (
                BotStatus.STOPPED, BotStatus.PAUSED, BotStatus.ERROR
            ):
                self._running = False
                break