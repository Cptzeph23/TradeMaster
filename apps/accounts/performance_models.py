# ============================================================
# AccountPerformance — per-account metrics snapshot
# Updated after every trade close by the performance service
# ============================================================
import uuid
from django.db import models
from django.utils import timezone


class AccountPerformance(models.Model):
    """
    Rolling performance snapshot for one TradingAccount.

    One record per account — updated in-place after each trade.
    Historical snapshots are stored in AccountPerformanceHistory.

    Fields cover every metric the client requested:
      - total pips gained/lost
      - total profit in USD
      - win rate
      - drawdown
      - profit factor
      - per-symbol breakdown (JSON)
    """
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    account = models.OneToOneField(
        'accounts.TradingAccount',
        on_delete=models.CASCADE,
        related_name='performance',
    )

    # ── Trade counts ─────────────────────────────────────────
    total_trades    = models.PositiveIntegerField(default=0)
    winning_trades  = models.PositiveIntegerField(default=0)
    losing_trades   = models.PositiveIntegerField(default=0)
    breakeven_trades= models.PositiveIntegerField(default=0)

    # ── Pip metrics ───────────────────────────────────────────
    total_pips      = models.FloatField(default=0.0,
        help_text='Net pips across all closed trades (+ = profit)')
    total_pips_won  = models.FloatField(default=0.0,
        help_text='Total pips from winning trades only')
    total_pips_lost = models.FloatField(default=0.0,
        help_text='Total pips from losing trades (positive number)')
    avg_win_pips    = models.FloatField(default=0.0)
    avg_loss_pips   = models.FloatField(default=0.0)
    largest_win_pips= models.FloatField(default=0.0)
    largest_loss_pips=models.FloatField(default=0.0)

    # ── Monetary metrics ─────────────────────────────────────
    total_profit    = models.FloatField(default=0.0,
        help_text='Net P&L in account currency across all trades')
    gross_profit    = models.FloatField(default=0.0)
    gross_loss      = models.FloatField(default=0.0,
        help_text='Stored as positive number')
    largest_win     = models.FloatField(default=0.0)
    largest_loss    = models.FloatField(default=0.0,
        help_text='Stored as positive number')
    avg_win         = models.FloatField(default=0.0)
    avg_loss        = models.FloatField(default=0.0)

    # ── Rate metrics ──────────────────────────────────────────
    win_rate        = models.FloatField(default=0.0,
        help_text='Win rate as percentage 0–100')
    profit_factor   = models.FloatField(default=0.0,
        help_text='gross_profit / gross_loss (0 if no losses)')
    expectancy      = models.FloatField(default=0.0,
        help_text='Average expected profit per trade in account currency')

    # ── RRR metrics ───────────────────────────────────────────
    avg_rrr_used    = models.FloatField(default=0.0,
        help_text='Average RRR set at entry across all trades')
    avg_rrr_achieved= models.FloatField(default=0.0,
        help_text='Average RRR actually achieved at close')

    # ── Drawdown ──────────────────────────────────────────────
    max_drawdown_pct= models.FloatField(default=0.0,
        help_text='Maximum drawdown as % of peak balance')
    max_drawdown_usd= models.FloatField(default=0.0,
        help_text='Maximum drawdown in USD')
    current_drawdown= models.FloatField(default=0.0)
    peak_balance    = models.FloatField(default=0.0)

    # ── Streak ────────────────────────────────────────────────
    current_streak  = models.IntegerField(default=0,
        help_text='Positive = win streak, negative = loss streak')
    longest_win_streak  = models.PositiveIntegerField(default=0)
    longest_loss_streak = models.PositiveIntegerField(default=0)

    # ── Per-symbol breakdown ──────────────────────────────────
    symbol_stats    = models.JSONField(default=dict, blank=True,
        help_text='Dict keyed by symbol with per-symbol metrics')

    # ── Timestamps ───────────────────────────────────────────
    first_trade_at  = models.DateTimeField(null=True, blank=True)
    last_trade_at   = models.DateTimeField(null=True, blank=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table     = 'accounts_performance'
        verbose_name = 'Account Performance'

    def __str__(self):
        return (
            f"{self.account.name} — "
            f"WR={self.win_rate:.1f}% "
            f"Pips={self.total_pips:+.1f} "
            f"PF={self.profit_factor:.2f}"
        )

    def to_dict(self) -> dict:
        return {
            'account_id':      str(self.account_id),
            'account_name':    self.account.name,
            'broker_type':     getattr(self.account, 'broker_type', ''),
            'account_type':    getattr(self.account, 'account_type', ''),
            'funded_firm':     getattr(self.account, 'funded_firm', ''),
            'total_trades':    self.total_trades,
            'winning_trades':  self.winning_trades,
            'losing_trades':   self.losing_trades,
            'win_rate':        round(self.win_rate, 2),
            'total_pips':      round(self.total_pips, 1),
            'total_profit':    round(self.total_profit, 2),
            'gross_profit':    round(self.gross_profit, 2),
            'gross_loss':      round(self.gross_loss, 2),
            'profit_factor':   round(self.profit_factor, 2),
            'expectancy':      round(self.expectancy, 2),
            'avg_win_pips':    round(self.avg_win_pips, 1),
            'avg_loss_pips':   round(self.avg_loss_pips, 1),
            'largest_win_pips':round(self.largest_win_pips, 1),
            'avg_rrr_used':    round(self.avg_rrr_used, 2),
            'avg_rrr_achieved':round(self.avg_rrr_achieved, 2),
            'max_drawdown_pct':round(self.max_drawdown_pct, 2),
            'max_drawdown_usd':round(self.max_drawdown_usd, 2),
            'current_streak':  self.current_streak,
            'longest_win_streak': self.longest_win_streak,
            'symbol_stats':    self.symbol_stats,
            'last_trade_at':   (
                self.last_trade_at.isoformat()
                if self.last_trade_at else None
            ),
            'updated_at':      self.updated_at.isoformat(),
        }


class AccountPerformanceHistory(models.Model):
    """
    Daily snapshot of AccountPerformance for charting equity curves
    and tracking progress over time.

    One record per account per day — created by a Celery beat task.
    """
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    account     = models.ForeignKey(
        'accounts.TradingAccount',
        on_delete=models.CASCADE,
        related_name='performance_history',
    )
    snapshot_date  = models.DateField()
    balance        = models.FloatField(default=0.0)
    equity         = models.FloatField(default=0.0)
    daily_pnl      = models.FloatField(default=0.0)
    daily_pips     = models.FloatField(default=0.0)
    daily_trades   = models.PositiveIntegerField(default=0)
    daily_win_rate = models.FloatField(default=0.0)
    drawdown_pct   = models.FloatField(default=0.0)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = 'accounts_performance_history'
        unique_together = [('account', 'snapshot_date')]
        ordering        = ['-snapshot_date']

    def __str__(self):
        return (
            f"{self.account.name} {self.snapshot_date} "
            f"P&L={self.daily_pnl:+.2f}"
        )