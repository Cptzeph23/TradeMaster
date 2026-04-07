# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/services/broker_api/exceptions.py
# ============================================================


class BrokerError(Exception):
    """Base exception for all broker errors."""


class BrokerConnectionError(BrokerError):
    """Raised when broker connection fails or drops."""


class BrokerOrderError(BrokerError):
    """Raised when order placement or modification fails."""
    def __init__(self, message: str, retcode: int = 0):
        super().__init__(message)
        self.retcode = retcode


class BrokerAuthError(BrokerError):
    """Raised when API credentials are invalid or expired."""


class BrokerSymbolError(BrokerError):
    """Raised when a requested symbol is not available on the broker."""


class BrokerPositionError(BrokerError):
    """Raised when a position operation (close/modify) fails."""


class BrokerRateLimitError(BrokerError):
    """Raised when the broker API rate limit is exceeded."""