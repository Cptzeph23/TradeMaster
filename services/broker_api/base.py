# ============================================================
# BrokerInterface — abstract base class all brokers must implement
# ============================================================
from abc import ABC, abstractmethod
import logging
from typing import List, Optional

from .exceptions import BrokerConnectionError
from .types import AccountInfo, OrderResult, PositionInfo, PriceInfo


logger = logging.getLogger('trading.broker')


class BrokerInterface(ABC):
    """
    Abstract base class for all broker connectors.

    Every broker (MT5, OANDA, etc.) must implement every
    @abstractmethod. This lets the trading engine swap brokers
    without touching any other code.
    """

    def __init__(self, credentials: dict):
        """
        Args:
            credentials: broker-specific connection dict.
                OANDA: {'api_key': str, 'account_id': str, 'environment': str}
                MT5:   {'login': int, 'password': str, 'server': str}
        """
        self.credentials = credentials
        self.connected = False
        self._logger = logging.getLogger(
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
        """Return live bid/ask for a symbol."""

    @abstractmethod
    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
    ) -> list:
        """
        Return OHLCV candle data.

        Returns:
            [{'time': ISO str, 'open': float, 'high': float,
              'low': float, 'close': float, 'volume': int}, ...]
        """

    # ── Order execution ──────────────────────────────────────

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = 'ForexBot',
        magic: int = 0,
    ) -> OrderResult:
        """Place a market order and return an OrderResult."""

    @abstractmethod
    def close_position(
        self,
        ticket: str,
        volume: Optional[float] = None,
    ) -> OrderResult:
        """Close an open position."""

    @abstractmethod
    def modify_position(
        self,
        ticket: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """Modify SL and/or TP on an existing open position."""

    # ── Position queries ─────────────────────────────────────

    @abstractmethod
    def get_open_positions(
        self,
        symbol: Optional[str] = None,
    ) -> List[PositionInfo]:
        """Return all open positions, optionally filtered by symbol."""

    @abstractmethod
    def get_position(self, ticket: str) -> Optional[PositionInfo]:
        """Return a single open position by ticket, or None if missing."""

    # ── Shared non-abstract helpers ───────────────────────────

    def reconnect(self, max_retries: int = 3) -> bool:
        """
        Attempt to reconnect with exponential backoff.
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
            except Exception as exc:
                self._logger.warning(
                    f"Reconnect attempt {attempt} failed: {exc}"
                )
            time.sleep(2 ** attempt)

        self._logger.error("All reconnect attempts exhausted")
        return False

    def _ensure_connected(self) -> None:
        """
        Internal guard for methods that require an active connection.
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
        return False

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"connected={self.connected} "
            f"account={self.credentials.get('account_id', '?')}>"
        )
