# ============================================================
# Central dispatcher — routes data requests to the right broker
# ============================================================
import logging
from typing import List, Dict, Optional
from django.conf import settings

logger = logging.getLogger('market_data')


class FeedManager:
    """
    Routes candle fetch requests to the correct data source.

    Priority order:
      1. OANDA      (default, best for Linux servers)
      2. AlphaVantage (fallback when no broker account configured)
      3. MT5         (Windows only)

    All methods return raw list-of-dicts.
    Normalisation happens in CandleNormalizer.
    """

    @staticmethod
    def fetch_candles(
        symbol: str,
        timeframe: str,
        count: int = 500,
        broker: str = 'oanda',
        **kwargs,
    ) -> List[Dict]:
        """
        Fetch OHLCV candles from the specified broker.
        Falls back to AlphaVantage if broker fetch fails.
        """
        symbol = symbol.upper().replace('/', '_').replace('-', '_')

        try:
            if broker in ('oanda', 'demo'):
                return FeedManager._fetch_oanda(symbol, timeframe, count)
            elif broker == 'metatrader5':
                return FeedManager._fetch_mt5(symbol, timeframe, count)
            elif broker == 'alpha_vantage':
                return FeedManager._fetch_alphavantage(symbol, timeframe, count)
            else:
                logger.warning(f"Unknown broker '{broker}', falling back to OANDA")
                return FeedManager._fetch_oanda(symbol, timeframe, count)

        except Exception as e:
            logger.error(f"Primary fetch failed ({broker}): {e} — trying AlphaVantage fallback")
            try:
                return FeedManager._fetch_alphavantage(symbol, timeframe, count)
            except Exception as e2:
                logger.error(f"AlphaVantage fallback also failed: {e2}")
                return []

    @staticmethod
    def fetch_live_price(symbol: str, broker: str = 'oanda') -> Optional[Dict]:
        """Return current bid/ask for a symbol."""
        try:
            if broker in ('oanda', 'demo'):
                from services.data_feed.oanda_feed import OandaFeed
                return OandaFeed().get_price(symbol)
            else:
                from services.data_feed.oanda_feed import OandaFeed
                return OandaFeed().get_price(symbol)
        except Exception as e:
            logger.error(f"Live price fetch failed for {symbol}: {e}")
            return None

    # ── Private fetchers ──────────────────────────────────────
    @staticmethod
    def _fetch_oanda(symbol: str, timeframe: str, count: int) -> List[Dict]:
        from services.data_feed.oanda_feed import OandaFeed
        feed = OandaFeed()
        return feed.fetch_candles(symbol, timeframe, count)

    @staticmethod
    def _fetch_mt5(symbol: str, timeframe: str, count: int) -> List[Dict]:
        from services.data_feed.mt5_feed import MT5Feed
        # MT5 uses EURUSD format (no underscore)
        mt5_symbol = symbol.replace('_', '')
        feed = MT5Feed()
        return feed.fetch_candles(mt5_symbol, timeframe, count)

    @staticmethod
    def _fetch_alphavantage(symbol: str, timeframe: str, count: int) -> List[Dict]:
        from services.broker_api.alpha_vantage import AlphaVantageFeed
        # AlphaVantage uses EURUSD format
        av_symbol = symbol.replace('_', '')
        feed = AlphaVantageFeed()
        return feed.fetch_candles(av_symbol, timeframe, count)