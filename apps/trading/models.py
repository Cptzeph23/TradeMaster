# ============================================================
# TradingBot, Trade, BotLog, NLPCommand models
# ============================================================
import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.accounts.models import User, TradingAccount
from apps.strategies.models import Strategy
from utils.constants import (
    BotStatus, OrderType, TradeStatus,
    Timeframe, CommandType, Broker
)


# ── TradingBot ───────────────────────────────────────────────
class TradingBot(models.Model):
    """
    An automated trading bot that runs a Strategy on a TradingAccount.

    The bot has:
    - One strategy
    - One linked broker account
    - A JSON risk_settings block (mirrors RiskRule but stored inline
      for fast access by the engine without DB joins)
    - Full NLP command history (see NLPCommand FK below)
    - Status machine: idle → running → paused → stopped | error

    Risk settings JSON schema:
    {
        "risk_percent":       1.0,    // % of balance per trade
        "max_drawdown":       20.0,   // halt bot at this % drawdown
        "stop_loss_pips":     50,
        "take_profit_pips":   100,
        "max_trades_per_day": 10,
        "max_open_trades":    3,
        "trailing_stop":      false,
        "trailing_stop_pips": 20
    }
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user            = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='bots'
    )
    trading_account = models.ForeignKey(
        TradingAccount, on_delete=models.PROTECT,
        related_name='bots'
    )
    strategy        = models.ForeignKey(
        Strategy, on_delete=models.PROTECT,
        related_name='bots'
    )

    # Identity
    name            = models.CharField(max_length=200)
    description     = models.TextField(blank=True)

    # Configuration
    broker          = models.CharField(max_length=30, choices=Broker.choices)
    symbols         = ArrayField(
        models.CharField(max_length=20),
        default=list,
        help_text="Pairs this bot trades, e.g. ['EUR_USD', 'GBP_USD']"
    )
    timeframe       = models.CharField(
        max_length=5,
        choices=Timeframe.choices,
        default=Timeframe.H1
    )

    # Risk settings (JSON — fast engine access, no extra DB join)
    risk_settings   = models.JSONField(default=dict)

    # Status
    status          = models.CharField(
        max_length=20,
        choices=BotStatus.choices,
        default=BotStatus.IDLE,
        db_index=True
    )
    error_message   = models.TextField(blank=True)

    # Celery task ID of the currently running bot task
    celery_task_id  = models.CharField(max_length=255, blank=True)

    # Live performance snapshot (updated after every trade)
    total_trades        = models.PositiveIntegerField(default=0)
    winning_trades      = models.PositiveIntegerField(default=0)
    total_profit_loss   = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    current_drawdown    = models.FloatField(default=0.0)
    peak_balance        = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    # Control flags (can be flipped by NLP commands / API)
    is_active           = models.BooleanField(default=True)
    allow_buy           = models.BooleanField(default=True)
    allow_sell          = models.BooleanField(default=True)

    # Timestamps
    started_at      = models.DateTimeField(null=True, blank=True)
    stopped_at      = models.DateTimeField(null=True, blank=True)
    last_signal_at  = models.DateTimeField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table    = 'trading_bot'
        ordering    = ['-created_at']
        indexes     = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['broker', 'status']),
            models.Index(fields=['is_active']),
        ]
        verbose_name        = 'Trading Bot'
        verbose_name_plural = 'Trading Bots'

    def __str__(self):
        return f"{self.name} [{self.status}] — {self.strategy.name}"

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return round((self.winning_trades / self.total_trades) * 100, 2)

    @property
    def is_running(self) -> bool:
        return self.status == BotStatus.RUNNING

    def get_risk_setting(self, key: str, default=None):
        return self.risk_settings.get(key, default)


# ── Trade ─────────────────────────────────────────────────────
class Trade(models.Model):
    """
    A single executed trade by a TradingBot.
    Covers the full lifecycle: pending → open → closed/cancelled.

    Broker-assigned IDs are stored for reconciliation.
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot             = models.ForeignKey(
        TradingBot, on_delete=models.CASCADE,
        related_name='trades'
    )
    trading_account = models.ForeignKey(
        TradingAccount, on_delete=models.PROTECT,
        related_name='trades'
    )

    # Broker-side identifiers
    broker_order_id = models.CharField(max_length=150, blank=True, db_index=True)
    broker_trade_id = models.CharField(max_length=150, blank=True, db_index=True)

    # Trade details
    symbol          = models.CharField(max_length=20, db_index=True)
    order_type      = models.CharField(max_length=20, choices=OrderType.choices)
    status          = models.CharField(
        max_length=20,
        choices=TradeStatus.choices,
        default=TradeStatus.PENDING,
        db_index=True
    )

    # Sizing
    lot_size        = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0.01), MaxValueValidator(100)]
    )
    units           = models.IntegerField(default=0)  # broker units (OANDA style)

    # Prices
    entry_price     = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    exit_price      = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    stop_loss       = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    take_profit     = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    trailing_stop   = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)

    # P&L
    profit_loss     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    profit_loss_pips= models.FloatField(default=0.0)
    commission      = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    swap            = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    # Context — which strategy signal triggered this
    signal_data     = models.JSONField(
        default=dict, blank=True,
        help_text="Snapshot of indicator values at signal time"
    )

    # Timestamps
    opened_at       = models.DateTimeField(null=True, blank=True, db_index=True)
    closed_at       = models.DateTimeField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table    = 'trading_trade'
        ordering    = ['-created_at']
        indexes     = [
            models.Index(fields=['bot', 'status']),
            models.Index(fields=['bot', 'symbol']),
            models.Index(fields=['symbol', 'opened_at']),
            models.Index(fields=['status', 'opened_at']),
            models.Index(fields=['trading_account', 'status']),
            models.Index(fields=['broker_order_id']),
        ]
        verbose_name        = 'Trade'
        verbose_name_plural = 'Trades'

    def __str__(self):
        return (
            f"Trade {self.id} | {self.order_type.upper()} {self.lot_size} "
            f"{self.symbol} @ {self.entry_price} [{self.status}]"
        )

    @property
    def is_profitable(self) -> bool:
        return float(self.profit_loss) > 0

    @property
    def duration_seconds(self):
        if self.opened_at and self.closed_at:
            return (self.closed_at - self.opened_at).total_seconds()
        return None


