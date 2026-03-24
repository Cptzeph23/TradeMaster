# ============================================================
# Portfolio — aggregates P&L and stats across all trading accounts
# ============================================================
import uuid
from django.db import models
from apps.accounts.models import User, TradingAccount


class Portfolio(models.Model):
    """
    A named collection of TradingAccounts belonging to one user.
    Allows grouping accounts (e.g. 'Live Accounts', 'Demo Testing').

    A user can have multiple portfolios.
    Each TradingAccount can belong to at most one portfolio.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='portfolios'
    )
    name        = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_default  = models.BooleanField(
        default=False,
        help_text="The default portfolio is shown on the main dashboard."
    )
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table    = 'accounts_portfolio'
        ordering    = ['-is_default', 'name']
        unique_together = [('user', 'name')]

    def __str__(self):
        return f"{self.name} ({self.user.email})"

    # ── Computed properties ──────────────────────────────────
    @property
    def accounts(self):
        return self.trading_accounts.filter(is_active=True)

    @property
    def total_balance(self) -> float:
        return sum(
            float(a.balance or 0) for a in self.accounts
        )

    @property
    def total_equity(self) -> float:
        return sum(
            float(a.equity or 0) for a in self.accounts
        )

    @property
    def total_pnl(self) -> float:
        from apps.trading.models import Trade
        from utils.constants import TradeStatus
        pnl = Trade.objects.filter(
            bot__trading_account__in=self.accounts,
            status=TradeStatus.CLOSED,
        ).values_list('profit_loss', flat=True)
        return round(sum(float(p) for p in pnl), 2)

    @property
    def running_bots(self) -> int:
        from apps.trading.models import TradingBot
        from utils.constants import BotStatus
        return TradingBot.objects.filter(
            trading_account__in=self.accounts,
            status=BotStatus.RUNNING,
            is_active=True,
        ).count()

    @property
    def open_trades(self) -> int:
        from apps.trading.models import Trade
        from utils.constants import TradeStatus
        return Trade.objects.filter(
            bot__trading_account__in=self.accounts,
            status=TradeStatus.OPEN,
        ).count()

    def get_equity_curve(self) -> list:
        """Combined equity curve across all accounts."""
        from apps.trading.models import Trade
        from utils.constants import TradeStatus
        trades = Trade.objects.filter(
            bot__trading_account__in=self.accounts,
            status=TradeStatus.CLOSED,
        ).order_by('closed_at').values_list('profit_loss', flat=True)

        balance = self.total_balance
        curve   = [round(balance - sum(float(p) for p in trades), 2)]
        running = curve[0]
        for pnl in trades:
            running += float(pnl)
            curve.append(round(running, 2))
        return curve


class AccountAllocation(models.Model):
    """
    Defines how much capital (%) is allocated to each account
    within a portfolio. Used for portfolio-level risk management.
    """
    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE,
        related_name='allocations'
    )
    account   = models.ForeignKey(
        TradingAccount, on_delete=models.CASCADE,
        related_name='portfolio_allocations'
    )
    allocation_pct = models.FloatField(
        default=100.0,
        help_text="Percentage of portfolio capital allocated to this account (0-100)"
    )
    max_drawdown_pct = models.FloatField(
        default=20.0,
        help_text="Max drawdown for this account before it's paused"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table        = 'accounts_allocation'
        unique_together = [('portfolio', 'account')]

    def __str__(self):
        return f"{self.portfolio.name} → {self.account.name} ({self.allocation_pct}%)"