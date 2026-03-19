
import pandas as pd
import ta
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry


@StrategyRegistry.register('ma_crossover')
class MACrossoverStrategy(BaseStrategy):
    """
    Moving Average Crossover Strategy
    BUY  when fast MA crosses ABOVE slow MA (golden cross)
    SELL when fast MA crosses BELOW slow MA (death cross)
    Uses ATR for dynamic SL/TP. Optional RSI and volume filters.
    """

    name        = 'Moving Average Crossover'
    version     = '1.1.0'
    description = (
        'Generates buy/sell signals when a fast moving average crosses '
        'a slow moving average. Supports EMA, SMA and WMA. '
        'Uses ATR for dynamic stop-loss and take-profit placement.'
    )

    def validate_parameters(self):
        fast = self.p('fast_period', 50)
        slow = self.p('slow_period', 200)
        if fast >= slow:
            raise ValueError(f"fast_period ({fast}) must be less than slow_period ({slow}).")
        if fast < 2:
            raise ValueError("fast_period must be at least 2.")

    def get_required_candles(self) -> int:
        return self.p('slow_period', 200) + 50

    @classmethod
    def get_default_parameters(cls) -> dict:
        return {
            'fast_period':   50,
            'slow_period':   200,
            'ma_type':       'EMA',
            'atr_period':    14,
            'atr_sl_mult':   1.5,
            'atr_tp_mult':   3.0,
            'rsi_period':    14,
            'rsi_filter':    True,
            'volume_filter': False,
            'volume_period': 20,
        }

    @classmethod
    def get_parameter_schema(cls) -> dict:
        return {
            'type': 'object',
            'properties': {
                'fast_period':   {'type': 'integer', 'minimum': 2,   'maximum': 500,  'title': 'Fast MA Period'},
                'slow_period':   {'type': 'integer', 'minimum': 5,   'maximum': 2000, 'title': 'Slow MA Period'},
                'ma_type':       {'type': 'string',  'enum': ['EMA', 'SMA', 'WMA'],   'title': 'MA Type'},
                'atr_period':    {'type': 'integer', 'minimum': 1,   'maximum': 100,  'title': 'ATR Period'},
                'atr_sl_mult':   {'type': 'number',  'minimum': 0.5, 'maximum': 10,   'title': 'ATR SL Multiplier'},
                'atr_tp_mult':   {'type': 'number',  'minimum': 0.5, 'maximum': 20,   'title': 'ATR TP Multiplier'},
                'rsi_period':    {'type': 'integer', 'minimum': 0,   'maximum': 100,  'title': 'RSI Period (0=off)'},
                'rsi_filter':    {'type': 'boolean', 'title': 'Enable RSI Filter'},
                'volume_filter': {'type': 'boolean', 'title': 'Enable Volume Filter'},
                'volume_period': {'type': 'integer', 'minimum': 5,   'maximum': 200,  'title': 'Volume MA Period'},
            },
            'required': ['fast_period', 'slow_period'],
        }

    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        df = self.prepare_dataframe(df)
        min_c = self.get_required_candles()
        if len(df) < min_c:
            return Signal(action='hold', symbol=symbol,
                          reason=f"Not enough candles ({len(df)}/{min_c})")

        fast_p  = self.p('fast_period',  50)
        slow_p  = self.p('slow_period',  200)
        ma_type = self.p('ma_type',      'EMA').upper()
        atr_p   = self.p('atr_period',   14)
        sl_mult = self.p('atr_sl_mult',  1.5)
        tp_mult = self.p('atr_tp_mult',  3.0)
        close   = df['close']

        # Moving averages
        if ma_type == 'SMA':
            fast_ma = ta.trend.sma_indicator(close, window=fast_p)
            slow_ma = ta.trend.sma_indicator(close, window=slow_p)
        elif ma_type == 'WMA':
            fast_ma = ta.trend.wma_indicator(close, window=fast_p)
            slow_ma = ta.trend.wma_indicator(close, window=slow_p)
        else:  # EMA default
            fast_ma = ta.trend.ema_indicator(close, window=fast_p)
            slow_ma = ta.trend.ema_indicator(close, window=slow_p)

        atr = ta.volatility.average_true_range(df['high'], df['low'], close, window=atr_p)

        rsi = None
        if self.p('rsi_filter', True) and self.p('rsi_period', 14) > 0:
            rsi = ta.momentum.rsi(close, window=self.p('rsi_period', 14))

        vol_ok = True
        if self.p('volume_filter', False) and 'volume' in df.columns:
            vol_ma = df['volume'].rolling(self.p('volume_period', 20)).mean()
            vol_ok = df['volume'].iloc[-1] > vol_ma.iloc[-1]

        golden_cross = self.crossover(fast_ma,  slow_ma).iloc[-1]
        death_cross  = self.crossunder(fast_ma, slow_ma).iloc[-1]

        price     = float(close.iloc[-1])
        cur_atr   = float(atr.iloc[-1])   if not pd.isna(atr.iloc[-1])          else 0.001
        cur_fast  = float(fast_ma.iloc[-1])
        cur_slow  = float(slow_ma.iloc[-1])
        cur_rsi   = float(rsi.iloc[-1])   if rsi is not None and not pd.isna(rsi.iloc[-1]) else 50.0

        indicators = {
            'fast_ma': round(cur_fast, 5), 'slow_ma': round(cur_slow, 5),
            'atr': round(cur_atr, 5),      'rsi': round(cur_rsi, 2),
            'ma_type': ma_type, 'fast_period': fast_p, 'slow_period': slow_p,
        }

        if golden_cross and vol_ok:
            if rsi is not None and cur_rsi > 70:
                return Signal(action='hold', symbol=symbol, indicators=indicators,
                              reason=f"Golden cross but RSI={cur_rsi:.1f} overbought")
            sl = round(price - cur_atr * sl_mult, 5)
            tp = round(price + cur_atr * tp_mult, 5)
            return Signal(action='buy', symbol=symbol, strength=0.8,
                          stop_loss=sl, take_profit=tp, indicators=indicators,
                          reason=f"Golden cross: {ma_type}({fast_p})={cur_fast:.5f} > {ma_type}({slow_p})={cur_slow:.5f}")

        if death_cross and vol_ok:
            if rsi is not None and cur_rsi < 30:
                return Signal(action='hold', symbol=symbol, indicators=indicators,
                              reason=f"Death cross but RSI={cur_rsi:.1f} oversold")
            sl = round(price + cur_atr * sl_mult, 5)
            tp = round(price - cur_atr * tp_mult, 5)
            return Signal(action='sell', symbol=symbol, strength=0.8,
                          stop_loss=sl, take_profit=tp, indicators=indicators,
                          reason=f"Death cross: {ma_type}({fast_p})={cur_fast:.5f} < {ma_type}({slow_p})={cur_slow:.5f}")

        trend = 'bullish' if cur_fast > cur_slow else 'bearish'
        return Signal(action='hold', symbol=symbol, indicators=indicators,
                      reason=f"No crossover. Trend={trend}")