# ── BotLog ────────────────────────────────────────────────────
class BotLog(models.Model):
    """
    Append-only audit log for all bot events.
    Covers: signals, orders, errors, status changes, NLP commands.
    """
    class Level(models.TextChoices):
        DEBUG   = 'debug',   'Debug'
        INFO    = 'info',    'Info'
        WARNING = 'warning', 'Warning'
        ERROR   = 'error',   'Error'

    class EventType(models.TextChoices):
        SIGNAL          = 'signal',         'Strategy Signal'
        ORDER_PLACED    = 'order_placed',   'Order Placed'
        ORDER_FILLED    = 'order_filled',   'Order Filled'
        ORDER_REJECTED  = 'order_rejected', 'Order Rejected'
        ORDER_CLOSED    = 'order_closed',   'Order Closed'
        RISK_BLOCK      = 'risk_block',     'Risk Rule Blocked'
        STATUS_CHANGE   = 'status_change',  'Status Changed'
        NLP_COMMAND     = 'nlp_command',    'NLP Command'
        ERROR           = 'error',          'Error'
        MARKET_DATA     = 'market_data',    'Market Data'
        HEARTBEAT       = 'heartbeat',      'Heartbeat'

    id          = models.BigAutoField(primary_key=True)
    bot         = models.ForeignKey(
        TradingBot, on_delete=models.CASCADE,
        related_name='logs'
    )
    trade       = models.ForeignKey(
        Trade, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='logs'
    )

    level       = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    event_type  = models.CharField(max_length=30, choices=EventType.choices)
    message     = models.TextField()
    data        = models.JSONField(
        default=dict, blank=True,
        help_text="Extra structured data (prices, indicator values, etc.)"
    )

    timestamp   = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table    = 'trading_botlog'
        ordering    = ['-timestamp']
        indexes     = [
            models.Index(fields=['bot', 'timestamp']),
            models.Index(fields=['bot', 'level']),
            models.Index(fields=['bot', 'event_type']),
            models.Index(fields=['event_type', 'timestamp']),
        ]
        verbose_name        = 'Bot Log'
        verbose_name_plural = 'Bot Logs'

    def __str__(self):
        return f"[{self.level.upper()}] {self.event_type} — Bot {self.bot_id} @ {self.timestamp}"


# ── NLPCommand ───────────────────────────────────────────────
class NLPCommand(models.Model):
    """
    Stores every natural-language command the user sends to a bot.

    Flow:
        User types:  "Set stop loss to 30 pips and trade only EUR/USD"
        AI parses:   {action: 'set_risk', stop_loss_pips: 30, symbols: ['EUR_USD']}
        Bot applies: updates risk_settings and symbols on the bot
        Result:      stored in execution_result

    The raw_command and parsed_intent fields allow full audit of
    what the AI understood vs. what the user intended.
    """
    class Status(models.TextChoices):
        PENDING  = 'pending',  'Pending'
        SUCCESS  = 'success',  'Success'
        FAILED   = 'failed',   'Failed'
        PARTIAL  = 'partial',  'Partial'
        REJECTED = 'rejected', 'Rejected (Risk / Permission)'

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='nlp_commands'
    )
    bot         = models.ForeignKey(
        TradingBot, on_delete=models.CASCADE,
        related_name='nlp_commands',
        null=True, blank=True,
        help_text="Null means command targets all bots or is global"
    )

    # Input
    raw_command     = models.TextField(help_text="Exact text the user typed")

    # AI parsing output
    command_type    = models.CharField(
        max_length=30,
        choices=CommandType.choices,
        default=CommandType.UNKNOWN
    )
    parsed_intent   = models.JSONField(
        default=dict,
        help_text="Structured intent extracted by AI, e.g. "
                  "{'action': 'set_risk', 'risk_percent': 1.5}"
    )
    ai_explanation  = models.TextField(
        blank=True,
        help_text="Human-readable explanation of what the AI understood"
    )
    confidence      = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="AI confidence score 0–1"
    )

    # Execution
    status              = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    execution_result    = models.JSONField(
        default=dict, blank=True,
        help_text="What actually happened when the command was applied"
    )
    error_detail        = models.TextField(blank=True)

    # AI model used for this parse
    model_used  = models.CharField(max_length=100, blank=True)
    tokens_used = models.PositiveIntegerField(default=0)

    # Timestamps
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table    = 'trading_nlpcommand'
        ordering    = ['-created_at']
        indexes     = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['bot', 'created_at']),
            models.Index(fields=['command_type', 'status']),
            models.Index(fields=['status']),
        ]
        verbose_name        = 'NLP Command'
        verbose_name_plural = 'NLP Commands'

    def __str__(self):
        return (
            f"Command [{self.command_type}] by {self.user.email} "
            f"→ {self.status} @ {self.created_at:%Y-%m-%d %H:%M}"
        )