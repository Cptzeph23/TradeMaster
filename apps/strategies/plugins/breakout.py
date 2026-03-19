
import pandas as pd
import ta
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry


@StrategyRegistry.register('breakout')
class BreakoutStrategy(BaseStrategy):
    """Donchian Channel Breakout — buys new N-bar highs, sells new N-bar lows."""
    name        = 'Donchian Breakout'
    version     = '1.0.0'
    description = (
        'Momentum breakout strategy using Donchian channels. '
        'Buys new N-period highs, sells new N-period lows. '
        'ATR and ADX filters reduce false breakout entries.'
    )

    def validate_parameters(self):
        p = self.p('channel_period', 20)
        if p < 5:   raise ValueError("channel_period must be at least 5.")
        if p > 500: raise ValueError("channel_period cannot exceed 500.")

    def get_required_candles(self) -> int:
        return self.p('channel_period', 20) + self.p('adx_period', 14) + 50

    @classmethod
    def get_default_parameters(cls) -> dict:
        return {
            'channel_period': 20, 'atr_period': 14,
            'atr_sl_mult': 1.0,   'atr_tp_mult': 2.5,
            'adx_period': 14,     'adx_threshold': 25.0,
            'adx_filter': True,   'volume_filter': True,
            'volume_period': 20,  'min_breakout_atr': 0.5,
        }

    @classmethod
    def get_parameter_schema(cls) -> dict:
        return {
            'type': 'object',
            'properties': {
                'channel_period':   {'type': 'integer', 'minimum': 5,   'maximum': 500, 'title': 'Channel Period'},
                'atr_period':       {'type': 'integer', 'minimum': 1,   'maximum': 100, 'title': 'ATR Period'},
                'atr_sl_mult':      {'type': 'number',  'minimum': 0.5, 'maximum': 10,  'title': 'ATR SL Multiplier'},
                'atr_tp_mult':      {'type': 'number',  'minimum': 0.5, 'maximum': 20,  'title': 'ATR TP Multiplier'},
                'adx_period':       {'type': 'integer', 'minimum': 5,   'maximum': 100, 'title': 'ADX Period'},
                'adx_threshold':    {'type': 'number',  'minimum': 10,  'maximum': 60,  'title': 'Min ADX'},
                'adx_filter':       {'type': 'boolean', 'title': 'Enable ADX Filter'},
                'volume_filter':    {'type': 'boolean', 'title': 'Enable Volume Filter'},
                'min_breakout_atr': {'type': 'number',  'minimum': 0.1, 'maximum': 5,   'title': 'Min Breakout ATR'},
            },
            'required': ['channel_period'],
        }

    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        df = self.prepare_dataframe(df)
        min_c = self.get_required_candles()
        if len(df) < min_c:
            return Signal(action='hold', symbol=symbol,
                          reason=f"Not enough candles ({len(df)}/{min_c})")

        ch_p    = self.p('channel_period', 20)
        atr_p   = self.p('atr_period', 14)
        sl_mult = self.p('atr_sl_mult', 1.0)
        tp_mult = self.p('atr_tp_mult', 2.5)
        adx_thr = self.p('adx_threshold', 25.0)
        min_bo  = self.p('min_breakout_atr', 0.5)

        close = df['close']; high = df['high']; low = df['low']

        upper_band = high.shift(1).rolling(ch_p).max()
        lower_band = low.shift(1).rolling(ch_p).min()
        atr        = ta.volatility.average_true_range(high, low, close, window=atr_p)
        adx        = ta.trend.ADXIndicator(high, low, close, window=self.p('adx_period', 14)).adx()

        vol_ok = True
        if self.p('volume_filter', True) and 'volume' in df.columns:
            vol_ma = df['volume'].rolling(self.p('volume_period', 20)).mean()
            vol_ok = df['volume'].iloc[-1] > vol_ma.iloc[-1]

        cur_close = float(close.iloc[-1])
        cur_upper = float(upper_band.iloc[-1])
        cur_lower = float(lower_band.iloc[-1])
        cur_atr   = float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.001
        cur_adx   = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
        adx_ok    = cur_adx >= adx_thr if self.p('adx_filter', True) else True

        indicators = {
            'upper_band': round(cur_upper, 5), 'lower_band': round(cur_lower, 5),
            'atr': round(cur_atr, 5), 'adx': round(cur_adx, 2),
        }

        if cur_close > cur_upper and abs(cur_close - cur_upper) >= cur_atr * min_bo and adx_ok and vol_ok:
            sl = round(cur_close - cur_atr * sl_mult, 5)
            tp = round(cur_close + cur_atr * tp_mult, 5)
            return Signal(action='buy', symbol=symbol, strength=0.85,
                          stop_loss=sl, take_profit=tp, indicators=indicators,
                          reason=f"Bullish breakout: {cur_close:.5f} > {ch_p}-bar high={cur_upper:.5f}, ADX={cur_adx:.1f}")

        if cur_close < cur_lower and abs(cur_lower - cur_close) >= cur_atr * min_bo and adx_ok and vol_ok:
            sl = round(cur_close + cur_atr * sl_mult, 5)
            tp = round(cur_close - cur_atr * tp_mult, 5)
            return Signal(action='sell', symbol=symbol, strength=0.85,
                          stop_loss=sl, take_profit=tp, indicators=indicators,
                          reason=f"Bearish breakout: {cur_close:.5f} < {ch_p}-bar low={cur_lower:.5f}, ADX={cur_adx:.1f}")

        return Signal(action='hold', symbol=symbol, indicators=indicators,
                      reason=f"Price inside channel [{cur_lower:.5f}–{cur_upper:.5f}], ADX={cur_adx:.1f}")