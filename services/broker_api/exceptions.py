# ============================================================
# Custom exceptions for broker API layer
# ============================================================


class BrokerException(Exception):
    """Base class for all broker errors."""
    def __init__(self, message: str, code: str = 'BROKER_ERROR', raw=None):
        super().__init__(message)
        self.message = message
        self.code    = code
        self.raw     = raw or {}

    def __str__(self):
        return f"[{self.code}] {self.message}"


class BrokerAuthError(BrokerException):
    """Invalid credentials or expired session."""
    def __init__(self, message='Authentication failed with broker.'):
        super().__init__(message, code='AUTH_ERROR')


class BrokerConnectionError(BrokerException):
    """Network or connectivity issue reaching the broker."""
    def __init__(self, message='Cannot connect to broker API.'):
        super().__init__(message, code='CONNECTION_ERROR')


class BrokerOrderError(BrokerException):
    """Order was rejected or failed at the broker level."""
    def __init__(self, message='Order rejected by broker.', raw=None):
        super().__init__(message, code='ORDER_ERROR', raw=raw)


class InsufficientMarginError(BrokerException):
    """Not enough free margin to place the order."""
    def __init__(self):
        super().__init__('Insufficient margin for this order.', code='MARGIN_ERROR')


class MarketClosedError(BrokerException):
    """Market is closed for the requested instrument."""
    def __init__(self, symbol=''):
        super().__init__(
            f"Market is closed for {symbol}." if symbol else "Market is closed.",
            code='MARKET_CLOSED'
        )


class InvalidSymbolError(BrokerException):
    """The requested symbol is not supported by this broker."""
    def __init__(self, symbol=''):
        super().__init__(
            f"Symbol '{symbol}' is not supported.", code='INVALID_SYMBOL'
        )


class RateLimitError(BrokerException):
    """Broker API rate limit exceeded."""
    def __init__(self):
        super().__init__('Broker API rate limit exceeded.', code='RATE_LIMIT')