# ============================================================
# RRR enforcement, SL/TP validation, trade pre-flight checks
# ============================================================
import logging
from dataclasses import dataclass, field
from typing import Optional, List

from utils.pip_calculator import (
    get_pip_size, price_to_pips, pips_to_price,
    sl_price_from_pips, tp_price_from_pips,
    tp_from_sl_and_rrr, calculate_lot_size,
)
from utils.constants import (
    SL_PIPS_MAX, SL_PIPS_MIN, SL_PIPS_IDEAL,
    DEFAULT_RISK_PERCENT, MAX_RISK_PERCENT,
    SYMBOL_CONFIG,
)

logger = logging.getLogger('trading.risk_manager')


# ── Result dataclasses ────────────────────────────────────────

@dataclass
class ValidationResult:
    """
    Result of validate_trade().
    Check .valid before using any other field.
    """
    valid:        bool
    errors:       List[str]         = field(default_factory=list)
    warnings:     List[str]         = field(default_factory=list)
    sl_pips:      float             = 0.0
    tp_pips:      float             = 0.0
    rrr:          float             = 0.0
    lot_size:     float             = 0.0
    risk_amount:  float             = 0.0
    sl_price:     Optional[float]   = None
    tp_price:     Optional[float]   = None

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    @property
    def summary(self) -> str:
        lines = []
        if self.valid:
            lines.append(
                f"✅ Valid | SL={self.sl_pips}p TP={self.tp_pips}p "
                f"RRR=1:{self.rrr} Lot={self.lot_size} Risk=${self.risk_amount:.2f}"
            )
        else:
            lines.append(f"❌ Invalid: {'; '.join(self.errors)}")
        if self.warnings:
            lines.append(f"⚠ {'; '.join(self.warnings)}")
        return ' | '.join(lines)


@dataclass
class TradeSetup:
    """
    A fully calculated, validated trade setup ready for execution.
    Built by RiskManager.build_trade_setup().
    """
    symbol:       str
    order_type:   str           # 'buy' | 'sell'
    entry_price:  float
    sl_price:     float
    tp_price:     float
    sl_pips:      float
    tp_pips:      float
    rrr:          float
    lot_size:     float
    risk_percent: float
    risk_amount:  float         # in account currency
    account_balance: float
    warnings:     List[str]     = field(default_factory=list)

    @property
    def rrr_label(self) -> str:
        return f"1:{self.rrr}"

    def to_dict(self) -> dict:
        return {
            'symbol':          self.symbol,
            'order_type':      self.order_type,
            'entry_price':     self.entry_price,
            'sl_price':        self.sl_price,
            'tp_price':        self.tp_price,
            'sl_pips':         self.sl_pips,
            'tp_pips':         self.tp_pips,
            'rrr':             self.rrr,
            'rrr_label':       self.rrr_label,
            'lot_size':        self.lot_size,
            'risk_percent':    self.risk_percent,
            'risk_amount':     round(self.risk_amount, 2),
            'account_balance': self.account_balance,
        }


# ── Main class ────────────────────────────────────────────────

