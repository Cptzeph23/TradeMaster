# ============================================================
# DESTINATION: /opt/forex_bot/utils/decorators.py
# Custom decorators and middleware for the platform
# ============================================================
import time
import logging
import functools
from typing import Callable
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger('django')


# ── Request Logging Middleware ───────────────────────────────
class RequestLoggingMiddleware:
    """
    Log every inbound HTTP request with timing.
    Attached in settings.MIDDLEWARE.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - start) * 1000

        # Skip static/media file logging
        if not request.path.startswith(('/static/', '/media/')):
            logger.info(
                f"{request.method} {request.path} → {response.status_code} "
                f"({duration_ms:.1f}ms) user={getattr(request.user, 'id', 'anon')}"
            )
        return response


# ── Timing Decorator ─────────────────────────────────────────
def timing(func: Callable) -> Callable:
    """Log execution time of any function."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.monotonic()
        result = func(*args, **kwargs)
        elapsed = (time.monotonic() - start) * 1000
        logger.debug(f"{func.__qualname__} completed in {elapsed:.2f}ms")
        return result
    return wrapper


# ── Retry Decorator ──────────────────────────────────────────
def retry(max_attempts: int = 3, delay: float = 1.0,
          exceptions: tuple = (Exception,)):
    """Retry a function on failure with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        raise
                    wait = delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"{func.__qualname__} failed (attempt {attempt}/{max_attempts}): "
                        f"{exc}. Retrying in {wait:.1f}s…"
                    )
                    time.sleep(wait)
        return wrapper
    return decorator


# ── Rate-limit guard for trading actions ─────────────────────
def require_bot_owner(view_func):
    """
    DRF view decorator: ensures request.user owns the bot
    referenced in URL kwargs (bot_pk or pk).
    Applied in Phase J (API views).
    """
    @functools.wraps(view_func)
    def wrapped_view(self, request, *args, **kwargs):
        from apps.trading.models import TradingBot
        bot_id = kwargs.get('bot_pk') or kwargs.get('pk')
        if bot_id:
            try:
                bot = TradingBot.objects.get(pk=bot_id)
                if bot.user != request.user and not request.user.is_staff:
                    from rest_framework.exceptions import PermissionDenied
                    raise PermissionDenied("You do not own this bot.")
            except TradingBot.DoesNotExist:
                from rest_framework.exceptions import NotFound
                raise NotFound("Bot not found.")
        return view_func(self, request, *args, **kwargs)
    return wrapped_view
