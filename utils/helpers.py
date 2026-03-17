# ============================================================
# DESTINATION: /opt/forex_bot/utils/helpers.py
# General-purpose utility functions used across the platform
# ============================================================
import math
from typing import Optional
from decimal import Decimal, ROUND_HALF_UP
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


# ── Custom DRF Exception Handler ────────────────────────────
def custom_exception_handler(exc, context):
    """
    Wraps all DRF errors in a consistent envelope:
    {
        "success": false,
        "error": { "code": "...", "message": "...", "details": {...} }
    }
    """
    response = exception_handler(exc, context)
    if response is not None:
        response.data = {
            'success': False,
            'error': {
                'code': response.status_code,
                'message': _get_error_message(response.data),
                'details': response.data if isinstance(response.data, dict) else {},
            }
        }
    return response


def _get_error_message(data) -> str:
    if isinstance(data, dict):
        if 'detail' in data:
            return str(data['detail'])
        return '; '.join(
            f"{k}: {v[0] if isinstance(v, list) else v}"
            for k, v in data.items()
        )
    if isinstance(data, list):
        return str(data[0]) if data else 'An error occurred'
    return str(data)


# ── Pip Calculation ──────────────────────────────────────────
def get_pip_size(symbol: str) -> float:
    """Return the pip size for a given forex symbol."""
    if 'JPY' in symbol.upper():
        return 0.01
    return 0.0001


def pips_to_price(pips: float, symbol: str) -> float:
    return pips * get_pip_size(symbol)


def price_to_pips(price_diff: float, symbol: str) -> float:
    pip_size = get_pip_size(symbol)
    return round(abs(price_diff) / pip_size, 1)


# ── Position Sizing ──────────────────────────────────────────
def calculate_lot_size(
    account_balance: float,
    risk_percent: float,
    stop_loss_pips: float,
    symbol: str,
    pip_value_per_lot: float = 10.0,  # standard lot pip value in USD
) -> float:
    """
    Calculate position size in lots using fixed fractional risk.

    Formula:
        risk_amount = account_balance * risk_percent / 100
        lot_size    = risk_amount / (stop_loss_pips * pip_value_per_lot)
    """
    if stop_loss_pips <= 0:
        return 0.01  # minimum lot
    risk_amount = account_balance * (risk_percent / 100)
    lot_size = risk_amount / (stop_loss_pips * pip_value_per_lot)
    # Round to 2 decimal places, min 0.01 lot, max 100 lots
    return float(Decimal(str(lot_size)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


# ── Performance Metrics ──────────────────────────────────────
def calculate_sharpe_ratio(
    returns: list,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> float:
    """Annualised Sharpe Ratio from a list of daily returns."""
    if not returns or len(returns) < 2:
        return 0.0
    import numpy as np
    r = np.array(returns, dtype=float)
    excess = r - (risk_free_rate / periods_per_year)
    std = np.std(r, ddof=1)
    if std == 0:
        return 0.0
    return float((np.mean(excess) / std) * math.sqrt(periods_per_year))


def calculate_profit_factor(trades: list) -> float:
    """
    Profit Factor = Gross Profit / Gross Loss
    trades: list of profit_loss values (float)
    """
    gross_profit = sum(t for t in trades if t > 0)
    gross_loss   = abs(sum(t for t in trades if t < 0))
    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0
    return round(gross_profit / gross_loss, 2)


def calculate_max_drawdown(equity_curve: list) -> float:
    """Max Drawdown as a percentage of peak equity."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
    return round(max_dd, 2)


def calculate_win_rate(trades: list) -> float:
    """Win rate as a percentage."""
    if not trades:
        return 0.0
    winners = sum(1 for t in trades if t > 0)
    return round((winners / len(trades)) * 100, 2)


# ── Formatting ───────────────────────────────────────────────
def format_currency(amount: float, currency: str = 'USD') -> str:
    return f"{currency} {amount:,.2f}"


def truncate_string(s: str, max_len: int = 100) -> str:
    return s if len(s) <= max_len else s[:max_len - 3] + '...'
