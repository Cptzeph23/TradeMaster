# ============================================================
# Broker factory — get_broker(account) returns correct connector
# ============================================================
import logging
from .base import BrokerInterface
from .oanda_service import OandaBroker
from .mt5_service import MT5Broker
from .exceptions import *
from .types import *

logger = logging.getLogger('trading.broker')

BROKER_MT5   = 'mt5'
BROKER_OANDA = 'oanda'


def get_broker(account) -> BrokerInterface:
    """
    Return an initialised (not yet connected) broker for a TradingAccount.

    Usage:
        from services.broker_api import get_broker
        broker = get_broker(bot.trading_account)
        broker.connect()
        info = broker.get_account_info()
        broker.disconnect()

    Or as context manager:
        with get_broker(bot.trading_account) as broker:
            info = broker.get_account_info()
    """
    broker_type = (
        getattr(account, 'broker_type', None)
        or getattr(account, 'broker', 'oanda')
    )
    broker_type = str(broker_type).lower().strip()

    if broker_type == BROKER_MT5:
        return _build_mt5(account)
    else:
        if broker_type not in (BROKER_OANDA, 'oanda'):
            logger.warning(
                f"Unknown broker_type '{broker_type}' — defaulting to OANDA"
            )
        return _build_oanda(account)


def get_broker_for_bot(bot) -> BrokerInterface:
    """Convenience wrapper — get broker directly from a TradingBot."""
    return get_broker(bot.trading_account)


# ── Private builders ──────────────────────────────────────────

def _build_oanda(account) -> 'OandaBroker':
    from django.conf import settings
    try:
        api_key = account.get_api_key()
    except Exception:
        api_key = getattr(settings, 'OANDA_API_KEY', '')

    return OandaBroker({
        'api_key':     api_key,
        'account_id':  getattr(account, 'account_id', ''),
        'environment': getattr(
            account, 'environment',
            getattr(settings, 'OANDA_ENVIRONMENT', 'practice')
        ),
    })


def _build_mt5(account) -> 'MT5Broker':
    from .mt5_service import MT5Broker
    import json

    try:
        raw  = account.get_api_key()
        creds = json.loads(raw)
    except Exception:
        creds = {
            'login':    getattr(account, 'mt5_login',    0),
            'password': getattr(account, 'mt5_password', ''),
            'server':   getattr(account, 'mt5_server',   ''),
        }
    return MT5Broker(creds)


__all__ = [
    'get_broker',
    'get_broker_for_bot',
    'BrokerInterface',
    'BROKER_MT5',
    'BROKER_OANDA',
]