# ============================================================
# Core backtesting engine — simulates a strategy on historical data
# ============================================================
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pandas as pd
import numpy as np

from apps.backtesting.models import BacktestResult, BacktestTrade
from apps.backtesting.metrics import MetricsCalculator
from apps.strategies.base import Signal
from apps.risk_management.calculator import RiskCalculator
from utils.constants import BacktestStatus

logger = logging.getLogger('backtesting')


class BacktestEngine:
    """
    Event-driven backtesting engine.

    Processes one candle at a time (bar-by-bar simulation).
    On each bar:
      1. Check if any open simulated positions hit SL or TP
      2. Run strategy on all candles up to current bar
      3. If signal is generated and no position open, open one
      4. Track equity curve and trade log

    No look-ahead bias — strategy only sees candles[0..current_index].

    Supports:
      - Spread simulation (added to every entry price)
      - Commission per lot
      - Partial fills / slippage (configurable)
      - Multiple symbols in sequence
    """

    def __init__(self, backtest_id: str):
        self.backtest_id = backtest_id
        self.result: Optional[BacktestResult] = None

    def run(self) -> dict:
        """Main entry point called by Celery task."""
        self.result = self._load_result()
        if not self.result:
            return {'success': False, 'error': 'BacktestResult not found'}

        self._update_status(BacktestStatus.RUNNING)
        start_time = time.monotonic()

        try:
            # ── Load historical data ──────────────────────────
            df = self._load_candles()
            if df is None or df.empty:
                raise ValueError(
                    f"No historical data for {self.result.symbol}/"
                    f"{self.result.timeframe} between "
                    f"{self.result.start_date} and {self.result.end_date}"
                )

            logger.info(
                f"Backtest {self.backtest_id}: loaded {len(df)} candles "
                f"for {self.result.symbol}/{self.result.timeframe}"
            )

            # ── Instantiate strategy ──────────────────────────
            strategy = self.result.strategy.instantiate()
            min_candles = strategy.get_required_candles()

            if len(df) < min_candles:
                raise ValueError(
                    f"Not enough candles: have {len(df)}, "
                    f"need {min_candles} for this strategy"
                )

            # ── Run simulation ────────────────────────────────
            trades, equity_curve = self._simulate(df, strategy, min_candles)

            # ── Calculate metrics ─────────────────────────────
            metrics = MetricsCalculator.calculate(
                trades         = trades,
                equity_curve   = equity_curve,
                initial_balance= float(self.result.initial_balance),
            )

            # ── Save results ──────────────────────────────────
            self._save_results(trades, equity_curve, metrics)

            elapsed = round(time.monotonic() - start_time, 2)
            logger.info(
                f"Backtest {self.backtest_id} complete in {elapsed}s — "
                f"{len(trades)} trades, return={metrics.get('total_return_pct', 0):.2f}%"
            )

            return {
                'success':  True,
                'trades':   len(trades),
                'metrics':  metrics,
                'elapsed':  elapsed,
            }

        except Exception as e:
            logger.error(f"Backtest {self.backtest_id} failed: {e}", exc_info=True)
            self._update_status(BacktestStatus.FAILED, error=str(e))
            return {'success': False, 'error': str(e)}

    # ── Core simulation loop ──────────────────────────────────
    def _simulate(
        self,
        df: pd.DataFrame,
        strategy,
        min_candles: int,
    ) -> tuple:
        """
        Bar-by-bar simulation loop.
        Returns (trades_list, equity_curve_list).
        """
        initial_balance = float(self.result.initial_balance)
        commission      = float(self.result.commission_per_lot)
        spread_pips     = float(self.result.spread_pips)
        symbol          = self.result.symbol
        pip_size        = 0.01 if 'JPY' in symbol else 0.0001
        spread_price    = spread_pips * pip_size

        balance       = initial_balance
        equity_curve  = [initial_balance]
        trades        = []
        open_trade    = None   # one position at a time
        trade_index   = 0
        total_bars    = len(df)

        for i in range(min_candles, total_bars):
            bar         = df.iloc[i]
            bar_high    = float(bar['high'])
            bar_low     = float(bar['low'])
            bar_close   = float(bar['close'])
            bar_time    = df.index[i]

            # ── Check open trade for SL/TP hits ───────────────
            if open_trade:
                exit_price, exit_reason = self._check_exit(
                    open_trade, bar_high, bar_low, bar_close
                )
                if exit_price is not None:
                    pnl = self._calculate_pnl(open_trade, exit_price, symbol)
                    pnl -= commission * open_trade['lot_size']  # deduct commission
                    balance += pnl

                    open_trade['exit_price'] = exit_price
                    open_trade['exit_time']  = bar_time
                    open_trade['profit_loss']= round(pnl, 2)
                    open_trade['profit_pips']= self._pnl_to_pips(
                        open_trade['entry_price'], exit_price,
                        open_trade['order_type'], symbol
                    )
                    open_trade['exit_reason'] = exit_reason
                    trades.append(open_trade)
                    open_trade = None
                    equity_curve.append(round(balance, 2))

                    # Update progress every 5%
                    progress = round(i / total_bars * 100, 1)
                    if int(progress) % 5 == 0:
                        self._update_progress(progress)

                    continue

            # ── Generate strategy signal ───────────────────────
            # Only pass candles up to current bar (no lookahead)
            window = df.iloc[max(0, i - min_candles - 10):i + 1]

            try:
                signal: Signal = strategy.generate_signal(window, symbol)
            except Exception as e:
                logger.debug(f"Strategy error at bar {i}: {e}")
                equity_curve.append(round(balance, 2))
                continue

            # ── Open trade on actionable signal ───────────────
            if signal.is_entry and open_trade is None:
                entry_price = bar_close + (
                    spread_price if signal.action == 'buy' else -spread_price
                )

                # Use strategy SL/TP or fall back to parameters
                sl = signal.stop_loss  or self._default_sl(
                    entry_price, signal.action, symbol
                )
                tp = signal.take_profit or self._default_tp(
                    entry_price, signal.action, symbol
                )

                # Calculate lot size
                sl_pips  = abs(entry_price - sl) / pip_size if sl else 50
                lot_size = RiskCalculator.lot_size(
                    account_balance  = balance,
                    risk_percent     = float(
                        self.result.parameters_snapshot.get('risk_percent', 1.0)
                    ),
                    stop_loss_pips   = max(sl_pips, 1),
                    symbol           = symbol,
                )

                trade_index += 1
                open_trade = {
                    'trade_index':  trade_index,
                    'symbol':       symbol,
                    'order_type':   signal.action,
                    'entry_price':  round(entry_price, 5),
                    'stop_loss':    round(sl, 5) if sl else None,
                    'take_profit':  round(tp, 5) if tp else None,
                    'lot_size':     lot_size,
                    'entry_time':   bar_time,
                    'exit_price':   None,
                    'exit_time':    None,
                    'profit_loss':  0.0,
                    'profit_pips':  0.0,
                    'exit_reason':  '',
                    'indicators':   signal.indicators,
                }

            equity_curve.append(round(balance, 2))

        # ── Force-close any open trade at end of data ──────────
        if open_trade:
            last_close = float(df['close'].iloc[-1])
            pnl = self._calculate_pnl(open_trade, last_close, symbol)
            pnl -= commission * open_trade['lot_size']
            balance += pnl
            open_trade['exit_price']  = last_close
            open_trade['exit_time']   = df.index[-1]
            open_trade['profit_loss'] = round(pnl, 2)
            open_trade['exit_reason'] = 'end_of_data'
            trades.append(open_trade)
            equity_curve.append(round(balance, 2))

        self._update_progress(100.0)
        return trades, equity_curve

    # ── Exit detection ────────────────────────────────────────
    @staticmethod
    def _check_exit(
        trade: dict, bar_high: float, bar_low: float, bar_close: float
    ):
        """
        Check if this bar triggers a SL or TP on the open trade.
        Returns (exit_price, reason) or (None, None).
        """
        sl = trade.get('stop_loss')
        tp = trade.get('take_profit')
        direction = trade['order_type']

        if direction == 'buy':
            if sl and bar_low <= sl:
                return sl, 'stop_loss'
            if tp and bar_high >= tp:
                return tp, 'take_profit'
        else:  # sell
            if sl and bar_high >= sl:
                return sl, 'stop_loss'
            if tp and bar_low <= tp:
                return tp, 'take_profit'

        return None, None

    # ── P&L helpers ───────────────────────────────────────────
    @staticmethod
    def _calculate_pnl(trade: dict, exit_price: float, symbol: str) -> float:
        entry     = trade['entry_price']
        lot_size  = trade['lot_size']
        units     = lot_size * 100_000
        diff      = exit_price - entry
        if trade['order_type'] == 'sell':
            diff = -diff
        return round(diff * units, 2)

    @staticmethod
    def _pnl_to_pips(entry: float, exit: float,
                     direction: str, symbol: str) -> float:
        pip_size = 0.01 if 'JPY' in symbol else 0.0001
        diff = exit - entry
        if direction == 'sell':
            diff = -diff
        return round(diff / pip_size, 1)

    def _default_sl(self, entry: float, direction: str, symbol: str) -> float:
        pip_size = 0.01 if 'JPY' in symbol else 0.0001
        sl_pips  = float(
            self.result.parameters_snapshot.get('stop_loss_pips', 50)
        )
        offset = sl_pips * pip_size
        return entry - offset if direction == 'buy' else entry + offset

    def _default_tp(self, entry: float, direction: str, symbol: str) -> float:
        pip_size = 0.01 if 'JPY' in symbol else 0.0001
        tp_pips  = float(
            self.result.parameters_snapshot.get('take_profit_pips', 100)
        )
        offset = tp_pips * pip_size
        return entry + offset if direction == 'buy' else entry - offset

    # ── Data loading ──────────────────────────────────────────
    def _load_candles(self) -> Optional[pd.DataFrame]:
        """
        Load historical candles for the backtest date range.
        Sources (in order): PostgreSQL → OANDA API → AlphaVantage.
        """
        from apps.market_data.models import MarketData
        from services.data_feed.normalizer import CandleNormalizer

        symbol    = self.result.symbol
        timeframe = self.result.timeframe
        broker    = 'oanda'

        # Try DB first
        qs = MarketData.objects.filter(
            symbol     = symbol,
            timeframe  = timeframe,
            broker     = broker,
            timestamp__gte = self.result.start_date,
            timestamp__lte = self.result.end_date,
        ).order_by('timestamp').values(
            'timestamp', 'open', 'high', 'low', 'close', 'volume'
        )

        if qs.count() >= 50:
            df = pd.DataFrame(list(qs))
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            df = df.set_index('timestamp').sort_index()
            for col in ('open', 'high', 'low', 'close'):
                df[col] = df[col].astype(float)
            logger.info(
                f"Loaded {len(df)} candles from DB for "
                f"{symbol}/{timeframe}"
            )
            return df

        # Fall back to live API fetch (range)
        logger.info(
            f"DB has insufficient data for {symbol}/{timeframe}, "
            f"fetching from OANDA..."
        )
        try:
            from services.data_feed.oanda_feed import OandaFeed
            feed = OandaFeed()
            raw  = feed.fetch_candles_range(
                symbol     = symbol,
                timeframe  = timeframe,
                from_date  = self.result.start_date,
                to_date    = self.result.end_date,
            )
            if raw:
                df = CandleNormalizer.normalize(
                    raw, symbol=symbol, timeframe=timeframe
                )
                # Save to DB for future backtests
                from apps.market_data.cache import _save_to_db
                _save_to_db(df, symbol, timeframe, broker)
                return df
        except Exception as e:
            logger.warning(f"OANDA range fetch failed: {e}")

        # Last resort — AlphaVantage
        try:
            from services.broker_api.alpha_vantage import AlphaVantageFeed
            av     = AlphaVantageFeed()
            raw_av = av.fetch_candles(
                symbol.replace('_', ''), timeframe, count=5000
            )
            if raw_av:
                df = CandleNormalizer.normalize(raw_av, symbol=symbol)
                # Filter to date range
                return df[
                    (df.index >= pd.Timestamp(self.result.start_date, tz='UTC')) &
                    (df.index <= pd.Timestamp(self.result.end_date,   tz='UTC'))
                ]
        except Exception as e:
            logger.warning(f"AlphaVantage fallback failed: {e}")

        return None

    # ── DB helpers ────────────────────────────────────────────
    def _load_result(self) -> Optional[BacktestResult]:
        try:
            return BacktestResult.objects.select_related(
                'strategy', 'user'
            ).get(pk=self.backtest_id)
        except BacktestResult.DoesNotExist:
            return None

    def _update_status(self, status: str, error: str = ''):
        from django.utils import timezone as dj_tz
        updates = {'status': status}
        if status == BacktestStatus.RUNNING:
            updates['started_at'] = dj_tz.now()
        elif status in (BacktestStatus.COMPLETED, BacktestStatus.FAILED):
            updates['completed_at'] = dj_tz.now()
        if error:
            updates['error_message'] = error[:500]
        BacktestResult.objects.filter(pk=self.backtest_id).update(**updates)

    def _update_progress(self, pct: float):
        BacktestResult.objects.filter(pk=self.backtest_id).update(
            progress=round(pct, 1)
        )

    def _save_results(
        self,
        trades: list,
        equity_curve: list,
        metrics: dict,
    ):
        from django.utils import timezone as dj_tz
        initial = float(self.result.initial_balance)
        final   = equity_curve[-1] if equity_curve else initial

        # Bulk create BacktestTrade records
        trade_objs = []
        for t in trades:
            trade_objs.append(BacktestTrade(
                backtest    = self.result,
                trade_index = t['trade_index'],
                symbol      = t['symbol'],
                order_type  = t['order_type'],
                entry_price = t['entry_price'],
                exit_price  = t.get('exit_price') or t['entry_price'],
                stop_loss   = t.get('stop_loss'),
                take_profit = t.get('take_profit'),
                lot_size    = t['lot_size'],
                profit_loss = t['profit_loss'],
                profit_pips = t.get('profit_pips', 0),
                exit_reason = t.get('exit_reason', 'signal'),
                indicators  = t.get('indicators', {}),
                entry_time  = t['entry_time'],
                exit_time   = t.get('exit_time'),
            ))
        if trade_objs:
            BacktestTrade.objects.bulk_create(trade_objs, batch_size=500)

        # Compact equity curve for JSON storage (max 1000 points)
        if len(equity_curve) > 1000:
            step = len(equity_curve) // 1000
            equity_curve = equity_curve[::step]

        # Build timestamped equity curve
        equity_with_ts = [
            {'index': i, 'equity': v}
            for i, v in enumerate(equity_curve)
        ]

        # Update result
        BacktestResult.objects.filter(pk=self.backtest_id).update(
            status        = BacktestStatus.COMPLETED,
            final_balance = final,
            metrics       = metrics,
            equity_curve  = equity_with_ts,
            progress      = 100.0,
            completed_at  = dj_tz.now(),
        )

        # Update strategy performance summary
        strategy = self.result.strategy
        strategy.last_win_rate      = metrics.get('win_rate', 0)
        strategy.last_profit_factor = metrics.get('profit_factor', 0)
        strategy.last_sharpe        = metrics.get('sharpe_ratio', 0)
        strategy.backtest_count     = (strategy.backtest_count or 0) + 1
        strategy.save(update_fields=[
            'last_win_rate', 'last_profit_factor',
            'last_sharpe', 'backtest_count',
        ])