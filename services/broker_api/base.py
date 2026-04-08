# ============================================================
# BrokerInterface — abstract base class all brokers must implement
# ============================================================
from abc import ABC, abstractmethod
from typing import Optional, List
import logging

from .types import AccountInfo, PositionInfo, OrderResult, PriceInfo
from .exceptions import BrokerConnectionError

from abc import ABC, abstractmethod
from typing import Optional, List
import logging
 
from .types import AccountInfo, PositionInfo, OrderResult, PriceInfo
from .exceptions import BrokerConnectionError


logger = logging.getLogger('trading.broker')


class BrokerInterface(ABC):
    """
    Abstract base class for all broker connectors.

    Every broker (MT5, OANDA, etc.) MUST implement all
    @abstractmethod methods below. The trading engine only
    ever interacts with this interface — never with broker-
    specific code directly. This allows swapping brokers
    without changing any trading logic.

    Lifecycle:
        broker = OandaBroker(credentials)   # or MT5Broker
        broker.connect()
        info   = broker.get_account_info()
        price  = broker.get_price('EURUSD')
        order  = broker.place_order('EURUSD', 'buy', 0.1, ...)
        broker.disconnect()

    Context manager also supported:
        with OandaBroker(credentials) as broker:
            info = broker.get_account_info()
    """

    def __init__(self, credentials: dict):
        """
        Args:
            credentials: broker-specific dict.
                MT5:   {'login': 123456, 'password': 'x', 'server': 'ICMarkets-Demo'}
                OANDA: {'api_key': 'token', 'account_id': '101-001-x', 'environment': 'practice'}
        """
        self.credentials = credentials
        self.connected   = False
        self._logger     = logging.getLogger(
            f'trading.broker.{self.__class__.__name__}'
        )

    # ── Connection lifecycle ──────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection / verify credentials with the broker.
        Must set self.connected = True on success.
        Returns True on success, False on failure.
        Never raises — catch and return False instead.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """
        Close connection cleanly and release all resources.
        Must set self.connected = False.
        """

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Return True if the broker connection is currently active.
        Should do a lightweight liveness check, not a full reconnect.
        """

    # ── Account info ─────────────────────────────────────────

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """
        Return current account snapshot: balance, equity, margin.
        Raises BrokerConnectionError if not connected.
        """

    # ── Market data ───────────────────────────────────────────

    @abstractmethod
    def get_price(self, symbol: str) -> PriceInfo:
        """
        Return live bid/ask for a symbol.
        symbol: 'EURUSD', 'XAUUSD', 'GBPUSD', etc.
        Raises BrokerSymbolError if symbol unavailable.
        """

    @abstractmethod
    def get_candles(
        self,
        symbol:    str,
        timeframe: str,
        count:     int = 200,
    ) -> list:
        """
        Return OHLCV candle data as list of dicts.
        Each dict: {'time': str, 'open': float, 'high': float,
                    'low': float, 'close': float, 'volume': int}
        timeframe: 'M1','M5','M15','M30','H1','H4','D1'
        """

    # ── Order execution ───────────────────────────────────────

    @abstractmethod
    def place_order(
        self,
        symbol:      str,
        order_type:  str,
        volume:      float,
        stop_loss:   Optional[float] = None,
        take_profit: Optional[float] = None,
        comment:     str             = 'ForexBot',
        magic:       int             = 0,
    ) -> OrderResult:
        """
        Place a market order.

        Args:
            symbol:      e.g. 'EURUSD', 'XAUUSD'
            order_type:  'buy' or 'sell'
            volume:      lot size e.g. 0.10
            stop_loss:   absolute price level (not pips)
            take_profit: absolute price level (not pips)
            comment:     broker-visible comment string
            magic:       magic number for bot identification (MT5)

        Returns:
            OrderResult with success=True and ticket on success,
            or success=False and error message on failure.
        """

    @abstractmethod
    def close_position(
        self,
        ticket:  str,
        volume:  Optional[float] = None,
    ) -> OrderResult:
        """
        Close an open position.

        Args:
            ticket: position/trade ID from place_order result
            volume: lots to close; None = close entire position

        Returns OrderResult.
        """

    @abstractmethod
    def modify_position(
        self,
        ticket:      str,
        stop_loss:   Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """
        Modify SL and/or TP on an existing position.
        Returns True on success.
        """

    # ── Position queries ──────────────────────────────────────

    @abstractmethod
    def get_open_positions(
        self,
        symbol: Optional[str] = None,
    ) -> List[PositionInfo]:
        """
        Return all open positions.
        If symbol is provided, filter to that symbol only.
        Returns empty list (not None) when no positions found.
        """

    @abstractmethod
    def get_position(self, ticket: str) -> Optional[PositionInfo]:
        """
        Return a single position by ticket ID.
        Returns None if not found.
        """

    # ── Shared non-abstract helpers ───────────────────────────

    def reconnect(self, max_retries: int = 3) -> bool:
        """
        Attempt reconnection with exponential backoff.
        Called automatically by _ensure_connected().
        """
        import time
        for attempt in range(1, max_retries + 1):
            self._logger.info(
                f"Reconnect attempt {attempt}/{max_retries}"
            )
            try:
                if self.connect():
                    self._logger.info("Reconnected successfully")
                    return True
            except Exception as e:
                self._logger.warning(f"Reconnect attempt {attempt} failed: {e}")
            time.sleep(2 ** attempt)   # 2s, 4s, 8s
        self._logger.error(
            f"All {max_retries} reconnect attempts failed"
        )
        return False

    def _ensure_connected(self) -> None:
        """
        Internal guard — call at the start of any method that
        requires an active broker connection.
        Raises BrokerConnectionError if connection cannot be restored.
        """
        if not self.is_connected():
            self._logger.warning(
                "Broker not connected — attempting reconnect"
            )
            if not self.reconnect():
                raise BrokerConnectionError(
                    f"{self.__class__.__name__} is not connected "
                    f"and all reconnect attempts failed."
                )

    # ── Context manager ───────────────────────────────────────

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False   # don't suppress exceptions

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"connected={self.connected}>"
        )



class BrokerInterface(ABC):
    """
    Abstract base class for all broker connectors.
 
    Every broker (MT5, OANDA, etc.) must implement every
    @abstractmethod. This lets the trading engine swap brokers
    without touching any other code.
 
    Typical lifecycle:
        broker = OandaBroker(credentials)
        broker.connect()
        info  = broker.get_account_info()
        price = broker.get_price('EUR_USD')
        order = broker.place_order('EUR_USD', 'buy', 0.1, sl=1.08, tp=1.11)
        broker.disconnect()
 
    Or as context manager:
        with OandaBroker(credentials) as broker:
            info = broker.get_account_info()
    """
 
    def __init__(self, credentials: dict):
        """
        Args:
            credentials: broker-specific connection dict.
                OANDA: {'api_key': str, 'account_id': str, 'environment': str}
                MT5:   {'login': int, 'password': str, 'server': str}
        """
        self.credentials = credentials
        self.connected   = False
        self._logger     = logging.getLogger(
            f'trading.broker.{self.__class__.__name__}'
        )
 
    # ── Connection lifecycle ──────────────────────────────────
 
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the broker.
        Returns True on success, False on failure.
        Must set self.connected = True on success.
        """
 
    @abstractmethod
    def disconnect(self) -> None:
        """
        Close the connection and release all resources.
        Must set self.connected = False.
        """
 
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Return True if connection is currently active.
        Should do a lightweight live check, not just read self.connected.
        """
 
    # ── Account info ─────────────────────────────────────────
 
    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """
        Return current account snapshot: balance, equity, margin.
        Raises BrokerConnectionError if not connected.
        """
 
    # ── Market data ──────────────────────────────────────────
 
    @abstractmethod
    def get_price(self, symbol: str) -> PriceInfo:
        """
        Return live bid/ask for a symbol.
 
        Args:
            symbol: broker-native symbol string e.g. 'EUR_USD' or 'EURUSD'
 
        Returns:
            PriceInfo with bid, ask, spread, timestamp
        """
 
    @abstractmethod
    def get_candles(
        self,
        symbol:    str,
        timeframe: str,
        count:     int = 200,
    ) -> list:
        """
        Return OHLCV candle data.
 
        Args:
            symbol:    e.g. 'EUR_USD'
            timeframe: 'M1','M5','M15','M30','H1','H4','D1'
            count:     number of candles to return
 
        Returns:
            List of dicts:
            [{'time': ISO str, 'open': float, 'high': float,
              'low': float, 'close': float, 'volume': int}, ...]
        """
 
    # ── Order execution ──────────────────────────────────────
 
    @abstractmethod
    def place_order(
        self,
        symbol:      str,
        order_type:  str,
        volume:      float,
        stop_loss:   Optional[float] = None,
        take_profit: Optional[float] = None,
        comment:     str             = '',
        magic:       int             = 0,
    ) -> OrderResult:
        """
        Place a market order.
 
        Args:
            symbol:      trading symbol e.g. 'EURUSD' or 'EUR_USD'
            order_type:  'buy' or 'sell'
            volume:      lot size e.g. 0.10
            stop_loss:   absolute SL price (not pips) — Phase 2 converts
            take_profit: absolute TP price (not pips) — Phase 2 converts
            comment:     order comment/label
            magic:       magic number for EA identification (MT5)
 
        Returns:
            OrderResult — always check result.success before using ticket
        """
 
    @abstractmethod
    def close_position(
        self,
        ticket: str,
        volume: Optional[float] = None,
    ) -> OrderResult:
        """
        Close an open position.
 
        Args:
            ticket: broker position/trade ID
            volume: partial close volume; None = close full position
 
        Returns:
            OrderResult
        """
 
    @abstractmethod
    def modify_position(
        self,
        ticket:      str,
        stop_loss:   Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """
        Modify SL and/or TP on an existing open position.
 
        Returns True on success, False on failure.
        """
 
    # ── Position queries ─────────────────────────────────────
 
    @abstractmethod
    def get_open_positions(
        self,
        symbol: Optional[str] = None,
    ) -> List[PositionInfo]:
        """
        Return all open positions.
 
        Args:
            symbol: optional filter — return only positions for this symbol
 
        Returns:
            List of PositionInfo (empty list if none open)
        """
 
    @abstractmethod
    def get_position(self, ticket: str) -> Optional[PositionInfo]:
        """
        Return a single open position by ticket.
 
        Returns None if the position is not found.
        """
 
    # ── Shared non-abstract helpers ───────────────────────────
 
    def reconnect(self, max_retries: int = 3) -> bool:
        """
        Attempt to reconnect with exponential backoff.
        Called automatically by _ensure_connected().
        """
        import time
        for attempt in range(1, max_retries + 1):
            self._logger.info(
                f"Reconnect attempt {attempt}/{max_retries}…"
            )
            try:
                if self.connect():
                    self._logger.info("Reconnected successfully")
                    return True
            except Exception as e:
                self._logger.warning(f"Reconnect attempt {attempt} failed: {e}")
            time.sleep(2 ** attempt)   # 2s, 4s, 8s
        self._logger.error("All reconnect attempts exhausted")
        return False
 
    def _ensure_connected(self) -> None:
        """
        Internal guard — call at the start of every method that
        requires an active connection.
        Raises BrokerConnectionError if reconnect also fails.
        """
        if not self.is_connected():
            self._logger.warning(
                f"{self.__class__.__name__} not connected — attempting reconnect"
            )
            if not self.reconnect():
                raise BrokerConnectionError(
                    f"{self.__class__.__name__} is not connected "
                    "and all reconnect attempts failed."
                )
 
    # ── Context manager support ───────────────────────────────
 
    def __enter__(self):
        self.connect()
        return self
 
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False   # don't suppress exceptions
 
    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"connected={self.connected} "
            f"account={self.credentials.get('account_id', '?')}>"
        )