# ============================================================
# FIXED: self.parameters → self.params (matches BaseStrategy.__init__)
# ============================================================
import pandas as pd
import numpy as np
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry
 
 
@StrategyRegistry.register('ichimoku')
class IchimokuStrategy(BaseStrategy):
 
    # Lowercase to match BaseStrategy attribute names
    name        = 'Ichimoku Cloud'
    description = (
        'Full Ichimoku system — trades in the direction of the cloud '
        'with Tenkan/Kijun crossover confirmation and Chikou span filter.'
    )
    version     = '1.0.0'
    author      = 'ForexBot Phase N'
 
    DEFAULT_PARAMETERS = {
        'tenkan_period':   9,
        'kijun_period':    26,
        'senkou_b_period': 52,
        'displacement':    26,
        'risk_reward':     1.5,
        'cloud_filter':    True,
        'chikou_filter':   True,
    }
 
    def _p(self, key):
        return self.params.get(key, self.DEFAULT_PARAMETERS.get(key))
 
    def get_required_candles(self) -> int:
        return int(self._p('senkou_b_period')) + int(self._p('displacement')) + 10
 
    def get_default_parameters(self) -> dict:
        return self.DEFAULT_PARAMETERS.copy()
 
    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        tenkan_p   = int(self._p('tenkan_period'))
        kijun_p    = int(self._p('kijun_period'))
        senkou_b_p = int(self._p('senkou_b_period'))
        disp       = int(self._p('displacement'))
        rr         = float(self._p('risk_reward'))
        chikou_filt= bool(self._p('chikou_filter'))
 
        if len(df) < self.get_required_candles():
            return Signal(action='hold', symbol=symbol,
                         reason='Insufficient data', strength=0.0)
 
        high  = df['high'].astype(float)
        low   = df['low'].astype(float)
        close = df['close'].astype(float)
 
        def mid(h, l, n):
            return (h.rolling(n).max() + l.rolling(n).min()) / 2
 
        tenkan   = mid(high, low, tenkan_p)
        kijun    = mid(high, low, kijun_p)
        senkou_a = ((tenkan + kijun) / 2).shift(disp)
        senkou_b = mid(high, low, senkou_b_p).shift(disp)
 
        price     = float(close.iloc[-1])
        t_now     = float(tenkan.iloc[-1])
        k_now     = float(kijun.iloc[-1])
        t_prev    = float(tenkan.iloc[-2])
        k_prev    = float(kijun.iloc[-2])
 
        cloud_top = max(float(senkou_a.iloc[-1]), float(senkou_b.iloc[-1]))
        cloud_bot = min(float(senkou_a.iloc[-1]), float(senkou_b.iloc[-1]))
 
        chikou_val   = float(close.iloc[-1 - disp]) if len(close) > disp else np.nan
        cloud_top_26 = (max(float(senkou_a.iloc[-1 - disp]),
                           float(senkou_b.iloc[-1 - disp]))
                        if len(senkou_a) > disp else np.nan)
        cloud_bot_26 = (min(float(senkou_a.iloc[-1 - disp]),
                           float(senkou_b.iloc[-1 - disp]))
                        if len(senkou_b) > disp else np.nan)
 
        bullish_cross = (t_prev <= k_prev) and (t_now > k_now)
        bearish_cross = (t_prev >= k_prev) and (t_now < k_now)
        above_cloud   = price > cloud_top
        below_cloud   = price < cloud_bot
        chikou_above  = (not chikou_filt or
                         (not np.isnan(chikou_val) and not np.isnan(cloud_top_26)
                          and chikou_val > cloud_top_26))
        chikou_below  = (not chikou_filt or
                         (not np.isnan(chikou_val) and not np.isnan(cloud_bot_26)
                          and chikou_val < cloud_bot_26))
 
        sl_dist = abs(price - k_now)
        tp_dist = sl_dist * rr
 
        indicators = {
            'tenkan':    round(t_now, 5),
            'kijun':     round(k_now, 5),
            'cloud_top': round(cloud_top, 5),
            'cloud_bot': round(cloud_bot, 5),
            'price':     round(price, 5),
        }
 
        if bullish_cross and above_cloud and chikou_above:
            return Signal(
                action='buy', symbol=symbol, strength=0.8,
                stop_loss=round(price - sl_dist, 5),
                take_profit=round(price + tp_dist, 5),
                reason=f"Ichimoku BUY: Tenkan/Kijun cross above cloud",
                indicators=indicators,
            )
 
        if bearish_cross and below_cloud and chikou_below:
            return Signal(
                action='sell', symbol=symbol, strength=0.8,
                stop_loss=round(price + sl_dist, 5),
                take_profit=round(price - tp_dist, 5),
                reason=f"Ichimoku SELL: Tenkan/Kijun cross below cloud",
                indicators=indicators,
            )
 
        pos = 'above' if above_cloud else 'below' if below_cloud else 'inside'
        return Signal(action='hold', symbol=symbol, strength=0.0,
                     reason=f"Ichimoku neutral — price {pos} cloud",
                     indicators=indicators)
 