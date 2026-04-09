# ============================================================
# Normalised data structures shared by all broker connectors.
# Import these in base.py, oanda_service.py, mt5_service.py.
# ============================================================
from dataclasses import dataclass, field
from typing import Optional, Any, Dict


@dataclass
class AccountInfo:
    account_id:    str
    broker:        str
    balance:       float
    equity:        float
    # Ensure these have explicit float defaults to satisfy assertions
    margin:        float = 0.0
    free_margin:   float = 0.0
    margin_level:  float = 0.0   
    currency:      str   = 'USD'
    leverage:      int   = 100
    is_live:       bool  = False  
    # Use the typing Dict for the hint
    extra:         Dict[str, Any] = field(default_factory=dict)

    @property
    def is_demo(self) -> bool:
        return not self.is_live


@dataclass
class PositionInfo:
    """Normalised open trade/position."""
    ticket:        str
    symbol:        str
    order_type:    str           # 'buy' | 'sell'
    volume:        float         # lot size e.g. 0.10
    entry_price:   float
    current_price: float
    stop_loss:     Optional[float] = None
    take_profit:   Optional[float] = None
    profit:        float         = 0.0   # unrealised P&L in account currency
    profit_pips:   float         = 0.0   # calculated by pip engine (Phase 2)
    open_time:     Optional[str] = None  # ISO 8601
    comment:       str           = ''
    magic:         int           = 0


@dataclass
class OrderResult:
    """
    Result returned by place_order() and close_position().
    Check result.success before using other fields.
    """
    success:       bool
    ticket:        Optional[str]   = None
    symbol:        str             = ''
    order_type:    str             = ''  # 'buy' | 'sell'
    volume:        float           = 0.0
    entry_price:   float           = 0.0
    stop_loss:     Optional[float] = None
    take_profit:   Optional[float] = None
    error:         str             = ''
    retcode:       int             = 0
    raw:           dict            = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return not self.success


@dataclass
class PriceInfo:
    """Live bid/ask quote for a symbol."""
    symbol:        str
    bid:           float
    ask:           float
    spread:        float          = 0.0
    timestamp:     Optional[str]  = None  # ISO 8601

    def __post_init__(self) -> None:
        # Derive spread automatically when callers only provide bid/ask.
        if self.spread == 0.0:
            self.spread = round(self.ask - self.bid, 5)

    @property
    def mid(self) -> float:
        return round((self.bid + self.ask) / 2, 5)

    @property
    def spread_pips(self) -> float:
        """
        Spread in pips — correct for JPY pairs and XAUUSD.
        Exact pip calculation delegated to Phase 2 pip engine.
        """
        if 'JPY' in self.symbol:
            return round(self.spread / 0.01, 1)
        elif 'XAU' in self.symbol or 'GOLD' in self.symbol:
            return round(self.spread / 0.1, 1)
        else:
            return round(self.spread / 0.0001, 1)