class RiskManager:
    """
    Enforces RRR, pip constraints, and lot sizing rules
    before any order is placed.

    Core rules (client requirements):
      1. SL must be between SL_PIPS_MIN and SL_PIPS_MAX (3–50 pips)
      2. TP is always derived from SL × RRR — never set independently
      3. Lot size is calculated from account balance and risk %
      4. Risk per trade capped at MAX_RISK_PERCENT (5%)

    Usage:
        rm = RiskManager(account_balance=10000, risk_percent=1.0, rrr=2.0)

        # From pip values (recommended)
        setup = rm.build_trade_setup('XAUUSD', 'buy', entry=2350.0, sl_pips=20)
        if setup:
            broker.place_order(setup.symbol, setup.order_type,
                               setup.lot_size, setup.sl_price, setup.tp_price)

        # From price levels (validates existing signal SL/TP)
        result = rm.validate_trade('EURUSD', 'buy',
                                   entry=1.1000, sl=1.0980, tp=1.1040)
        if result.valid:
            broker.place_order(...)
    """

    def __init__(
        self,
        account_balance: float,
        risk_percent:    float = DEFAULT_RISK_PERCENT,
        rrr:             float = 2.0,
        sl_pips_max:     int   = SL_PIPS_MAX,
        sl_pips_min:     int   = SL_PIPS_MIN,
    ):
        if risk_percent > MAX_RISK_PERCENT:
            logger.warning(
                f"risk_percent={risk_percent} exceeds MAX_RISK_PERCENT="
                f"{MAX_RISK_PERCENT} — clamping"
            )
            risk_percent = MAX_RISK_PERCENT

        self.account_balance = float(account_balance)
        self.risk_percent    = float(risk_percent)
        self.rrr             = float(rrr)
        self.sl_pips_max     = int(sl_pips_max)
        self.sl_pips_min     = int(sl_pips_min)

    # ── Primary API ───────────────────────────────────────────

    def build_trade_setup(
        self,
        symbol:      str,
        order_type:  str,
        entry:       float,
        sl_pips:     float,
        rrr:         Optional[float] = None,
        risk_percent:Optional[float] = None,
    ) -> Optional[TradeSetup]:
        """
        Build a complete, validated trade setup from pip inputs.

        This is the RECOMMENDED entry point — it enforces all rules
        and returns None if the setup is invalid.

        Args:
            symbol:       'XAUUSD', 'EURUSD', etc.
            order_type:   'buy' or 'sell'
            entry:        entry price
            sl_pips:      desired SL in pips (e.g. 20)
            rrr:          override instance RRR (optional)
            risk_percent: override instance risk % (optional)

        Returns:
            TradeSetup on success, None on validation failure
        """
        use_rrr  = float(rrr)          if rrr          is not None else self.rrr
        use_risk = float(risk_percent) if risk_percent  is not None else self.risk_percent

        # Validate SL pips
        result = ValidationResult(valid=True)
        self._check_sl_pips(sl_pips, result)
        if not result.valid:
            logger.warning(
                f"build_trade_setup rejected: {result.errors}"
            )
            return None

        # Calculate SL, TP, lot
        sl_price, tp_price, tp_pips = tp_from_sl_and_rrr(
            symbol, entry, sl_pips, use_rrr, order_type
        )
        lot_size    = calculate_lot_size(
            self.account_balance, use_risk, sl_pips, symbol
        )
        risk_amount = self.account_balance * (use_risk / 100.0)

        setup = TradeSetup(
            symbol          = symbol,
            order_type      = order_type.lower(),
            entry_price     = entry,
            sl_price        = sl_price,
            tp_price        = tp_price,
            sl_pips         = sl_pips,
            tp_pips         = tp_pips,
            rrr             = use_rrr,
            lot_size        = lot_size,
            risk_percent    = use_risk,
            risk_amount     = risk_amount,
            account_balance = self.account_balance,
            warnings        = result.warnings,
        )

        logger.info(
            f"TradeSetup: {order_type.upper()} {symbol} @ {entry} | "
            f"SL={sl_price}({sl_pips}p) TP={tp_price}({tp_pips}p) "
            f"RRR={use_rrr} Lot={lot_size}"
        )
        return setup

    def validate_trade(
        self,
        symbol:      str,
        order_type:  str,
        entry:       float,
        sl:          float,
        tp:          float,
        lot_size:    Optional[float] = None,
        enforce_rrr: bool            = True,
    ) -> ValidationResult:
        """
        Validate an existing signal's SL/TP prices against all rules.

        Used when a strategy plugin returns absolute SL/TP prices
        and we need to verify they comply with pip limits and RRR.

        Args:
            symbol:      trading symbol
            order_type:  'buy' or 'sell'
            entry:       entry price
            sl:          stop-loss price
            tp:          take-profit price
            lot_size:    optional lot to validate against min/max
            enforce_rrr: if True, reject trades with RRR < self.rrr

        Returns:
            ValidationResult — check .valid
        """
        result = ValidationResult(valid=True)

        # 1. Symbol supported?
        if symbol.upper().replace('_','') not in {
            k.replace('_','') for k in SYMBOL_CONFIG
        }:
            result.add_warning(
                f"Symbol '{symbol}' not in SYMBOL_CONFIG — "
                "pip calculations may be approximate"
            )

        # 2. SL in correct direction?
        ot = order_type.lower()
        if ot == 'buy' and sl >= entry:
            result.add_error(
                f"BUY trade: SL ({sl}) must be below entry ({entry})"
            )
        if ot == 'sell' and sl <= entry:
            result.add_error(
                f"SELL trade: SL ({sl}) must be above entry ({entry})"
            )

        # 3. TP in correct direction?
        if ot == 'buy' and tp <= entry:
            result.add_error(
                f"BUY trade: TP ({tp}) must be above entry ({entry})"
            )
        if ot == 'sell' and tp >= entry:
            result.add_error(
                f"SELL trade: TP ({tp}) must be below entry ({entry})"
            )

        if not result.valid:
            return result

        # 4. SL pips within range?
        sl_pips = price_to_pips(symbol, abs(entry - sl))
        self._check_sl_pips(sl_pips, result)
        result.sl_pips = sl_pips
        result.sl_price = sl

        # 5. RRR check
        tp_pips = price_to_pips(symbol, abs(entry - tp))
        result.tp_pips  = tp_pips
        result.tp_price = tp

        if sl_pips > 0:
            trade_rrr = round(tp_pips / sl_pips, 2)
            result.rrr = trade_rrr
            if enforce_rrr and trade_rrr < self.rrr:
                result.add_error(
                    f"RRR {trade_rrr:.1f} is below required {self.rrr} "
                    f"(SL={sl_pips}p TP={tp_pips}p)"
                )
        else:
            result.add_error("SL distance is zero — cannot calculate RRR")

        # 6. Lot size validation
        if lot_size is not None:
            cfg     = SYMBOL_CONFIG.get(symbol.upper().replace('_',''), {})
            min_lot = float(cfg.get('min_lot', 0.01))
            max_lot = float(cfg.get('max_lot', 100.0))
            if lot_size < min_lot:
                result.add_error(
                    f"Lot {lot_size} is below minimum {min_lot} for {symbol}"
                )
            elif lot_size > max_lot:
                result.add_error(
                    f"Lot {lot_size} exceeds maximum {max_lot} for {symbol}"
                )
            result.lot_size  = lot_size
            result.risk_amount = (
                self.account_balance * (self.risk_percent / 100.0)
            )

        return result

    def enforce_rrr_on_signal(
        self,
        symbol:      str,
        order_type:  str,
        entry:       float,
        sl_price:    float,
        rrr:         Optional[float] = None,
    ) -> tuple:
        """
        Given entry + SL price, compute a compliant TP price.

        Ignores any TP from the strategy signal and recalculates
        it from SL × RRR. This guarantees RRR is always enforced.

        Args:
            symbol:     trading symbol
            order_type: 'buy' | 'sell'
            entry:      entry price
            sl_price:   stop-loss price (absolute)
            rrr:        override RRR (default: self.rrr)

        Returns:
            (sl_price, tp_price, sl_pips, tp_pips)
        """
        use_rrr = float(rrr) if rrr is not None else self.rrr
        sl_dist = abs(entry - sl_price)
        sl_pips = price_to_pips(symbol, sl_dist)
        tp_pips = round(sl_pips * use_rrr, 1)
        tp_price = tp_price_from_pips(symbol, entry, tp_pips, order_type)

        logger.debug(
            f"enforce_rrr: {symbol} {order_type} entry={entry} "
            f"sl={sl_price}({sl_pips}p) → tp={tp_price}({tp_pips}p) "
            f"RRR=1:{use_rrr}"
        )
        return sl_price, tp_price, sl_pips, tp_pips

    def adjust_sl_to_max(
        self,
        symbol:      str,
        order_type:  str,
        entry:       float,
        sl_price:    float,
    ) -> float:
        """
        If SL exceeds SL_PIPS_MAX, pull it in to the maximum allowed.
        Returns the (possibly adjusted) SL price.
        """
        sl_pips = price_to_pips(symbol, abs(entry - sl_price))
        if sl_pips > self.sl_pips_max:
            logger.warning(
                f"SL {sl_pips}p exceeds max {self.sl_pips_max}p "
                f"for {symbol} — clamping to {self.sl_pips_max}p"
            )
            return sl_price_from_pips(
                symbol, entry, self.sl_pips_max, order_type
            )
        return sl_price

    # ── Internal helpers ──────────────────────────────────────

    def _check_sl_pips(self, sl_pips: float, result: ValidationResult):
        if sl_pips < self.sl_pips_min:
            result.add_error(
                f"SL {sl_pips}p is below minimum {self.sl_pips_min}p"
            )
        elif sl_pips > self.sl_pips_max:
            result.add_error(
                f"SL {sl_pips}p exceeds maximum {self.sl_pips_max}p"
            )
        elif sl_pips > SL_PIPS_IDEAL:
            result.add_warning(
                f"SL {sl_pips}p is above ideal {SL_PIPS_IDEAL}p — "
                "consider tightening"
            )