# ============================================================
# MT5Broker — MetaTrader 5 connector implementing BrokerInterface
#
# Install:  pip install MetaTrader5
#
# Platform notes:
#   Windows: works natively — MT5 terminal must be running
#   Linux:   requires Wine + MT5 terminal installed under Wine
#            OR use a Windows VPS and proxy via socket
#   The lib is imported lazily so the app boots fine even without it.
# ============================================================
import logging
import time
from typing import Optional, List
from datetime import datetime, timezone

from .base import BrokerInterface
from .types import AccountInfo, PositionInfo, OrderResult, PriceInfo
from .exceptions import (
    BrokerConnectionError, BrokerOrderError,
    BrokerAuthError, BrokerSymbolError,
)

logger = logging.getLogger('trading.broker.mt5')

# ── Timeframe map ─────────────────────────────────────────────
# Our string → MT5 integer constant
# Values match MetaTrader5.TIMEFRAME_* constants
MT5_TIMEFRAMES = {
    'M1':  1,
    'M5':  5,
    'M15': 15,
    'M30': 30,
    'H1':  16385,
    'H4':  16388,
    'D1':  16408,
    'W1':  32769,
    'MN1': 49153,
}

# MT5 order type integers
MT5_ORDER_TYPE_BUY  = 0
MT5_ORDER_TYPE_SELL = 1

# MT5 return codes
TRADE_RETCODE_DONE = 10009


