# ============================================================
# Stochastic Oscillator Strategy
#
# Logic:
#   BUY:  %K crosses above %D in oversold zone (<20) + price above SMA filter
#   SELL: %K crosses below %D in overbought zone (>80) + price below SMA filter
#   Stochastic RSI mode: optional ultra-sensitive variant
#   SL: ATR-based below/above recent swing
#   TP: configurable RR or next overbought/oversold level
# ============================================================
import pandas as pd
import numpy as np
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry


@StrategyRegistry.register('stochastic')
class StochasticStrategy(BaseStrategy):

    NAME        = 'Stochastic Oscillator'
    DESCRIPTION = (
        'Stochastic %K/%D crossover in oversold/overbought zones, '
        'with trend filter and ATR-based stops.'
    )
    VERSION     = '1.0.0'

    DEFAULT_PARAMETERS = {
        'k_period':        14,
        'd_period':        3,
        'smooth_k':        3,      # slow stochastic smoothing
        'oversold':        20,
        'overbought':      80,
        'trend_sma':       200,    # 0 to disable trend filter
        'atr_period':      14,
        'atr_sl_mult':     1.5,
        'risk_reward':     2.0,
        'stoch_rsi_mode':  False,  # use Stochastic RSI instead
    }

    def get_required_candles(self) -> int:
        return (self.parameters.get('trend_sma', 200) +
                self.parameters.get('k_period', 14) + 20)

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        p          = self.parameters
        k_p        = int(p.get('k_period',    14))
        d_p        = int(p.get('d_period',     3))
        smooth_k   = int(p.get('smooth_k',     3))
        oversold   = float(p.get('oversold',  20))
        overbought = float(p.get('overbought',80))
        sma_p      = int(p.get('trend_sma',  200))
        atr_p      = int(p.get('atr_period', 14))
        atr_mult   = float(p.get('atr_sl_mult', 1.5))
        rr         = float(p.get('risk_reward',  2.0))

        if len(df) < self.get_required_candles():
            return Signal.neutral(symbol, 'Insufficient data')

        close = df['close'].astype(float)
        high  = df['high'].astype(float)
        low   = df['low'].astype(float)

        # ── Stochastic calculation ─────────────────────────────
        if p.get('stoch_rsi_mode'):
            # Stochastic RSI
            delta    = close.diff()
            gain     = delta.clip(lower=0).ewm(com=k_p - 1, adjust=False).mean()
            loss     = (-delta.clip(upper=0)).ewm(com=k_p - 1, adjust=False).mean()
            rs       = gain / loss.replace(0, np.nan)
            rsi      = 100 - 100 / (1 + rs)
            rsi_min  = rsi.rolling(k_p).min()
            rsi_max  = rsi.rolling(k_p).max()
            raw_k    = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan) * 100
        else:
            # Standard Stochastic
            lowest_low   = low.rolling(k_p).min()
            highest_high = high.rolling(k_p).max()
            raw_k = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100

        k_line = raw_k.rolling(smooth_k).mean()
        d_line = k_line.rolling(d_p).mean()

        # ── Trend filter ───────────────────────────────────────
        sma200 = close.rolling(sma_p).mean() if sma_p > 0 else None
        trend_up   = sma200 is None or close.iloc[-1] > sma200.iloc[-1]
        trend_down = sma200 is None or close.iloc[-1] < sma200.iloc[-1]

        # ── ATR ────────────────────────────────────────────────
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

        cross_up   = (k_prev <= d_prev) and (k_now > d_now)
        cross_down = (k_prev >= d_prev) and (k_now < d_now)
        in_oversold    = k_now < oversold
        in_overbought  = k_now > overbought

        indicators = {
            'k': round(k_now, 2),
            'd': round(d_now, 2),
            'atr': round(atr, 6),
            'trend': 'up' if trend_up else 'down',
        }

        if cross_up and in_oversold and trend_up:
            sl = price - atr * atr_mult
            tp = price + abs(price - sl) * rr
            return Signal(
                action      = 'buy',
                symbol      = symbol,
                strength    = 0.75,
                stop_loss   = round(sl, 5),
                take_profit = round(tp, 5),
                reason      = f"Stochastic BUY: %K({k_now:.1f}) crossed %D in oversold",
                indicators  = indicators,
            )

        if cross_down and in_overbought and trend_down:
            sl = price + atr * atr_mult
            tp = price - abs(sl - price) * rr
            return Signal(
                action      = 'sell',
                symbol      = symbol,
                strength    = 0.75,
                stop_loss   = round(sl, 5),
                take_profit = round(tp, 5),
                reason      = f"Stochastic SELL: %K({k_now:.1f}) crossed %D in overbought",
                indicators  = indicators,
            )

        return Signal.neutral(
            symbol,
            f"Stochastic neutral — K={k_now:.1f}, D={d_now:.1f}",
            indicators,
        )