# ============================================================
# EMA Ribbon Strategy
#
# Logic:
#   Uses 5 EMAs (8, 13, 21, 34, 55 — Fibonacci periods)
#   BUY:  all EMAs aligned bullish (8>13>21>34>55) + price above all
#         + EMA spread expanding (momentum confirmation)
#   SELL: all EMAs aligned bearish (8<13<21<34<55) + price below all
#   FILTER: ADX > threshold (strong trend only, avoid whipsaws)
#   EXIT signal: ribbon begins to compress (EMAs converging)
#   SL: below/above the slowest EMA (55) + ATR buffer
# ============================================================
import pandas as pd
import numpy as np
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry
 
 
@StrategyRegistry.register('ema_ribbon')
class EMARibbonStrategy(BaseStrategy):
 
    name        = 'EMA Ribbon'
    description = 'Five-EMA Fibonacci ribbon — trades when all EMAs are stacked and ADX confirms trend.'
    version     = '1.0.0'
    author      = 'ForexBot Phase N'
 
    DEFAULT_PARAMETERS = {
        'ema_periods':   [8, 13, 21, 34, 55],
        'adx_period':    14,
        'adx_threshold': 25,
        'atr_period':    14,
        'atr_sl_mult':   1.2,
        'risk_reward':   3.0,
        'expansion_bars':3,
    }
 
    def _p(self, key):
        return self.params.get(key, self.DEFAULT_PARAMETERS.get(key))
 
    def get_required_candles(self) -> int:
        periods = self._p('ema_periods') or [8,13,21,34,55]
        return max(periods) + int(self._p('adx_period')) + 20
 
    def get_default_parameters(self) -> dict:
        return self.DEFAULT_PARAMETERS.copy()
 
    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        ema_ps     = self._p('ema_periods') or [8,13,21,34,55]
        adx_p      = int(self._p('adx_period'))
        adx_thresh = float(self._p('adx_threshold'))
        atr_p      = int(self._p('atr_period'))
        atr_mult   = float(self._p('atr_sl_mult'))
        rr         = float(self._p('risk_reward'))
        exp_bars   = int(self._p('expansion_bars'))
 
        if len(df) < self.get_required_candles():
            return Signal(action='hold', symbol=symbol, reason='Insufficient data', strength=0.0)
 
        close = df['close'].astype(float)
        high  = df['high'].astype(float)
        low   = df['low'].astype(float)
 
        emas         = {p: close.ewm(span=p, adjust=False).mean() for p in ema_ps}
        current_emas = {p: float(emas[p].iloc[-1]) for p in ema_ps}
        price        = float(close.iloc[-1])
        ema_vals     = [current_emas[p] for p in sorted(ema_ps)]
 
        bull_aligned = all(ema_vals[i] > ema_vals[i+1] for i in range(len(ema_vals)-1))
        bear_aligned = all(ema_vals[i] < ema_vals[i+1] for i in range(len(ema_vals)-1))
 
        spread_now  = ema_vals[0] - ema_vals[-1]
        exp_idx     = min(exp_bars, len(df)-1)
        spread_prev = (float(emas[ema_ps[0]].iloc[-1-exp_idx]) -
                       float(emas[ema_ps[-1]].iloc[-1-exp_idx]))
        expanding   = abs(spread_now) > abs(spread_prev) * 0.95
 
        tr    = pd.concat([high-low,(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
        atr_s = tr.rolling(atr_p).mean()
        atr_v = float(atr_s.iloc[-1])
 
        pos_dm = (high.diff()).clip(lower=0)
        neg_dm = (-low.diff()).clip(lower=0)
        pos_dm = pos_dm.where(pos_dm > neg_dm, 0)
        neg_dm = neg_dm.where(neg_dm > pos_dm, 0)
        di_sum = (100*pos_dm.rolling(adx_p).mean()/atr_s.replace(0,np.nan) +
                  100*neg_dm.rolling(adx_p).mean()/atr_s.replace(0,np.nan)).replace(0,np.nan)
        di_diff= (100*pos_dm.rolling(adx_p).mean()/atr_s.replace(0,np.nan) -
                  100*neg_dm.rolling(adx_p).mean()/atr_s.replace(0,np.nan)).abs()
        adx    = float((100*di_diff/di_sum).rolling(adx_p).mean().iloc[-1])
 
        sl_ema = float(emas[ema_ps[-1]].iloc[-1])
        indicators = {**{f'ema{p}':round(current_emas[p],5) for p in ema_ps},
                      'adx':round(adx,2),'atr':round(atr_v,6)}
 
        if bull_aligned and price > max(ema_vals) and expanding and adx >= adx_thresh:
            sl = sl_ema - atr_v * atr_mult
            return Signal(action='buy', symbol=symbol,
                         strength=min(0.95, 0.6+(adx-adx_thresh)/100),
                         stop_loss=round(sl,5), take_profit=round(price+abs(price-sl)*rr,5),
                         reason=f"EMA Ribbon BUY: {len(ema_ps)} EMAs bullish, ADX={adx:.1f}",
                         indicators=indicators)
 
        if bear_aligned and price < min(ema_vals) and adx >= adx_thresh:
            sl = sl_ema + atr_v * atr_mult
            return Signal(action='sell', symbol=symbol,
                         strength=min(0.95, 0.6+(adx-adx_thresh)/100),
                         stop_loss=round(sl,5), take_profit=round(price-abs(sl-price)*rr,5),
                         reason=f"EMA Ribbon SELL: {len(ema_ps)} EMAs bearish, ADX={adx:.1f}",
                         indicators=indicators)
 
        alignment = 'bull' if bull_aligned else 'bear' if bear_aligned else 'mixed'
        return Signal(action='hold', symbol=symbol, strength=0.0,
                     reason=f"EMA Ribbon neutral — {alignment} aligned, ADX={adx:.1f}",
                     indicators=indicators)
 