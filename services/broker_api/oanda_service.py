# ============================================================
# OandaBroker — implements BrokerInterface for OANDA REST v20
# ============================================================
import logging
import requests
from typing import Optional, List
from datetime import datetime, timezone

from .base import BrokerInterface
from .types import AccountInfo, PositionInfo, OrderResult, PriceInfo
from .exceptions import (
    BrokerConnectionError, BrokerOrderError,
    BrokerSymbolError, BrokerAuthError, BrokerRateLimitError,
)

logger = logging.getLogger('trading.broker.oanda')

ENVIRONMENTS = {
    'live':     'https://api-fxtrade.oanda.com',
    'practice': 'https://api-fxpractice.oanda.com',
}

# OANDA granularity strings
TIMEFRAME_MAP = {
    'M1': 'M1', 'M5': 'M5', 'M15': 'M15', 'M30': 'M30',
    'H1': 'H1', 'H4': 'H4', 'D1':  'D',
    'W1': 'W',  'MN1': 'M',
}


def _oanda_symbol(symbol: str) -> str:
    """Convert 'EURUSD' or 'EUR_USD' → 'EUR_USD' (OANDA format)."""
    s = symbol.replace('/', '').replace('-', '').upper()
    if '_' in s:
        return s
    # Insert underscore: EURUSD → EUR_USD, XAUUSD → XAU_USD
    if len(s) == 6:
        return s[:3] + '_' + s[3:]
    return s


