# ============================================================
# FIXED: self.parameters → self.params
# ============================================================
import pandas as pd
import numpy as np
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry
 
 
@StrategyRegistry.register('macd_divergence')
class MACDDivergenceStrategy(BaseStrategy):
 
    name        = 'MACD Divergence'
    description = 'Detects regular and hidden MACD divergences for reversal and continuation trades.'
    version     = '1.0.0'
    author      = 'ForexBot Phase N'
 
    DEFAULT_PARAMETERS = {
        'fast_period':   12,
        'slow_period':   26,
        'signal_period':  9,
        'lookback':      20,
        'atr_period':    14,
        'atr_sl_mult':   1.5,
        'hidden_div':    True,
        'min_div_pips':  10,
        'risk_reward':   2.0,
    }
 
    def _p(self, key):
        return self.params.get(key, self.DEFAULT_PARAMETERS.get(key))
 
    def get_required_candles(self) -> int:
        return int(self._p('slow_period')) + int(self._p('lookback')) + int(self._p('atr_period')) + 10
 
    def get_default_parameters(self) -> dict:
        return self.DEFAULT_PARAMETERS.copy()
 
    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        fast     = int(self._p('fast_period'))
        slow     = int(self._p('slow_period'))
        sig_p    = int(self._p('signal_period'))
        lookback = int(self._p('lookback'))
        atr_p    = int(self._p('atr_period'))
        atr_mult = float(self._p('atr_sl_mult'))
        rr       = float(self._p('risk_reward'))
        min_pips = float(self._p('min_div_pips'))
        pip_size = 0.01 if 'JPY' in symbol else 0.0001
        min_dist = min_pips * pip_size
 
        if len(df) < self.get_required_candles():
            return Signal(action='hold', symbol=symbol, reason='Insufficient data', strength=0.0)
 
        close = df['close'].astype(float)
        high  = df['high'].astype(float)
        low   = df['low'].astype(float)
 
        macd_line   = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
        signal_line = macd_line.ewm(span=sig_p, adjust=False).mean()
        histogram   = macd_line - signal_line
 
        tr  = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.rolling(atr_p).mean().iloc[-1])
        price = float(close.iloc[-1])
 
        recent_close = close.iloc[-lookback:]
        recent_macd  = macd_line.iloc[-lookback:]
 
        price_low_now   = float(recent_close.iloc[-1])
        price_low_prev  = float(recent_close.iloc[:-5].min())
        macd_low_now    = float(recent_macd.iloc[-1])
        macd_low_prev   = float(recent_macd.iloc[:-5].min())
        price_high_now  = float(recent_close.iloc[-1])
        price_high_prev = float(recent_close.iloc[:-5].max())
        macd_high_now   = float(recent_macd.iloc[-1])
        macd_high_prev  = float(recent_macd.iloc[:-5].max())
 
        cross_up   = (float(macd_line.iloc[-2]) <= float(signal_line.iloc[-2]) and
                      float(macd_line.iloc[-1]) >  float(signal_line.iloc[-1]))
        cross_down = (float(macd_line.iloc[-2]) >= float(signal_line.iloc[-2]) and
                      float(macd_line.iloc[-1]) <  float(signal_line.iloc[-1]))
 
        reg_bull = price_low_now  < price_low_prev  - min_dist and macd_low_now  > macd_low_prev  and cross_up
        reg_bear = price_high_now > price_high_prev + min_dist and macd_high_now < macd_high_prev and cross_down
        hid_bull = (bool(self._p('hidden_div')) and
                    price_low_now  > price_low_prev  + min_dist and macd_low_now  < macd_low_prev  and cross_up)
        hid_bear = (bool(self._p('hidden_div')) and
                    price_high_now < price_high_prev - min_dist and macd_high_now > macd_high_prev and cross_down)
 
        indicators = {
            'macd':      round(float(macd_line.iloc[-1]), 6),
            'signal':    round(float(signal_line.iloc[-1]), 6),
            'histogram': round(float(histogram.iloc[-1]), 6),
            'atr':       round(atr, 6),
        }
 
        if reg_bull or hid_bull:
            sl = price - atr * atr_mult
            return Signal(action='buy', symbol=symbol,
                         strength=0.85 if reg_bull else 0.7,
                         stop_loss=round(sl, 5),
                         take_profit=round(price + abs(price-sl)*rr, 5),
                         reason=f"{'Regular' if reg_bull else 'Hidden'} MACD Bullish Divergence",
                         indicators=indicators)
 
        if reg_bear or hid_bear:
            sl = price + atr * atr_mult
            return Signal(action='sell', symbol=symbol,
                         strength=0.85 if reg_bear else 0.7,
                         stop_loss=round(sl, 5),
                         take_profit=round(price - abs(sl-price)*rr, 5),
                         reason=f"{'Regular' if reg_bear else 'Hidden'} MACD Bearish Divergence",
                         indicators=indicators)
 
        return Signal(action='hold', symbol=symbol, strength=0.0,
                     reason='No MACD divergence detected', indicators=indicators)
 