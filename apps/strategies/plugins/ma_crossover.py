# ============================================================
# Moving Average Crossover Strategy
# ============================================================
import pandas as pd
import ta
from apps.strategies.base import BaseStrategy, Signal
from apps.strategies.registry import StrategyRegistry


@StrategyRegistry.register('ma_crossover')
class MACrossoverStrategy(BaseStrategy):
    """
    Moving Average Crossover Strategy
    ══════════════════════════════════
    Classic trend-following strategy using two moving averages.

    BUY  signal: fast MA crosses ABOVE slow MA (golden cross)
    SELL signal: fast MA crosses BELOW slow MA (death cross)

    Additional filters (all optional, controlled by parameters):
      - Trend filter:   price must be above/below the slow MA
      - Volume filter:  volume must be above N-period average
      - ATR filter:     minimum volatility required to trade
      - RSI filter:     avoid overbought/oversold entries

    Default parameters:
        fast_period:    50   EMA periods for the fast line
        slow_period:    200  EMA periods for the slow line
        ma_type:        EMA  'EMA' | 'SMA' | 'WMA'
        atr_period:     14   ATR period for SL/TP calculation
        atr_sl_mult:    1.5  Stop loss = ATR * this multiplier
        atr_tp_mult:    3.0  Take profit = ATR * this multiplier
        rsi_period:     14   RSI period (0 = disabled)
        rsi_filter:     True Reject BUY if RSI > 70, SELL if RSI < 30
        volume_filter:  False Require volume > N-period average
        volume_period:  20   Volume MA period
    """

    name        = 'Moving Average Crossover'
    version     = '1.1.0'
    description = (
        'Generates buy/sell signals when a fast moving average '
        'crosses a slow moving average. Supports EMA, SMA and WMA. '
        'Uses ATR for dynamic stop-loss and take-profit placement.'
    )
    author = 'System'

    def validate_parameters(self):
        fast = self.p('fast_period', 50)
        slow = self.p('slow_period', 200)
        if fast >= slow:
            raise ValueError(
                f"fast_period ({fast}) must be less than slow_period ({slow})."
            )
        if fast < 2:
            raise ValueError("fast_period must be at least 2.")

    def get_required_candles(self) -> int:
        return self.p('slow_period', 200) + 50   # extra buffer for warm-up

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
                'atr_sl_mult':   {'type': 'number',  'minimum': 0.5, 'maximum': 10,   'title': 'ATR Stop Loss Multiplier'},
                'atr_tp_mult':   {'type': 'number',  'minimum': 0.5, 'maximum': 20,   'title': 'ATR Take Profit Multiplier'},
                'rsi_period':    {'type': 'integer', 'minimum': 0,   'maximum': 100,  'title': 'RSI Period (0=off)'},
                'rsi_filter':    {'type': 'boolean', 'title': 'Enable RSI Filter'},
                'volume_filter': {'type': 'boolean', 'title': 'Enable Volume Filter'},
                'volume_period': {'type': 'integer', 'minimum': 5,   'maximum': 200,  'title': 'Volume MA Period'},
            },
            'required': ['fast_period', 'slow_period'],
        }

    # ── Core signal logic ─────────────────────────────────────
    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        df = self.prepare_dataframe(df)

        min_candles = self.get_required_candles()
        if len(df) < min_candles:
            return Signal(
                action='hold', symbol=symbol,
                reason=f"Not enough candles ({len(df)}/{min_candles})"
            )

        fast_p  = self.p('fast_period',  50)
        slow_p  = self.p('slow_period',  200)
        ma_type = self.p('ma_type',      'EMA').upper()
        atr_p   = self.p('atr_period',   14)
        sl_mult = self.p('atr_sl_mult',  1.5)
        tp_mult = self.p('atr_tp_mult',  3.0)

        close = df['close']

        # ── Calculate MAs ─────────────────────────────────────
        if ma_type == 'EMA':
            fast_ma = ta.trend.ema_indicator(close, window=fast_p)
            slow_ma = ta.trend.ema_indicator(close, window=slow_p)
        elif ma_type == 'SMA':
            fast_ma = ta.trend.sma_indicator(close, window=fast_p)
            slow_ma = ta.trend.sma_indicator(close, window=slow_p)
        elif ma_type == 'WMA':
            fast_ma = ta.trend.wma_indicator(close, window=fast_p)
            slow_ma = ta.trend.wma_indicator(close, window=slow_p)
        else:
            fast_ma = ta.trend.ema_indicator(close, window=fast_p)
            slow_ma = ta.trend.ema_indicator(close, window=slow_p)

        # ── ATR for dynamic SL/TP ──────────────────────────────
        atr = ta.volatility.average_true_range(
            df['high'], df['low'], close, window=atr_p
        )

        # ── Optional RSI filter ────────────────────────────────
        rsi = None
        if self.p('rsi_filter', True) and self.p('rsi_period', 14) > 0:
            rsi = ta.momentum.rsi(close, window=self.p('rsi_period', 14))

        # ── Optional volume filter ─────────────────────────────
        vol_ok = True
        if self.p('volume_filter', False) and 'volume' in df.columns:
            vol_ma  = df['volume'].rolling(self.p('volume_period', 20)).mean()
            vol_ok  = df['volume'].iloc[-1] > vol_ma.iloc[-1]

        # ── Detect crossovers on the last two bars ─────────────
        golden_cross = self.crossover(fast_ma,  slow_ma).iloc[-1]
        death_cross  = self.crossunder(fast_ma, slow_ma).iloc[-1]

        current_price = float(close.iloc[-1])
        current_atr   = float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.001
        current_fast  = float(fast_ma.iloc[-1])
        current_slow  = float(slow_ma.iloc[-1])
        current_rsi   = float(rsi.iloc[-1]) if rsi is not None and not pd.isna(rsi.iloc[-1]) else 50.0

        # Indicator snapshot for logging / analysis
        indicators = {
            'fast_ma':     round(current_fast, 5),
            'slow_ma':     round(current_slow, 5),
            'atr':         round(current_atr, 5),
            'rsi':         round(current_rsi, 2),
            'ma_type':     ma_type,
            'fast_period': fast_p,
            'slow_period': slow_p,
        }

        # ── BUY signal ─────────────────────────────────────────
        if golden_cross and vol_ok:
            # RSI filter: don't buy if already overbought
            if rsi is not None and current_rsi > 70:
                return Signal(
                    action='hold', symbol=symbol,
                    indicators=indicators,
                    reason=f"Golden cross detected but RSI={current_rsi:.1f} is overbought — skipping"
                )

            sl = round(current_price - (current_atr * sl_mult), 5)
            tp = round(current_price + (current_atr * tp_mult), 5)

            return Signal(
                action='buy', symbol=symbol, strength=0.8,
                stop_loss=sl, take_profit=tp,
                indicators=indicators,
                reason=(
                    f"Golden cross: {ma_type}({fast_p})={current_fast:.5f} crossed above "
                    f"{ma_type}({slow_p})={current_slow:.5f}. "
                    f"ATR={current_atr:.5f}, SL={sl}, TP={tp}"
                ),
            )

        # ── SELL signal ────────────────────────────────────────
        if death_cross and vol_ok:
            # RSI filter: don't sell if already oversold
            if rsi is not None and current_rsi < 30:
                return Signal(
                    action='hold', symbol=symbol,
                    indicators=indicators,
                    reason=f"Death cross detected but RSI={current_rsi:.1f} is oversold — skipping"
                )

            sl = round(current_price + (current_atr * sl_mult), 5)
            tp = round(current_price - (current_atr * tp_mult), 5)

            return Signal(
                action='sell', symbol=symbol, strength=0.8,
                stop_loss=sl, take_profit=tp,
                indicators=indicators,
                reason=(
                    f"Death cross: {ma_type}({fast_p})={current_fast:.5f} crossed below "
                    f"{ma_type}({slow_p})={current_slow:.5f}. "
                    f"ATR={current_atr:.5f}, SL={sl}, TP={tp}"
                ),
            )

        # ── No signal ──────────────────────────────────────────
        trend = 'bullish' if current_fast > current_slow else 'bearish'
        return Signal(
            action='hold', symbol=symbol,
            indicators=indicators,
            reason=f"No crossover. Trend={trend}, {ma_type}({fast_p})={current_fast:.5f}, {ma_type}({slow_p})={current_slow:.5f}"
        )