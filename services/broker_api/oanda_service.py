import logging
import requests
from typing import Optional, List
from .base import BrokerInterface
from .types import AccountInfo, PositionInfo, OrderResult, PriceInfo
from .exceptions import (
    BrokerConnectionError, BrokerOrderError,
    BrokerSymbolError, BrokerAuthError, BrokerRateLimitError,
)

logger = logging.getLogger('trading.broker.oanda')

# This was named ENVIRONMENTS before, causing your NameError
OANDA_BASE_URLS = {
    'live':     'https://api-fxtrade.oanda.com',
    'practice': 'https://api-fxpractice.oanda.com',
}

# OANDA granularity strings
OANDA_TF_MAP = {
    'M1':  'M1',  'M5':  'M5',  'M15': 'M15', 'M30': 'M30',
    'H1':  'H1',  'H4':  'H4',  'D1':  'D',
    'W1':  'W',   'MN1': 'M',
}

def _oanda_symbol(symbol: str) -> str:
    """Convert 'EURUSD' or 'EUR_USD' → 'EUR_USD' (OANDA format)."""
    s = symbol.upper().replace('/', '').replace('-', '').replace(' ', '')
    if '_' in s:
        return s
    # Insert underscore for standard 6-char pairs or metals
    if len(s) == 6 or s.startswith(('XAU', 'XAG')):
        return s[:3] + '_' + s[3:]
    return s

