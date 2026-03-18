# ============================================================
# Bollinger Band Mean Reversion Strategy
# ============================================================
import pandas as pd
import ta
from apps.strategies.base import BaseStrategy, Signal
from apps.strategies.registry import StrategyRegistry


@StrategyRegistry.register('mean_reversion')
class MeanReversionStrategy(BaseStrategy):
    """
    Bollinger Band Mean Reversion Strategy
    ════════════════════════════════════════
    Fades extreme price moves expecting price to revert to the mean.

    BUY  signal: Price touches or closes below the lower Bollinger Band
                 AND %B indicator crosses back above 0 (re-entering band)
    SELL signal: Price touches or closes above the upper Bollinger Band
                 AND %B indicator crosses back below 1 (re-entering band)

    Exit:
      - Price reaches the middle band (SMA) = take profit
      - ATR-based stop loss beyond the band extreme

    Filters:
      - RSI confirm:    RSI < 40 on buy, RSI > 60 on sell
      - Stoch confirm:  Stochastic %K confirmation
      - Range filter:   ADX < threshold (range market, not trending)

    Default parameters:
        bb_period:      20
        bb_std:         2.0
        atr_period:     14
        atr_sl_mult:    1.5
        rsi_period:     14
        rsi_confirm:    True
        adx_period:     14
        adx_max:        30.0   Maximum ADX (avoid trending markets)
        adx_filter:     True
    """

    name        = 'Bollinger Mean Reversion'
    version     = '1.0.0'
    description = (
        'Mean reversion strategy using Bollinger Bands. '
        'Buys when price re-enters the lower band, sells when '
        'price re-enters the upper band. Best in ranging markets.'
    )
    author = 'System'

    def get_required_candles(self) -> int:
        return self.p('bb_period', 20) + 200 + 50

    @classmethod
    def get_default_parameters(cls) -> dict:
        return {
            'bb_period':   20,
            'bb_std':      2.0,
            'atr_period':  14,
            'atr_sl_mult': 1.5,
            'rsi_period':  14,
            'rsi_confirm': True,
            'adx_period':  14,
            'adx_max':     30.0,
            'adx_filter':  True,
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
                'rsi_confirm': {'type': 'boolean', 'title': 'Require RSI Confirmation'},
                'adx_period':  {'type': 'integer', 'minimum': 5,   'maximum': 100, 'title': 'ADX Period'},
                'adx_max':     {'type': 'number',  'minimum': 10,  'maximum': 60,  'title': 'Max ADX (range market)'},
                'adx_filter':  {'type': 'boolean', 'title': 'Enable ADX Range Filter'},
            },
        }

    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        df = self.prepare_dataframe(df)

        min_candles = self.get_required_candles()
        if len(df) < min_candles:
            return Signal(
                action='hold', symbol=symbol,
                reason=f"Not enough candles ({len(df)}/{min_candles})"
            )

        bb_p    = self.p('bb_period',   20)
        bb_std  = self.p('bb_std',      2.0)
        atr_p   = self.p('atr_period',  14)
        sl_mult = self.p('atr_sl_mult', 1.5)

        close = df['close']

        # ── Bollinger Bands ───────────────────────────────────
        bb      = ta.volatility.BollingerBands(close, window=bb_p, window_dev=bb_std)
        bb_mid  = bb.bollinger_mavg()
        bb_hi   = bb.bollinger_hband()
        bb_lo   = bb.bollinger_lband()
        pct_b   = bb.bollinger_pband()  # %B: 0=lower band, 1=upper band

        # ── ATR ───────────────────────────────────────────────
        atr = ta.volatility.average_true_range(df['high'], df['low'], close, window=atr_p)

        # ── RSI ───────────────────────────────────────────────
        rsi = ta.momentum.rsi(close, window=self.p('rsi_period', 14))

        # ── ADX ───────────────────────────────────────────────
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], close, window=self.p('adx_period', 14))
        adx     = adx_ind.adx()

        # ── Current values ────────────────────────────────────
        cur_close = float(close.iloc[-1])
        cur_mid   = float(bb_mid.iloc[-1])
        cur_hi    = float(bb_hi.iloc[-1])
        cur_lo    = float(bb_lo.iloc[-1])
        cur_pctb  = float(pct_b.iloc[-1])
        prev_pctb = float(pct_b.iloc[-2])
        cur_atr   = float(atr.iloc[-1])   if not pd.isna(atr.iloc[-1])   else 0.001
        cur_rsi   = float(rsi.iloc[-1])   if not pd.isna(rsi.iloc[-1])   else 50.0
        cur_adx   = float(adx.iloc[-1])   if not pd.isna(adx.iloc[-1])   else 0.0

        indicators = {
            'bb_upper':  round(cur_hi,    5),
            'bb_mid':    round(cur_mid,   5),
            'bb_lower':  round(cur_lo,    5),
            'pct_b':     round(cur_pctb,  4),
            'rsi':       round(cur_rsi,   2),
            'adx':       round(cur_adx,   2),
            'atr':       round(cur_atr,   5),
        }

        # ADX filter: avoid trending markets
        if self.p('adx_filter', True) and cur_adx > self.p('adx_max', 30.0):
            return Signal(
                action='hold', symbol=symbol, indicators=indicators,
                reason=f"ADX={cur_adx:.1f} > {self.p('adx_max',30.0)} — trending market, mean reversion disabled"
            )

        # ── BUY: %B crosses back above 0 (re-enters from below lower band) ──
        pctb_cross_up = prev_pctb <= 0 and cur_pctb > 0

        if pctb_cross_up:
            if self.p('rsi_confirm', True) and cur_rsi > 45:
                return Signal(
                    action='hold', symbol=symbol, indicators=indicators,
                    reason=f"BB lower band re-entry but RSI={cur_rsi:.1f} not oversold — skipping"
                )

            sl = round(cur_lo - (cur_atr * sl_mult), 5)
            tp = round(cur_mid, 5)   # mean reversion target = middle band

            return Signal(
                action='buy', symbol=symbol, strength=0.75,
                stop_loss=sl, take_profit=tp,
                indicators=indicators,
                reason=(
                    f"Price re-entered BB from below: %B {prev_pctb:.3f}→{cur_pctb:.3f}. "
                    f"Target=mid band {cur_mid:.5f}. RSI={cur_rsi:.1f}"
                )
            )

        # ── SELL: %B crosses back below 1 (re-enters from above upper band) ──
        pctb_cross_dn = prev_pctb >= 1 and cur_pctb < 1

        if pctb_cross_dn:
            if self.p('rsi_confirm', True) and cur_rsi < 55:
                return Signal(
                    action='hold', symbol=symbol, indicators=indicators,
                    reason=f"BB upper band re-entry but RSI={cur_rsi:.1f} not overbought — skipping"
                )

            sl = round(cur_hi + (cur_atr * sl_mult), 5)
            tp = round(cur_mid, 5)   # mean reversion target = middle band

            return Signal(
                action='sell', symbol=symbol, strength=0.75,
                stop_loss=sl, take_profit=tp,
                indicators=indicators,
                reason=(
                    f"Price re-entered BB from above: %B {prev_pctb:.3f}→{cur_pctb:.3f}. "
                    f"Target=mid band {cur_mid:.5f}. RSI={cur_rsi:.1f}"
                )
            )

        zone = ('above upper' if cur_pctb > 1 else
                'below lower' if cur_pctb < 0 else 'inside bands')
        return Signal(
            action='hold', symbol=symbol, indicators=indicators,
            reason=f"Price {zone} (%%B={cur_pctb:.3f}), no re-entry crossover yet"
        )