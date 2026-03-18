# ============================================================
# Abstract base class all broker connectors must implement
# ============================================================
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from decimal import Decimal


@dataclass
class OrderRequest:
    """Standardised order request passed to any broker."""
    symbol:      str
    order_type:  str          # 'buy' | 'sell'
    units:       int          # positive = buy, negative = sell (OANDA style)
    lot_size:    float = 0.1
    stop_loss:   Optional[float] = None
    take_profit: Optional[float] = None
    comment:     str = ''
    magic:       int = 0      # MT5 magic number


@dataclass
class OrderResult:
    """Standardised result returned by any broker after order placement."""
    success:       bool
    order_id:      str = ''
    trade_id:      str = ''
    fill_price:    float = 0.0
    units_filled:  int = 0
    error_message: str = ''
    raw_response:  dict = field(default_factory=dict)


@dataclass
class AccountInfo:
    """Standardised account summary from any broker."""
    account_id: str
    balance:    float
    equity:     float
    margin_used:  float
    margin_free:  float
    currency:   str
    leverage:   int = 50
    raw:        dict = field(default_factory=dict)


class BaseBroker(ABC):
    """
    Abstract base class for all broker API connectors.
    Every broker (OANDA, MT5, etc.) must implement these methods.
    """

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection / authenticate. Returns True on success."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Clean up connection resources."""
        ...

    @abstractmethod
    def get_account_info(self) -> dict:
        """Return raw account dict with at least: balance, equity, currency."""
        ...

    @abstractmethod
    def get_price(self, symbol: str) -> dict:
        """Return current bid/ask dict for a symbol."""
        ...

    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResult:
        """Place a market order and return the result."""
        ...

    @abstractmethod
    def close_trade(self, trade_id: str, units: Optional[int] = None) -> OrderResult:
        """Close an open trade fully or partially."""
        ...

    @abstractmethod
    def get_open_trades(self) -> list:
        """Return list of all open trade dicts."""
        ...

    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str,
                    count: int = 200) -> list:
        """Return list of OHLCV dicts for the given symbol/timeframe."""
        ...

    def is_market_open(self, symbol: str) -> bool:
        """Default implementation — override per broker if needed."""
        from datetime import datetime, timezone as tz
        now = datetime.now(tz.utc)
        # Forex market closed Sat 22:00 UTC → Sun 22:00 UTC
        if now.weekday() == 5:   # Saturday
            return now.hour < 22
        if now.weekday() == 6:   # Sunday
            return now.hour >= 22
        return True