class MT5Broker(BrokerInterface):
    """
    MetaTrader 5 broker connector.

    credentials = {
        'login':    123456,               # MT5 account number (int)
        'password': 'your_password',
        'server':   'ICMarkets-Demo',     # broker server name
        'path':     '/path/terminal64.exe',  # optional on Linux/Wine
        'timeout':  10000,                # connection timeout ms
    }

    Usage:
        broker = MT5Broker(credentials)
        if broker.connect():
            info = broker.get_account_info()
            order = broker.place_order('XAUUSD', 'buy', 0.01, sl=2330.0, tp=2370.0)
        broker.disconnect()
    """

    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self._mt5 = None
        self._load_mt5_lib()

    def _load_mt5_lib(self):
        """
        Lazy import — app boots cleanly even if MetaTrader5 is not installed.
        self._mt5 will be None if the library is missing.
        """
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
            self._logger.debug("MetaTrader5 library loaded successfully")
        except ImportError:
            self._logger.warning(
                "MetaTrader5 Python library not installed. "
                "Run: pip install MetaTrader5\n"
                "  Windows: MT5 terminal must be installed and running.\n"
                "  Linux:   Requires Wine with MT5, or a Windows VPS proxy."
            )
            self._mt5 = None

    # ── Connection ────────────────────────────────────────────

    def connect(self) -> bool:
        if self._mt5 is None:
            self._logger.error(
                "MetaTrader5 library not available — cannot connect."
            )
            return False

        mt5      = self._mt5
        login    = int(self.credentials.get('login', 0))
        password = str(self.credentials.get('password', ''))
        server   = str(self.credentials.get('server', ''))
        timeout  = int(self.credentials.get('timeout', 10000))
        path     = self.credentials.get('path')

        init_kwargs = {
            'login':    login,
            'password': password,
            'server':   server,
            'timeout':  timeout,
        }
        if path:
            init_kwargs['path'] = path

        try:
            if not mt5.initialize(**init_kwargs):
                code, msg = mt5.last_error()
                self._logger.error(
                    f"MT5 initialize failed: code={code} msg={msg}"
                )
                if code == -6:
                    raise BrokerAuthError(
                        f"MT5: wrong login/password/server (code={code})"
                    )
                return False

            info = mt5.account_info()
            if info is None:
                code, msg = mt5.last_error()
                self._logger.error(
                    f"MT5 account_info() returned None: code={code} msg={msg}"
                )
                mt5.shutdown()
                return False

            self.connected = True
            self._logger.info(
                f"MT5 connected: login={info.login} "
                f"server={info.server} "
                f"balance={info.balance} {info.currency} "
                f"mode={'LIVE' if info.trade_mode == 0 else 'DEMO'}"
            )
            return True

        except BrokerAuthError:
            raise
        except Exception as e:
            self._logger.error(f"MT5 connect exception: {e}", exc_info=True)
            return False

    def disconnect(self) -> None:
        if self._mt5 is not None and self.connected:
            self._mt5.shutdown()
            self.connected = False
            self._logger.info("MT5 terminal disconnected")

    def is_connected(self) -> bool:
        if self._mt5 is None or not self.connected:
            return False
        try:
            info = self._mt5.terminal_info()
            return info is not None and info.connected
        except Exception:
            return False

    # ── Account ───────────────────────────────────────────────

    def get_account_info(self) -> AccountInfo:
        self._ensure_connected()
        info = self._mt5.account_info()
        if info is None:
            code, msg = self._mt5.last_error()
            raise BrokerConnectionError(
                f"MT5 account_info() failed: code={code} msg={msg}"
            )

        # trade_mode: 0=real/live, 1=demo, 2=contest
        is_live = (info.trade_mode == 0)

        return AccountInfo(
            account_id   = str(info.login),
            broker       = info.company,
            balance      = float(info.balance),
            equity       = float(info.equity),
            margin       = float(info.margin),
            free_margin  = float(info.margin_free),
            margin_level = float(info.margin_level or 0),
            currency     = info.currency,
            leverage     = int(info.leverage),
            is_live      = is_live,
            extra        = {
                'name':          info.name,
                'server':        info.server,
                'trade_mode':    info.trade_mode,
                'profit':        float(info.profit),
                'credit':        float(info.credit),
                'limit_orders':  info.limit_orders,
            }
        )

    # ── Market data ───────────────────────────────────────────

    def get_price(self, symbol: str) -> PriceInfo:
        self._ensure_connected()
        mt5 = self._mt5

        # Ensure symbol is visible in MarketWatch
        if not mt5.symbol_select(symbol, True):
            self._logger.warning(
                f"MT5: symbol_select({symbol}) returned False"
            )

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            # Brief wait and retry once
            time.sleep(0.2)
            tick = mt5.symbol_info_tick(symbol)

        if tick is None:
            code, msg = mt5.last_error()
            raise BrokerSymbolError(
                f"MT5: cannot get price for '{symbol}': "
                f"code={code} msg={msg}"
            )

        return PriceInfo(
            symbol    = symbol,
            bid       = float(tick.bid),
            ask       = float(tick.ask),
            spread    = round(float(tick.ask - tick.bid), 5),
            timestamp = datetime.fromtimestamp(
                tick.time, tz=timezone.utc
            ).isoformat(),
        )

    def get_candles(
        self,
        symbol:    str,
        timeframe: str,
        count:     int = 200,
    ) -> list:
        self._ensure_connected()
        mt5 = self._mt5

        tf_const = MT5_TIMEFRAMES.get(timeframe.upper())
        if tf_const is None:
            raise ValueError(
                f"Unknown timeframe '{timeframe}'. "
                f"Valid: {list(MT5_TIMEFRAMES.keys())}"
            )

        # Ensure symbol visible
        mt5.symbol_select(symbol, True)

        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, count)
        if rates is None or len(rates) == 0:
            self._logger.warning(
                f"MT5: no candles returned for {symbol}/{timeframe}"
            )
            return []

        return [
            {
                'time':   datetime.fromtimestamp(
                              r['time'], tz=timezone.utc
                          ).isoformat(),
                'open':   float(r['open']),
                'high':   float(r['high']),
                'low':    float(r['low']),
                'close':  float(r['close']),
                'volume': int(r['tick_volume']),
            }
            for r in rates
        ]

    # ── Order execution ───────────────────────────────────────

    def place_order(
        self,
        symbol:      str,
        order_type:  str,
        volume:      float,
        stop_loss:   Optional[float] = None,
        take_profit: Optional[float] = None,
        comment:     str             = 'ForexBot',
        magic:       int             = 234000,
    ) -> OrderResult:
        self._ensure_connected()
        mt5 = self._mt5

        # Ensure symbol visible
        if not mt5.symbol_select(symbol, True):
            self._logger.warning(f"MT5: symbol_select({symbol}) failed")

        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return OrderResult(
                success=False,
                error=f"Cannot get price for '{symbol}'"
            )

        ot = order_type.lower()
        if ot == 'buy':
            mt5_type = mt5.ORDER_TYPE_BUY
            price    = float(tick.ask)
        elif ot == 'sell':
            mt5_type = mt5.ORDER_TYPE_SELL
            price    = float(tick.bid)
        else:
            return OrderResult(
                success=False,
                error=f"Invalid order_type '{order_type}' — use 'buy' or 'sell'"
            )

        # Get symbol info for filling mode
        sym_info = mt5.symbol_info(symbol)
        filling  = mt5.ORDER_FILLING_IOC
        if sym_info is not None:
            # Use FOK if supported, else IOC
            if sym_info.filling_mode & mt5.SYMBOL_FILLING_FOK:
                filling = mt5.ORDER_FILLING_FOK

        request = {
            'action':       mt5.TRADE_ACTION_DEAL,
            'symbol':       symbol,
            'volume':       float(round(volume, 2)),
            'type':         mt5_type,
            'price':        price,
            'deviation':    20,
            'magic':        int(magic),
            'comment':      comment[:31],   # MT5 limit: 31 chars
            'type_time':    mt5.ORDER_TIME_GTC,
            'type_filling': filling,
        }
        if stop_loss is not None:
            request['sl'] = float(stop_loss)
        if take_profit is not None:
            request['tp'] = float(take_profit)

        result = mt5.order_send(request)

        if result is None:
            code, msg = mt5.last_error()
            self._logger.error(f"MT5 order_send returned None: code={code} msg={msg}")
            return OrderResult(success=False, error=f"order_send None: {msg}")

        if result.retcode == TRADE_RETCODE_DONE:
            self._logger.info(
                f"MT5 order placed: {ot.upper()} {volume} {symbol} "
                f"@ {result.price} ticket={result.order}"
            )
            return OrderResult(
                success     = True,
                ticket      = str(result.order),
                symbol      = symbol,
                order_type  = ot,
                volume      = volume,
                entry_price = float(result.price),
                stop_loss   = stop_loss,
                take_profit = take_profit,
                retcode     = result.retcode,
                raw         = result._asdict() if hasattr(result, '_asdict') else {},
            )

        # Order failed
        self._logger.error(
            f"MT5 order failed: retcode={result.retcode} "
            f"comment={result.comment} "
            f"symbol={symbol} type={ot} vol={volume}"
        )
        return OrderResult(
            success = False,
            error   = f"retcode={result.retcode}: {result.comment}",
            retcode = result.retcode,
            raw     = result._asdict() if hasattr(result, '_asdict') else {},
        )

    def close_position(
        self,
        ticket: str,
        volume: Optional[float] = None,
    ) -> OrderResult:
        self._ensure_connected()
        mt5 = self._mt5

        positions = mt5.positions_get(ticket=int(ticket))
        if not positions:
            return OrderResult(
                success=False,
                error=f"Position ticket={ticket} not found"
            )
        pos = positions[0]

        close_vol = float(volume) if volume else float(pos.volume)

        # Get current price
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            return OrderResult(
                success=False,
                error=f"Cannot get price for '{pos.symbol}'"
            )

        # Close = opposite direction to open
        if pos.type == mt5.ORDER_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price      = float(tick.bid)
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price      = float(tick.ask)

        request = {
            'action':       mt5.TRADE_ACTION_DEAL,
            'symbol':       pos.symbol,
            'volume':       close_vol,
            'type':         close_type,
            'position':     int(ticket),
            'price':        price,
            'deviation':    20,
            'comment':      'ForexBot close',
            'type_time':    mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result and result.retcode == TRADE_RETCODE_DONE:
            self._logger.info(
                f"MT5 position closed: ticket={ticket} "
                f"price={result.price}"
            )
            return OrderResult(
                success     = True,
                ticket      = str(result.order),
                symbol      = pos.symbol,
                volume      = close_vol,
                entry_price = float(result.price),
                retcode     = result.retcode,
            )

        err = result.comment if result else str(mt5.last_error())
        retcode = result.retcode if result else 0
        self._logger.error(
            f"MT5 close failed: ticket={ticket} retcode={retcode} err={err}"
        )
        return OrderResult(success=False, error=err, retcode=retcode)

    def modify_position(
        self,
        ticket:      str,
        stop_loss:   Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        self._ensure_connected()
        mt5 = self._mt5

        positions = mt5.positions_get(ticket=int(ticket))
        if not positions:
            self._logger.warning(f"MT5 modify: position {ticket} not found")
            return False
        pos = positions[0]

        request = {
            'action':   mt5.TRADE_ACTION_SLTP,
            'symbol':   pos.symbol,
            'position': int(ticket),
            'sl':       float(stop_loss)   if stop_loss   is not None else float(pos.sl),
            'tp':       float(take_profit) if take_profit is not None else float(pos.tp),
        }

        result = mt5.order_send(request)
        if result and result.retcode == TRADE_RETCODE_DONE:
            self._logger.info(
                f"MT5 modify: ticket={ticket} sl={stop_loss} tp={take_profit}"
            )
            return True

        retcode = result.retcode if result else 0
        self._logger.error(
            f"MT5 modify failed: ticket={ticket} retcode={retcode}"
        )
        return False

    # ── Position queries ──────────────────────────────────────

    def get_open_positions(
        self,
        symbol: Optional[str] = None,
    ) -> List[PositionInfo]:
        self._ensure_connected()
        if symbol:
            raw = self._mt5.positions_get(symbol=symbol)
        else:
            raw = self._mt5.positions_get()

        if raw is None:
            return []
        return [self._normalise_position(p) for p in raw]

    def get_position(self, ticket: str) -> Optional[PositionInfo]:
        self._ensure_connected()
        raw = self._mt5.positions_get(ticket=int(ticket))
        if not raw:
            return None
        return self._normalise_position(raw[0])

    # ── Internal helpers ──────────────────────────────────────

    def _normalise_position(self, pos) -> PositionInfo:
        """Convert MT5 position struct to normalised PositionInfo."""
        mt5 = self._mt5
        ot  = 'buy' if pos.type == mt5.ORDER_TYPE_BUY else 'sell'
        return PositionInfo(
            ticket        = str(pos.ticket),
            symbol        = pos.symbol,
            order_type    = ot,
            volume        = float(pos.volume),
            entry_price   = float(pos.price_open),
            current_price = float(pos.price_current),
            stop_loss     = float(pos.sl)     if pos.sl     else None,
            take_profit   = float(pos.tp)     if pos.tp     else None,
            profit        = float(pos.profit),
            profit_pips   = 0.0,  # Phase 2 pip engine fills this
            open_time     = datetime.fromtimestamp(
                pos.time, tz=timezone.utc
            ).isoformat(),
            comment       = pos.comment,
            magic         = int(pos.magic),
        )