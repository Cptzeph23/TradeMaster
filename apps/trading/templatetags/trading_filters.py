# ============================================================
# Custom Django template filters for the trading dashboard
# ============================================================
from django import template

register = template.Library()


@register.filter(name='replace')
def replace_filter(value, args):
    """
    Replace a substring in a string.
    Usage in template: {{ "EUR_USD"|replace:"_,/" }}  → "EUR/USD"
    Usage in template: {{ pair|replace:"_,/" }}
    Args format: "old,new"
    """
    try:
        old, new = args.split(',', 1)
        return str(value).replace(old, new)
    except (ValueError, AttributeError):
        return value


@register.filter(name='abs_val')
def abs_val(value):
    """Return absolute value. Usage: {{ number|abs_val }}"""
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return value


@register.filter(name='pnl_class')
def pnl_class(value):
    """Return CSS class based on P&L sign. Usage: {{ pnl|pnl_class }}"""
    try:
        return 'positive' if float(value) >= 0 else 'negative'
    except (TypeError, ValueError):
        return ''


@register.filter(name='pnl_sign')
def pnl_sign(value):
    """Add + prefix to positive numbers. Usage: {{ pnl|pnl_sign }}"""
    try:
        n = float(value)
        return f"+{n:.2f}" if n >= 0 else f"{n:.2f}"
    except (TypeError, ValueError):
        return value


@register.filter(name='status_badge')
def status_badge(status):
    """Return HTML badge for bot status."""
    labels = {
        'running':     ('Running',     'badge-running'),
        'idle':        ('Idle',        'badge-idle'),
        'paused':      ('Paused',      'badge-paused'),
        'stopped':     ('Stopped',     'badge-stopped'),
        'error':       ('Error',       'badge-error'),
        'backtesting': ('Backtesting', 'badge-backtesting'),
    }
    label, css = labels.get(status, (status, 'badge-idle'))
    return f'<span class="badge {css}">{label}</span>'