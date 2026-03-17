# ============================================================
# BacktestResult and BacktestTrade models
# ============================================================
import uuid
from django.db import models
from django.core.validators import MinValueValidator
from apps.accounts.models import User
from apps.strategies.models import Strategy
from utils.constants import BacktestStatus, Timeframe


class BacktestResult(models.Model):
    """
    Stores the full result of a backtest run.

    The equity_curve and trade_list are stored as JSON arrays
    for fast Chart.js rendering on the dashboard.

    equity_curve format:  [{"ts": "2024-01-01T00:00:00Z", "equity": 10050.0}, ...]
    metrics format:
    {
        "total_return_pct":   12.5,
        "annualised_return":  24.3,
        "max_drawdown_pct":   8.2,
        "win_rate":           58.3,
        "profit_factor":      1.87,
        "sharpe_ratio":       1.43,
        "sortino_ratio":      1.91,
        "total_trades":       142,
        "winning_trades":     83,
        "losing_trades":      59,
        "avg_win_pips":       45.2,
        "avg_loss_pips":      22.1,
        "avg_trade_duration_hours": 6.4,
        "expectancy":         0.82,
        "calmar_ratio":       2.96
    }
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='backtests'
    )
    strategy    = models.ForeignKey(
        Strategy, on_delete=models.CASCADE,
        related_name='backtests'
    )

    # Test configuration
    name        = models.CharField(max_length=200, blank=True)
    symbol      = models.CharField(max_length=20)
    timeframe   = models.CharField(max_length=5, choices=Timeframe.choices)
    start_date  = models.DateTimeField()
    end_date    = models.DateTimeField()

    # Parameters snapshot (copy of strategy.parameters at time of test)
    parameters_snapshot = models.JSONField(default=dict)

    # Initial conditions
    initial_balance     = models.DecimalField(
        max_digits=18, decimal_places=2, default=10000,
        validators=[MinValueValidator(1)]
    )
    commission_per_lot  = models.DecimalField(max_digits=10, decimal_places=4, default=7.0)
    spread_pips         = models.FloatField(default=1.5)

    # Status
    status      = models.CharField(
        max_length=20,
        choices=BacktestStatus.choices,
        default=BacktestStatus.QUEUED,
        db_index=True
    )
    celery_task_id  = models.CharField(max_length=255, blank=True)
    error_message   = models.TextField(blank=True)
    progress        = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="0–100 completion percentage"
    )

    # Results
    final_balance   = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    metrics         = models.JSONField(default=dict, blank=True)
    equity_curve    = models.JSONField(default=list, blank=True)

    # Duration
    started_at      = models.DateTimeField(null=True, blank=True)
    completed_at    = models.DateTimeField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table    = 'backtesting_result'
        ordering    = ['-created_at']
        indexes     = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['strategy', 'created_at']),
            models.Index(fields=['symbol', 'timeframe']),
            models.Index(fields=['status', 'created_at']),
        ]
        verbose_name        = 'Backtest Result'
        verbose_name_plural = 'Backtest Results'

    def __str__(self):
        m = self.metrics or {}
        ret = m.get('total_return_pct', 'N/A')
        return (
            f"Backtest: {self.strategy.name} | {self.symbol}/{self.timeframe} | "
            f"{self.start_date:%Y-%m-%d}→{self.end_date:%Y-%m-%d} | "
            f"Return: {ret}% [{self.status}]"
        )

    @property
    def duration_seconds(self):
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def get_metric(self, key: str, default=None):
        return (self.metrics or {}).get(key, default)


class BacktestTrade(models.Model):
    """
    Individual simulated trade within a BacktestResult.
    Stored separately so we can paginate/filter backtest trade history
    without loading the entire result JSON.
    """
    id          = models.BigAutoField(primary_key=True)
    backtest    = models.ForeignKey(
        BacktestResult, on_delete=models.CASCADE,
        related_name='trades'
    )

    trade_index = models.PositiveIntegerField(help_text="Sequential trade number in this backtest")

    symbol      = models.CharField(max_length=20)
    order_type  = models.CharField(max_length=10)   # buy / sell

    entry_price = models.DecimalField(max_digits=18, decimal_places=6)
    exit_price  = models.DecimalField(max_digits=18, decimal_places=6)
    stop_loss   = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    take_profit = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)

    lot_size    = models.DecimalField(max_digits=10, decimal_places=2, default=0.1)
    profit_loss = models.DecimalField(max_digits=18, decimal_places=2)
    profit_pips = models.FloatField(default=0.0)

    # Exit reason: 'take_profit' | 'stop_loss' | 'signal' | 'end_of_data'
    exit_reason = models.CharField(max_length=30, default='signal')

    # Indicator snapshot at entry
    indicators  = models.JSONField(default=dict, blank=True)

    entry_time  = models.DateTimeField(db_index=True)
    exit_time   = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table    = 'backtesting_trade'
        ordering    = ['entry_time']
        indexes     = [
            models.Index(fields=['backtest', 'entry_time']),
            models.Index(fields=['backtest', 'order_type']),
        ]
        verbose_name        = 'Backtest Trade'
        verbose_name_plural = 'Backtest Trades'

    def __str__(self):
        return (
            f"BT-Trade #{self.trade_index} | {self.order_type.upper()} "
            f"{self.symbol} | P&L={self.profit_loss}"
        )

    @property
    def is_winner(self):
        return float(self.profit_loss) > 0

    @property
    def duration_hours(self):
        if self.entry_time and self.exit_time:
            return (self.exit_time - self.entry_time).total_seconds() / 3600
        return 0.0