# ============================================================
# Pip calculator — all pip math in one place
# ============================================================
import logging
from typing import Optional

logger = logging.getLogger('trading.pip_calculator')


def get_pip_size(symbol: str) -> float:
    """
    Return the pip size for a symbol.

    XAUUSD → 0.01
    EURUSD → 0.0001
    USDJPY → 0.01
    Unknown → 0.0001 (safe default)
    """
    from utils.constants import SYMBOL_CONFIG
    sym = _normalise(symbol)
    cfg = SYMBOL_CONFIG.get(sym)
    if cfg:
        return cfg['pip_size']
    # Fallback rules for unlisted symbols
    if 'JPY' in sym or 'XAU' in sym or 'XAG' in sym:
        return 0.01
    return 0.0001


def get_pip_value(symbol: str, lot_size: float = 1.0) -> float:
    """
    Return the monetary value of 1 pip for the given lot size.

    For a standard lot (1.0) on EURUSD: $10 per pip.
    For 0.01 lot (micro) on EURUSD:     $0.10 per pip.

    Args:
        symbol:   e.g. 'EURUSD', 'XAUUSD'
        lot_size: lot size (1.0 = standard, 0.1 = mini, 0.01 = micro)
    """
    from utils.constants import SYMBOL_CONFIG
    sym = _normalise(symbol)
    cfg = SYMBOL_CONFIG.get(sym, {})
    base_pip_value = float(cfg.get('pip_value', 10.0))
    return round(base_pip_value * lot_size, 6)


def price_to_pips(symbol: str, price_distance: float) -> float:
    """
    Convert a price distance to pips.

    Example:
        EURUSD: price_distance=0.0050 → 50 pips
        XAUUSD: price_distance=0.50   → 50 pips
        USDJPY: price_distance=0.50   → 50 pips
    """
    pip_size = get_pip_size(symbol)
    if pip_size == 0:
        return 0.0
    return round(abs(price_distance) / pip_size, 1)


def pips_to_price(symbol: str, pips: float) -> float:
    """
    Convert pips to a price distance.

    Example:
        EURUSD: 20 pips → 0.0020
        XAUUSD: 20 pips → 0.20
        USDJPY: 20 pips → 0.20
    """
    return round(pips * get_pip_size(symbol), 5)


def sl_price_from_pips(
    symbol:     str,
    entry:      float,
    sl_pips:    float,
    order_type: str,        # 'buy' or 'sell'
) -> float:
    """
    Calculate stop-loss price from pip distance.

    BUY:  SL is below entry  → entry - (sl_pips × pip_size)
    SELL: SL is above entry  → entry + (sl_pips × pip_size)
    """
    dist = pips_to_price(symbol, sl_pips)
    if order_type.lower() == 'buy':
        sl = entry - dist
    else:
        sl = entry + dist
    return round(sl, _digits(symbol))


def tp_price_from_pips(
    symbol:     str,
    entry:      float,
    tp_pips:    float,
    order_type: str,
) -> float:
    """
    Calculate take-profit price from pip distance.

    BUY:  TP is above entry  → entry + (tp_pips × pip_size)
    SELL: TP is below entry  → entry - (tp_pips × pip_size)
    """
    dist = pips_to_price(symbol, tp_pips)
    if order_type.lower() == 'buy':
        tp = entry + dist
    else:
        tp = entry - dist
    return round(tp, _digits(symbol))


def tp_from_sl_and_rrr(
    symbol:     str,
    entry:      float,
    sl_pips:    float,
    rrr:        float,
    order_type: str,
) -> tuple:
    """
    Calculate TP price given SL pips and Risk:Reward Ratio.

    Args:
        symbol:     trading symbol
        entry:      entry price
        sl_pips:    stop loss in pips (e.g. 20)
        rrr:        risk reward ratio (e.g. 2.0 = 1:2)
        order_type: 'buy' or 'sell'

    Returns:
        (sl_price, tp_price, tp_pips)

    Example:
        sl_pips=20, rrr=2.0 → tp_pips=40
        EURUSD BUY @ 1.1000, sl=1.0980, tp=1.1040
    """
    tp_pips = round(sl_pips * rrr, 1)
    sl_price = sl_price_from_pips(symbol, entry, sl_pips, order_type)
    tp_price = tp_price_from_pips(symbol, entry, tp_pips, order_type)
    return sl_price, tp_price, tp_pips


