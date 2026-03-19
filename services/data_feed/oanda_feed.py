# ============================================================
# OANDA historical candle + live price feed
# ============================================================
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone
from django.conf import settings

logger = logging.getLogger('market_data')


class OandaFeed:
    """
    Dedicated OANDA data feed — wraps OandaBroker for market data only.
    Keeps data concerns separate from order execution concerns.
    """

    TF_MAP = {
        'M1': 'M1', 'M5': 'M5', 'M15': 'M15', 'M30': 'M30',
        'H1': 'H1', 'H4': 'H4', 'D1': 'D', 'W1': 'W', 'MN1': 'M',
    }

    def __init__(self):
        self._broker = None

    def _get_broker(self):
        if self._broker is None:
            from services.broker_api.oanda import OandaBroker
            self._broker = OandaBroker(
                api_key     = settings.OANDA_API_KEY,
                account_id  = settings.OANDA_ACCOUNT_ID,
                environment = settings.OANDA_ENVIRONMENT,
            )
        return self._broker

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 500,
    ) -> List[Dict]:
        """
        Fetch up to 5000 historical candles from OANDA.
        Handles pagination automatically for large requests.
        """
        if not settings.OANDA_API_KEY:
            logger.warning("OANDA_API_KEY not configured — returning empty candles")
            return []

        broker = self._get_broker()
        gran   = self.TF_MAP.get(timeframe, 'H1')

        # OANDA max per request = 5000
        all_candles = []
        remaining   = min(count, 5000)

        try:
            import oandapyV20.endpoints.instruments as instruments_ep

            params = {
                'granularity': gran,
                'count':       remaining,
                'price':       'M',    # Mid prices
            }
            r    = instruments_ep.InstrumentsCandles(symbol, params=params)
            resp = broker._client or broker.connect() and broker._client
            broker._ensure_connected()
            resp = broker._client.request(r)

            for c in resp.get('candles', []):
                if not c.get('complete', True):
                    continue
                mid = c.get('mid', {})
                all_candles.append({
                    'timestamp': c['time'],
                    'open':      float(mid.get('o', 0)),
                    'high':      float(mid.get('h', 0)),
                    'low':       float(mid.get('l', 0)),
                    'close':     float(mid.get('c', 0)),
                    'volume':    int(c.get('volume', 0)),
                })

            logger.info(
                f"OANDA fetched {len(all_candles)} candles "
                f"for {symbol}/{timeframe}"
            )
            return all_candles

        except Exception as e:
            logger.error(f"OandaFeed.fetch_candles failed: {e}", exc_info=True)
            return []

    def get_price(self, symbol: str) -> Optional[Dict]:
        """Return current bid/ask/mid for a symbol."""
        if not settings.OANDA_API_KEY:
            return None
        try:
            broker = self._get_broker()
            return broker.get_price(symbol)
        except Exception as e:
            logger.error(f"OandaFeed.get_price failed for {symbol}: {e}")
            return None

    def fetch_candles_range(
        self,
        symbol: str,
        timeframe: str,
        from_date: datetime,
        to_date: datetime,
    ) -> List[Dict]:
        """
        Fetch candles between two datetime objects.
        Used by the backtesting engine to load historical data.
        """
        if not settings.OANDA_API_KEY:
            return []

        try:
            import oandapyV20.endpoints.instruments as instruments_ep

            broker = self._get_broker()
            broker._ensure_connected()

            gran = self.TF_MAP.get(timeframe, 'H1')

            # OANDA expects RFC3339 format
            from_str = from_date.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            to_str   = to_date.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

            all_candles = []
            params = {
                'granularity': gran,
                'from':        from_str,
                'to':          to_str,
                'price':       'M',
                'count':       5000,
            }

            r    = instruments_ep.InstrumentsCandles(symbol, params=params)
            resp = broker._client.request(r)

            for c in resp.get('candles', []):
                mid = c.get('mid', {})
                all_candles.append({
                    'timestamp': c['time'],
                    'open':      float(mid.get('o', 0)),
                    'high':      float(mid.get('h', 0)),
                    'low':       float(mid.get('l', 0)),
                    'close':     float(mid.get('c', 0)),
                    'volume':    int(c.get('volume', 0)),
                })

            logger.info(
                f"OANDA range fetch: {symbol}/{timeframe} "
                f"{from_str}→{to_str} = {len(all_candles)} candles"
            )
            return all_candles

        except Exception as e:
            logger.error(f"OandaFeed.fetch_candles_range failed: {e}", exc_info=True)
            return []