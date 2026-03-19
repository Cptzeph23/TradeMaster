
import pandas as pd
import ta
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry


@StrategyRegistry.register('rsi_reversal')
class RSIReversalStrategy(BaseStrategy):
    """
    RSI Reversal — buys oversold crossovers, sells overbought crossovers.
    Optional 200 EMA trend filter and Bollinger Band proximity filter.
    """
    name        = 'RSI Reversal'
    version     = '1.0.0'
    description = (
        'Counter-trend strategy using RSI overbought/oversold levels. '
        'Buys when RSI crosses back above the oversold threshold, '
        'sells when RSI crosses back below the overbought threshold.'
    )

    def validate_parameters(self):
        os  = self.p('oversold',   30)
        ob  = self.p('overbought', 70)
        if os >= ob:
            raise ValueError(f"oversold ({os}) must be less than overbought ({ob}).")

    def get_required_candles(self) -> int:
        return max(self.p('rsi_period', 14), 200) + 50

    @classmethod
    def get_default_parameters(cls) -> dict:
        return {
            'rsi_period': 14, 'oversold': 30, 'overbought': 70,
            'atr_period': 14, 'atr_sl_mult': 1.2, 'atr_tp_mult': 2.0,
            'trend_filter': True, 'bb_filter': False,
            'bb_period': 20,  'bb_std': 2.0,
        }

    @classmethod
    def get_parameter_schema(cls) -> dict:
        return {
            'type': 'object',
            'properties': {
                'rsi_period':   {'type': 'integer', 'minimum': 2,   'maximum': 100, 'title': 'RSI Period'},
                'oversold':     {'type': 'number',  'minimum': 5,   'maximum': 45,  'title': 'Oversold Level'},
                'overbought':   {'type': 'number',  'minimum': 55,  'maximum': 95,  'title': 'Overbought Level'},
                'atr_period':   {'type': 'integer', 'minimum': 1,   'maximum': 100, 'title': 'ATR Period'},
                'atr_sl_mult':  {'type': 'number',  'minimum': 0.5, 'maximum': 10,  'title': 'ATR SL Multiplier'},
                'atr_tp_mult':  {'type': 'number',  'minimum': 0.5, 'maximum': 20,  'title': 'ATR TP Multiplier'},
                'trend_filter': {'type': 'boolean', 'title': 'Enable 200 EMA Trend Filter'},
                'bb_filter':    {'type': 'boolean', 'title': 'Enable Bollinger Band Filter'},
            },
            'required': ['rsi_period', 'oversold', 'overbought'],
        }

    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        df = self.prepare_dataframe(df)
        min_c = self.get_required_candles()
        if len(df) < min_c:
            return Signal(action='hold', symbol=symbol,
                          reason=f"Not enough candles ({len(df)}/{min_c})")

        close   = df['close']
        rsi     = ta.momentum.rsi(close, window=self.p('rsi_period', 14))
        atr     = ta.volatility.average_true_range(df['high'], df['low'], close,
                                                   window=self.p('atr_period', 14))
        ema200  = ta.trend.ema_indicator(close, window=200)

        cur_rsi  = float(rsi.iloc[-1]);    prev_rsi = float(rsi.iloc[-2])
        cur_px   = float(close.iloc[-1])
        cur_atr  = float(atr.iloc[-1])    if not pd.isna(atr.iloc[-1])   else 0.001
        cur_ema  = float(ema200.iloc[-1]) if not pd.isna(ema200.iloc[-1]) else 0.0
        os_lvl   = self.p('oversold', 30);  ob_lvl = self.p('overbought', 70)
        sl_mult  = self.p('atr_sl_mult', 1.2); tp_mult = self.p('atr_tp_mult', 2.0)

        indicators = {
            'rsi': round(cur_rsi, 2), 'rsi_prev': round(prev_rsi, 2),
            'ema200': round(cur_ema, 5), 'atr': round(cur_atr, 5),
            'oversold': os_lvl, 'overbought': ob_lvl,
        }

        rsi_cross_up   = prev_rsi <= os_lvl and cur_rsi > os_lvl
        rsi_cross_down = prev_rsi >= ob_lvl and cur_rsi < ob_lvl

        if rsi_cross_up:
            if self.p('trend_filter', True) and cur_px < cur_ema:
                return Signal(action='hold', symbol=symbol, indicators=indicators,
                              reason=f"RSI oversold crossover but price below EMA200 — skipping")
            sl = round(cur_px - cur_atr * sl_mult, 5)
            tp = round(cur_px + cur_atr * tp_mult, 5)
            return Signal(action='buy', symbol=symbol, strength=0.75,
                          stop_loss=sl, take_profit=tp, indicators=indicators,
                          reason=f"RSI crossed above oversold: {prev_rsi:.1f}→{cur_rsi:.1f} (threshold={os_lvl})")

        if rsi_cross_down:
            if self.p('trend_filter', True) and cur_px > cur_ema:
                return Signal(action='hold', symbol=symbol, indicators=indicators,
                              reason=f"RSI overbought crossover but price above EMA200 — skipping")
            sl = round(cur_px + cur_atr * sl_mult, 5)
            tp = round(cur_px - cur_atr * tp_mult, 5)
            return Signal(action='sell', symbol=symbol, strength=0.75,
                          stop_loss=sl, take_profit=tp, indicators=indicators,
                          reason=f"RSI crossed below overbought: {prev_rsi:.1f}→{cur_rsi:.1f} (threshold={ob_lvl})")

        zone = 'overbought' if cur_rsi > ob_lvl else ('oversold' if cur_rsi < os_lvl else 'neutral')
        return Signal(action='hold', symbol=symbol, indicators=indicators,
                      reason=f"RSI={cur_rsi:.1f} — {zone}, waiting for crossover")