def calculate_lot_size(
    account_balance: float,
    risk_percent:    float,
    sl_pips:         float,
    symbol:          str,
    lot_size_override: Optional[float] = None,
) -> float:
    """
    Calculate position size using the pip-based formula.

    Formula:
        risk_amount = account_balance × (risk_percent / 100)
        pip_value   = pip_value_per_lot(symbol)
        lot_size    = risk_amount / (pip_value × sl_pips)

    Args:
        account_balance: current account balance in USD
        risk_percent:    risk as % of account (e.g. 1.0 = 1%)
        sl_pips:         stop loss distance in pips
        symbol:          trading symbol
        lot_size_override: if set, skip calculation and use this value

    Returns:
        lot_size rounded to 2 decimal places, clamped to symbol min/max

    Example:
        account=10000, risk=1%, sl=20 pips, EURUSD
        risk_amount = 100
        pip_value   = 10 (per standard lot)
        lot_size    = 100 / (10 × 20) = 0.50 lots
    """
    if lot_size_override is not None:
        return _clamp_lot(symbol, lot_size_override)

    if sl_pips <= 0:
        logger.warning(f"sl_pips={sl_pips} is invalid — defaulting to 0.01 lot")
        return _min_lot(symbol)

    risk_amount  = account_balance * (risk_percent / 100.0)
    pip_val      = get_pip_value(symbol, lot_size=1.0)

    if pip_val <= 0:
        logger.warning(f"pip_value=0 for {symbol} — cannot calculate lot size")
        return _min_lot(symbol)

    raw_lot = risk_amount / (pip_val * sl_pips)
    return _clamp_lot(symbol, raw_lot)


def profit_in_pips(
    symbol:      str,
    entry_price: float,
    exit_price:  float,
    order_type:  str,
) -> float:
    """
    Calculate profit/loss in pips for a closed trade.

    BUY:  profit_pips = (exit - entry) / pip_size
    SELL: profit_pips = (entry - exit) / pip_size
    """
    if order_type.lower() == 'buy':
        distance = exit_price - entry_price
    else:
        distance = entry_price - exit_price
    pip_size = get_pip_size(symbol)
    return round(distance / pip_size, 1) if pip_size else 0.0


def actual_rrr(
    symbol:      str,
    entry_price: float,
    exit_price:  float,
    sl_price:    float,
    order_type:  str,
) -> Optional[float]:
    """
    Calculate the actual RRR achieved on a closed trade.

    Returns None if SL distance is zero (invalid trade data).
    """
    if order_type.lower() == 'buy':
        profit_dist = exit_price - entry_price
        sl_dist     = entry_price - sl_price
    else:
        profit_dist = entry_price - exit_price
        sl_dist     = sl_price - entry_price

    if sl_dist <= 0:
        return None
    return round(profit_dist / sl_dist, 2)


# ── Internal helpers ──────────────────────────────────────────

def _normalise(symbol: str) -> str:
    """Strip broker-specific separators: EUR/USD → EURUSD, XAU_USD → XAUUSD."""
    return symbol.upper().replace('/', '').replace('_', '').replace('-', '')


def _digits(symbol: str) -> int:
    """Return the decimal digits for a symbol's price."""
    from utils.constants import SYMBOL_CONFIG
    sym = _normalise(symbol)
    return SYMBOL_CONFIG.get(sym, {}).get('digits', 5)


def _min_lot(symbol: str) -> float:
    from utils.constants import SYMBOL_CONFIG
    sym = _normalise(symbol)
    return float(SYMBOL_CONFIG.get(sym, {}).get('min_lot', 0.01))


def _clamp_lot(symbol: str, lot: float) -> float:
    """Round and clamp lot size to symbol min/max/step."""
    from utils.constants import SYMBOL_CONFIG
    sym  = _normalise(symbol)
    cfg  = SYMBOL_CONFIG.get(sym, {})
    mn   = float(cfg.get('min_lot',  0.01))
    mx   = float(cfg.get('max_lot',  100.0))
    step = float(cfg.get('lot_step', 0.01))

    # Round to nearest step
    if step > 0:
        lot = round(round(lot / step) * step, 2)

    # Clamp
    lot = max(mn, min(mx, lot))
    return round(lot, 2)