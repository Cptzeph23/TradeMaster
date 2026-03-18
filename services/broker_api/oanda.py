# ============================================================
# OANDA REST API v20 broker connector
# ============================================================
import logging
from typing import Optional
import oandapyV20
import oandapyV20.endpoints.accounts as accounts_ep
import oandapyV20.endpoints.orders as orders_ep
import oandapyV20.endpoints.trades as trades_ep
import oandapyV20.endpoints.pricing as pricing_ep
import oandapyV20.endpoints.instruments as instruments_ep
from oandapyV20.exceptions import V20Error

from .base import BaseBroker, OrderRequest, OrderResult
from .exceptions import (
    BrokerAuthError, BrokerConnectionError,
    BrokerOrderError, InsufficientMarginError,
    MarketClosedError, InvalidSymbolError, RateLimitError,
)

logger = logging.getLogger('trading')


class OandaBroker(BaseBroker):
    """
    OANDA v20 REST API connector.

    Supports:
      - Practice (demo) and live environments
      - Market orders with SL/TP
      - Account info sync
      - OHLCV candle fetch
      - Live price streaming (via data feed layer)

    Symbol format: 'EUR_USD' (OANDA uses underscore, not slash)
    Units: positive = buy (long), negative = sell (short)
    """

    ENVIRONMENTS = {
        'practice': 'practice',
        'demo':     'practice',   # alias
        'live':     'live',
    }

    def __init__(self, api_key: str, account_id: str,
                 environment: str = 'practice'):
        self.api_key      = api_key
        self.account_id   = account_id
        self.environment  = self.ENVIRONMENTS.get(environment, 'practice')
        self._client: Optional[oandapyV20.API] = None

    # ── Connection ────────────────────────────────────────────
    def connect(self) -> bool:
        try:
            self._client = oandapyV20.API(
                access_token=self.api_key,
                environment=self.environment,
            )
            # Test connection by fetching account summary
            self.get_account_info()
            logger.info(f"OANDA connected: account={self.account_id} env={self.environment}")
            return True
        except V20Error as e:
            if e.code in (401, 403):
                raise BrokerAuthError(f"OANDA auth failed: {e.msg}")
            raise BrokerConnectionError(f"OANDA connection error: {e.msg}")
        except Exception as e:
            raise BrokerConnectionError(f"OANDA connection error: {e}")

    def disconnect(self) -> None:
        self._client = None
        logger.info("OANDA disconnected.")

    def _ensure_connected(self):
        if not self._client:
            self.connect()

    # ── Account Info ──────────────────────────────────────────
    def get_account_info(self) -> dict:
        self._ensure_connected()
        try:
            r        = accounts_ep.AccountSummary(self.account_id)
            response = self._client.request(r)
            acct     = response['account']
            return {
                'account_id':  acct['id'],
                'balance':     float(acct['balance']),
                'equity':      float(acct.get('NAV', acct['balance'])),
                'margin_used': float(acct.get('marginUsed', 0)),
                'margin_free': float(acct.get('marginAvailable', 0)),
                'currency':    acct['currency'],
                'leverage':    int(acct.get('marginRate', 0.02) and
                                   round(1 / float(acct.get('marginRate', 0.02)))),
                'open_trades': int(acct.get('openTradeCount', 0)),
                'raw':         acct,
            }
        except V20Error as e:
            self._handle_v20_error(e)

    # ── Live Price ────────────────────────────────────────────
    def get_price(self, symbol: str) -> dict:
        self._ensure_connected()
        try:
            params = {'instruments': symbol}
            r      = pricing_ep.PricingInfo(self.account_id, params=params)
            resp   = self._client.request(r)
            price  = resp['prices'][0]
            bid    = float(price['bids'][0]['price'])
            ask    = float(price['asks'][0]['price'])
            return {
                'symbol': symbol,
                'bid':    bid,
                'ask':    ask,
                'mid':    round((bid + ask) / 2, 5),
                'spread': round(ask - bid, 5),
                'time':   price.get('time'),
            }
        except (V20Error, IndexError, KeyError) as e:
            raise BrokerConnectionError(f"Failed to get price for {symbol}: {e}")

    # ── Place Order ───────────────────────────────────────────
    def place_order(self, order: OrderRequest) -> OrderResult:
        self._ensure_connected()

        # OANDA: positive units = buy, negative = sell
        units = abs(order.units) if order.order_type == 'buy' else -abs(order.units)

        order_body = {
            "order": {
                "type":         "MARKET",
                "instrument":   order.symbol,
                "units":        str(units),
                "timeInForce":  "FOK",   # Fill or Kill
                "positionFill": "DEFAULT",
            }
        }

        # Attach SL / TP if provided
        if order.stop_loss:
            order_body["order"]["stopLossOnFill"] = {
                "price":       f"{order.stop_loss:.5f}",
                "timeInForce": "GTC",
            }
        if order.take_profit:
            order_body["order"]["takeProfitOnFill"] = {
                "price":       f"{order.take_profit:.5f}",
                "timeInForce": "GTC",
            }
        if order.comment:
            order_body["order"]["clientExtensions"] = {
                "comment": order.comment[:128]
            }

        try:
            r    = orders_ep.OrderCreate(self.account_id, data=order_body)
            resp = self._client.request(r)

            # Parse fill
            fill = resp.get('orderFillTransaction', {})
            if fill:
                return OrderResult(
                    success      = True,
                    order_id     = fill.get('orderID', ''),
                    trade_id     = fill.get('tradeOpened', {}).get('tradeID', ''),
                    fill_price   = float(fill.get('price', 0)),
                    units_filled = abs(int(fill.get('units', 0))),
                    raw_response = resp,
                )

            # Order was cancelled (e.g. market closed)
            cancelled = resp.get('orderCancelTransaction', {})
            reason    = cancelled.get('reason', 'UNKNOWN')
            return OrderResult(
                success       = False,
                error_message = f"Order cancelled: {reason}",
                raw_response  = resp,
            )

        except V20Error as e:
            self._handle_v20_error(e, order)

    # ── Close Trade ───────────────────────────────────────────
    def close_trade(self, trade_id: str, units: Optional[int] = None) -> OrderResult:
        self._ensure_connected()
        try:
            data = {"units": "ALL"} if units is None else {"units": str(units)}
            r    = trades_ep.TradeClose(self.account_id, trade_id, data=data)
            resp = self._client.request(r)
            fill = resp.get('orderFillTransaction', {})
            return OrderResult(
                success      = True,
                order_id     = fill.get('orderID', ''),
                trade_id     = trade_id,
                fill_price   = float(fill.get('price', 0)),
                units_filled = abs(int(fill.get('units', 0))),
                raw_response = resp,
            )
        except V20Error as e:
            self._handle_v20_error(e)

    # ── Open Trades ───────────────────────────────────────────
    def get_open_trades(self) -> list:
        self._ensure_connected()
        try:
            r    = trades_ep.OpenTrades(self.account_id)
            resp = self._client.request(r)
            return [
                {
                    'trade_id':      t['id'],
                    'symbol':        t['instrument'],
                    'units':         int(t['currentUnits']),
                    'open_price':    float(t['price']),
                    'unrealized_pl': float(t.get('unrealizedPL', 0)),
                    'open_time':     t.get('openTime'),
                    'stop_loss':     t.get('stopLossOrder', {}).get('price'),
                    'take_profit':   t.get('takeProfitOrder', {}).get('price'),
                }
                for t in resp.get('trades', [])
            ]
        except V20Error as e:
            raise BrokerConnectionError(f"Failed to fetch open trades: {e.msg}")

    # ── OHLCV Candles ─────────────────────────────────────────
    def get_candles(self, symbol: str, timeframe: str,
                    count: int = 200) -> list:
        self._ensure_connected()

        # Map internal timeframe codes to OANDA granularity strings
        tf_map = {
            'M1': 'M1', 'M5': 'M5', 'M15': 'M15', 'M30': 'M30',
            'H1': 'H1', 'H4': 'H4', 'D1': 'D',
            'W1': 'W', 'MN1': 'M',
        }
        gran = tf_map.get(timeframe, 'H1')

        try:
            params = {
                'granularity': gran,
                'count':       min(count, 5000),
                'price':       'MBA',   # Mid, Bid, Ask
            }
            r    = instruments_ep.InstrumentsCandles(symbol, params=params)
            resp = self._client.request(r)

            candles = []
            for c in resp.get('candles', []):
                if not c.get('complete', True):
                    continue
                mid = c.get('mid', {})
                candles.append({
                    'timestamp': c['time'],
                    'open':      float(mid.get('o', 0)),
                    'high':      float(mid.get('h', 0)),
                    'low':       float(mid.get('l', 0)),
                    'close':     float(mid.get('c', 0)),
                    'volume':    int(c.get('volume', 0)),
                })
            return candles

        except V20Error as e:
            if 'Invalid value' in str(e.msg):
                raise InvalidSymbolError(symbol)
            raise BrokerConnectionError(f"Candle fetch failed: {e.msg}")

    # ── Error Handler ─────────────────────────────────────────
    def _handle_v20_error(self, error: V20Error, order=None):
        code = error.code
        msg  = error.msg if hasattr(error, 'msg') else str(error)

        logger.error(f"OANDA V20Error code={code}: {msg}")

        if code in (401, 403):
            raise BrokerAuthError(f"OANDA authentication error: {msg}")
        if code == 404:
            raise InvalidSymbolError()
        if code == 429:
            raise RateLimitError()
        if 'INSUFFICIENT_MARGIN' in str(msg):
            raise InsufficientMarginError()
        if 'MARKET_HALTED' in str(msg) or 'MARKET_CLOSED' in str(msg):
            symbol = order.symbol if order else ''
            raise MarketClosedError(symbol)
        raise BrokerOrderError(msg, raw={'code': code, 'msg': msg})