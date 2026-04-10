# ============================================================
# Pure calculation functions — no DB access, fully testable
# ============================================================
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import math


from utils.pip_calculator import (
    get_pip_size        as _get_pip_size,
    get_pip_value       as _get_pip_value,
    price_to_pips       as _price_to_pips,
    calculate_lot_size  as _calculate_lot_size,
    profit_in_pips      as _profit_in_pips,
    actual_rrr          as _actual_rrr,
)
from utils.risk_manager import RiskManager as _RiskManager
 
 

class RiskCalculator:
    """
    Stateless calculator for all risk-related computations.
    All methods are @staticmethod — no instantiation needed.

    Used by:
      - SignalProcessor     (lot size calculation)
      - RiskRuleChecker     (drawdown, daily loss)
      - Backtesting engine  (position sizing simulation)
      - Dashboard           (display metrics)
    """

    # ── Position Sizing ───────────────────────────────────────
    @staticmethod
    def lot_size(
        account_balance: float,
        risk_percent: float,
        stop_loss_pips: float,
        symbol: str,
        pip_value_per_lot: float = 10.0,
        min_lot: float = 0.01,
        max_lot: float = 100.0,
    ) -> float:
        """
        Fixed fractional position sizing.

        Formula:
            risk_amount  = balance * risk_percent / 100
            lot_size     = risk_amount / (sl_pips * pip_value_per_lot)

        pip_value_per_lot:
            USD account standard lot:  $10 per pip
            JPY pairs:                 ~$9 (approximate, use 10 for simplicity)
        """
        if stop_loss_pips <= 0 or account_balance <= 0:
            return min_lot

        risk_amount = account_balance * (risk_percent / 100.0)
        raw_lot     = risk_amount / (stop_loss_pips * pip_value_per_lot)

        # Round to 2 decimal places
        lot = float(
            Decimal(str(raw_lot)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        )
        return max(min_lot, min(lot, max_lot))

    @staticmethod
    def risk_amount(
        account_balance: float,
        risk_percent: float,
    ) -> float:
        """Dollar amount being risked on a trade."""
        return round(account_balance * risk_percent / 100, 2)

    @staticmethod
    def pip_value(symbol: str, lot_size: float = 1.0) -> float:
        """
        Approximate pip value in USD for a given symbol and lot size.
        Standard lot = 100,000 units.
        """
        pip_size = 0.01 if 'JPY' in symbol.upper() else 0.0001
        # For USD-quoted pairs (EURUSD, GBPUSD): pip_value = pip_size * units
        # For USD-base pairs (USDJPY, USDCHF): pip_value = pip_size * units / price
        # Simplified: assume ~$10 per pip per standard lot
        return round(10.0 * lot_size, 4)

    @staticmethod
    def stop_loss_price(
        entry_price: float,
        stop_loss_pips: float,
        order_type: str,  # 'buy' | 'sell'
        symbol: str,
    ) -> float:
        pip_size = 0.01 if 'JPY' in symbol.upper() else 0.0001
        distance = stop_loss_pips * pip_size
        if order_type == 'buy':
            return round(entry_price - distance, 5)
        return round(entry_price + distance, 5)

    @staticmethod
    def take_profit_price(
        entry_price: float,
        take_profit_pips: float,
        order_type: str,
        symbol: str,
    ) -> float:
        pip_size = 0.01 if 'JPY' in symbol.upper() else 0.0001
        distance = take_profit_pips * pip_size
        if order_type == 'buy':
            return round(entry_price + distance, 5)
        return round(entry_price - distance, 5)

    @staticmethod
    def take_profit_from_rr(
        entry_price: float,
        stop_loss_price: float,
        risk_reward: float,
        order_type: str,
    ) -> float:
        """Calculate TP from a risk:reward ratio."""
        sl_distance = abs(entry_price - stop_loss_price)
        tp_distance = sl_distance * risk_reward
        if order_type == 'buy':
            return round(entry_price + tp_distance, 5)
        return round(entry_price - tp_distance, 5)

    # ── Drawdown ──────────────────────────────────────────────
    @staticmethod
    def drawdown_percent(
        peak_balance: float,
        current_balance: float,
    ) -> float:
        """Current drawdown as a percentage of peak balance."""
        if peak_balance <= 0:
            return 0.0
        dd = (peak_balance - current_balance) / peak_balance * 100
        return round(max(0.0, dd), 4)

    @staticmethod
    def max_drawdown(equity_curve: list) -> float:
        """
        Maximum drawdown percentage from an equity curve list.
        equity_curve: [10000, 10200, 9800, 10500, ...]
        """
        if not equity_curve or len(equity_curve) < 2:
            return 0.0
        peak   = equity_curve[0]
        max_dd = 0.0
        for value in equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100 if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return round(max_dd, 4)

    # ── Daily P&L ─────────────────────────────────────────────
    @staticmethod
    def daily_loss_percent(
        starting_balance: float,
        current_balance: float,
    ) -> float:
        """Today's loss as a percentage of starting balance."""
        if starting_balance <= 0:
            return 0.0
        loss = starting_balance - current_balance
        return round(max(0.0, loss / starting_balance * 100), 4)

    # ── Performance Metrics ───────────────────────────────────
    @staticmethod
    def sharpe_ratio(
        returns: list,
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252,
    ) -> float:
        """Annualised Sharpe ratio from a list of period returns."""
        if not returns or len(returns) < 2:
            return 0.0
        import numpy as np
        r       = np.array(returns, dtype=float)
        excess  = r - (risk_free_rate / periods_per_year)
        std     = np.std(r, ddof=1)
        if std == 0:
            return 0.0
        return round(float(np.mean(excess) / std * math.sqrt(periods_per_year)), 4)

    @staticmethod
    def sortino_ratio(
        returns: list,
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252,
    ) -> float:
        """Sortino ratio — like Sharpe but only penalises downside volatility."""
        if not returns or len(returns) < 2:
            return 0.0
        import numpy as np
        r        = np.array(returns, dtype=float)
        excess   = r - (risk_free_rate / periods_per_year)
        downside = r[r < 0]
        if len(downside) == 0:
            return float('inf')
        down_std = np.std(downside, ddof=1)
        if down_std == 0:
            return 0.0
        return round(float(np.mean(excess) / down_std * math.sqrt(periods_per_year)), 4)

    @staticmethod
    def profit_factor(trades_pnl: list) -> float:
        """
        Gross profit / gross loss.
        trades_pnl: list of individual trade P&L values.
        """
        gross_profit = sum(p for p in trades_pnl if p > 0)
        gross_loss   = abs(sum(p for p in trades_pnl if p < 0))
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        return round(gross_profit / gross_loss, 4)

    @staticmethod
    def win_rate(trades_pnl: list) -> float:
        """Percentage of profitable trades."""
        if not trades_pnl:
            return 0.0
        winners = sum(1 for p in trades_pnl if p > 0)
        return round(winners / len(trades_pnl) * 100, 2)

    @staticmethod
    def expectancy(trades_pnl: list) -> float:
        """
        Average expected return per trade.
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        """
        if not trades_pnl:
            return 0.0
        wins   = [p for p in trades_pnl if p > 0]
        losses = [p for p in trades_pnl if p < 0]
        wr     = len(wins) / len(trades_pnl)
        lr     = 1 - wr
        avg_w  = sum(wins)   / len(wins)   if wins   else 0
        avg_l  = sum(losses) / len(losses) if losses else 0
        return round(wr * avg_w + lr * avg_l, 4)

    @staticmethod
    def calmar_ratio(
        annualised_return: float,
        max_drawdown_pct: float,
    ) -> float:
        """Annualised return divided by max drawdown."""
        if max_drawdown_pct == 0:
            return 0.0
        return round(annualised_return / max_drawdown_pct, 4)

    @staticmethod
    def r_multiple(
        entry_price: float,
        exit_price: float,
        stop_loss: float,
        order_type: str,
    ) -> float:
        """
        R-multiple: how many R (risk units) was won/lost.
        R = distance from entry to stop loss.
        A 2R trade means profit was 2x the initial risk.
        """
        if not stop_loss or stop_loss == entry_price:
            return 0.0
        r       = abs(entry_price - stop_loss)
        outcome = exit_price - entry_price
        if order_type == 'sell':
            outcome = -outcome
        return round(outcome / r, 2) if r > 0 else 0.0
    

class PipAwareRiskCalculator:
    """
    Extends the existing RiskCalculator with pip-based methods.
 
    Drop-in addition — existing code is unchanged.
    New code should use this class for pip/RRR-aware calculations.
 
    Usage:
        calc = PipAwareRiskCalculator(
            account_balance=10000,
            risk_percent=1.0,
            rrr=2.0,
        )
        setup = calc.build_setup('XAUUSD', 'buy', entry=2350.0, sl_pips=20)
        if setup:
            # setup.sl_price, setup.tp_price, setup.lot_size all ready
            broker.place_order(...)
    """
 
    def __init__(
        self,
        account_balance: float,
        risk_percent:    float = 1.0,
        rrr:             float = 2.0,
    ):
        self.account_balance = float(account_balance)
        self.risk_percent    = float(risk_percent)
        self.rrr             = float(rrr)
        self._rm = _RiskManager(
            account_balance = account_balance,
            risk_percent    = risk_percent,
            rrr             = rrr,
        )
 
    def build_setup(
        self,
        symbol:      str,
        order_type:  str,
        entry:       float,
        sl_pips:     float,
        rrr:         float = None,
        risk_percent:float = None,
    ):
        """
        Build a complete validated TradeSetup from pip inputs.
        Returns TradeSetup or None if validation fails.
        See utils.risk_manager.RiskManager.build_trade_setup() for full docs.
        """
        return self._rm.build_trade_setup(
            symbol       = symbol,
            order_type   = order_type,
            entry        = entry,
            sl_pips      = sl_pips,
            rrr          = rrr,
            risk_percent = risk_percent,
        )
 
    def validate(
        self,
        symbol:      str,
        order_type:  str,
        entry:       float,
        sl:          float,
        tp:          float,
        lot_size:    float = None,
        enforce_rrr: bool  = True,
    ):
        """
        Validate an existing signal's SL/TP prices.
        Returns ValidationResult — check .valid.
        """
        return self._rm.validate_trade(
            symbol      = symbol,
            order_type  = order_type,
            entry       = entry,
            sl          = sl,
            tp          = tp,
            lot_size    = lot_size,
            enforce_rrr = enforce_rrr,
        )
 
    def enforce_rrr(
        self,
        symbol:      str,
        order_type:  str,
        entry:       float,
        sl_price:    float,
        rrr:         float = None,
    ) -> tuple:
        """
        Recalculate TP from SL × RRR — ignores signal's original TP.
        Returns (sl_price, tp_price, sl_pips, tp_pips).
        """
        return self._rm.enforce_rrr_on_signal(
            symbol, order_type, entry, sl_price, rrr
        )
 
    def lot_size(
        self,
        symbol:   str,
        sl_pips:  float,
        risk_pct: float = None,
    ) -> float:
        """Calculate lot size using pip-based formula."""
        return _calculate_lot_size(
            account_balance = self.account_balance,
            risk_percent    = risk_pct if risk_pct is not None else self.risk_percent,
            sl_pips         = sl_pips,
            symbol          = symbol,
        )
 
    def pips(self, symbol: str, price_distance: float) -> float:
        """Convert price distance to pips."""
        return _price_to_pips(symbol, price_distance)
 
    def pip_size(self, symbol: str) -> float:
        """Return pip size for a symbol."""
        return _get_pip_size(symbol)
 
    def profit_pips(
        self,
        symbol:      str,
        entry:       float,
        exit_price:  float,
        order_type:  str,
    ) -> float:
        """Calculate profit/loss in pips for a closed trade."""
        return _profit_in_pips(symbol, entry, exit_price, order_type)
 
    def achieved_rrr(
        self,
        symbol:      str,
        entry:       float,
        exit_price:  float,
        sl_price:    float,
        order_type:  str,
    ) -> float:
        """Return the actual RRR achieved on a closed trade."""
        return _actual_rrr(symbol, entry, exit_price, sl_price, order_type)
 
    @staticmethod
    def from_bot(bot) -> 'PipAwareRiskCalculator':
        """
        Build a PipAwareRiskCalculator from a TradingBot instance.
        Reads balance from linked TradingAccount and risk settings from bot.
        """
        balance  = float(
            getattr(bot.trading_account, 'balance', 10000) or 10000
        )
        settings = getattr(bot, 'risk_settings', {}) or {}
        risk_pct = float(settings.get('risk_percent', 1.0))
        rrr      = float(settings.get('risk_reward_ratio', 2.0))
        return PipAwareRiskCalculator(balance, risk_pct, rrr)
    
    
 


