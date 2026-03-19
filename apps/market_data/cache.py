# ============================================================
# Redis-backed candle cache — avoids DB hits on every signal check
# ============================================================
import json
import logging
import pandas as pd
from typing import Optional
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger('market_data')

# Cache TTL per timeframe (seconds)
CACHE_TTL = {
    'M1':  60,        # 1 minute
    'M5':  300,       # 5 minutes
    'M15': 900,
    'M30': 1800,
    'H1':  3600,      # 1 hour
    'H4':  14400,
    'D1':  86400,
    'W1':  604800,
}

DEFAULT_TTL = 3600


def _cache_key(symbol: str, timeframe: str, count: int) -> str:
    return f"candles:{symbol}:{timeframe}:{count}"


def get_cached_candles(
    symbol: str,
    timeframe: str,
    count: int = 500,
    broker: str = 'oanda',
) -> Optional[pd.DataFrame]:
    """
    Return candles as a DataFrame.
    Order of data sources:
      1. Redis cache (fastest — microseconds)
      2. PostgreSQL MarketData table (milliseconds)
      3. Live broker API fetch (seconds — updates cache + DB)

    Returns None if all sources fail.
    """
    key = _cache_key(symbol, timeframe, count)

    # ── 1. Try Redis cache ────────────────────────────────────
    cached = cache.get(key)
    if cached:
        try:
            df = _deserialize(cached)
            if df is not None and len(df) >= 10:
                logger.debug(f"Cache HIT: {key} ({len(df)} candles)")
                return df
        except Exception as e:
            logger.warning(f"Cache deserialise error for {key}: {e}")

    # ── 2. Try PostgreSQL ─────────────────────────────────────
    df = _load_from_db(symbol, timeframe, count, broker)
    if df is not None and len(df) >= 10:
        logger.debug(f"DB HIT: {symbol}/{timeframe} ({len(df)} candles)")
        _set_cache(key, df, timeframe)
        return df

    # ── 3. Fetch from broker API ──────────────────────────────
    df = _fetch_from_broker(symbol, timeframe, count, broker)
    if df is not None and not df.empty:
        logger.info(f"BROKER FETCH: {symbol}/{timeframe} ({len(df)} candles)")
        _save_to_db(df, symbol, timeframe, broker)
        _set_cache(key, df, timeframe)
        return df

    logger.warning(f"No candle data available for {symbol}/{timeframe}")
    return None


def invalidate_cache(symbol: str, timeframe: str, count: int = 500):
    """Force-expire cached candles for a symbol/timeframe."""
    key = _cache_key(symbol, timeframe, count)
    cache.delete(key)
    logger.debug(f"Cache invalidated: {key}")


def _set_cache(key: str, df: pd.DataFrame, timeframe: str):
    ttl = CACHE_TTL.get(timeframe, DEFAULT_TTL)
    try:
        cache.set(key, _serialize(df), timeout=ttl)
    except Exception as e:
        logger.warning(f"Cache set failed for {key}: {e}")


def _serialize(df: pd.DataFrame) -> str:
    """Serialise DataFrame to JSON string for Redis storage."""
    df_copy = df.copy()
    df_copy.index = df_copy.index.astype(str)
    return df_copy.to_json(orient='split', date_format='iso')


def _deserialize(data: str) -> Optional[pd.DataFrame]:
    """Deserialise JSON string back to DataFrame."""
    df = pd.read_json(data, orient='split')
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        df = df.set_index('timestamp')
    else:
        df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = 'timestamp'
    return df.sort_index()


def _load_from_db(
    symbol: str, timeframe: str, count: int, broker: str
) -> Optional[pd.DataFrame]:
    """Load most recent N candles from PostgreSQL."""
    try:
        from apps.market_data.models import MarketData
        qs = (
            MarketData.objects
            .filter(symbol=symbol, timeframe=timeframe, broker=broker)
            .order_by('-timestamp')
            [:count]
            .values('timestamp', 'open', 'high', 'low', 'close', 'volume')
        )
        if not qs:
            return None

        df = pd.DataFrame(list(qs))
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        df = df.set_index('timestamp').sort_index()

        for col in ('open', 'high', 'low', 'close'):
            df[col] = df[col].astype(float)
        df['volume'] = df['volume'].astype(int)

        return df

    except Exception as e:
        logger.error(f"DB load failed for {symbol}/{timeframe}: {e}")
        return None


def _fetch_from_broker(
    symbol: str, timeframe: str, count: int, broker: str
) -> Optional[pd.DataFrame]:
    """Fetch fresh candles from the broker API and normalise."""
    try:
        from services.data_feed.feed_manager import FeedManager
        from services.data_feed.normalizer import CandleNormalizer

        raw = FeedManager.fetch_candles(
            symbol=symbol,
            timeframe=timeframe,
            count=count,
            broker=broker,
        )
        if not raw:
            return None
        return CandleNormalizer.normalize(raw, symbol=symbol, timeframe=timeframe)

    except Exception as e:
        logger.error(f"Broker fetch failed for {symbol}/{timeframe}: {e}")
        return None


def _save_to_db(
    df: pd.DataFrame, symbol: str, timeframe: str, broker: str
):
    """Bulk-upsert candles into PostgreSQL, ignoring duplicates."""
    try:
        from apps.market_data.models import MarketData
        from services.data_feed.normalizer import CandleNormalizer

        records = CandleNormalizer.to_db_records(df, symbol, timeframe, broker)
        objs = [MarketData(**r) for r in records]

        # ignore_conflicts=True skips duplicate (symbol,timeframe,broker,timestamp)
        MarketData.objects.bulk_create(objs, ignore_conflicts=True, batch_size=500)
        logger.debug(f"Saved {len(objs)} candles to DB for {symbol}/{timeframe}")

    except Exception as e:
        logger.error(f"DB save failed for {symbol}/{timeframe}: {e}")