# ============================================================
# Ichimoku Cloud Strategy
#
# Logic:
#   ENTRY BUY:  price above cloud, tenkan > kijun, chikou above cloud
#   ENTRY SELL: price below cloud, tenkan < kijun, chikou below cloud
#   EXIT:       opposite crossover OR price re-enters cloud
#   SL:         kijun-sen line (baseline)
#   TP:         1.5 × risk (configurable RR)
# ============================================================
import pandas as pd
import numpy as np
from ..base import BaseStrategy, Signal
from ..registry import StrategyRegistry


@StrategyRegistry.register('ichimoku')
class IchimokuStrategy(BaseStrategy):
    """
    Classic Ichimoku Kinko Hyo trading system.
    Uses all five components: Tenkan, Kijun, Senkou A/B, Chikou.
    """

    NAME        = 'Ichimoku Cloud'
    DESCRIPTION = (
        'Full Ichimoku system — trades in the direction of the cloud '
        'with Tenkan/Kijun crossover confirmation and Chikou span filter.'
    )
    VERSION     = '1.0.0'

    DEFAULT_PARAMETERS = {
        'tenkan_period':   9,
        'kijun_period':    26,
        'senkou_b_period': 52,
        'displacement':    26,
        'risk_reward':     1.5,
        'cloud_filter':    True,   # price must be fully above/below cloud
        'chikou_filter':   True,   # chikou span must confirm
    }

    def get_required_candles(self) -> int:
        p = self.parameters
        return p.get('senkou_b_period', 52) + p.get('displacement', 26) + 10

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        p          = self.parameters
        tenkan_p   = int(p.get('tenkan_period',   9))
        kijun_p    = int(p.get('kijun_period',   26))
        senkou_b_p = int(p.get('senkou_b_period',52))
        disp       = int(p.get('displacement',   26))
        rr         = float(p.get('risk_reward',  1.5))

        if len(df) < self.get_required_candles():
            return Signal.neutral(symbol, 'Insufficient data')

        high  = df['high'].astype(float)
        low   = df['low'].astype(float)
        close = df['close'].astype(float)

        def mid(h, l, n):
            return (h.rolling(n).max() + l.rolling(n).min()) / 2

        tenkan  = mid(high, low, tenkan_p)
        kijun   = mid(high, low, kijun_p)
        senkou_a = ((tenkan + kijun) / 2).shift(disp)
        senkou_b = mid(high, low, senkou_b_p).shift(disp)
        chikou  = close.shift(-disp)

        price     = close.iloc[-1]
        t_now     = tenkan.iloc[-1]
        k_now     = kijun.iloc[-1]
        t_prev    = tenkan.iloc[-2]
        k_prev    = kijun.iloc[-2]
        cloud_top = max(senkou_a.iloc[-1], senkou_b.iloc[-1])
        cloud_bot = min(senkou_a.iloc[-1], senkou_b.iloc[-1])

        # Chikou span vs cloud 26 periods ago
        chikou_val   = close.iloc[-1 - disp] if len(close) > disp else np.nan
        cloud_top_26 = max(senkou_a.iloc[-1 - disp], senkou_b.iloc[-1 - disp]) if len(senkou_a) > disp else np.nan
        cloud_bot_26 = min(senkou_a.iloc[-1 - disp], senkou_b.iloc[-1 - disp]) if len(senkou_b) > disp else np.nan

        # Tenkan/Kijun crossover
        bullish_cross = (t_prev <= k_prev) and (t_now > k_now)
        bearish_cross = (t_prev >= k_prev) and (t_now < k_now)

        # Cloud filters
        above_cloud = price > cloud_top
        below_cloud = price < cloud_bot
        chikou_above = (not p.get('chikou_filter') or
                        (not np.isnan(chikou_val) and chikou_val > cloud_top_26))
        chikou_below = (not p.get('chikou_filter') or
                        (not np.isnan(chikou_val) and chikou_val < cloud_bot_26))

        pip_size = 0.01 if 'JPY' in symbol else 0.0001
        sl_dist  = abs(price - k_now)
        tp_dist  = sl_dist * rr

        indicators = {
            'tenkan':    round(t_now, 5),
            'kijun':     round(k_now, 5),
            'cloud_top': round(cloud_top, 5),
            'cloud_bot': round(cloud_bot, 5),
            'price':     round(price, 5),
        }

        # ── BUY Signal ─────────────────────────────────────────
        if bullish_cross and above_cloud and chikou_above:
            sl = price - sl_dist
            tp = price + tp_dist
            return Signal(
                action      = 'buy',
                symbol      = symbol,
                strength    = 0.8,
                stop_loss   = round(sl, 5),
                take_profit = round(tp, 5),
                reason      = (f"Ichimoku BUY: Tenkan/Kijun cross above cloud "
                               f"(cloud_top={cloud_top:.5f})"),
                indicators  = indicators,
            )

        # ── SELL Signal ────────────────────────────────────────
        if bearish_cross and below_cloud and chikou_below:
            sl = price + sl_dist
            tp = price - tp_dist
            return Signal(
                action      = 'sell',
                symbol      = symbol,
                strength    = 0.8,
                stop_loss   = round(sl, 5),
                take_profit = round(tp, 5),
                reason      = (f"Ichimoku SELL: Tenkan/Kijun cross below cloud "
                               f"(cloud_bot={cloud_bot:.5f})"),
                indicators  = indicators,
            )

        return Signal.neutral(
            symbol,
            f"No signal — price={'above' if above_cloud else 'below' if below_cloud else 'IN'} cloud",
            indicators,
        )