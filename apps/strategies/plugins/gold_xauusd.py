# ============================================================
# Gold/XAUUSD strategy plugin
#
# XAUUSD-specific logic:
#   - Pip size = 0.01 (built into all calculations via pip engine)
#   - Trades intraday momentum using EMA + RSI + ATR
#   - Respects SL <= 50 pips, ideal 20 pips (client requirement)
#   - RRR enforced by RiskManager before execution
#   - ATR-based dynamic SL/TP scaled to Gold's volatility
#
# Signal logic:
#   BUY:  fast EMA > slow EMA + RSI > 50 + price > ATR channel mid
#         + SL below recent swing low (ATR × 1.5)
#   SELL: fast EMA < slow EMA + RSI < 50 + price < ATR channel mid
#         + SL above recent swing high (ATR × 1.5)
#
#   All SL/TP values are in absolute prices; pip conversion
#   and RRR enforcement happen in utils/risk_manager.py
# ============================================================
import pandas as pd
import numpy as np
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry


@StrategyRegistry.register('gold_xauusd')
class GoldXAUUSDStrategy(BaseStrategy):

    name        = 'Gold XAUUSD'
    description = (
        'XAUUSD-optimised momentum strategy using EMA crossover, '
        'RSI confirmation, and ATR-scaled stops. '
        'Pip size = 0.01. Max SL = 50 pips (0.50 price). '
        'Ideal SL = 20 pips (0.20 price).'
    )
    version     = '1.0.0'
    author      = 'ForexBot Phase 4'

    DEFAULT_PARAMETERS = {
        # EMA periods
        'fast_ema':      9,
        'slow_ema':      21,
        'trend_ema':     50,    # filters direction — only trade with trend

        # RSI
        'rsi_period':    14,
        'rsi_bull':      55,    # RSI must be above this for BUY
        'rsi_bear':      45,    # RSI must be below this for SELL

        # ATR — Gold needs wider ATR mult due to higher volatility
        'atr_period':    14,
        'atr_sl_mult':   1.5,   # SL = ATR × 1.5  (≈ 15–25 pips typically)
        'atr_max_sl':    0.50,  # Hard cap: 50 pips × 0.01 = 0.50 price units

        # RRR — applied by RiskManager, stored here for reference
        'risk_reward':   2.0,   # default 1:2

        # Volume spike filter — Gold spikes on news
        'volume_filter': True,
        'volume_mult':   1.3,   # volume must be > avg × this

        # Session filter — Gold is most active during London/NY overlap
        'session_filter': False,   # set True to restrict to 12:00–20:00 UTC
    }

    def _p(self, key):
        return self.params.get(key, self.DEFAULT_PARAMETERS.get(key))

    def get_required_candles(self) -> int:
        return max(
            int(self._p('trend_ema')) + 10,
            int(self._p('atr_period'))  + 10,
            int(self._p('rsi_period'))  + 10,
        )

    def get_default_parameters(self) -> dict:
        return self.DEFAULT_PARAMETERS.copy()

    def generate_signal(self, df: pd.DataFrame, symbol: str, **kwargs) -> Signal:
        # Gold pip size constant — 1 pip = 0.01
        PIP      = 0.01
        MAX_SL   = float(self._p('atr_max_sl'))   # 0.50 = 50 pips

        fast_p   = int(self._p('fast_ema'))
        slow_p   = int(self._p('slow_ema'))
        trend_p  = int(self._p('trend_ema'))
        rsi_p    = int(self._p('rsi_period'))
        rsi_bull = float(self._p('rsi_bull'))
        rsi_bear = float(self._p('rsi_bear'))
        atr_p    = int(self._p('atr_period'))
        atr_mult = float(self._p('atr_sl_mult'))
        rr       = float(self._p('risk_reward'))
        vol_filt = bool(self._p('volume_filter'))
        vol_mult = float(self._p('volume_mult'))

        if len(df) < self.get_required_candles():
            return Signal(
                action='hold', symbol=symbol, strength=0.0,
                reason='Insufficient candle data'
            )

        close  = df['close'].astype(float)
        high   = df['high'].astype(float)
        low    = df['low'].astype(float)
        volume = df.get('volume', pd.Series([1]*len(df))).astype(float)

        # ── EMAs ──────────────────────────────────────────────
        ema_fast  = close.ewm(span=fast_p,  adjust=False).mean()
        ema_slow  = close.ewm(span=slow_p,  adjust=False).mean()
        ema_trend = close.ewm(span=trend_p, adjust=False).mean()

        # ── RSI ───────────────────────────────────────────────
        delta  = close.diff()
        gain   = delta.clip(lower=0).ewm(com=rsi_p - 1, adjust=False).mean()
        loss   = (-delta.clip(upper=0)).ewm(com=rsi_p - 1, adjust=False).mean()
        rs     = gain / loss.replace(0, np.nan)
        rsi    = 100 - 100 / (1 + rs)

        # ── ATR ───────────────────────────────────────────────
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(atr_p).mean()

        # ── Current values ────────────────────────────────────
        price     = float(close.iloc[-1])
        atr_val   = float(atr.iloc[-1])
        fast_now  = float(ema_fast.iloc[-1])
        fast_prev = float(ema_fast.iloc[-2])
        slow_now  = float(ema_slow.iloc[-1])
        slow_prev = float(ema_slow.iloc[-2])
        trend_now = float(ema_trend.iloc[-1])
        rsi_now   = float(rsi.iloc[-1])

        # ── Volume filter ──────────────────────────────────────
        avg_vol    = float(volume.rolling(20).mean().iloc[-1])
        cur_vol    = float(volume.iloc[-1])
        vol_ok     = (not vol_filt) or (avg_vol == 0) or (cur_vol >= avg_vol * vol_mult)

        # ── EMA crossover ─────────────────────────────────────
        bull_cross = (fast_prev <= slow_prev) and (fast_now > slow_now)
        bear_cross = (fast_prev >= slow_prev) and (fast_now < slow_now)

        # Trend direction
        bull_trend = price > trend_now
        bear_trend = price < trend_now

        # ── SL calculation ────────────────────────────────────
        raw_sl_dist = atr_val * atr_mult

        # Clamp SL to max 50 pips (0.50 price units for Gold)
        sl_dist = min(raw_sl_dist, MAX_SL)

        # Warn if ATR is very small (illiquid market)
        if sl_dist < 0.10:   # < 10 pips — suspicious
            return Signal(
                action='hold', symbol=symbol, strength=0.0,
                reason=f'ATR={atr_val:.4f} too small — possible illiquid data'
            )

        tp_dist = sl_dist * rr

        # ── Swing confirmation ────────────────────────────────
        # Use recent swing high/low as additional SL reference
        lookback       = min(10, len(df))
        swing_low      = float(low.iloc[-lookback:].min())
        swing_high     = float(high.iloc[-lookback:].max())

        # ── Indicators dict ───────────────────────────────────
        indicators = {
            'ema_fast':   round(fast_now, 2),
            'ema_slow':   round(slow_now, 2),
            'ema_trend':  round(trend_now, 2),
            'rsi':        round(rsi_now, 2),
            'atr':        round(atr_val, 4),
            'sl_dist':    round(sl_dist, 4),
            'sl_pips':    round(sl_dist / PIP, 1),
            'price':      round(price, 2),
            'vol_ok':     vol_ok,
        }

        # ── BUY signal ────────────────────────────────────────
        if (bull_cross and bull_trend
                and rsi_now  > rsi_bull
                and vol_ok):
            sl = round(price - sl_dist, 2)
            tp = round(price + tp_dist, 2)

            # Prefer swing low as SL if it's tighter but still > min
            if swing_low < sl and (price - swing_low) <= MAX_SL:
                sl = round(swing_low - 0.05, 2)   # 5 cent buffer
                tp = round(price + (price - sl) * rr, 2)

            sl_pips = round((price - sl) / PIP, 1)
            tp_pips = round((tp - price) / PIP, 1)

            return Signal(
                action      = 'buy',
                symbol      = symbol,
                strength    = self._strength(rsi_now, atr_val, vol_ok, 'buy'),
                stop_loss   = sl,
                take_profit = tp,
                reason      = (
                    f"Gold BUY: EMA{fast_p}/{slow_p} cross above trend | "
                    f"RSI={rsi_now:.1f} | "
                    f"SL={sl_pips:.0f}p TP={tp_pips:.0f}p | "
                    f"RRR=1:{rr}"
                ),
                indicators  = indicators,
            )

        # ── SELL signal ───────────────────────────────────────
        if (bear_cross and bear_trend
                and rsi_now  < rsi_bear
                and vol_ok):
            sl = round(price + sl_dist, 2)
            tp = round(price - tp_dist, 2)

            # Prefer swing high as SL if it's tighter but still > min
            if swing_high > sl and (swing_high - price) <= MAX_SL:
                sl = round(swing_high + 0.05, 2)
                tp = round(price - (sl - price) * rr, 2)

            sl_pips = round((sl - price) / PIP, 1)
            tp_pips = round((price - tp) / PIP, 1)

            return Signal(
                action      = 'sell',
                symbol      = symbol,
                strength    = self._strength(rsi_now, atr_val, vol_ok, 'sell'),
                stop_loss   = sl,
                take_profit = tp,
                reason      = (
                    f"Gold SELL: EMA{fast_p}/{slow_p} cross below trend | "
                    f"RSI={rsi_now:.1f} | "
                    f"SL={sl_pips:.0f}p TP={tp_pips:.0f}p | "
                    f"RRR=1:{rr}"
                ),
                indicators  = indicators,
            )

        # ── No signal ─────────────────────────────────────────
        trend_str = 'bullish' if bull_trend else 'bearish'
        return Signal(
            action     = 'hold',
            symbol     = symbol,
            strength   = 0.0,
            reason     = (
                f"Gold neutral — {trend_str} trend | "
                f"RSI={rsi_now:.1f} | "
                f"No EMA cross"
            ),
            indicators = indicators,
        )

    def _strength(
        self,
        rsi:    float,
        atr:    float,
        vol_ok: bool,
        side:   str,
    ) -> float:
        """
        Signal strength 0.0–1.0.
        Higher RSI conviction + volume confirmation = stronger signal.
        """
        base = 0.60
        # RSI contribution
        if side == 'buy':
            rsi_bonus = min((rsi - 55) / 45, 0.20)  # max +0.20
        else:
            rsi_bonus = min((45 - rsi) / 45, 0.20)
        # Volume confirmation
        vol_bonus = 0.10 if vol_ok else 0.0
        # ATR bonus — higher volatility = more opportunity on Gold
        atr_bonus = min(atr / 2.0, 0.10)
        return round(min(base + rsi_bonus + vol_bonus + atr_bonus, 1.0), 2)