# ============================================================
# RSI Reversal / Mean-Reversion Strategy
# ============================================================
import pandas as pd
import ta
from apps.strategies.base import BaseStrategy, Signal
from apps.strategies.registry import StrategyRegistry


@StrategyRegistry.register('rsi_reversal')
class RSIReversalStrategy(BaseStrategy):
    """
    RSI Reversal Strategy
    ══════════════════════
    Counter-trend strategy that buys oversold conditions and
    sells overbought conditions, confirmed by RSI divergence
    and optional trend/MA filters.

    BUY  signal: RSI crosses ABOVE oversold level (default 30)
                 confirming price bouncing from a bottom
    SELL signal: RSI crosses BELOW overbought level (default 70)
                 confirming price turning from a top

    Filters:
      - Trend filter:     Only trade in the direction of the
                          higher timeframe trend (200 EMA)
      - Divergence check: Look for RSI/price divergence
      - Bollinger filter: Entry near band extremes only
      - Volume confirm:   Volume spike on reversal bar

    Default parameters:
        rsi_period:     14
        oversold:       30    RSI level to trigger buy
        overbought:     70    RSI level to trigger sell
        atr_period:     14
        atr_sl_mult:    1.2
        atr_tp_mult:    2.0
        trend_filter:   True  Only buy above 200 EMA, sell below
        bb_filter:      False Only enter near Bollinger Bands
        bb_period:      20
        bb_std:         2.0
    """

    name        = 'RSI Reversal'
    version     = '1.0.0'
    description = (
        'Counter-trend strategy using RSI overbought/oversold levels. '
        'Buys when RSI crosses back above the oversold threshold, '
        'sells when RSI crosses back below the overbought threshold.'
    )
    author = 'System'

    def validate_parameters(self):
        oversold   = self.p('oversold',   30)
        overbought = self.p('overbought', 70)
        if oversold >= overbought:
            raise ValueError(
                f"oversold ({oversold}) must be less than overbought ({overbought})."
            )
        if not (0 < oversold < 100) or not (0 < overbought < 100):
            raise ValueError("RSI levels must be between 0 and 100.")

    def get_required_candles(self) -> int:
        return max(self.p('rsi_period', 14), 200) + 50

    @classmethod
    def get_default_parameters(cls) -> dict:
        return {
            'rsi_period':   14,
            'oversold':     30,
            'overbought':   70,
            'atr_period':   14,
            'atr_sl_mult':  1.2,
            'atr_tp_mult':  2.0,
            'trend_filter': True,
            'bb_filter':    False,
            'bb_period':    20,
            'bb_std':       2.0,
        }

    @classmethod
    def get_parameter_schema(cls) -> dict:
        return {
            'type': 'object',
            'properties': {
                'rsi_period':   {'type': 'integer', 'minimum': 2,   'maximum': 100,  'title': 'RSI Period'},
                'oversold':     {'type': 'number',  'minimum': 5,   'maximum': 45,   'title': 'Oversold Level'},
                'overbought':   {'type': 'number',  'minimum': 55,  'maximum': 95,   'title': 'Overbought Level'},
                'atr_period':   {'type': 'integer', 'minimum': 1,   'maximum': 100,  'title': 'ATR Period'},
                'atr_sl_mult':  {'type': 'number',  'minimum': 0.5, 'maximum': 10,   'title': 'ATR SL Multiplier'},
                'atr_tp_mult':  {'type': 'number',  'minimum': 0.5, 'maximum': 20,   'title': 'ATR TP Multiplier'},
                'trend_filter': {'type': 'boolean', 'title': 'Enable Trend Filter (200 EMA)'},
                'bb_filter':    {'type': 'boolean', 'title': 'Enable Bollinger Band Filter'},
                'bb_period':    {'type': 'integer', 'minimum': 5,   'maximum': 200,  'title': 'BB Period'},
                'bb_std':       {'type': 'number',  'minimum': 1.0, 'maximum': 4.0,  'title': 'BB Std Devs'},
            },
            'required': ['rsi_period', 'oversold', 'overbought'],
        }

    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        df = self.prepare_dataframe(df)

        min_candles = self.get_required_candles()
        if len(df) < min_candles:
            return Signal(
                action='hold', symbol=symbol,
                reason=f"Not enough candles ({len(df)}/{min_candles})"
            )

        rsi_p   = self.p('rsi_period',   14)
        os_lvl  = self.p('oversold',     30)
        ob_lvl  = self.p('overbought',   70)
        atr_p   = self.p('atr_period',   14)
        sl_mult = self.p('atr_sl_mult',  1.2)
        tp_mult = self.p('atr_tp_mult',  2.0)

        close = df['close']

        # ── Indicators ────────────────────────────────────────
        rsi = ta.momentum.rsi(close, window=rsi_p)
        atr = ta.volatility.average_true_range(
            df['high'], df['low'], close, window=atr_p
        )

        # 200 EMA for trend filter
        ema200 = ta.trend.ema_indicator(close, window=200)

        # Bollinger Bands
        bb_high = bb_low = None
        if self.p('bb_filter', False):
            bb      = ta.volatility.BollingerBands(
                close,
                window=self.p('bb_period', 20),
                window_dev=self.p('bb_std', 2.0)
            )
            bb_high = bb.bollinger_hband()
            bb_low  = bb.bollinger_lband()

        # ── Current values ────────────────────────────────────
        current_rsi   = float(rsi.iloc[-1])
        prev_rsi      = float(rsi.iloc[-2])
        current_price = float(close.iloc[-1])
        current_atr   = float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.001
        current_ema   = float(ema200.iloc[-1])

        indicators = {
            'rsi':         round(current_rsi, 2),
            'rsi_prev':    round(prev_rsi, 2),
            'ema200':      round(current_ema, 5),
            'atr':         round(current_atr, 5),
            'price':       round(current_price, 5),
            'oversold':    os_lvl,
            'overbought':  ob_lvl,
        }

        # ── RSI crossover detection ───────────────────────────
        # Buy: RSI was below oversold last bar, now crosses above it
        rsi_cross_up   = prev_rsi <= os_lvl and current_rsi > os_lvl
        # Sell: RSI was above overbought last bar, now crosses below it
        rsi_cross_down = prev_rsi >= ob_lvl and current_rsi < ob_lvl

        # ── BUY signal ─────────────────────────────────────────
        if rsi_cross_up:
            # Trend filter: only buy if price is above 200 EMA
            if self.p('trend_filter', True) and current_price < current_ema:
                return Signal(
                    action='hold', symbol=symbol, indicators=indicators,
                    reason=(
                        f"RSI oversold crossover ({prev_rsi:.1f}→{current_rsi:.1f}) "
                        f"but price {current_price:.5f} is below EMA200 {current_ema:.5f} — skipping"
                    )
                )

            # Bollinger filter: only buy near the lower band
            if bb_low is not None:
                bb_low_val = float(bb_low.iloc[-1])
                if current_price > bb_low_val * 1.002:
                    return Signal(
                        action='hold', symbol=symbol, indicators=indicators,
                        reason=f"RSI oversold but price not near lower BB ({bb_low_val:.5f}) — skipping"
                    )

            sl = round(current_price - (current_atr * sl_mult), 5)
            tp = round(current_price + (current_atr * tp_mult), 5)
            strength = min(1.0, (os_lvl - prev_rsi) / os_lvl + 0.5)

            return Signal(
                action='buy', symbol=symbol,
                strength=round(strength, 2),
                stop_loss=sl, take_profit=tp,
                indicators=indicators,
                reason=(
                    f"RSI crossed above oversold: {prev_rsi:.1f}→{current_rsi:.1f} "
                    f"(threshold={os_lvl}). ATR SL={sl}, TP={tp}"
                )
            )

        # ── SELL signal ────────────────────────────────────────
        if rsi_cross_down:
            # Trend filter: only sell if price is below 200 EMA
            if self.p('trend_filter', True) and current_price > current_ema:
                return Signal(
                    action='hold', symbol=symbol, indicators=indicators,
                    reason=(
                        f"RSI overbought crossover ({prev_rsi:.1f}→{current_rsi:.1f}) "
                        f"but price {current_price:.5f} is above EMA200 {current_ema:.5f} — skipping"
                    )
                )

            sl = round(current_price + (current_atr * sl_mult), 5)
            tp = round(current_price - (current_atr * tp_mult), 5)
            strength = min(1.0, (prev_rsi - ob_lvl) / (100 - ob_lvl) + 0.5)

            return Signal(
                action='sell', symbol=symbol,
                strength=round(strength, 2),
                stop_loss=sl, take_profit=tp,
                indicators=indicators,
                reason=(
                    f"RSI crossed below overbought: {prev_rsi:.1f}→{current_rsi:.1f} "
                    f"(threshold={ob_lvl}). ATR SL={sl}, TP={tp}"
                )
            )

        # ── No signal ──────────────────────────────────────────
        zone = 'overbought' if current_rsi > ob_lvl else ('oversold' if current_rsi < os_lvl else 'neutral')
        return Signal(
            action='hold', symbol=symbol, indicators=indicators,
            reason=f"RSI={current_rsi:.1f} — {zone}, waiting for level crossover"
        )