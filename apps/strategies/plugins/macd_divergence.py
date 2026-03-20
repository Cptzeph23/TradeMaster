# ============================================================
# MACD Divergence Strategy
#
# Logic:
#   REGULAR BULLISH DIVERGENCE: price makes lower low, MACD makes higher low
#   REGULAR BEARISH DIVERGENCE: price makes higher high, MACD makes lower high
#   HIDDEN BULLISH DIVERGENCE:  price makes higher low, MACD makes lower low (trend continuation)
#   HIDDEN BEARISH DIVERGENCE:  price makes lower high, MACD makes higher high
#   Confirmation: MACD crossover in signal direction
#   SL: recent swing high/low + ATR buffer
# ============================================================
import pandas as pd
import numpy as np
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry


@StrategyRegistry.register('macd_divergence')
class MACDDivergenceStrategy(BaseStrategy):

    NAME        = 'MACD Divergence'
    DESCRIPTION = (
        'Detects regular and hidden MACD divergences for high-probability '
        'reversal and continuation trades.'
    )
    VERSION     = '1.0.0'

    DEFAULT_PARAMETERS = {
        'fast_period':      12,
        'slow_period':      26,
        'signal_period':    9,
        'lookback':         20,       # bars to look back for divergence
        'atr_period':       14,
        'atr_sl_mult':      1.5,
        'hidden_div':       True,     # also trade hidden divergences
        'min_div_pips':     10,       # minimum divergence magnitude
        'risk_reward':      2.0,
    }

    def get_required_candles(self) -> int:
        return self.parameters.get('slow_period', 26) + \
               self.parameters.get('lookback', 20) + \
               self.parameters.get('atr_period', 14) + 10

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        p         = self.parameters
        fast      = int(p.get('fast_period',   12))
        slow      = int(p.get('slow_period',   26))
        sig_p     = int(p.get('signal_period',  9))
        lookback  = int(p.get('lookback',       20))
        atr_p     = int(p.get('atr_period',     14))
        atr_mult  = float(p.get('atr_sl_mult',  1.5))
        rr        = float(p.get('risk_reward',  2.0))
        min_pips  = float(p.get('min_div_pips', 10))

        if len(df) < self.get_required_candles():
            return Signal.neutral(symbol, 'Insufficient data')

        close  = df['close'].astype(float)
        high   = df['high'].astype(float)
        low    = df['low'].astype(float)

        # ── MACD calculation ───────────────────────────────────
        ema_fast    = close.ewm(span=fast,   adjust=False).mean()
        ema_slow    = close.ewm(span=slow,   adjust=False).mean()
        macd_line   = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=sig_p, adjust=False).mean()
        histogram   = macd_line - signal_line

        # ── ATR ────────────────────────────────────────────────
        tr  = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(atr_p).mean().iloc[-1]

        price       = close.iloc[-1]
        pip_size    = 0.01 if 'JPY' in symbol else 0.0001
        min_dist    = min_pips * pip_size

        window = lookback

        # Recent price pivots
        recent_close = close.iloc[-window:]
        recent_macd  = macd_line.iloc[-window:]
        recent_high  = high.iloc[-window:]
        recent_low   = low.iloc[-window:]

        price_low_now  = recent_close.iloc[-1]
        price_low_prev = recent_close.iloc[:-5].min()
        macd_low_now   = recent_macd.iloc[-1]
        macd_low_prev  = recent_macd.iloc[:-5].min()

        price_high_now  = recent_close.iloc[-1]
        price_high_prev = recent_close.iloc[:-5].max()
        macd_high_now   = recent_macd.iloc[-1]
        macd_high_prev  = recent_macd.iloc[:-5].max()

        # MACD crossover
        macd_cross_up   = (macd_line.iloc[-2] <= signal_line.iloc[-2] and
                           macd_line.iloc[-1] >  signal_line.iloc[-1])
        macd_cross_down = (macd_line.iloc[-2] >= signal_line.iloc[-2] and
                           macd_line.iloc[-1] <  signal_line.iloc[-1])

        # Regular bullish divergence: price lower low, MACD higher low
        reg_bull = (price_low_now  < price_low_prev - min_dist and
                    macd_low_now   > macd_low_prev and
                    macd_cross_up)

        # Regular bearish divergence: price higher high, MACD lower high
        reg_bear = (price_high_now  > price_high_prev + min_dist and
                    macd_high_now   < macd_high_prev and
                    macd_cross_down)

        # Hidden bullish: price higher low, MACD lower low (continuation)
        hid_bull = (p.get('hidden_div') and
                    price_low_now > price_low_prev + min_dist and
                    macd_low_now  < macd_low_prev and
                    macd_cross_up)

        # Hidden bearish: price lower high, MACD higher high (continuation)
        hid_bear = (p.get('hidden_div') and
                    price_high_now < price_high_prev - min_dist and
                    macd_high_now  > macd_high_prev and
                    macd_cross_down)

        swing_low  = recent_low.min()
        swing_high = recent_high.max()

        indicators = {
            'macd':       round(float(macd_line.iloc[-1]), 6),
            'signal':     round(float(signal_line.iloc[-1]), 6),
            'histogram':  round(float(histogram.iloc[-1]), 6),
            'atr':        round(float(atr), 6),
        }

        if reg_bull or hid_bull:
            sl = price - atr * atr_mult
            tp = price + abs(price - sl) * rr
            div_type = 'Regular' if reg_bull else 'Hidden'
            return Signal(
                action      = 'buy',
                symbol      = symbol,
                strength    = 0.85 if reg_bull else 0.7,
                stop_loss   = round(sl, 5),
                take_profit = round(tp, 5),
                reason      = f"{div_type} MACD Bullish Divergence — MACD cross up",
                indicators  = indicators,
            )

        if reg_bear or hid_bear:
            sl = price + atr * atr_mult
            tp = price - abs(sl - price) * rr
            div_type = 'Regular' if reg_bear else 'Hidden'
            return Signal(
                action      = 'sell',
                symbol      = symbol,
                strength    = 0.85 if reg_bear else 0.7,
                stop_loss   = round(sl, 5),
                take_profit = round(tp, 5),
                reason      = f"{div_type} MACD Bearish Divergence — MACD cross down",
                indicators  = indicators,
            )

        return Signal.neutral(symbol, 'No MACD divergence', indicators)