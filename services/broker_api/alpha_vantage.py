# ============================================================
# AlphaVantage market data feed — free tier fallback
# ============================================================
import logging
import requests
from typing import List, Dict, Optional
from django.conf import settings

logger = logging.getLogger('market_data')


class AlphaVantageFeed:
    """
    AlphaVantage REST API data feed.
    Free tier: 25 requests/day, 5 requests/minute.
    Best used as a fallback when no broker account is configured.

    Supports FX_INTRADAY (M1–H1) and FX_DAILY for D1+.
    Symbol format: 'EURUSD' (no underscore or slash).
    """

    BASE_URL = 'https://www.alphavantage.co/query'

    # Map internal timeframes to AlphaVantage interval strings
    INTRADAY_MAP = {
        'M1':  '1min',
        'M5':  '5min',
        'M15': '15min',
        'M30': '30min',
        'H1':  '60min',
    }

    def __init__(self):
        self.api_key = settings.ALPHA_VANTAGE_API_KEY

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 500,
    ) -> List[Dict]:
        """
        Fetch OHLCV candles from AlphaVantage.
        Automatically selects FX_INTRADAY or FX_DAILY based on timeframe.
        """
        if not self.api_key:
            logger.warning("ALPHA_VANTAGE_API_KEY not configured")
            return []

        # AlphaVantage needs two separate currency codes
        symbol_clean = symbol.replace('_', '').replace('/', '').upper()
        if len(symbol_clean) != 6:
            logger.error(f"Cannot parse symbol '{symbol}' for AlphaVantage")
            return []

        from_currency = symbol_clean[:3]
        to_currency   = symbol_clean[3:]

        try:
            if timeframe in self.INTRADAY_MAP:
                return self._fetch_intraday(
                    from_currency, to_currency, timeframe, count
                )
            else:
                return self._fetch_daily(from_currency, to_currency, count)

        except Exception as e:
            logger.error(f"AlphaVantage fetch failed for {symbol}/{timeframe}: {e}")
            return []

    def _fetch_intraday(
        self,
        from_ccy: str,
        to_ccy: str,
        timeframe: str,
        count: int,
    ) -> List[Dict]:
        interval = self.INTRADAY_MAP[timeframe]
        params = {
            'function':      'FX_INTRADAY',
            'from_symbol':   from_ccy,
            'to_symbol':     to_ccy,
            'interval':      interval,
            'outputsize':    'full' if count > 100 else 'compact',
            'apikey':        self.api_key,
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        key = f"Time Series FX ({interval})"
        if key not in data:
            error = data.get('Note') or data.get('Information') or str(data)
            logger.warning(f"AlphaVantage intraday no data: {error}")
            return []

        return self._parse_timeseries(data[key], count)

    def _fetch_daily(
        self,
        from_ccy: str,
        to_ccy: str,
        count: int,
    ) -> List[Dict]:
        params = {
            'function':    'FX_DAILY',
            'from_symbol': from_ccy,
            'to_symbol':   to_ccy,
            'outputsize':  'full' if count > 100 else 'compact',
            'apikey':      self.api_key,
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        key = 'Time Series FX (Daily)'
        if key not in data:
            error = data.get('Note') or data.get('Information') or str(data)
            logger.warning(f"AlphaVantage daily no data: {error}")
            return []

        return self._parse_timeseries(data[key], count)

    @staticmethod
    def _parse_timeseries(series: dict, count: int) -> List[Dict]:
        """Convert AlphaVantage time series dict to normalised list."""
        candles = []
        for ts_str, values in sorted(series.items(), reverse=True)[:count]:
            try:
                candles.append({
                    'timestamp': ts_str,
                    'open':      float(values.get('1. open',  0)),
                    'high':      float(values.get('2. high',  0)),
                    'low':       float(values.get('3. low',   0)),
                    'close':     float(values.get('4. close', 0)),
                    'volume':    0,   # AV forex doesn't provide volume
                })
            except (ValueError, KeyError):
                continue
        return list(reversed(candles))   # oldest first