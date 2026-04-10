# ============================================================
# User, UserProfile, TradingAccount, Portfolio, AccountAllocation models
# ============================================================
import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from utils.constants import Broker, AccountType
from utils.encryption import encrypt_value, decrypt_value


# ── Custom User Manager ──────────────────────────────────────
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


# ── User ─────────────────────────────────────────────────────
class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model using email as the unique identifier.
    Replaces Django's default username-based auth.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email       = models.EmailField(unique=True, db_index=True)
    first_name  = models.CharField(max_length=100, blank=True)
    last_name   = models.CharField(max_length=100, blank=True)

    # Permissions / status
    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)   # email verified

    # Timestamps
    date_joined = models.DateTimeField(default=timezone.now)
    last_login  = models.DateTimeField(null=True, blank=True)
    updated_at  = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table   = 'accounts_user'
        ordering   = ['-date_joined']
        indexes    = [
            models.Index(fields=['email']),
            models.Index(fields=['is_active', 'is_verified']),
        ]
        verbose_name        = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.get_full_name()} <{self.email}>"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def full_name(self):
        return self.get_full_name()


# ── UserProfile ──────────────────────────────────────────────
class UserProfile(models.Model):
    """
    Extended profile data for a User.
    One-to-one with User; auto-created via signal (Phase C).
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE,
        related_name='profile', primary_key=True
    )

    # Preferences
    timezone        = models.CharField(max_length=50, default='UTC')
    currency        = models.CharField(max_length=10, default='USD')
    language        = models.CharField(max_length=10, default='en')

    # Dashboard / notification settings
    email_alerts        = models.BooleanField(default=True)
    email_on_trade      = models.BooleanField(default=True)
    email_on_error      = models.BooleanField(default=True)
    dashboard_theme     = models.CharField(
        max_length=20,
        choices=[('dark', 'Dark'), ('light', 'Light')],
        default='dark'
    )

    # NLP command interface preference
    nlp_enabled     = models.BooleanField(default=True)
    nlp_model       = models.CharField(max_length=80, default='claude-3-5-sonnet-20241022')

    # Timestamps
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_userprofile'
        verbose_name        = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"Profile({self.user.email})"
    


class BrokerType(models.TextChoices):
    OANDA = 'oanda', 'OANDA'
    MT5   = 'mt5',   'MetaTrader 5'
    OTHER = 'other', 'Other'
 
 
class AccountType(models.TextChoices):
    PERSONAL = 'personal', 'Personal'
    FUNDED   = 'funded',   'Funded Account'
    DEMO     = 'demo',     'Demo / Practice'
    CONTEST  = 'contest',  'Contest'
 
 
class FundedFirm(models.TextChoices):
    FTMO          = 'ftmo',          'FTMO'
    MFF           = 'mff',           'MyForexFunds'
    TRUE_FOREX    = 'true_forex',    'True Forex Funds'
    FUNDED_NEXT   = 'funded_next',   'FundedNext'
    ALPHA_CAPITAL = 'alpha_capital', 'Alpha Capital Group'
    E8_FUNDING    = 'e8_funding',    'E8 Funding'
    OTHER         = 'other',         'Other'
    NONE          = '',              'N/A'
 






# ── TradingAccount ───────────────────────────────────────────
# ── TradingAccount ───────────────────────────────────────────
class TradingAccount(models.Model):
    """
    Broker trading account linked to a User.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='trading_accounts'
    )
    
    portfolio = models.ForeignKey(
        'accounts.Portfolio',
        on_delete=models.SET_NULL,
        null=True, blank=True, 
        related_name='trading_accounts'
    )

    # Account identity
    name = models.CharField(max_length=150)
    broker = models.CharField(max_length=30, choices=Broker.choices)

    
    broker_type = models.CharField(
        max_length=20,
        choices=BrokerType.choices,
        default=BrokerType.OANDA,
        help_text='Broker connector type (OANDA REST or MT5)',
    )
    
    # Note: Removed the duplicate account_type definition that was further down
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.DEMO,
        help_text='Account category — personal, funded, demo',
    )
    
    funded_firm = models.CharField(
        max_length=30,
        choices=FundedFirm.choices,
        default='',
        blank=True,
        help_text='Funded firm name (FTMO, MFF, etc.) — leave blank for personal',
    )
    
    max_loss_limit = models.FloatField(
        null=True,
        blank=True,
        help_text='Maximum allowed loss for funded accounts (USD)',
    )
    
    profit_target = models.FloatField(
        null=True,
        blank=True,
        help_text='Profit target for funded account challenge (USD)',
    )
    
    daily_loss_limit = models.FloatField(
        null=True,
        blank=True,
        help_text='Daily max drawdown limit (USD) — funded account rule',
    )

    account_id = models.CharField(max_length=100)

    # ── Encrypted broker credentials ─────────────────────────
    _api_key_encrypted = models.TextField(blank=True, db_column='api_key')
    _api_secret_encrypted = models.TextField(blank=True, db_column='api_secret')

    # Account financials (synced periodically from broker)
    balance         = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    equity          = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    margin_used     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    margin_free     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    currency        = models.CharField(max_length=10, default='USD')

    # Status
    is_active       = models.BooleanField(default=True)
    is_verified     = models.BooleanField(default=False)
    last_synced     = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table    = 'accounts_tradingaccount'
        ordering    = ['-created_at']
        unique_together = [('user', 'broker', 'account_id')]
        indexes = [
            models.Index(fields=['user', 'broker']),
            models.Index(fields=['is_active']),
            models.Index(fields=['broker', 'account_id']),
        ]
        verbose_name        = 'Trading Account'
        verbose_name_plural = 'Trading Accounts'

    def __str__(self):
        return f"{self.name} [{self.broker}] ({self.account_type})"

    def set_api_key(self, raw_key: str):
        self._api_key_encrypted = encrypt_value(raw_key)

    def get_api_key(self) -> str:
        return decrypt_value(self._api_key_encrypted)

    def set_api_secret(self, raw_secret: str):
        self._api_secret_encrypted = encrypt_value(raw_secret)

    def get_api_secret(self) -> str:
        return decrypt_value(self._api_secret_encrypted)

    def __repr__(self):
        return (
            f"<TradingAccount id={self.id} broker={self.broker} "
            f"type={self.account_type} user={self.user_id}>"
        )


# ── Portfolio ─────────────────────────────────────────────────
class Portfolio(models.Model):
    """
    A named collection of TradingAccounts belonging to one user.
    Allows grouping accounts (e.g. 'Live Accounts', 'Demo Testing').

    A user can have multiple portfolios.
    Each TradingAccount can belong to at most one portfolio.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey(
        User, on_delete=models.CASCADE, 
        related_name='portfolios'
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
        verbose_name = 'Portfolio'
        verbose_name_plural = 'Portfolios'

    def __str__(self):
        return f"{self.name} ({self.user.email})"

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


# ── AccountAllocation ─────────────────────────────────────────
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
        verbose_name = 'Account Allocation'
        verbose_name_plural = 'Account Allocations'

    def __str__(self):
        return f"{self.portfolio.name} → {self.account.name} ({self.allocation_pct}%)"
    
    

