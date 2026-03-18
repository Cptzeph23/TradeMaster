# ============================================================
# MetaTrader 5 Python API broker connector
# NOTE: MT5 Python library only works on Windows.
# On Linux, set BROKER=oanda or use a Windows MT5 bridge server.
# ============================================================
import logging
from typing import Optional
from .base import BaseBroker, OrderRequest, OrderResult
from .exceptions import (
    BrokerAuthError, BrokerConnectionError,
    BrokerOrderError, InsufficientMarginError,
    MarketClosedError, InvalidSymbolError,
)

logger = logging.getLogger('trading')


class MT5Broker(BaseBroker):
    """
    MetaTrader 5 broker connector via the official MT5 Python package.

    Important platform note:
        The MetaTrader5 Python library requires Windows + MT5 terminal installed.
        On Ubuntu servers, use one of these approaches:
          1. Run MT5 on a Windows VM and expose via a REST bridge
          2. Use Wine + MT5 (community-supported, not official)
          3. Switch to OANDA for Linux deployments (recommended)

    Symbol format: 'EURUSD' (MT5 uses no separator)
    Lot sizing:    standard 1 lot = 100,000 units
    """

    # MT5 order type constants (mirrored here so the file
    # is importable even when MetaTrader5 is not installed)
    ORDER_TYPE_BUY  = 0
    ORDER_TYPE_SELL = 1

    def __init__(self, login: str, password: str, server: str):
        self.login    = int(login)
        self.password = password
        self.server   = server
        self._mt5     = None

    def _import_mt5(self):
        """Lazy import — avoids ImportError on Linux where MT5 is unavailable."""
        try:
            import MetaTrader5 as mt5
            return mt5
        except ImportError:
            raise BrokerConnectionError(
                "MetaTrader5 Python package is not available on this platform. "
                "Install on Windows or use the OANDA connector on Linux."
            )

    def connect(self) -> bool:
        mt5 = self._import_mt5()
        if not mt5.initialize(
            login=self.login,
            password=self.password,
            server=self.server,
        ):
            error = mt5.last_error()
            raise BrokerAuthError(f"MT5 init failed: {error}")
        self._mt5 = mt5
        logger.info(f"MT5 connected: login={self.login} server={self.server}")
        return True

    def disconnect(self) -> None:
        if self._mt5:
            self._mt5.shutdown()
            self._mt5 = None

    def _ensure_connected(self):
        if not self._mt5:
            self.connect()

    def get_account_info(self) -> dict:
        self._ensure_connected()
        info = self._mt5.account_info()
        if info is None:
            raise BrokerConnectionError(f"MT5 account info failed: {self._mt5.last_error()}")
        return {
            'account_id':  str(info.login),
            'balance':     float(info.balance),
            'equity':      float(info.equity),
            'margin_used': float(info.margin),
            'margin_free': float(info.margin_free),
            'currency':    info.currency,
            'leverage':    info.leverage,
        }

    def get_price(self, symbol: str) -> dict:
        self._ensure_connected()
        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            raise InvalidSymbolError(symbol)
        return {
            'symbol': symbol,
            'bid':    float(tick.bid),
            'ask':    float(tick.ask),
            'mid':    round((tick.bid + tick.ask) / 2, 5),
            'spread': round(tick.ask - tick.bid, 5),
        }

    def place_order(self, order: OrderRequest) -> OrderResult:
        self._ensure_connected()

        action   = self.ORDER_TYPE_BUY if order.order_type == 'buy' else self.ORDER_TYPE_SELL
        price    = self.get_price(order.symbol)
        fill_px  = price['ask'] if order.order_type == 'buy' else price['bid']

        request = {
            "action":      self._mt5.TRADE_ACTION_DEAL,
            "symbol":      order.symbol,
            "volume":      float(order.lot_size),
            "type":        action,
            "price":       fill_px,
            "deviation":   20,
            "magic":       order.magic or 234000,
            "comment":     order.comment[:31],
            "type_time":   self._mt5.ORDER_TIME_GTC,
            "type_filling":self._mt5.ORDER_FILLING_FOK,
        }
        if order.stop_loss:
            request["sl"] = order.stop_loss
        if order.take_profit:
            request["tp"] = order.take_profit

        result = self._mt5.order_send(request)
        if result is None:
            error = self._mt5.last_error()
            raise BrokerOrderError(f"MT5 order send failed: {error}")

        if result.retcode == self._mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                success      = True,
                order_id     = str(result.order),
                trade_id     = str(result.deal),
                fill_price   = float(result.price),
                units_filled = int(result.volume * 100_000),
                raw_response = result._asdict(),
            )

        # Map common MT5 error codes
        if result.retcode == 10019:
            raise InsufficientMarginError()
        if result.retcode in (10018, 10021):
            raise MarketClosedError(order.symbol)

        return OrderResult(
            success       = False,
            error_message = f"MT5 retcode={result.retcode}: {result.comment}",
            raw_response  = result._asdict(),
        )

    def close_trade(self, trade_id: str, units: Optional[int] = None) -> OrderResult:
        self._ensure_connected()
        # MT5 close: send opposite order for the open position
        positions = self._mt5.positions_get(ticket=int(trade_id))
        if not positions:
            raise BrokerOrderError(f"No open position found for trade_id={trade_id}")

        pos   = positions[0]
        close_type = (self.ORDER_TYPE_SELL if pos.type == self.ORDER_TYPE_BUY
                      else self.ORDER_TYPE_BUY)
        price = self.get_price(pos.symbol)
        px    = price['bid'] if close_type == self.ORDER_TYPE_SELL else price['ask']

        request = {
            "action":       self._mt5.TRADE_ACTION_DEAL,
            "symbol":       pos.symbol,
            "volume":       pos.volume,
            "type":         close_type,
            "position":     pos.ticket,
            "price":        px,
            "deviation":    20,
            "magic":        pos.magic,
            "comment":      "close by bot",
            "type_time":    self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_FOK,
        }
        result = self._mt5.order_send(request)
        if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                success      = True,
                trade_id     = trade_id,
                fill_price   = float(result.price),
                raw_response = result._asdict(),
            )
        return OrderResult(
            success       = False,
            error_message = str(result.comment if result else 'Unknown error'),
        )

    def get_open_trades(self) -> list:
        self._ensure_connected()
        positions = self._mt5.positions_get() or []
        return [
            {
                'trade_id':      str(p.ticket),
                'symbol':        p.symbol,
                'units':         int(p.volume * 100_000),
                'open_price':    float(p.price_open),
                'unrealized_pl': float(p.profit),
                'open_time':     p.time,
                'stop_loss':     float(p.sl) if p.sl else None,
                'take_profit':   float(p.tp) if p.tp else None,
            }
            for p in positions
        ]

    def get_candles(self, symbol: str, timeframe: str,
                    count: int = 200) -> list:
        self._ensure_connected()

        tf_map = {
            'M1': self._mt5.TIMEFRAME_M1,
            'M5': self._mt5.TIMEFRAME_M5,
            'M15': self._mt5.TIMEFRAME_M15,
            'M30': self._mt5.TIMEFRAME_M30,
            'H1': self._mt5.TIMEFRAME_H1,
            'H4': self._mt5.TIMEFRAME_H4,
            'D1': self._mt5.TIMEFRAME_D1,
            'W1': self._mt5.TIMEFRAME_W1,
            'MN1': self._mt5.TIMEFRAME_MN1,
        }
        tf = tf_map.get(timeframe, self._mt5.TIMEFRAME_H1)
        rates = self._mt5.copy_rates_from_pos(symbol, tf, 0, count)

        if rates is None:
            raise InvalidSymbolError(symbol)

        import pandas as pd
        df = pd.DataFrame(rates)
        df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)

        return [
            {
                'timestamp': row['timestamp'].isoformat(),
                'open':      float(row['open']),
                'high':      float(row['high']),
                'low':       float(row['low']),
                'close':     float(row['close']),
                'volume':    int(row['tick_volume']),
            }
            for _, row in df.iterrows()
        ]