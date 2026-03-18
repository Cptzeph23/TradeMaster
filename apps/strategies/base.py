# ============================================================
# Abstract base class every strategy plugin must inherit from
# ============================================================
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


# ── Signal dataclass ─────────────────────────────────────────
@dataclass
class Signal:
    """
    Returned by every strategy's generate_signal() method.

    action:     'buy' | 'sell' | 'close' | 'hold'
    symbol:     forex pair e.g. 'EUR_USD'
    strength:   0.0–1.0  (1.0 = maximum conviction)
    stop_loss:  absolute price level (None = use risk module default)
    take_profit:absolute price level (None = use risk module default)
    indicators: snapshot of all indicator values at signal time
                stored in Trade.signal_data for analysis
    reason:     human-readable explanation — shown in bot logs
                and used by the NLP command interface
    """
    action:      str                        # 'buy' | 'sell' | 'close' | 'hold'
    symbol:      str
    strength:    float       = 1.0
    stop_loss:   Optional[float] = None
    take_profit: Optional[float] = None
    indicators:  dict        = field(default_factory=dict)
    reason:      str         = ''
    timeframe:   str         = 'H1'
    timestamp:   Optional[str] = None

    @property
    def is_entry(self) -> bool:
        return self.action in ('buy', 'sell')

    @property
    def is_exit(self) -> bool:
        return self.action == 'close'

    @property
    def is_hold(self) -> bool:
        return self.action == 'hold'

    def to_dict(self) -> dict:
        return {
            'action':      self.action,
            'symbol':      self.symbol,
            'strength':    self.strength,
            'stop_loss':   self.stop_loss,
            'take_profit': self.take_profit,
            'indicators':  self.indicators,
            'reason':      self.reason,
            'timeframe':   self.timeframe,
            'timestamp':   self.timestamp,
        }


# ── Base Strategy ─────────────────────────────────────────────
class BaseStrategy(ABC):
    """
    Abstract base class for all strategy plugins.

    Every strategy must implement:
        generate_signal(df, symbol, **kwargs) -> Signal

    Optionally override:
        validate_parameters()    — raise ValueError on bad config
        get_required_candles()   — minimum candles needed
        get_parameter_schema()   — JSON Schema for UI validation

    Parameters are passed as a dict at instantiation and stored
    in self.params. Access with self.p('key', default).
    """

    # Subclasses should declare these for the registry / UI
    name:        str = 'Base Strategy'
    version:     str = '1.0.0'
    description: str = ''
    author:      str = 'System'

    def __init__(self, parameters: dict = None):
        self.params = parameters or {}
        self.validate_parameters()

    def p(self, key: str, default=None):
        """Shorthand parameter accessor."""
        return self.params.get(key, default)

    # ── Must implement ────────────────────────────────────────
    @abstractmethod
    def generate_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        **kwargs,
    ) -> Signal:
        """
        Analyse the OHLCV DataFrame and return a Signal.

        df columns expected:
            timestamp, open, high, low, close, volume
            (all numeric, timestamp as DatetimeIndex or column)

        Must always return a Signal — never None.
        Return Signal(action='hold', ...) when no trade is triggered.
        """
        ...

    # ── May override ──────────────────────────────────────────
    def validate_parameters(self):
        """
        Validate self.params on instantiation.
        Raise ValueError with a clear message on invalid config.
        """
        pass

    def get_required_candles(self) -> int:
        """
        Minimum number of candles needed before a signal is valid.
        Strategy should return Signal(action='hold') if df is shorter.
        """
        return 200

    @classmethod
    def get_parameter_schema(cls) -> dict:
        """
        Return a JSON Schema dict describing valid parameters.
        Used by the frontend to render dynamic strategy config forms.
        """
        return {}

    @classmethod
    def get_default_parameters(cls) -> dict:
        """Return sensible default parameter values."""
        return {}

    # ── Helpers available to all strategies ───────────────────
    @staticmethod
    def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """
        Ensure the DataFrame has the correct column types and index.
        Call at the start of generate_signal().
        """
        df = df.copy()
        for col in ('open', 'high', 'low', 'close', 'volume'):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        if 'timestamp' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            df = df.set_index('timestamp').sort_index()

        df = df.dropna(subset=['open', 'high', 'low', 'close'])
        return df

    @staticmethod
    def crossover(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
        """
        Returns a boolean Series that is True on the bar where
        series_a crosses ABOVE series_b.
        """
        return (series_a > series_b) & (series_a.shift(1) <= series_b.shift(1))

    @staticmethod
    def crossunder(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
        """
        Returns a boolean Series that is True on the bar where
        series_a crosses BELOW series_b.
        """
        return (series_a < series_b) & (series_a.shift(1) >= series_b.shift(1))

    def __repr__(self):
        return f"<{self.__class__.__name__} params={self.params}>"