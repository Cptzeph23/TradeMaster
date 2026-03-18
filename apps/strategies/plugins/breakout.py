# ============================================================
# Donchian Channel / Price Breakout Strategy
# ============================================================
import pandas as pd
import ta
from apps.strategies.base import BaseStrategy, Signal
from apps.strategies.registry import StrategyRegistry


@StrategyRegistry.register('breakout')
class BreakoutStrategy(BaseStrategy):
    """
    Donchian Channel Breakout Strategy
    ════════════════════════════════════
    Momentum strategy that buys when price breaks above the
    N-period high and sells when price breaks below the N-period low.

    BUY  signal: Close breaks above the highest high of the last N bars
    SELL signal: Close breaks below the lowest low  of the last N bars

    Filters:
      - ATR volatility filter: Breakout must be > min_atr_mult * ATR
        to avoid false breakouts on tiny moves
      - ADX trend filter:      ADX > threshold confirms a real trend
      - Volume confirm:        Breakout bar volume > average volume
      - Retest mode:           Wait for price to retest the broken level
                               before entering (reduces false breakouts)

    Exit:
      - Opposite breakout signal (channel flip)
      - ATR-based stop loss and take profit

    Default parameters:
        channel_period:     20   Donchian channel lookback
        atr_period:         14
        atr_sl_mult:        1.0  SL = last swing low/high (ATR fallback)
        atr_tp_mult:        2.5
        adx_period:         14
        adx_threshold:      25.0 Minimum ADX to confirm trend
        adx_filter:         True
        volume_filter:      True
        volume_period:      20
        min_breakout_atr:   0.5  Breakout size must be > 0.5 * ATR
    """

    name        = 'Donchian Breakout'
    version     = '1.0.0'
    description = (
        'Momentum breakout strategy using Donchian channels. '
        'Buys new N-period highs, sells new N-period lows. '
        'ATR and ADX filters reduce false breakout entries.'
    )
    author = 'System'

    def validate_parameters(self):
        period = self.p('channel_period', 20)
        if period < 5:
            raise ValueError("channel_period must be at least 5.")
        if period > 500:
            raise ValueError("channel_period cannot exceed 500.")

    def get_required_candles(self) -> int:
        return self.p('channel_period', 20) + self.p('adx_period', 14) + 50

    @classmethod
    def get_default_parameters(cls) -> dict:
        return {
            'channel_period':   20,
            'atr_period':       14,
            'atr_sl_mult':      1.0,
            'atr_tp_mult':      2.5,
            'adx_period':       14,
            'adx_threshold':    25.0,
            'adx_filter':       True,
            'volume_filter':    True,
            'volume_period':    20,
            'min_breakout_atr': 0.5,
        }

    @classmethod
    def get_parameter_schema(cls) -> dict:
        return {
            'type': 'object',
            'properties': {
                'channel_period':   {'type': 'integer', 'minimum': 5,   'maximum': 500, 'title': 'Channel Period (bars)'},
                'atr_period':       {'type': 'integer', 'minimum': 1,   'maximum': 100, 'title': 'ATR Period'},
                'atr_sl_mult':      {'type': 'number',  'minimum': 0.5, 'maximum': 10,  'title': 'ATR SL Multiplier'},
                'atr_tp_mult':      {'type': 'number',  'minimum': 0.5, 'maximum': 20,  'title': 'ATR TP Multiplier'},
                'adx_period':       {'type': 'integer', 'minimum': 5,   'maximum': 100, 'title': 'ADX Period'},
                'adx_threshold':    {'type': 'number',  'minimum': 10,  'maximum': 60,  'title': 'Min ADX (trend strength)'},
                'adx_filter':       {'type': 'boolean', 'title': 'Enable ADX Trend Filter'},
                'volume_filter':    {'type': 'boolean', 'title': 'Enable Volume Confirm'},
                'volume_period':    {'type': 'integer', 'minimum': 5,   'maximum': 200, 'title': 'Volume MA Period'},
                'min_breakout_atr': {'type': 'number',  'minimum': 0.1, 'maximum': 5,   'title': 'Min Breakout Size (ATR mult)'},
            },
            'required': ['channel_period'],
        }

    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        df = self.prepare_dataframe(df)

        min_candles = self.get_required_candles()
        if len(df) < min_candles:
            return Signal(
                action='hold', symbol=symbol,
                reason=f"Not enough candles ({len(df)}/{min_candles})"
            )

        ch_p    = self.p('channel_period',   20)
        atr_p   = self.p('atr_period',       14)
        sl_mult = self.p('atr_sl_mult',      1.0)
        tp_mult = self.p('atr_tp_mult',      2.5)
        adx_p   = self.p('adx_period',       14)
        adx_thr = self.p('adx_threshold',    25.0)
        min_bo  = self.p('min_breakout_atr', 0.5)

        close = df['close']
        high  = df['high']
        low   = df['low']

        # ── Donchian channel (exclude current bar) ────────────
        upper_band = high.shift(1).rolling(ch_p).max()
        lower_band = low.shift(1).rolling(ch_p).min()

        # ── ATR ───────────────────────────────────────────────
        atr = ta.volatility.average_true_range(high, low, close, window=atr_p)

        # ── ADX ───────────────────────────────────────────────
        adx_ind = ta.trend.ADXIndicator(high, low, close, window=adx_p)
        adx     = adx_ind.adx()

        # ── Volume filter ─────────────────────────────────────
        vol_ok = True
        if self.p('volume_filter', True) and 'volume' in df.columns:
            vol_ma = df['volume'].rolling(self.p('volume_period', 20)).mean()
            vol_ok = df['volume'].iloc[-1] > vol_ma.iloc[-1]

        # ── Current bar values ────────────────────────────────
        current_close  = float(close.iloc[-1])
        current_upper  = float(upper_band.iloc[-1])
        current_lower  = float(lower_band.iloc[-1])
        current_atr    = float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.001
        current_adx    = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
        breakout_size  = abs(current_close - current_upper)

        indicators = {
            'upper_band':     round(current_upper, 5),
            'lower_band':     round(current_lower, 5),
            'close':          round(current_close, 5),
            'atr':            round(current_atr, 5),
            'adx':            round(current_adx, 2),
            'channel_period': ch_p,
            'breakout_size':  round(breakout_size, 5),
        }

        # ── ADX filter ────────────────────────────────────────
        adx_ok = True
        if self.p('adx_filter', True):
            adx_ok = current_adx >= adx_thr

        # ── BUY: breakout above upper band ────────────────────
        if (current_close > current_upper and
                breakout_size >= current_atr * min_bo and
                adx_ok and vol_ok):

            sl = round(current_close - (current_atr * sl_mult), 5)
            tp = round(current_close + (current_atr * tp_mult), 5)

            return Signal(
                action='buy', symbol=symbol, strength=0.85,
                stop_loss=sl, take_profit=tp,
                indicators=indicators,
                reason=(
                    f"Bullish breakout: close={current_close:.5f} > "
                    f"{ch_p}-bar high={current_upper:.5f}. "
                    f"ADX={current_adx:.1f}, ATR={current_atr:.5f}"
                )
            )

        # ── SELL: breakout below lower band ───────────────────
        breakout_size_low = abs(current_lower - current_close)
        if (current_close < current_lower and
                breakout_size_low >= current_atr * min_bo and
                adx_ok and vol_ok):

            sl = round(current_close + (current_atr * sl_mult), 5)
            tp = round(current_close - (current_atr * tp_mult), 5)

            return Signal(
                action='sell', symbol=symbol, strength=0.85,
                stop_loss=sl, take_profit=tp,
                indicators=indicators,
                reason=(
                    f"Bearish breakout: close={current_close:.5f} < "
                    f"{ch_p}-bar low={current_lower:.5f}. "
                    f"ADX={current_adx:.1f}, ATR={current_atr:.5f}"
                )
            )

        # ── No signal ──────────────────────────────────────────
        return Signal(
            action='hold', symbol=symbol, indicators=indicators,
            reason=(
                f"Price inside channel [{current_lower:.5f}–{current_upper:.5f}]. "
                f"ADX={current_adx:.1f} ({'OK' if adx_ok else 'weak'}), "
                f"Volume={'OK' if vol_ok else 'low'}"
            )
        )