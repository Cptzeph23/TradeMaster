# ============================================================
# DESTINATION: /opt/forex_bot/utils/validators.py
# Input validation utilities
# ============================================================
import re
from typing import Any
from django.core.exceptions import ValidationError
from .constants import ALL_FOREX_PAIRS, Timeframe


def validate_forex_symbol(symbol: str) -> str:
    """Ensure the symbol is a recognised forex pair."""
    normalised = symbol.upper().replace('/', '_').replace('-', '_')
    if normalised not in ALL_FOREX_PAIRS:
        raise ValidationError(
            f"'{symbol}' is not a supported forex pair. "
            f"Supported pairs: {', '.join(ALL_FOREX_PAIRS)}"
        )
    return normalised


def validate_timeframe(value: str) -> str:
    valid = [t.value for t in Timeframe]
    if value not in valid:
        raise ValidationError(f"Invalid timeframe '{value}'. Valid: {valid}")
    return value


def validate_risk_percent(value: float) -> float:
    if not (0.01 <= value <= 10.0):
        raise ValidationError("Risk percent must be between 0.01% and 10%.")
    return value


def validate_lot_size(value: float) -> float:
    if not (0.01 <= value <= 100.0):
        raise ValidationError("Lot size must be between 0.01 and 100.")
    return round(value, 2)


def validate_stop_loss_pips(value: float) -> float:
    if value < 1:
        raise ValidationError("Stop loss must be at least 1 pip.")
    if value > 10000:
        raise ValidationError("Stop loss cannot exceed 10,000 pips.")
    return value


def validate_api_key_format(key: str, broker: str) -> bool:
    """Basic format check for broker API keys."""
    patterns = {
        'oanda': r'^[a-f0-9\-]{36,72}$',
        'metatrader5': r'^\d{6,10}$',  # MT5 login is numeric
    }
    pattern = patterns.get(broker.lower())
    if pattern and not re.match(pattern, key, re.IGNORECASE):
        return False
    return True
