# ============================================================
# risk_management/models.py
# RiskRule and DrawdownEvent models for detailed risk management per bot
# ============================================================
import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.accounts.models import User
from apps.trading.models import TradingBot


class RiskRule(models.Model):
    """
    Detailed per-bot risk management rules.
    These are checked by the RiskManager service before every order.

    The TradingBot also has a risk_settings JSON field for fast
    in-memory access. This model is the authoritative source and
    syncs into that JSON on save (via signal in Phase G).
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot         = models.OneToOneField(
        TradingBot, on_delete=models.CASCADE,
        related_name='risk_rule'
    )

    # ── Position Sizing ──────────────────────────────────────
    risk_percent        = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.01), MaxValueValidator(10.0)],
        help_text="% of account balance to risk per trade (0.01–10)"
    )
    max_lot_size        = models.DecimalField(
        max_digits=8, decimal_places=2, default=1.0,
        help_text="Hard ceiling on lot size regardless of risk calc"
    )
    min_lot_size        = models.DecimalField(
        max_digits=8, decimal_places=2, default=0.01
    )

    # ── Stop Loss / Take Profit ───────────────────────────────
    stop_loss_pips      = models.FloatField(
        default=50.0,
        validators=[MinValueValidator(1.0)],
        help_text="Default SL in pips if strategy does not specify"
    )
    take_profit_pips    = models.FloatField(
        default=100.0,
        validators=[MinValueValidator(1.0)]
    )
    risk_reward_ratio   = models.FloatField(
        default=2.0,
        help_text="If set, TP = SL * risk_reward_ratio (overrides take_profit_pips)"
    )
    use_risk_reward     = models.BooleanField(default=False)

    # ── Trailing Stop ────────────────────────────────────────
    trailing_stop_enabled   = models.BooleanField(default=False)
    trailing_stop_pips      = models.FloatField(default=20.0)
    trailing_step_pips      = models.FloatField(default=5.0)

    # ── Daily Limits ─────────────────────────────────────────
    max_trades_per_day      = models.PositiveIntegerField(default=10)
    max_daily_loss          = models.FloatField(
        default=5.0,
        help_text="Max % account loss in a single day before halting bot"
    )
    max_daily_profit        = models.FloatField(
        default=0.0,
        help_text="0 = disabled. Stop bot when daily profit reaches this %"
    )

    # ── Drawdown Control ─────────────────────────────────────
    max_drawdown_percent    = models.FloatField(
        default=20.0,
        validators=[MinValueValidator(1.0), MaxValueValidator(100.0)],
        help_text="Halt bot permanently if drawdown exceeds this %"
    )
    drawdown_pause_percent  = models.FloatField(
        default=10.0,
        help_text="Pause (not stop) bot at this % drawdown — resume manually"
    )

    # ── Concurrent Position Limits ────────────────────────────
    max_open_trades         = models.PositiveIntegerField(default=3)
    max_trades_per_symbol   = models.PositiveIntegerField(default=1)

    # ── Spread Filter ────────────────────────────────────────
    max_spread_pips         = models.FloatField(
        default=3.0,
        help_text="Do not trade if spread exceeds this in pips"
    )

    # ── Time Filters ─────────────────────────────────────────
    trade_start_hour    = models.PositiveIntegerField(
        default=0, validators=[MaxValueValidator(23)],
        help_text="UTC hour to start trading (0–23)"
    )
    trade_end_hour      = models.PositiveIntegerField(
        default=23, validators=[MaxValueValidator(23)],
        help_text="UTC hour to stop trading (0–23)"
    )
    avoid_news_events   = models.BooleanField(
        default=False,
        help_text="Pause trading around high-impact economic events"
    )
    news_buffer_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Minutes before/after news to avoid trading"
    )

    # Timestamps
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'risk_rule'
        verbose_name        = 'Risk Rule'
        verbose_name_plural = 'Risk Rules'

    def __str__(self):
        return (
            f"RiskRule for {self.bot.name} | "
            f"risk={self.risk_percent}% SL={self.stop_loss_pips}pips "
            f"maxDD={self.max_drawdown_percent}%"
        )

    def to_dict(self) -> dict:
        """Serialise for storage in TradingBot.risk_settings JSON."""
        return {
            'risk_percent':           self.risk_percent,
            'max_lot_size':           float(self.max_lot_size),
            'min_lot_size':           float(self.min_lot_size),
            'stop_loss_pips':         self.stop_loss_pips,
            'take_profit_pips':       self.take_profit_pips,
            'risk_reward_ratio':      self.risk_reward_ratio,
            'use_risk_reward':        self.use_risk_reward,
            'trailing_stop_enabled':  self.trailing_stop_enabled,
            'trailing_stop_pips':     self.trailing_stop_pips,
            'max_trades_per_day':     self.max_trades_per_day,
            'max_daily_loss':         self.max_daily_loss,
            'max_drawdown_percent':   self.max_drawdown_percent,
            'drawdown_pause_percent': self.drawdown_pause_percent,
            'max_open_trades':        self.max_open_trades,
            'max_trades_per_symbol':  self.max_trades_per_symbol,
            'max_spread_pips':        self.max_spread_pips,
            'trade_start_hour':       self.trade_start_hour,
            'trade_end_hour':         self.trade_end_hour,
        }


class DrawdownEvent(models.Model):
    """
    Records every time a bot hits a drawdown threshold.
    Used for analytics and compliance auditing.
    """
    id          = models.BigAutoField(primary_key=True)
    bot         = models.ForeignKey(
        TradingBot, on_delete=models.CASCADE,
        related_name='drawdown_events'
    )

    class EventType(models.TextChoices):
        PAUSE   = 'pause',  'Bot Paused (drawdown_pause_percent hit)'
        HALT    = 'halt',   'Bot Halted (max_drawdown_percent hit)'
        DAILY   = 'daily',  'Daily Loss Limit Hit'
        RESUME  = 'resume', 'Bot Resumed'

    event_type          = models.CharField(max_length=10, choices=EventType.choices)
    drawdown_percent    = models.FloatField()
    balance_at_event    = models.DecimalField(max_digits=18, decimal_places=2)
    peak_balance        = models.DecimalField(max_digits=18, decimal_places=2)
    triggered_by        = models.CharField(
        max_length=100, blank=True,
        help_text="Trade ID or 'daily_check' that triggered this event"
    )
    notes               = models.TextField(blank=True)

    timestamp   = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table    = 'risk_drawdown_event'
        ordering    = ['-timestamp']
        indexes     = [
            models.Index(fields=['bot', 'timestamp']),
            models.Index(fields=['event_type', 'timestamp']),
        ]
        verbose_name        = 'Drawdown Event'
        verbose_name_plural = 'Drawdown Events'

    def __str__(self):
        return (
            f"{self.event_type.upper()} | Bot {self.bot.name} | "
            f"DD={self.drawdown_percent:.2f}% @ {self.timestamp:%Y-%m-%d %H:%M}"
        )