# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/apps/accounts/models.py
# User, UserProfile, TradingAccount models
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


# ── TradingAccount ───────────────────────────────────────────
class TradingAccount(models.Model):
    """
    Broker trading account linked to a User.
    API keys are stored ENCRYPTED using Fernet AES.
    A user may have multiple accounts (demo + live, multiple brokers).
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='trading_accounts'
    )

    # Account identity
    name        = models.CharField(max_length=150)        # e.g. "OANDA Live EUR"
    broker      = models.CharField(max_length=30, choices=Broker.choices)
    account_id  = models.CharField(max_length=100)        # broker-assigned account ID
    account_type= models.CharField(
        max_length=10,
        choices=AccountType.choices,
        default=AccountType.DEMO
    )

    # ── Encrypted broker credentials ─────────────────────────
    # Raw values are NEVER stored — only the encrypted token.
    # Use .get_api_key() / .set_api_key() methods below.
    _api_key_encrypted      = models.TextField(blank=True, db_column='api_key')
    _api_secret_encrypted   = models.TextField(blank=True, db_column='api_secret')

    # Account financials (synced periodically from broker)
    balance         = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    equity          = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    margin_used     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    margin_free     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    currency        = models.CharField(max_length=10, default='USD')

    # Status
    is_active       = models.BooleanField(default=True)
    is_verified     = models.BooleanField(default=False)  # connection tested
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

    # ── API key helpers (encrypt/decrypt on the fly) ──────────
    def set_api_key(self, raw_key: str):
        self._api_key_encrypted = encrypt_value(raw_key)

    def get_api_key(self) -> str:
        return decrypt_value(self._api_key_encrypted)

    def set_api_secret(self, raw_secret: str):
        self._api_secret_encrypted = encrypt_value(raw_secret)

    def get_api_secret(self) -> str:
        return decrypt_value(self._api_secret_encrypted)

    # Keep raw keys out of repr / logs
    def __repr__(self):
        return (
            f"<TradingAccount id={self.id} broker={self.broker} "
            f"type={self.account_type} user={self.user_id}>"
        )