class OandaBroker(BrokerInterface):
    """OANDA REST v20 broker connector."""

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        env = credentials.get('environment', 'practice').lower()
        # FIXED: Now matches the dictionary name at the top
        self._base     = OANDA_BASE_URLS.get(env, OANDA_BASE_URLS['practice'])
        self._acct_id  = credentials.get('account_id', '')
        self._timeout  = int(credentials.get('timeout', 15))
        
        self._session  = requests.Session()
        self._session.headers.update({
            'Authorization': f"Bearer {credentials.get('api_key', '')}",
            'Content-Type':  'application/json',
            'Accept-Datetime-Format': 'RFC3339',
        })

    def connect(self) -> bool:
        try:
            resp = self._session.get(
                f"{self._base}/v3/accounts/{self._acct_id}/summary",
                timeout=self._timeout,
            )
            if resp.status_code == 401:
                raise BrokerAuthError("OANDA: invalid API key")
            if resp.status_code == 200:
                self.connected = True
                return True
            return False
        except Exception as e:
            self._logger.error(f"OANDA connect error: {e}")
            return False

    def disconnect(self) -> None:
        self._session.close()
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def get_account_info(self) -> AccountInfo:
        self._ensure_connected()
        data = self._get(f"/v3/accounts/{self._acct_id}/summary")
        a    = data.get('account', {})
        
        margin_rate = float(a.get('marginRate', 0.02))
        leverage    = int(round(1 / margin_rate)) if margin_rate > 0 else 50
        
        # Calculate margin level percentage
        nav = float(a.get('NAV', 1))
        m_used = float(a.get('marginUsed', 0))
        m_level = (m_used / nav * 100) if nav != 0 else 0

        return AccountInfo(
            account_id   = self._acct_id,
            broker       = 'OANDA',
            balance      = float(a.get('balance', 0)),
            equity       = nav,
            margin       = m_used,
            free_margin  = float(a.get('marginAvailable', 0)),
            margin_level = round(m_level, 2),
            currency     = a.get('currency', 'USD'),
            leverage     = leverage,
            is_live      = 'fxtrade' in self._base,
            extra        = {'alias': a.get('alias', '')}
        )

    def get_price(self, symbol: str) -> PriceInfo:
        self._ensure_connected()
        oanda_sym = _oanda_symbol(symbol)
        data = self._get(
            f"/v3/accounts/{self._acct_id}/pricing",
            params={'instruments': oanda_sym},
        )
        p = data['prices'][0]
        bid = float(p['bids'][0]['price'])
        ask = float(p['asks'][0]['price'])
        return PriceInfo(
            symbol=symbol, bid=bid, ask=ask,
            spread=round(ask - bid, 5), timestamp=p.get('time')
        )

    def get_candles(self, symbol: str, timeframe: str, count: int = 200) -> list:
        self._ensure_connected()
        oanda_tf = OANDA_TF_MAP.get(timeframe.upper(), 'H1')
        data = self._get(
            f"/v3/instruments/{_oanda_symbol(symbol)}/candles",
            params={'granularity': oanda_tf, 'count': min(count, 5000), 'price': 'M'}
        )
        return [{
            'time': c['time'],
            'open': float(c['mid']['o']),
            'high': float(c['mid']['h']),
            'low': float(c['mid']['l']),
            'close': float(c['mid']['c']),
            'volume': int(c['volume'])
        } for c in data.get('candles', []) if c.get('complete')]

    def place_order(self, symbol: str, order_type: str, volume: float, **kwargs) -> OrderResult:
        self._ensure_connected()
        units = int(round(volume * 100_000))
        if order_type.lower() == 'sell': units = -units

        body = {
            'order': {
                'type': 'MARKET',
                'instrument': _oanda_symbol(symbol),
                'units': str(units),
                'timeInForce': 'FOK'
            }
        }
        # Add SL/TP if provided
        if kwargs.get('stop_loss'):
            body['order']['stopLossOnFill'] = {'price': f"{kwargs['stop_loss']:.5f}"}
        if kwargs.get('take_profit'):
            body['order']['takeProfitOnFill'] = {'price': f"{kwargs['take_profit']:.5f}"}

        resp = self._session.post(f"{self._base}/v3/accounts/{self._acct_id}/orders", json=body)
        data = resp.json()
        if resp.status_code in (200, 201) and 'orderFillTransaction' in data:
            fc = data['orderFillTransaction']
            return OrderResult(True, ticket=str(fc['id']), symbol=symbol, 
                               order_type=order_type, volume=volume, 
                               entry_price=float(fc['price']), raw=data)
        return OrderResult(False, error=data.get('errorMessage', 'Order Failed'), raw=data)

    def close_position(self, ticket: str, volume: float = None) -> OrderResult:
        self._ensure_connected()
        body = {'longUnits': 'ALL', 'shortUnits': 'ALL'} if volume is None else {'longUnits': str(int(volume * 100_000))}
        resp = self._session.put(f"{self._base}/v3/accounts/{self._acct_id}/trades/{ticket}/close", json=body)
        return OrderResult(resp.status_code == 200, ticket=ticket, raw=resp.json())

    def modify_position(self, ticket: str, stop_loss=None, take_profit=None) -> bool:
        self._ensure_connected()
        body = {'stopLoss': {'price': f"{stop_loss:.5f}"}} if stop_loss else {}
        if take_profit: body['takeProfit'] = {'price': f"{take_profit:.5f}"}
        resp = self._session.put(f"{self._base}/v3/accounts/{self._acct_id}/trades/{ticket}/orders", json=body)
        return resp.status_code == 200

    def get_open_positions(self, symbol=None) -> List[PositionInfo]:
        self._ensure_connected()
        data = self._get(f"/v3/accounts/{self._acct_id}/openTrades")
        result = []
        for t in data.get('trades', []):
            units = float(t['currentUnits'])
            result.append(PositionInfo(
                ticket=str(t['id']), symbol=t['instrument'],
                order_type='buy' if units > 0 else 'sell',
                volume=abs(units)/100000, entry_price=float(t['price']),
                profit=float(t['unrealizedPL']), open_time=t['openTime']
            ))
        return result

    def get_position(self, ticket: str) -> Optional[PositionInfo]:
        self._ensure_connected()
        data = self._get(f"/v3/accounts/{self._acct_id}/trades/{ticket}")
        t = data.get('trade', {})
        if not t: return None
        units = float(t['currentUnits'])
        return PositionInfo(
            ticket=ticket, symbol=t['instrument'],
            order_type='buy' if units > 0 else 'sell',
            volume=abs(units)/100000, entry_price=float(t['price']),
            profit=float(t['unrealizedPL']), open_time=t['openTime']
        )

    def _get(self, path: str, params: dict = None) -> dict:
        resp = self._session.get(f"{self._base}{path}", params=params, timeout=self._timeout)
        if resp.status_code == 401: raise BrokerAuthError("OANDA: Unauthorized")
        resp.raise_for_status()
        return resp.json()