# ============================================================
# Security utilities — audit logging, API key rotation helpers
# ============================================================
import hashlib
import secrets
import logging
from functools import wraps
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger('django')
audit_logger = logging.getLogger('audit')


# ── Audit logging ─────────────────────────────────────────────
class AuditLog:
    """
    Records security-relevant events to both the DB and log file.
    Events: login, logout, api_key_change, bot_start, bot_stop,
            trade_placed, risk_rule_changed, password_changed
    """

    @staticmethod
    def log(user, event: str, details: dict = None, request=None):
        ip = AuditLog._get_ip(request) if request else 'unknown'
        audit_logger.info(
            f"AUDIT | user={user.email if user else 'anon'} "
            f"event={event} ip={ip} "
            f"details={details or {}}"
        )

    @staticmethod
    def log_login(user, request, success: bool):
        AuditLog.log(
            user=user,
            event='login_success' if success else 'login_failure',
            details={'email': user.email if user else 'unknown'},
            request=request,
        )
        if not success:
            AuditLog._track_failed_login(request)

    @staticmethod
    def log_api_key_change(user, account_name: str, request):
        AuditLog.log(
            user=user,
            event='api_key_changed',
            details={'account': account_name},
            request=request,
        )

    @staticmethod
    def log_bot_action(user, bot_name: str, action: str, request=None):
        AuditLog.log(
            user=user,
            event=f'bot_{action}',
            details={'bot': bot_name},
            request=request,
        )

    @staticmethod
    def _get_ip(request) -> str:
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')

    @staticmethod
    def _track_failed_login(request):
        """Track failed logins for brute force detection."""
        if not request:
            return
        ip  = AuditLog._get_ip(request)
        key = f"failed_login:{ip}"
        try:
            count = cache.get(key, 0) + 1
            cache.set(key, count, timeout=3600)   # reset after 1h
            if count >= 10:
                logger.warning(
                    f"SECURITY: {count} failed login attempts from {ip} "
                    f"— consider blocking this IP"
                )
        except Exception:
            pass


# ── Sensitive data masking ────────────────────────────────────
def mask_api_key(key: str) -> str:
    """Show only last 4 chars of an API key."""
    if not key or len(key) < 8:
        return '****'
    return f"****{key[-4:]}"


def hash_sensitive(value: str) -> str:
    """One-way hash for storing sensitive reference values."""
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]


# ── Token generation ──────────────────────────────────────────
def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


# ── Input sanitisation ────────────────────────────────────────
def sanitise_symbol(symbol: str) -> str:
    """
    Clean and validate a forex symbol input.
    Prevents injection via symbol parameters.
    """
    import re
    cleaned = re.sub(r'[^A-Za-z_]', '', symbol).upper()
    if len(cleaned) < 6 or len(cleaned) > 7:
        raise ValueError(f"Invalid symbol: {symbol!r}")
    return cleaned


def sanitise_command(command: str, max_length: int = 500) -> str:
    """
    Basic sanitisation for NLP command input.
    Strips dangerous characters, enforces length limit.
    """
    if not isinstance(command, str):
        raise ValueError("Command must be a string")
    command = command.strip()
    if len(command) > max_length:
        raise ValueError(f"Command too long (max {max_length} chars)")
    # Strip null bytes and control characters
    command = ''.join(c for c in command if ord(c) >= 32 or c in '\n\t')
    return command


# ── Decorator: require verified account ──────────────────────
def require_verified_account(view_func):
    """
    DRF view decorator: block unverified broker accounts from
    triggering live trades.
    """
    @wraps(view_func)
    def wrapped(self, request, *args, **kwargs):
        from apps.accounts.models import TradingAccount
        account_id = kwargs.get('account_id') or request.data.get('trading_account')
        if account_id:
            try:
                account = TradingAccount.objects.get(
                    pk=account_id, user=request.user
                )
                if not account.is_verified:
                    from rest_framework.exceptions import PermissionDenied
                    raise PermissionDenied(
                        "Broker account must be verified before trading. "
                        "Visit /api/v1/auth/trading-accounts/<id>/verify/"
                    )
            except TradingAccount.DoesNotExist:
                pass
        return view_func(self, request, *args, **kwargs)
    return wrapped