# ============================================================
# Backtest performance metrics calculator
# ============================================================
import math
import logging
from typing import List, Dict
import numpy as np

logger = logging.getLogger('backtesting')


class MetricsCalculator:
    """
    Calculates all performance metrics from a completed backtest.
    All methods are @staticmethod — pure functions, no DB access.
    """

    @staticmethod
    def calculate(
        trades: List[Dict],
        equity_curve: List[float],
        initial_balance: float,
    ) -> Dict:
        """
        Master method — computes all metrics in one call.
        Returns a dict compatible with BacktestResult.metrics JSON field.
        """
        if not trades:
            return MetricsCalculator._empty_metrics(initial_balance)

        pnl_list    = [t['profit_loss'] for t in trades]
        pips_list   = [t.get('profit_pips', 0) for t in trades]
        winners     = [p for p in pnl_list if p > 0]
        losers      = [p for p in pnl_list if p < 0]
        total_trades = len(trades)
        win_count    = len(winners)
        loss_count   = len(losers)

        final_balance     = equity_curve[-1] if equity_curve else initial_balance
        total_return      = final_balance - initial_balance
        total_return_pct  = round(total_return / initial_balance * 100, 4) if initial_balance > 0 else 0

        gross_profit = sum(winners)
        gross_loss   = abs(sum(losers))
        profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else (
            float('inf') if gross_profit > 0 else 0.0
        )

        win_rate = round(win_count / total_trades * 100, 2) if total_trades > 0 else 0

        avg_win  = round(gross_profit / win_count,  2) if win_count  > 0 else 0
        avg_loss = round(gross_loss   / loss_count, 2) if loss_count > 0 else 0

        avg_win_pips  = round(
            sum(p for p in pips_list if p > 0) / max(win_count,  1), 1
        )
        avg_loss_pips = round(
            abs(sum(p for p in pips_list if p < 0)) / max(loss_count, 1), 1
        )

        max_dd = MetricsCalculator._max_drawdown(equity_curve)

        # Annualised return (approximate from total)
        durations = MetricsCalculator._trade_durations_hours(trades)
        total_hours = sum(durations) if durations else 1
        years       = max(total_hours / 8760, 1/365)
        ann_return  = round(
            ((final_balance / initial_balance) ** (1 / years) - 1) * 100, 4
        ) if initial_balance > 0 else 0

        # Sharpe ratio from per-trade returns
        per_trade_returns = [p / initial_balance for p in pnl_list]
        sharpe  = MetricsCalculator._sharpe(per_trade_returns)
        sortino = MetricsCalculator._sortino(per_trade_returns)
        calmar  = round(ann_return / max_dd, 4) if max_dd > 0 else 0

        # Expectancy
        wr_dec  = win_count  / total_trades if total_trades > 0 else 0
        lr_dec  = loss_count / total_trades if total_trades > 0 else 0
        expectancy = round(wr_dec * avg_win - lr_dec * avg_loss, 4)

        # Consecutive stats
        max_consec_wins   = MetricsCalculator._max_consecutive(pnl_list, positive=True)
        max_consec_losses = MetricsCalculator._max_consecutive(pnl_list, positive=False)

        # Avg trade duration
        avg_duration = round(sum(durations) / len(durations), 1) if durations else 0

        return {
            # Core
            'total_trades':          total_trades,
            'winning_trades':        win_count,
            'losing_trades':         loss_count,
            'win_rate':              win_rate,
            'profit_factor':         profit_factor,
            # Returns
            'total_return':          round(total_return, 2),
            'total_return_pct':      total_return_pct,
            'annualised_return':     ann_return,
            'initial_balance':       initial_balance,
            'final_balance':         round(final_balance, 2),
            # Risk
            'max_drawdown_pct':      max_dd,
            'sharpe_ratio':          sharpe,
            'sortino_ratio':         sortino,
            'calmar_ratio':          calmar,
            # Trade quality
            'gross_profit':          round(gross_profit, 2),
            'gross_loss':            round(gross_loss, 2),
            'avg_win':               avg_win,
            'avg_loss':              avg_loss,
            'avg_win_pips':          avg_win_pips,
            'avg_loss_pips':         avg_loss_pips,
            'expectancy':            expectancy,
            'max_consecutive_wins':  max_consec_wins,
            'max_consecutive_losses':max_consec_losses,
            'avg_trade_duration_hours': avg_duration,
            # Pip stats
            'total_pips':            round(sum(pips_list), 1),
        }

    @staticmethod
    def _max_drawdown(equity_curve: List[float]) -> float:
        if not equity_curve or len(equity_curve) < 2:
            return 0.0
        peak   = equity_curve[0]
        max_dd = 0.0
        for v in equity_curve:
            if v > peak:
                peak = v
            if peak > 0:
                dd = (peak - v) / peak * 100
                max_dd = max(max_dd, dd)
        return round(max_dd, 4)

    @staticmethod
    def _sharpe(returns: List[float], rf: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        r   = np.array(returns)
        std = np.std(r, ddof=1)
        if std == 0:
            return 0.0
        return round(float(np.mean(r - rf) / std * math.sqrt(252)), 4)

    @staticmethod
    def _sortino(returns: List[float], rf: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        r       = np.array(returns)
        down    = r[r < 0]
        if len(down) == 0:
            return float('inf')
        down_std = np.std(down, ddof=1)
        if down_std == 0:
            return 0.0
        return round(float(np.mean(r - rf) / down_std * math.sqrt(252)), 4)

    @staticmethod
    def _max_consecutive(pnl: List[float], positive: bool) -> int:
        max_streak = cur = 0
        for p in pnl:
            if (p > 0) == positive:
                cur += 1
                max_streak = max(max_streak, cur)
            else:
                cur = 0
        return max_streak

    @staticmethod
    def _trade_durations_hours(trades: List[Dict]) -> List[float]:
        durations = []
        for t in trades:
            et = t.get('entry_time')
            xt = t.get('exit_time')
            if et and xt:
                try:
                    diff = (xt - et).total_seconds() / 3600
                    durations.append(max(0, diff))
                except Exception:
                    pass
        return durations

    @staticmethod
    def _empty_metrics(initial_balance: float) -> Dict:
        return {
            'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
            'win_rate': 0, 'profit_factor': 0, 'total_return': 0,
            'total_return_pct': 0, 'annualised_return': 0,
            'initial_balance': initial_balance, 'final_balance': initial_balance,
            'max_drawdown_pct': 0, 'sharpe_ratio': 0, 'sortino_ratio': 0,
            'calmar_ratio': 0, 'gross_profit': 0, 'gross_loss': 0,
            'avg_win': 0, 'avg_loss': 0, 'expectancy': 0,
            'total_pips': 0, 'avg_win_pips': 0, 'avg_loss_pips': 0,
            'max_consecutive_wins': 0, 'max_consecutive_losses': 0,
            'avg_trade_duration_hours': 0,
        }