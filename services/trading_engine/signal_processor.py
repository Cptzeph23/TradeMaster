# ============================================================
# Converts raw strategy signals into validated, enriched order requests
# ============================================================
import logging
from typing import Optional
from dataclasses import dataclass

from apps.strategies.base import Signal
from services.broker_api.base import OrderRequest
from utils.constants import OrderType
from utils.helpers import calculate_lot_size, pips_to_price

logger = logging.getLogger('trading')


@dataclass
class ProcessedSignal:
    """
    A Signal that has passed all validations and is enriched
    with lot size, exact SL/TP prices, and units ready for
    the order executor.
    """
    signal:       Signal
    order_request: OrderRequest
    lot_size:     float
    stop_loss:    float
    take_profit:  float
    risk_amount:  float    # USD amount being risked
    valid:        bool
    reject_reason: str = ''


class SignalProcessor:
    """
    Takes a raw Signal from a strategy and:
      1. Validates it against risk rules
      2. Calculates position size (lot size / units)
      3. Calculates exact SL/TP price levels
      4. Checks spread is acceptable
      5. Returns a ProcessedSignal ready for OrderExecutor

    This layer is intentionally separate from:
      - Strategy logic  (what signal to generate)
      - Risk rules      (whether to allow the trade)
      - Order execution (sending to broker)
    """

    def __init__(self, bot, account_info: dict, current_price: dict):
        """
        bot:           TradingBot model instance
        account_info:  dict from broker.get_account_info()
        current_price: dict {'bid': x, 'ask': x, 'spread': x}
        """
        self.bot           = bot
        self.account_info  = account_info
        self.current_price = current_price
        self.risk_settings = bot.risk_settings or {}

    def process(self, signal: Signal) -> ProcessedSignal:
        """Main entry — validates and enriches a Signal."""

        # Hold signals need no processing
        if signal.action == 'hold':
            return ProcessedSignal(
                signal=signal, order_request=None,
                lot_size=0, stop_loss=0, take_profit=0,
                risk_amount=0, valid=False,
                reject_reason='hold'
            )

        # Check spread filter
        spread_ok, spread_reason = self._check_spread(signal.symbol)
        if not spread_ok:
            return self._reject(signal, spread_reason)

        # Determine entry price
        entry_price = self._get_entry_price(signal.action)

        # Calculate SL/TP
        stop_loss, take_profit = self._calculate_sl_tp(signal, entry_price)

        if stop_loss is None:
            return self._reject(signal, "Cannot calculate stop loss")

        # Calculate lot size
        stop_loss_pips = self._price_diff_to_pips(
            abs(entry_price - stop_loss), signal.symbol
        )
        lot_size = calculate_lot_size(
            account_balance  = float(self.account_info.get('balance', 10000)),
            risk_percent     = self.risk_settings.get('risk_percent', 1.0),
            stop_loss_pips   = stop_loss_pips,
            symbol           = signal.symbol,
        )

        # Enforce lot size limits
        min_lot = self.risk_settings.get('min_lot_size', 0.01)
        max_lot = self.risk_settings.get('max_lot_size', 1.0)
        lot_size = max(min_lot, min(lot_size, max_lot))

        # Calculate units for OANDA (positive=buy, negative=sell)
        units = self._lots_to_units(lot_size, signal.symbol)
        if signal.action == 'sell':
            units = -abs(units)

        # Calculate risk amount
        risk_amount = (
            float(self.account_info.get('balance', 10000)) *
            self.risk_settings.get('risk_percent', 1.0) / 100
        )

        order_request = OrderRequest(
            symbol      = signal.symbol,
            order_type  = signal.action,
            units       = units,
            lot_size    = lot_size,
            stop_loss   = stop_loss,
            take_profit = take_profit,
            comment     = f"Bot:{self.bot.id} | {signal.reason[:80]}",
        )

        logger.info(
            f"Signal processed: {signal.action} {signal.symbol} "
            f"lot={lot_size} SL={stop_loss} TP={take_profit} "
            f"risk=${risk_amount:.2f}"
        )

        return ProcessedSignal(
            signal        = signal,
            order_request = order_request,
            lot_size      = lot_size,
            stop_loss     = stop_loss,
            take_profit   = take_profit,
            risk_amount   = risk_amount,
            valid         = True,
        )

    def _get_entry_price(self, action: str) -> float:
        """Buy at ask, sell at bid."""
        if action == 'buy':
            return float(self.current_price.get('ask', 0))
        return float(self.current_price.get('bid', 0))

    def _calculate_sl_tp(
        self, signal: Signal, entry_price: float
    ) -> tuple:
        """
        Use signal-provided SL/TP if present,
        otherwise fall back to risk settings defaults.
        """
        # Use strategy-provided levels first
        sl = signal.stop_loss
        tp = signal.take_profit

        if sl is None:
            # Fall back to pip-based defaults from risk settings
            sl_pips = self.risk_settings.get('stop_loss_pips', 50)
            pip_size = 0.01 if 'JPY' in signal.symbol else 0.0001
            if signal.action == 'buy':
                sl = round(entry_price - sl_pips * pip_size, 5)
            else:
                sl = round(entry_price + sl_pips * pip_size, 5)

        if tp is None:
            if self.risk_settings.get('use_risk_reward', False):
                rr  = self.risk_settings.get('risk_reward_ratio', 2.0)
                sl_dist = abs(entry_price - sl)
                if signal.action == 'buy':
                    tp = round(entry_price + sl_dist * rr, 5)
                else:
                    tp = round(entry_price - sl_dist * rr, 5)
            else:
                tp_pips = self.risk_settings.get('take_profit_pips', 100)
                pip_size = 0.01 if 'JPY' in signal.symbol else 0.0001
                if signal.action == 'buy':
                    tp = round(entry_price + tp_pips * pip_size, 5)
                else:
                    tp = round(entry_price - tp_pips * pip_size, 5)

        return sl, tp

    def _check_spread(self, symbol: str) -> tuple:
        """Reject if spread exceeds the configured maximum."""
        max_spread = self.risk_settings.get('max_spread_pips', 3.0)
        spread_raw = float(self.current_price.get('spread', 0))
        pip_size   = 0.01 if 'JPY' in symbol else 0.0001
        spread_pips = spread_raw / pip_size

        if spread_pips > max_spread:
            return False, f"Spread {spread_pips:.1f} pips exceeds max {max_spread} pips"
        return True, ''

    @staticmethod
    def _price_diff_to_pips(diff: float, symbol: str) -> float:
        pip_size = 0.01 if 'JPY' in symbol else 0.0001
        return round(diff / pip_size, 1)

    @staticmethod
    def _lots_to_units(lot_size: float, symbol: str) -> int:
        """Convert standard lots to OANDA units (1 lot = 100,000 units)."""
        return int(lot_size * 100_000)

    @staticmethod
    def _reject(signal: Signal, reason: str) -> ProcessedSignal:
        logger.warning(f"Signal rejected [{signal.symbol}]: {reason}")
        return ProcessedSignal(
            signal=signal, order_request=None,
            lot_size=0, stop_loss=0, take_profit=0,
            risk_amount=0, valid=False,
            reject_reason=reason,
        )