# ============================================================

# Strategy model — stores strategy config and plugin reference
# ============================================================
import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField
from apps.accounts.models import User
from utils.constants import StrategyType, Timeframe


class Strategy(models.Model):
    """
    A reusable trading strategy definition.
    Parameters are stored as JSON so each strategy plugin
    can declare its own schema (validated in Phase D).

    Example parameters JSON for MA Crossover:
    {
        "fast_period": 50,
        "slow_period": 200,
        "ma_type": "EMA"
    }
    Example for RSI Reversal:
    {
        "rsi_period": 14,
        "oversold": 30,
        "overbought": 70
    }
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='strategies'
    )

    # Identity
    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    strategy_type = models.CharField(
        max_length=30,
        choices=StrategyType.choices,
        default=StrategyType.MA_CROSSOVER
    )

    # Plugin reference — maps to class in apps/strategies/plugins/
    plugin_path = models.CharField(
        max_length=300,
        help_text="Python dotted path to the strategy class, e.g. "
                  "'apps.strategies.plugins.ma_crossover.MACrossoverStrategy'"
    )

    # Strategy configuration (free-form JSON, validated per plugin)
    parameters  = models.JSONField(default=dict, blank=True)

    # Which pairs / timeframes this strategy applies to
    symbols     = ArrayField(
        models.CharField(max_length=20),
        default=list,
        blank=True,
        help_text="e.g. ['EUR_USD', 'GBP_USD']"
    )
    timeframe   = models.CharField(
        max_length=5,
        choices=Timeframe.choices,
        default=Timeframe.H1
    )

    # Status
    is_active   = models.BooleanField(default=True)
    is_public   = models.BooleanField(
        default=False,
        help_text="If True, other users can view (not edit) this strategy."
    )

    # Performance summary (updated after each backtest/live run)
    last_win_rate       = models.FloatField(null=True, blank=True)
    last_profit_factor  = models.FloatField(null=True, blank=True)
    last_sharpe         = models.FloatField(null=True, blank=True)
    backtest_count      = models.PositiveIntegerField(default=0)

    # Timestamps
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table    = 'strategies_strategy'
        ordering    = ['-created_at']
        indexes     = [
            models.Index(fields=['user', 'strategy_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_public']),
        ]
        verbose_name        = 'Strategy'
        verbose_name_plural = 'Strategies'

    def __str__(self):
        return f"{self.name} [{self.strategy_type}] — {self.user.email}"

    def get_plugin_class(self):
        """Dynamically import and return the strategy plugin class."""
        from importlib import import_module
        module_path, class_name = self.plugin_path.rsplit('.', 1)
        module = import_module(module_path)
        return getattr(module, class_name)

    def instantiate(self):
        """Return an initialised strategy instance with stored parameters."""
        cls = self.get_plugin_class()
        return cls(self.parameters)