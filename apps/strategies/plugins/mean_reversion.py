
import pandas as pd
import ta
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry


@StrategyRegistry.register('mean_reversion')
class MeanReversionStrategy(BaseStrategy):
    """Bollinger Band Mean Reversion — fades extremes back to the mean."""
    name        = 'Bollinger Mean Reversion'
    version     = '1.0.0'
    description = (
        'Mean reversion strategy using Bollinger Bands. '
        'Buys when price re-enters the lower band, sells when '
        'price re-enters the upper band. Best in ranging markets.'
    )

    def get_required_candles(self) -> int:
        return self.p('bb_period', 20) + 200 + 50

    @classmethod
    def get_default_parameters(cls) -> dict:
        return {
            'bb_period': 20, 'bb_std': 2.0,
            'atr_period': 14, 'atr_sl_mult': 1.5,
            'rsi_period': 14, 'rsi_confirm': True,
            'adx_period': 14, 'adx_max': 30.0, 'adx_filter': True,
        }

    @classmethod
    def get_parameter_schema(cls) -> dict:
        return {
            'type': 'object',
            'properties': {
                'bb_period':   {'type': 'integer', 'minimum': 5,   'maximum': 200, 'title': 'BB Period'},
                'bb_std':      {'type': 'number',  'minimum': 1.0, 'maximum': 4.0, 'title': 'BB Std Devs'},
                'atr_period':  {'type': 'integer', 'minimum': 1,   'maximum': 100, 'title': 'ATR Period'},
                'atr_sl_mult': {'type': 'number',  'minimum': 0.5, 'maximum': 10,  'title': 'ATR SL Multiplier'},
                'rsi_period':  {'type': 'integer', 'minimum': 2,   'maximum': 100, 'title': 'RSI Period'},
                'rsi_confirm': {'type': 'boolean', 'title': 'RSI Confirmation'},
                'adx_period':  {'type': 'integer', 'minimum': 5,   'maximum': 100, 'title': 'ADX Period'},
                'adx_max':     {'type': 'number',  'minimum': 10,  'maximum': 60,  'title': 'Max ADX'},
                'adx_filter':  {'type': 'boolean', 'title': 'ADX Range Filter'},
            },
        }

    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        df = self.prepare_dataframe(df)
        min_c = self.get_required_candles()
        if len(df) < min_c:
            return Signal(action='hold', symbol=symbol,
                          reason=f"Not enough candles ({len(df)}/{min_c})")

        close   = df['close']
        bb      = ta.volatility.BollingerBands(close,
                      window=self.p('bb_period', 20), window_dev=self.p('bb_std', 2.0))
        bb_mid  = bb.bollinger_mavg()
        bb_hi   = bb.bollinger_hband()
        bb_lo   = bb.bollinger_lband()
        pct_b   = bb.bollinger_pband()
        atr     = ta.volatility.average_true_range(df['high'], df['low'], close,
                      window=self.p('atr_period', 14))
        rsi     = ta.momentum.rsi(close, window=self.p('rsi_period', 14))
        adx     = ta.trend.ADXIndicator(df['high'], df['low'], close,
                      window=self.p('adx_period', 14)).adx()

        cur_mid   = float(bb_mid.iloc[-1]); cur_hi = float(bb_hi.iloc[-1])
        cur_lo    = float(bb_lo.iloc[-1])
        cur_pctb  = float(pct_b.iloc[-1]);  prev_pctb = float(pct_b.iloc[-2])
        cur_atr   = float(atr.iloc[-1])   if not pd.isna(atr.iloc[-1])  else 0.001
        cur_rsi   = float(rsi.iloc[-1])   if not pd.isna(rsi.iloc[-1])  else 50.0
        cur_adx   = float(adx.iloc[-1])   if not pd.isna(adx.iloc[-1])  else 0.0

        indicators = {
            'bb_upper': round(cur_hi, 5), 'bb_mid': round(cur_mid, 5),
            'bb_lower': round(cur_lo, 5), 'pct_b': round(cur_pctb, 4),
            'rsi': round(cur_rsi, 2),     'adx': round(cur_adx, 2),
        }

        if self.p('adx_filter', True) and cur_adx > self.p('adx_max', 30.0):
            return Signal(action='hold', symbol=symbol, indicators=indicators,
                          reason=f"ADX={cur_adx:.1f} — trending market, mean reversion disabled")

        if prev_pctb <= 0 and cur_pctb > 0:
            if self.p('rsi_confirm', True) and cur_rsi > 45:
                return Signal(action='hold', symbol=symbol, indicators=indicators,
                              reason=f"BB lower re-entry but RSI={cur_rsi:.1f} not oversold")
            sl = round(cur_lo - cur_atr * self.p('atr_sl_mult', 1.5), 5)
            return Signal(action='buy', symbol=symbol, strength=0.75,
                          stop_loss=sl, take_profit=round(cur_mid, 5),
                          indicators=indicators,
                          reason=f"Price re-entered BB from below. Target=mid {cur_mid:.5f}, RSI={cur_rsi:.1f}")

        if prev_pctb >= 1 and cur_pctb < 1:
            if self.p('rsi_confirm', True) and cur_rsi < 55:
                return Signal(action='hold', symbol=symbol, indicators=indicators,
                              reason=f"BB upper re-entry but RSI={cur_rsi:.1f} not overbought")
            sl = round(cur_hi + cur_atr * self.p('atr_sl_mult', 1.5), 5)
            return Signal(action='sell', symbol=symbol, strength=0.75,
                          stop_loss=sl, take_profit=round(cur_mid, 5),
                          indicators=indicators,
                          reason=f"Price re-entered BB from above. Target=mid {cur_mid:.5f}, RSI={cur_rsi:.1f}")

        return Signal(action='hold', symbol=symbol, indicators=indicators,
                      reason=f"%%B={cur_pctb:.3f}, no re-entry crossover")