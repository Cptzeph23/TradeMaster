# ============================================================
# DESTINATION: /opt/forex_bot/utils/constants.py
# Platform-wide constants and enumerations
# ============================================================
from django.db import models


# ── Broker Choices ───────────────────────────────────────────
class Broker(models.TextChoices):
    OANDA       = 'oanda',       'OANDA'
    METATRADER5 = 'metatrader5', 'MetaTrader 5'
    DEMO        = 'demo',        'Demo (Paper Trading)'


# ── Bot Status ───────────────────────────────────────────────
class BotStatus(models.TextChoices):
    IDLE        = 'idle',       'Idle'
    RUNNING     = 'running',    'Running'
    PAUSED      = 'paused',     'Paused'
    STOPPED     = 'stopped',    'Stopped'
    ERROR       = 'error',      'Error'
    BACKTESTING = 'backtesting','Backtesting'


# ── Order Types ──────────────────────────────────────────────
class OrderType(models.TextChoices):
    BUY         = 'buy',        'Buy (Long)'
    SELL        = 'sell',       'Sell (Short)'
    BUY_LIMIT   = 'buy_limit',  'Buy Limit'
    SELL_LIMIT  = 'sell_limit', 'Sell Limit'
    BUY_STOP    = 'buy_stop',   'Buy Stop'
    SELL_STOP   = 'sell_stop',  'Sell Stop'


# ── Trade Status ─────────────────────────────────────────────
class TradeStatus(models.TextChoices):
    PENDING     = 'pending',    'Pending'
    OPEN        = 'open',       'Open'
    CLOSED      = 'closed',     'Closed'
    CANCELLED   = 'cancelled',  'Cancelled'
    REJECTED    = 'rejected',   'Rejected'
    PARTIAL     = 'partial',    'Partially Filled'


# ── Timeframes ───────────────────────────────────────────────
class Timeframe(models.TextChoices):
    M1  = 'M1',  '1 Minute'
    M5  = 'M5',  '5 Minutes'
    M15 = 'M15', '15 Minutes'
    M30 = 'M30', '30 Minutes'
    H1  = 'H1',  '1 Hour'
    H4  = 'H4',  '4 Hours'
    D1  = 'D1',  '1 Day'
    W1  = 'W1',  '1 Week'
    MN1 = 'MN1', '1 Month'


# ── Strategy Types ───────────────────────────────────────────
class StrategyType(models.TextChoices):
    MA_CROSSOVER    = 'ma_crossover',   'Moving Average Crossover'
    RSI_REVERSAL    = 'rsi_reversal',   'RSI Reversal'
    BREAKOUT        = 'breakout',       'Breakout Strategy'
    MEAN_REVERSION  = 'mean_reversion', 'Mean Reversion'
    CUSTOM          = 'custom',         'Custom Strategy'
    ICHIMOKU       = 'ichimoku',        'Ichimoku Cloud'
    MACD_DIV       = 'macd_divergence', 'MACD Divergence'
    STOCHASTIC     = 'stochastic',      'Stochastic Oscillator'
    EMA_RIBBON     = 'ema_ribbon',      'EMA Ribbon'
    ATR_BREAKOUT   = 'atr_breakout',    'ATR Channel Breakout'


# ── Signal Types ─────────────────────────────────────────────
class SignalType(models.TextChoices):
    BUY     = 'buy',    'Buy Signal'
    SELL    = 'sell',   'Sell Signal'
    CLOSE   = 'close',  'Close Position'
    HOLD    = 'hold',   'Hold'


# ── Account Types ────────────────────────────────────────────
class AccountType(models.TextChoices):
    LIVE    = 'live',   'Live Trading'
    DEMO    = 'demo',   'Demo / Paper'


# ── Backtest Status ──────────────────────────────────────────
class BacktestStatus(models.TextChoices):
    QUEUED      = 'queued',     'Queued'
    RUNNING     = 'running',    'Running'
    COMPLETED   = 'completed',  'Completed'
    FAILED      = 'failed',     'Failed'


# ── Forex Major Pairs ────────────────────────────────────────
MAJOR_FOREX_PAIRS = [
    'EUR_USD', 'GBP_USD', 'USD_JPY', 'USD_CHF',
    'AUD_USD', 'USD_CAD', 'NZD_USD',
]

MINOR_FOREX_PAIRS = [
    'EUR_GBP', 'EUR_JPY', 'GBP_JPY', 'EUR_AUD',
    'GBP_AUD', 'AUD_JPY', 'EUR_CAD', 'GBP_CAD',
]

ALL_FOREX_PAIRS = MAJOR_FOREX_PAIRS + MINOR_FOREX_PAIRS

# ── Risk Defaults ────────────────────────────────────────────
DEFAULT_RISK_PERCENT    = 1.0      # % of account per trade
DEFAULT_MAX_DRAWDOWN    = 20.0     # % max drawdown before halt
DEFAULT_STOP_LOSS_PIPS  = 50       # default SL in pips
DEFAULT_TAKE_PROFIT_PIPS = 100     # default TP in pips
MAX_TRADES_PER_DAY      = 50

# ── Pip Values ───────────────────────────────────────────────
PIP_SIZES = {
    'JPY': 0.01,    # JPY pairs
    'DEFAULT': 0.0001,
}

# ── NLP Command Types ────────────────────────────────────────
class CommandType(models.TextChoices):
    START_BOT       = 'start_bot',      'Start Bot'
    STOP_BOT        = 'stop_bot',       'Stop Bot'
    PAUSE_BOT       = 'pause_bot',      'Pause Bot'
    SET_RISK        = 'set_risk',       'Set Risk Parameters'
    SET_STRATEGY    = 'set_strategy',   'Set Strategy'
    OPEN_TRADE      = 'open_trade',     'Open Trade'
    CLOSE_TRADE     = 'close_trade',    'Close Trade'
    CLOSE_ALL       = 'close_all',      'Close All Positions'
    RUN_BACKTEST    = 'run_backtest',   'Run Backtest'
    GET_STATUS      = 'get_status',     'Get Status'
    SET_TIMEFRAME   = 'set_timeframe',  'Set Timeframe'
    SET_PAIRS       = 'set_pairs',      'Set Trading Pairs'
    UNKNOWN         = 'unknown',        'Unknown Command'
