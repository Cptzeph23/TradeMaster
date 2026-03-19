# ============================================================
# Sends processed orders to the broker and records results in DB
# ============================================================
import logging
from datetime import datetime, timezone
from django.utils import timezone as dj_tz

from services.broker_api.base import OrderResult
from services.broker_api.exceptions import (
    BrokerException, InsufficientMarginError,
    MarketClosedError, BrokerOrderError,
)
from apps.trading.models import Trade, BotLog, TradingBot
from utils.constants import TradeStatus, OrderType
from utils.logger import TradingActivityLogger

logger = logging.getLogger('trading.orders')


class OrderExecutor:
    """
    Sends a ProcessedSignal to the broker API and:
      1. Creates a Trade record in PostgreSQL (status=pending)
      2. Calls broker.place_order()
      3. Updates Trade record with fill price, broker IDs
      4. Writes a BotLog entry for every outcome
      5. Updates bot performance counters

    All DB writes are wrapped in error handling so a DB failure
    never blocks the order placement, and a broker failure never
    leaves a dangling Trade record.
    """

    def __init__(self, bot: TradingBot, broker):
        """
        bot:    TradingBot model instance
        broker: Connected BaseBroker instance (OANDA, MT5, etc.)
        """
        self.bot    = bot
        self.broker = broker

    def execute(self, processed_signal) -> dict:
        """
        Main entry — execute a ProcessedSignal.
        Returns a result dict with success/failure details.
        """
        if not processed_signal.valid:
            return {
                'success': False,
                'reason':  processed_signal.reject_reason,
            }

        signal  = processed_signal.signal
        order   = processed_signal.order_request
        trade   = None

        # ── 1. Create pending Trade record ───────────────────
        try:
            trade = Trade.objects.create(
                bot             = self.bot,
                trading_account = self.bot.trading_account,
                symbol          = signal.symbol,
                order_type      = signal.action,
                status          = TradeStatus.PENDING,
                lot_size        = processed_signal.lot_size,
                units           = order.units,
                stop_loss       = processed_signal.stop_loss,
                take_profit     = processed_signal.take_profit,
                signal_data     = signal.indicators,
                opened_at       = dj_tz.now(),
            )
            logger.debug(f"Trade record created: {trade.id}")
        except Exception as e:
            logger.error(f"Failed to create Trade record: {e}", exc_info=True)
            # Continue — don't block order placement on DB error

        # ── 2. Place order at broker ──────────────────────────
        try:
            result: OrderResult = self.broker.place_order(order)
        except InsufficientMarginError as e:
            return self._handle_failure(trade, signal, str(e), 'insufficient_margin')
        except MarketClosedError as e:
            return self._handle_failure(trade, signal, str(e), 'market_closed')
        except BrokerException as e:
            return self._handle_failure(trade, signal, str(e), 'broker_error')
        except Exception as e:
            return self._handle_failure(trade, signal, str(e), 'unexpected_error')

        # ── 3. Handle broker response ─────────────────────────
        if not result.success:
            return self._handle_failure(
                trade, signal, result.error_message, 'order_rejected'
            )

        # ── 4. Update Trade with fill details ─────────────────
        try:
            if trade:
                trade.broker_order_id = result.order_id
                trade.broker_trade_id = result.trade_id
                trade.entry_price     = result.fill_price
                trade.units           = result.units_filled
                trade.status          = TradeStatus.OPEN
                trade.save(update_fields=[
                    'broker_order_id', 'broker_trade_id',
                    'entry_price', 'units', 'status',
                ])
        except Exception as e:
            logger.error(f"Failed to update Trade after fill: {e}")

        # ── 5. Log success ────────────────────────────────────
        TradingActivityLogger.log_order_placed(
            bot_id     = self.bot.id,
            symbol     = signal.symbol,
            order_type = signal.action,
            quantity   = processed_signal.lot_size,
            price      = result.fill_price,
            trade_id   = str(trade.id) if trade else '',
        )

        self._write_bot_log(
            event_type = BotLog.EventType.ORDER_FILLED,
            level      = BotLog.Level.INFO,
            message    = (
                f"Order filled: {signal.action.upper()} {signal.symbol} "
                f"@ {result.fill_price} | lot={processed_signal.lot_size} "
                f"SL={processed_signal.stop_loss} TP={processed_signal.take_profit}"
            ),
            trade  = trade,
            data   = {
                'fill_price':   result.fill_price,
                'lot_size':     processed_signal.lot_size,
                'stop_loss':    processed_signal.stop_loss,
                'take_profit':  processed_signal.take_profit,
                'risk_amount':  processed_signal.risk_amount,
                'broker_ids':   {
                    'order_id': result.order_id,
                    'trade_id': result.trade_id,
                },
                'signal_reason': signal.reason,
            },
        )

        return {
            'success':      True,
            'trade_id':     str(trade.id) if trade else None,
            'broker_trade': result.trade_id,
            'fill_price':   result.fill_price,
            'lot_size':     processed_signal.lot_size,
            'symbol':       signal.symbol,
            'action':       signal.action,
        }

    def close_trade(self, trade: Trade, reason: str = 'signal') -> dict:
        """Close an open trade at market price."""
        try:
            result = self.broker.close_trade(trade.broker_trade_id)
        except BrokerException as e:
            logger.error(f"Close trade failed for {trade.id}: {e}")
            return {'success': False, 'error': str(e)}

        if result.success:
            pnl = self._calculate_pnl(trade, result.fill_price)
            try:
                trade.exit_price  = result.fill_price
                trade.status      = TradeStatus.CLOSED
                trade.profit_loss = pnl
                trade.closed_at   = dj_tz.now()
                trade.save(update_fields=[
                    'exit_price', 'status', 'profit_loss', 'closed_at'
                ])
                self._update_bot_stats(pnl)
            except Exception as e:
                logger.error(f"Failed to update closed trade: {e}")

            self._write_bot_log(
                event_type = BotLog.EventType.ORDER_CLOSED,
                level      = BotLog.Level.INFO,
                message    = (
                    f"Trade closed: {trade.symbol} @ {result.fill_price} "
                    f"P&L={pnl:.2f} reason={reason}"
                ),
                trade = trade,
                data  = {'pnl': float(pnl), 'reason': reason,
                         'fill_price': result.fill_price},
            )

            TradingActivityLogger.log_order_filled(
                trade_id    = trade.id,
                symbol      = trade.symbol,
                fill_price  = result.fill_price,
                profit_loss = float(pnl),
            )

            return {'success': True, 'pnl': float(pnl), 'fill_price': result.fill_price}

        return {'success': False, 'error': result.error_message}

    # ── Helpers ───────────────────────────────────────────────
    def _handle_failure(
        self, trade, signal, reason: str, code: str
    ) -> dict:
        logger.warning(f"Order failed [{code}]: {signal.symbol} — {reason}")
        TradingActivityLogger.log_order_rejected(
            bot_id=self.bot.id, reason=reason, code=code
        )
        if trade:
            try:
                trade.status        = TradeStatus.REJECTED
                trade.save(update_fields=['status'])
            except Exception:
                pass
        self._write_bot_log(
            event_type = BotLog.EventType.ORDER_REJECTED,
            level      = BotLog.Level.WARNING,
            message    = f"Order rejected [{code}]: {reason}",
            trade      = trade,
            data       = {'code': code, 'reason': reason},
        )
        return {'success': False, 'code': code, 'reason': reason}

    def _write_bot_log(self, event_type, level, message, trade=None, data=None):
        try:
            BotLog.objects.create(
                bot        = self.bot,
                trade      = trade,
                level      = level,
                event_type = event_type,
                message    = message,
                data       = data or {},
            )
        except Exception as e:
            logger.error(f"BotLog write failed: {e}")

    def _calculate_pnl(self, trade: Trade, exit_price: float) -> float:
        if not trade.entry_price:
            return 0.0
        diff  = float(exit_price) - float(trade.entry_price)
        units = abs(trade.units) if trade.units else int(float(trade.lot_size) * 100_000)
        if trade.order_type == 'sell':
            diff = -diff
        return round(diff * units, 2)

    def _update_bot_stats(self, pnl: float):
        try:
            bot = self.bot
            bot.total_trades      += 1
            bot.total_profit_loss += pnl
            if pnl > 0:
                bot.winning_trades += 1
            # Update peak balance for drawdown tracking
            current_balance = float(
                bot.trading_account.balance or 0
            ) + float(bot.total_profit_loss)
            if current_balance > float(bot.peak_balance or 0):
                bot.peak_balance = current_balance

            bot.save(update_fields=[
                'total_trades', 'total_profit_loss',
                'winning_trades', 'peak_balance',
            ])
        except Exception as e:
            logger.error(f"Bot stats update failed: {e}")