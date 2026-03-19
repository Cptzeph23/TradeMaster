# ============================================================
# MetaTrader 5 historical data feed (Windows only)
# ============================================================
import logging
from typing import List, Dict
from django.conf import settings

logger = logging.getLogger('market_data')


class MT5Feed:
    """
    MT5 data feed wrapper.
    NOTE: MetaTrader5 Python library is Windows-only.
    On Linux, this class logs a warning and returns empty data.
    """

    def __init__(self):
        self._connected = False

    def _connect(self) -> bool:
        try:
            import MetaTrader5 as mt5
            result = mt5.initialize(
                login    = int(settings.MT5_LOGIN),
                password = settings.MT5_PASSWORD,
                server   = settings.MT5_SERVER,
            )
            if result:
                self._mt5 = mt5
                self._connected = True
            return result
        except ImportError:
            logger.warning(
                "MT5Feed: MetaTrader5 package not available on this platform. "
                "Use OANDA or AlphaVantage on Linux."
            )
            return False

    def fetch_candles(
        self, symbol: str, timeframe: str, count: int = 500
    ) -> List[Dict]:
        if not self._connect():
            return []

        tf_map = {
            'M1': self._mt5.TIMEFRAME_M1,  'M5': self._mt5.TIMEFRAME_M5,
            'M15': self._mt5.TIMEFRAME_M15, 'M30': self._mt5.TIMEFRAME_M30,
            'H1': self._mt5.TIMEFRAME_H1,   'H4': self._mt5.TIMEFRAME_H4,
            'D1': self._mt5.TIMEFRAME_D1,
        }
        tf    = tf_map.get(timeframe, self._mt5.TIMEFRAME_H1)
        rates = self._mt5.copy_rates_from_pos(symbol, tf, 0, count)

        if rates is None:
            logger.warning(f"MT5Feed: no rates returned for {symbol}/{timeframe}")
            return []

        import pandas as pd
        df = pd.DataFrame(rates)
        df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)

        return [
            {
                'timestamp': row['timestamp'].isoformat(),
                'open':      float(row['open']),
                'high':      float(row['high']),
                'low':       float(row['low']),
                'close':     float(row['close']),
                'volume':    int(row['tick_volume']),
            }
            for _, row in df.iterrows()
        ]