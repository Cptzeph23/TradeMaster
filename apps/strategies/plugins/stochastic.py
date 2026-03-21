# ============================================================
# FIXED: self.parameters → self.params
# ============================================================
import pandas as pd
import numpy as np
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry


@StrategyRegistry.register('stochastic')
class StochasticStrategy(BaseStrategy):

    NAME        = 'Stochastic Oscillator'
    DESCRIPTION = 'Stochastic %K/%D crossover in oversold/overbought zones.'
    VERSION     = '1.0.0'

    DEFAULT_PARAMETERS = {
        'k_period':       14,
        'd_period':        3,
        'smooth_k':        3,
        'oversold':       20,
        'overbought':     80,
        'trend_sma':     200,
        'atr_period':     14,
        'atr_sl_mult':   1.5,
        'risk_reward':   2.0,
        'stoch_rsi_mode':False,
    }

    def _p(self, key):
        return self.params.get(key, self.DEFAULT_PARAMETERS.get(key))

    def get_required_candles(self) -> int:
        return int(self._p('trend_sma')) + int(self._p('k_period')) + 20

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        k_p        = int(self._p('k_period'))
        d_p        = int(self._p('d_period'))
        smooth_k   = int(self._p('smooth_k'))
        oversold   = float(self._p('oversold'))
        overbought = float(self._p('overbought'))
        sma_p      = int(self._p('trend_sma'))
        atr_p      = int(self._p('atr_period'))
        atr_mult   = float(self._p('atr_sl_mult'))
        rr         = float(self._p('risk_reward'))

        if len(df) < self.get_required_candles():
            return Signal.neutral(symbol, 'Insufficient data')

        close = df['close'].astype(float)
        high  = df['high'].astype(float)
        low   = df['low'].astype(float)

        if self._p('stoch_rsi_mode'):
            delta    = close.diff()
            gain     = delta.clip(lower=0).ewm(com=k_p - 1, adjust=False).mean()
            loss     = (-delta.clip(upper=0)).ewm(com=k_p - 1, adjust=False).mean()
            rs       = gain / loss.replace(0, np.nan)
            rsi      = 100 - 100 / (1 + rs)
            rsi_min  = rsi.rolling(k_p).min()
            rsi_max  = rsi.rolling(k_p).max()
            raw_k    = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan) * 100
        else:
            lowest_low   = low.rolling(k_p).min()
            highest_high = high.rolling(k_p).max()
            raw_k = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100

        k_line = raw_k.rolling(smooth_k).mean()
        d_line = k_line.rolling(d_p).mean()

        sma200     = close.rolling(sma_p).mean() if sma_p > 0 else None
        trend_up   = sma200 is None or float(close.iloc[-1]) > float(sma200.iloc[-1])
        trend_down = sma200 is None or float(close.iloc[-1]) < float(sma200.iloc[-1])

        tr  = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(atr_p).mean().iloc[-1])

        k_now  = float(k_line.iloc[-1])
        k_prev = float(k_line.iloc[-2])
        d_now  = float(d_line.iloc[-1])
        d_prev = float(d_line.iloc[-2])
        price  = float(close.iloc[-1])

        cross_up      = (k_prev <= d_prev) and (k_now > d_now)
        cross_down    = (k_prev >= d_prev) and (k_now < d_now)
        in_oversold   = k_now < oversold
        in_overbought = k_now > overbought

        indicators = {
            'k': round(k_now, 2), 'd': round(d_now, 2),
            'atr': round(atr, 6), 'trend': 'up' if trend_up else 'down',
        }

        if cross_up and in_oversold and trend_up:
            sl = price - atr * atr_mult
            tp = price + abs(price - sl) * rr
            return Signal(action='buy', symbol=symbol, strength=0.75,
                         stop_loss=round(sl, 5), take_profit=round(tp, 5),
                         reason=f"Stochastic BUY: K({k_now:.1f}) crossed D in oversold",
                         indicators=indicators)

        if cross_down and in_overbought and trend_down:
            sl = price + atr * atr_mult
            tp = price - abs(sl - price) * rr
            return Signal(action='sell', symbol=symbol, strength=0.75,
                         stop_loss=round(sl, 5), take_profit=round(tp, 5),
                         reason=f"Stochastic SELL: K({k_now:.1f}) crossed D in overbought",
                         indicators=indicators)

        return Signal.neutral(symbol, f"Stochastic neutral — K={k_now:.1f} D={d_now:.1f}", indicators)