# ============================================================
# MarketData (OHLCV candles) and LiveTick models
# ============================================================
import uuid
from django.db import models
from utils.constants import Timeframe, Broker


class MarketData(models.Model):
    """
    OHLCV candlestick data for a symbol/timeframe combination.
    This table is the backbone of backtesting and indicator calculation.

    Indexed heavily for time-series queries:
        WHERE symbol = 'EUR_USD' AND timeframe = 'H1'
        AND timestamp BETWEEN '2024-01-01' AND '2024-06-01'
        ORDER BY timestamp ASC

    Uses a composite unique constraint to prevent duplicate candles.
    """
    id          = models.BigAutoField(primary_key=True)

    # Instrument
    symbol      = models.CharField(max_length=20, db_index=True)
    timeframe   = models.CharField(max_length=5, choices=Timeframe.choices)
    broker      = models.CharField(
        max_length=30, choices=Broker.choices,
        default=Broker.OANDA
    )

    # Candle data
    timestamp   = models.DateTimeField(db_index=True)
    open        = models.DecimalField(max_digits=18, decimal_places=6)
    high        = models.DecimalField(max_digits=18, decimal_places=6)
    low         = models.DecimalField(max_digits=18, decimal_places=6)
    close       = models.DecimalField(max_digits=18, decimal_places=6)
    volume      = models.BigIntegerField(default=0)

    # Bid/Ask spread data (available from OANDA)
    bid_open    = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    bid_close   = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    ask_open    = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    ask_close   = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)

    # Candle quality flags
    is_complete = models.BooleanField(default=True)   # False = forming candle

    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table    = 'market_data_ohlcv'
        ordering    = ['-timestamp']
        unique_together = [('symbol', 'timeframe', 'broker', 'timestamp')]
        indexes = [
            # Primary query pattern: symbol + timeframe + time range
            models.Index(fields=['symbol', 'timeframe', 'timestamp']),
            # For broker-specific queries
            models.Index(fields=['broker', 'symbol', 'timeframe']),
            # Latest candle per symbol
            models.Index(fields=['symbol', '-timestamp']),
        ]
        verbose_name        = 'Market Data (OHLCV)'
        verbose_name_plural = 'Market Data (OHLCV)'

    def __str__(self):
        return (
            f"{self.symbol} {self.timeframe} @ {self.timestamp:%Y-%m-%d %H:%M} "
            f"O:{self.open} H:{self.high} L:{self.low} C:{self.close}"
        )

    @property
    def mid_price(self) -> float:
        return float((self.high + self.low) / 2)

    @property
    def candle_range(self) -> float:
        return float(self.high - self.low)


class LiveTick(models.Model):
    """
    Real-time tick data (bid/ask) from the broker stream.
    Used by the trading engine for live signal checks.
    High-frequency — rows are pruned older than 24h by a Celery task.
    """
    id          = models.BigAutoField(primary_key=True)
    symbol      = models.CharField(max_length=20, db_index=True)
    broker      = models.CharField(max_length=30, choices=Broker.choices)

    bid         = models.DecimalField(max_digits=18, decimal_places=6)
    ask         = models.DecimalField(max_digits=18, decimal_places=6)
    spread      = models.DecimalField(max_digits=10, decimal_places=6)

    timestamp   = models.DateTimeField(db_index=True)

    class Meta:
        db_table    = 'market_data_livetick'
        ordering    = ['-timestamp']
        indexes     = [
            models.Index(fields=['symbol', 'timestamp']),
            models.Index(fields=['broker', 'symbol', '-timestamp']),
        ]
        verbose_name        = 'Live Tick'
        verbose_name_plural = 'Live Ticks'

    def __str__(self):
        return f"{self.symbol} bid={self.bid} ask={self.ask} @ {self.timestamp}"

    @property
    def mid(self) -> float:
        return float((self.bid + self.ask) / 2)


class DataFetchLog(models.Model):
    """
    Tracks data fetch operations (what was fetched, when, success/fail).
    Prevents duplicate fetches and helps debug data gaps.
    """
    id          = models.BigAutoField(primary_key=True)
    symbol      = models.CharField(max_length=20)
    timeframe   = models.CharField(max_length=5)
    broker      = models.CharField(max_length=30)
    source      = models.CharField(
        max_length=30,
        choices=[('oanda', 'OANDA'), ('mt5', 'MT5'), ('alpha_vantage', 'AlphaVantage')],
        default='oanda'
    )

    fetch_from  = models.DateTimeField()
    fetch_to    = models.DateTimeField()
    candles_fetched = models.PositiveIntegerField(default=0)

    success     = models.BooleanField(default=True)
    error_msg   = models.TextField(blank=True)

    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table    = 'market_data_fetchlog'
        ordering    = ['-created_at']
        indexes     = [
            models.Index(fields=['symbol', 'timeframe', 'broker']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        status = '✓' if self.success else '✗'
        return (
            f"{status} {self.symbol}/{self.timeframe} "
            f"[{self.fetch_from:%Y-%m-%d} → {self.fetch_to:%Y-%m-%d}] "
            f"{self.candles_fetched} candles"
        )