# ============================================================
# Normalises raw candle data from any broker into a standard
# pandas DataFrame used by all strategy plugins.
# ============================================================
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
import logging

logger = logging.getLogger('market_data')


class CandleNormalizer:
    """
    Converts raw candle dicts from any broker source into a
    clean, typed pandas DataFrame with a UTC DatetimeIndex.

    Expected input (list of dicts):
        [
          {
            'timestamp': '2024-01-01T00:00:00Z',  # ISO string or epoch
            'open':   1.09123,
            'high':   1.09456,
            'low':    1.09001,
            'close':  1.09234,
            'volume': 1234,
          },
          ...
        ]

    Output DataFrame columns:
        open, high, low, close, volume  (all float64)
        index: DatetimeIndex (UTC, sorted ascending)
    """

    REQUIRED_COLUMNS = ['open', 'high', 'low', 'close']
    NUMERIC_COLUMNS  = ['open', 'high', 'low', 'close', 'volume']

    @classmethod
    def normalize(
        cls,
        candles: List[Dict],
        symbol: str = '',
        timeframe: str = '',
        drop_incomplete: bool = True,
    ) -> pd.DataFrame:
        """
        Main entry point. Returns a clean DataFrame or empty DataFrame
        if input is empty / unparseable.
        """
        if not candles:
            logger.warning(f"normalize() called with empty candles list ({symbol}/{timeframe})")
            return pd.DataFrame()

        try:
            df = pd.DataFrame(candles)
            df = cls._parse_timestamp(df)
            df = cls._coerce_numeric(df)
            df = cls._validate_ohlc(df)
            df = cls._add_derived_columns(df)

            if drop_incomplete and 'is_complete' in df.columns:
                df = df[df['is_complete'] != False]  # noqa: E712

            df = df.sort_index()
            df = df[~df.index.duplicated(keep='last')]

            logger.debug(
                f"Normalized {len(df)} candles for {symbol}/{timeframe}"
            )
            return df

        except Exception as e:
            logger.error(f"Normalization failed for {symbol}/{timeframe}: {e}", exc_info=True)
            return pd.DataFrame()

    @classmethod
    def _parse_timestamp(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Find timestamp column, parse to UTC DatetimeIndex."""
        ts_candidates = ['timestamp', 'time', 'date', 'datetime', 't']
        ts_col = None
        for col in ts_candidates:
            if col in df.columns:
                ts_col = col
                break

        if ts_col is None:
            raise ValueError(
                f"No timestamp column found. Columns: {list(df.columns)}"
            )

        # Handle epoch integers (seconds)
        if pd.api.types.is_numeric_dtype(df[ts_col]):
            df[ts_col] = pd.to_datetime(df[ts_col], unit='s', utc=True)
        else:
            df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors='coerce')

        df = df.dropna(subset=[ts_col])
        df = df.set_index(ts_col)
        df.index.name = 'timestamp'
        return df

    @classmethod
    def _coerce_numeric(cls, df: pd.DataFrame) -> pd.DataFrame:
        for col in cls.NUMERIC_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        if 'volume' not in df.columns:
            df['volume'] = 0
        return df

    @classmethod
    def _validate_ohlc(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Drop rows with missing or clearly invalid OHLC data."""
        df = df.dropna(subset=cls.REQUIRED_COLUMNS)
        # Drop rows where high < low (data corruption)
        if 'high' in df.columns and 'low' in df.columns:
            df = df[df['high'] >= df['low']]
        # Drop rows with zero or negative prices
        df = df[(df['close'] > 0) & (df['open'] > 0)]
        return df

    @classmethod
    def _add_derived_columns(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Add useful derived columns for strategy use."""
        df['mid']    = (df['high'] + df['low']) / 2
        df['range']  = df['high'] - df['low']
        df['change'] = df['close'] - df['open']
        df['pct_change'] = df['change'] / df['open'] * 100
        return df

    @staticmethod
    def to_db_records(
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        broker: str = 'oanda',
    ) -> List[Dict]:
        """
        Convert normalised DataFrame back to a list of dicts
        suitable for bulk_create into MarketData model.
        """
        records = []
        for ts, row in df.iterrows():
            records.append({
                'symbol':    symbol,
                'timeframe': timeframe,
                'broker':    broker,
                'timestamp': ts,
                'open':      float(row['open']),
                'high':      float(row['high']),
                'low':       float(row['low']),
                'close':     float(row['close']),
                'volume':    int(row.get('volume', 0)),
            })
        return records