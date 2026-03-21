# ============================================================
# ATR Channel Breakout Strategy
#
# Logic:
#   Builds dynamic channel using ATR multiples above/below a baseline MA
#   BUY:  candle closes above upper channel band + volume/range confirmation
#   SELL: candle closes below lower channel band
#   Retest mode: wait for pullback to band after breakout (optional)
#   SL: opposite channel band
#   TP: ATR-based projection (breakout distance × multiplier)
# ============================================================
import pandas as pd
import numpy as np
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry
 
 
@StrategyRegistry.register('atr_breakout')
class ATRBreakoutStrategy(BaseStrategy):
 
    name        = 'ATR Channel Breakout'
    description = 'Dynamic ATR-based channel breakout — adapts to market volatility.'
    version     = '1.0.0'
    author      = 'ForexBot Phase N'
 
    DEFAULT_PARAMETERS = {
        'baseline_period':  20,
        'baseline_type':   'EMA',
        'atr_period':       14,
        'channel_mult':     2.0,
        'breakout_confirm': 2,
        'retest_mode':      False,
        'retest_tolerance': 0.3,
        'min_range_mult':   1.2,
        'risk_reward':      2.5,
        'tp_atr_mult':      4.0,
    }
 
    def _p(self, key):
        return self.params.get(key, self.DEFAULT_PARAMETERS.get(key))
 
    def get_required_candles(self) -> int:
        return int(self._p('baseline_period')) + int(self._p('atr_period')) + int(self._p('breakout_confirm')) + 20
 
    def get_default_parameters(self) -> dict:
        return self.DEFAULT_PARAMETERS.copy()
 
    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        base_p      = int(self._p('baseline_period'))
        base_type   = str(self._p('baseline_type'))
        atr_p       = int(self._p('atr_period'))
        ch_mult     = float(self._p('channel_mult'))
        confirm     = int(self._p('breakout_confirm'))
        retest_mode = bool(self._p('retest_mode'))
        retest_tol  = float(self._p('retest_tolerance'))
        min_rng     = float(self._p('min_range_mult'))
        rr          = float(self._p('risk_reward'))
        tp_mult     = float(self._p('tp_atr_mult'))
 
        if len(df) < self.get_required_candles():
            return Signal(action='hold', symbol=symbol, reason='Insufficient data', strength=0.0)
 
        close = df['close'].astype(float)
        high  = df['high'].astype(float)
        low   = df['low'].astype(float)
        open_ = df['open'].astype(float)
 
        if base_type == 'EMA':
            baseline = close.ewm(span=base_p, adjust=False).mean()
        elif base_type == 'WMA':
            w = np.arange(1, base_p+1)
            baseline = close.rolling(base_p).apply(lambda x: np.dot(x,w)/w.sum(), raw=True)
        else:
            baseline = close.rolling(base_p).mean()
 
        tr    = pd.concat([high-low,(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
        atr   = tr.rolling(atr_p).mean()
        atr_v = float(atr.iloc[-1])
        upper = baseline + atr * ch_mult
        lower = baseline - atr * ch_mult
 
        price      = float(close.iloc[-1])
        upper_band = float(upper.iloc[-1])
        lower_band = float(lower.iloc[-1])
 
        bull_confirm = all(float(close.iloc[-i]) > float(upper.iloc[-i]) for i in range(1, confirm+1))
        bear_confirm = all(float(close.iloc[-i]) < float(lower.iloc[-i]) for i in range(1, confirm+1))
 
        avg_range    = float((high-low).rolling(14).mean().iloc[-1])
        breakout_bar = abs(float(close.iloc[-1]) - float(open_.iloc[-1]))
        strong       = breakout_bar > avg_range * min_rng
 
        if retest_mode:
            entry_bull = (abs(price-upper_band) < atr_v*retest_tol and
                         float(close.iloc[-2]) > float(upper.iloc[-2]))
            entry_bear = (abs(price-lower_band) < atr_v*retest_tol and
                         float(close.iloc[-2]) < float(lower.iloc[-2]))
        else:
            entry_bull = bull_confirm and strong
            entry_bear = bear_confirm and strong
 
        indicators = {'upper_band':round(upper_band,5),'lower_band':round(lower_band,5),
                      'atr':round(atr_v,6),'price':round(price,5)}
 
        if entry_bull:
            sl = lower_band
            return Signal(action='buy', symbol=symbol, strength=0.80,
                         stop_loss=round(sl,5), take_profit=round(price+atr_v*tp_mult,5),
                         reason=f"ATR Breakout BUY above {upper_band:.5f}",
                         indicators=indicators)
 
        if entry_bear:
            sl = upper_band
            return Signal(action='sell', symbol=symbol, strength=0.80,
                         stop_loss=round(sl,5), take_profit=round(price-atr_v*tp_mult,5),
                         reason=f"ATR Breakout SELL below {lower_band:.5f}",
                         indicators=indicators)
 
        return Signal(action='hold', symbol=symbol, strength=0.0,
                     reason=f"ATR Channel neutral — upper={upper_band:.5f} lower={lower_band:.5f}",
                     indicators=indicators)
 