class OandaBroker(BrokerInterface):
    """
    OANDA REST v20 broker connector.

    credentials = {
        'api_key':     'your-oanda-api-token',
        'account_id':  '101-001-0000001-001',
        'environment': 'practice',   # 'practice' or 'live'
    }
    """

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        env = credentials.get('environment', 'practice')
        self._base      = ENVIRONMENTS.get(env, ENVIRONMENTS['practice'])
        self._acct_id   = credentials.get('account_id', '')
        self._headers   = {
            'Authorization': f"Bearer {credentials.get('api_key', '')}",
            'Content-Type':  'application/json',
            'Accept-Datetime-Format': 'RFC3339',
        }

    # ── Connection ────────────────────────────────────────────

    def connect(self) -> bool:
        """Verify credentials by fetching account summary."""
        try:
            resp = self._raw_get(f"/v3/accounts/{self._acct_id}/summary")
            if resp.status_code == 200:
                acct = resp.json().get('account', {})
                self.connected = True
                self._logger.info(
                    f"OANDA connected — account={self._acct_id} "
                    f"balance={acct.get('balance')} "
                    f"currency={acct.get('currency')}"
                )
                return True
            elif resp.status_code == 401:
                raise BrokerAuthError("Invalid OANDA API key")
            else:
                self._logger.error(
                    f"OANDA connect failed: {resp.status_code} {resp.text[:200]}"
                )
                return False
        except BrokerAuthError:
            raise
        except Exception as e:
            self._logger.error(f"OANDA connect error: {e}")
            return False

    def disconnect(self) -> None:
        self.connected = False
        self._logger.info("OANDA disconnected")

    def is_connected(self) -> bool:
        return self.connected

    # ── Account ───────────────────────────────────────────────

    def get_account_info(self) -> AccountInfo:
        self._ensure_connected()
        data = self._get(f"/v3/accounts/{self._acct_id}/summary")
        acct = data.get('account', {})

        margin_rate = float(acct.get('marginRate', 0.02))
        leverage    = int(round(1 / margin_rate)) if margin_rate else 50

        return AccountInfo(
            account_id   = self._acct_id,
            broker       = 'OANDA',
            balance      = float(acct.get('balance',           0)),
            equity       = float(acct.get('NAV',               0)),
            margin       = float(acct.get('marginUsed',        0)),
            free_margin  = float(acct.get('marginAvailable',   0)),
            margin_level = float(acct.get('marginCloseoutPercent', 0)),
            currency     = acct.get('currency', 'USD'),
            leverage     = leverage,
            is_live      = 'live' in self._base,
            extra={
                'unrealized_pnl': float(acct.get('unrealizedPL',    0)),
                'realized_pnl':   float(acct.get('pl',              0)),
                'open_trades':    int(acct.get('openTradeCount',     0)),
                'open_positions': int(acct.get('openPositionCount',  0)),
            }
        )

    # ── Market data ───────────────────────────────────────────

    def get_price(self, symbol: str) -> PriceInfo:
        self._ensure_connected()
        oanda_sym = _oanda_symbol(symbol)
        data      = self._get(
            f"/v3/accounts/{self._acct_id}/pricing",
            params={'instruments': oanda_sym}
        )
        prices = data.get('prices', [])
        if not prices:
            raise BrokerSymbolError(
                f"OANDA returned no price for {symbol} ({oanda_sym})"
            )
        p   = prices[0]
        bid = float(p['bids'][0]['price'])
        ask = float(p['asks'][0]['price'])
        return PriceInfo(
            symbol    = symbol,
            bid       = bid,
            ask       = ask,
            spread    = round(ask - bid, 5),
            timestamp = p.get('time'),
        )

    def get_candles(
        self,
        symbol:    str,
        timeframe: str,
        count:     int = 200,
    ) -> list:
        self._ensure_connected()
        oanda_sym = _oanda_symbol(symbol)
        gran      = TIMEFRAME_MAP.get(timeframe.upper(), 'H1')
        data      = self._get(
            f"/v3/instruments/{oanda_sym}/candles",
            params={'granularity': gran, 'count': min(count, 5000)}
        )
        result = []
        for c in data.get('candles', []):
            if not c.get('complete', True):
                continue
            mid = c.get('mid', {})
            result.append({
                'time':   c.get('time', ''),
                'open':   float(mid.get('o', 0)),
                'high':   float(mid.get('h', 0)),
                'low':    float(mid.get('l', 0)),
                'close':  float(mid.get('c', 0)),
                'volume': int(c.get('volume', 0)),
            })
        return result

    # ── Orders ────────────────────────────────────────────────

    def place_order(
        self,
        symbol:      str,
        order_type:  str,
        volume:      float,
        stop_loss:   Optional[float] = None,
        take_profit: Optional[float] = None,
        comment:     str             = 'ForexBot',
        magic:       int             = 0,
    ) -> OrderResult:
        self._ensure_connected()
        oanda_sym = _oanda_symbol(symbol)

        # OANDA uses signed units: positive=buy, negative=sell
        units = int(round(volume * 100_000))
        if order_type.lower() == 'sell':
            units = -units

        order_body: dict = {
            'order': {
                'type':         'MARKET',
                'instrument':   oanda_sym,
                'units':        str(units),
                'timeInForce':  'FOK',
                'positionFill': 'DEFAULT',
            }
        }

        if stop_loss is not None:
            order_body['order']['stopLossOnFill'] = {
                'price':       f"{stop_loss:.5f}",
                'timeInForce': 'GTC',
            }
        if take_profit is not None:
            order_body['order']['takeProfitOnFill'] = {
                'price':       f"{take_profit:.5f}",
                'timeInForce': 'GTC',
            }

        try:
            resp = requests.post(
                f"{self._base}/v3/accounts/{self._acct_id}/orders",
                headers = self._headers,
                json    = order_body,
                timeout = 15,
            )
            data = resp.json()

            if resp.status_code in (200, 201):
                fc = data.get('orderFillTransaction', {})
                price = float(fc.get('price', 0))
                self._logger.info(
                    f"OANDA order filled: {order_type.upper()} "
                    f"{volume} {symbol} @ {price} id={fc.get('id')}"
                )
                return OrderResult(
                    success     = True,
                    ticket      = str(fc.get('id', '')),
                    symbol      = symbol,
                    order_type  = order_type.lower(),
                    volume      = volume,
                    entry_price = price,
                    stop_loss   = stop_loss,
                    take_profit = take_profit,
                    raw         = data,
                )

            err = data.get('errorMessage', data.get('message', str(data)))
            self._logger.error(
                f"OANDA order failed: {resp.status_code} — {err}"
            )
            return OrderResult(
                success = False,
                error   = err,
                raw     = data,
            )

        except Exception as e:
            self._logger.error(
                f"OANDA place_order exception: {e}", exc_info=True
            )
            return OrderResult(success=False, error=str(e))

    def close_position(
        self,
        ticket:  str,
        volume:  Optional[float] = None,
    ) -> OrderResult:
        self._ensure_connected()
        try:
            if volume is None:
                body = {'longUnits': 'ALL', 'shortUnits': 'ALL'}
            else:
                units = str(int(round(volume * 100_000)))
                body  = {'longUnits': units}

            resp = requests.put(
                f"{self._base}/v3/accounts/{self._acct_id}/trades/{ticket}/close",
                headers = self._headers,
                json    = body,
                timeout = 15,
            )
            data = resp.json()
            if resp.status_code == 200:
                self._logger.info(f"OANDA closed position {ticket}")
                return OrderResult(
                    success = True,
                    ticket  = ticket,
                    raw     = data,
                )
            err = data.get('errorMessage', str(data))
            return OrderResult(success=False, error=err, raw=data)

        except Exception as e:
            return OrderResult(success=False, error=str(e))

    def modify_position(
        self,
        ticket:      str,
        stop_loss:   Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        self._ensure_connected()
        body = {}
        if stop_loss is not None:
            body['stopLoss']   = {
                'price': f"{stop_loss:.5f}", 'timeInForce': 'GTC'
            }
        if take_profit is not None:
            body['takeProfit'] = {
                'price': f"{take_profit:.5f}", 'timeInForce': 'GTC'
            }
        if not body:
            return True  # nothing to modify

        try:
            resp = requests.put(
                f"{self._base}/v3/accounts/{self._acct_id}"
                f"/trades/{ticket}/orders",
                headers = self._headers,
                json    = body,
                timeout = 10,
            )
            if resp.status_code == 200:
                self._logger.info(
                    f"OANDA modified position {ticket} "
                    f"SL={stop_loss} TP={take_profit}"
                )
                return True
            self._logger.warning(
                f"OANDA modify failed: {resp.status_code} {resp.text[:100]}"
            )
            return False
        except Exception as e:
            self._logger.error(f"OANDA modify_position error: {e}")
            return False

    # ── Positions ─────────────────────────────────────────────

    def get_open_positions(
        self,
        symbol: Optional[str] = None,
    ) -> List[PositionInfo]:
        self._ensure_connected()
        data   = self._get(f"/v3/accounts/{self._acct_id}/openTrades")
        trades = data.get('trades', [])
        result = []
        for t in trades:
            instr = t.get('instrument', '')
            # Filter by symbol if requested
            if symbol:
                oanda_sym = _oanda_symbol(symbol)
                if instr != oanda_sym:
                    continue
            units    = float(t.get('currentUnits', 0))
            ot       = 'buy' if units > 0 else 'sell'
            sl_order = t.get('stopLossOrder', {})
            tp_order = t.get('takeProfitOrder', {})
            result.append(PositionInfo(
                ticket        = str(t['id']),
                symbol        = instr,
                order_type    = ot,
                volume        = abs(units) / 100_000,
                entry_price   = float(t.get('price', 0)),
                current_price = float(t.get('price', 0)),
                stop_loss     = float(sl_order['price'])
                                if sl_order.get('price') else None,
                take_profit   = float(tp_order['price'])
                                if tp_order.get('price') else None,
                profit        = float(t.get('unrealizedPL', 0)),
                open_time     = t.get('openTime'),
                comment       = t.get('clientExtensions', {}).get('comment', ''),
            ))
        return result

    def get_position(self, ticket: str) -> Optional[PositionInfo]:
        self._ensure_connected()
        try:
            data = self._get(
                f"/v3/accounts/{self._acct_id}/trades/{ticket}"
            )
            t    = data.get('trade', {})
            if not t:
                return None
            units    = float(t.get('currentUnits', 0))
            sl_order = t.get('stopLossOrder', {})
            tp_order = t.get('takeProfitOrder', {})
            return PositionInfo(
                ticket        = ticket,
                symbol        = t.get('instrument', ''),
                order_type    = 'buy' if units > 0 else 'sell',
                volume        = abs(units) / 100_000,
                entry_price   = float(t.get('price', 0)),
                current_price = float(t.get('price', 0)),
                stop_loss     = float(sl_order['price'])
                                if sl_order.get('price') else None,
                take_profit   = float(tp_order['price'])
                                if tp_order.get('price') else None,
                profit        = float(t.get('unrealizedPL', 0)),
                open_time     = t.get('openTime'),
            )
        except Exception as e:
            self._logger.error(f"OANDA get_position {ticket}: {e}")
            return None

    # ── Internal HTTP helpers ─────────────────────────────────

    def _raw_get(self, path: str, params: dict = None):
        """Raw GET — returns Response object (not parsed JSON)."""
        return requests.get(
            f"{self._base}{path}",
            headers = self._headers,
            params  = params,
            timeout = 15,
        )

    def _get(self, path: str, params: dict = None) -> dict:
        """GET and parse JSON — raises on HTTP error."""
        try:
            resp = self._raw_get(path, params)
            if resp.status_code == 401:
                raise BrokerAuthError("OANDA API key invalid or expired")
            if resp.status_code == 429:
                raise BrokerRateLimitError("OANDA rate limit exceeded")
            resp.raise_for_status()
            return resp.json()
        except (BrokerAuthError, BrokerRateLimitError):
            raise
        except requests.HTTPError as e:
            self._logger.error(
                f"OANDA HTTP {e.response.status_code}: "
                f"{e.response.text[:200]}"
            )
            raise
        except Exception as e:
            self._logger.error(f"OANDA request error: {e}")
            raise