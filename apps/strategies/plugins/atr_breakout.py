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

    NAME        = 'ATR Channel Breakout'
    DESCRIPTION = (
        'Dynamic ATR-based channel breakout — adapts to market volatility. '
        'Trades strong momentum breakouts with optional retest confirmation.'
    )
    VERSION     = '1.0.0'

    DEFAULT_PARAMETERS = {
        'baseline_period':  20,       # MA for channel midpoint
        'baseline_type':    'EMA',    # EMA | SMA | WMA
        'atr_period':       14,
        'channel_mult':     2.0,      # ATR multiplier for channel width
        'breakout_confirm': 2,        # consecutive closes above/below (1 or 2)
        'retest_mode':      False,    # wait for pullback to band
        'retest_tolerance': 0.3,      # ATR fraction for retest zone
        'min_range_mult':   1.2,      # breakout candle must be > N × avg range
        'risk_reward':      2.5,
        'tp_atr_mult':      4.0,      # TP = entry + ATR × this
    }

    def get_required_candles(self) -> int:
        return (self.parameters.get('baseline_period', 20) +
                self.parameters.get('atr_period', 14) +
                self.parameters.get('breakout_confirm', 2) + 20)

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        p           = self.parameters
        base_p      = int(p.get('baseline_period',  20))
        base_type   = p.get('baseline_type',       'EMA')
        atr_p       = int(p.get('atr_period',       14))
        ch_mult     = float(p.get('channel_mult',   2.0))
        confirm     = int(p.get('breakout_confirm',  2))
        retest_mode = p.get('retest_mode', False)
        retest_tol  = float(p.get('retest_tolerance', 0.3))
        min_rng     = float(p.get('min_range_mult',  1.2))
        rr          = float(p.get('risk_reward',     2.5))
        tp_mult     = float(p.get('tp_atr_mult',     4.0))

        if len(df) < self.get_required_candles():
            return Signal.neutral(symbol, 'Insufficient data')

        close = df['close'].astype(float)
        high  = df['high'].astype(float)
        low   = df['low'].astype(float)
        open_ = df['open'].astype(float)

        # ── Baseline MA ────────────────────────────────────────
        if base_type == 'EMA':
            baseline = close.ewm(span=base_p, adjust=False).mean()
        elif base_type == 'WMA':
            weights  = np.arange(1, base_p + 1)
            baseline = close.rolling(base_p).apply(
                lambda x: np.dot(x, weights) / weights.sum(), raw=True
            )
        else:
            baseline = close.rolling(base_p).mean()

        # ── ATR channel ────────────────────────────────────────
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr     = tr.rolling(atr_p).mean()
        atr_val = float(atr.iloc[-1])

        upper = baseline + atr * ch_mult
        lower = baseline - atr * ch_mult

        price       = float(close.iloc[-1])
        upper_band  = float(upper.iloc[-1])
        lower_band  = float(lower.iloc[-1])
        mid_band    = float(baseline.iloc[-1])

        # ── Breakout confirmation ──────────────────────────────
        # Check last `confirm` candles all closed above/below band
        recent_close  = close.iloc[-confirm:]
        recent_upper  = upper.iloc[-confirm:]
        recent_lower  = lower.iloc[-confirm:]
        bull_confirm  = all(recent_close.iloc[i] > recent_upper.iloc[i]
                            for i in range(confirm))
        bear_confirm  = all(recent_close.iloc[i] < recent_lower.iloc[i]
                            for i in range(confirm))

        # ── Candle range filter ────────────────────────────────
        # Breakout bar must be larger than average candle
        avg_range     = (high - low).rolling(14).mean().iloc[-1]
        breakout_bar  = abs(close.iloc[-1] - open_.iloc[-1])
        strong_candle = breakout_bar > avg_range * min_rng

        # ── Retest mode ────────────────────────────────────────
        if retest_mode:
            retest_zone_bull = (abs(price - upper_band) < atr_val * retest_tol and
                                close.iloc[-2] > upper.iloc[-2])
            retest_zone_bear = (abs(price - lower_band) < atr_val * retest_tol and
                                close.iloc[-2] < lower.iloc[-2])
            entry_bull = retest_zone_bull
            entry_bear = retest_zone_bear
        else:
            entry_bull = bull_confirm and strong_candle
            entry_bear = bear_confirm and strong_candle

        indicators = {
            'upper_band': round(upper_band, 5),
            'lower_band': round(lower_band, 5),
            'mid_band':   round(mid_band, 5),
            'atr':        round(atr_val, 6),
            'price':      round(price, 5),
        }

        if entry_bull:
            sl = lower_band   # opposite band as SL
            tp = price + atr_val * tp_mult
            return Signal(
                action      = 'buy',
                symbol      = symbol,
                strength    = 0.80,
                stop_loss   = round(sl, 5),
                take_profit = round(tp, 5),
                reason      = (f"ATR Breakout BUY: {'Retest' if retest_mode else 'Breakout'} "
                               f"above upper band={upper_band:.5f}, ATR={atr_val:.5f}"),
                indicators  = indicators,
            )

        if entry_bear:
            sl = upper_band
            tp = price - atr_val * tp_mult
            return Signal(
                action      = 'sell',
                symbol      = symbol,
                strength    = 0.80,
                stop_loss   = round(sl, 5),
                take_profit = round(tp, 5),
                reason      = (f"ATR Breakout SELL: {'Retest' if retest_mode else 'Breakout'} "
                               f"below lower band={lower_band:.5f}"),
                indicators  = indicators,
            )

        return Signal.neutral(
            symbol,
            f"ATR Channel neutral — price={price:.5f}, "
            f"upper={upper_band:.5f}, lower={lower_band:.5f}",
            indicators,
        )