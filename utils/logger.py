# ============================================================
# DESTINATION: /opt/forex_bot/utils/logger.py
# Structured logging setup using structlog
# ============================================================
import logging
import structlog
from typing import Any


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a structured logger bound to a named context.
    Usage:
        from utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info("trade_executed", symbol="EUR_USD", profit=50.0)
    """
    return structlog.get_logger(name)


def configure_structlog():
    """Configure structlog processors and output format."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt='iso'),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


# ── Specialised loggers ──────────────────────────────────────
trade_logger   = get_logger('trading.orders')
bot_logger     = get_logger('trading.bots')
market_logger  = get_logger('market_data')
risk_logger    = get_logger('risk_management')
backtest_logger= get_logger('backtesting')
nlp_logger     = get_logger('nlp_commands')


class TradingActivityLogger:
    """High-level logging facade for the trading engine."""

    @staticmethod
    def log_order_placed(bot_id: int, symbol: str, order_type: str,
                          quantity: float, price: float, **kwargs: Any):
        trade_logger.info(
            'order_placed',
            bot_id=bot_id,
            symbol=symbol,
            order_type=order_type,
            quantity=quantity,
            price=price,
            **kwargs,
        )

    @staticmethod
    def log_order_filled(trade_id: int, symbol: str, fill_price: float,
                          profit_loss: float, **kwargs: Any):
        trade_logger.info(
            'order_filled',
            trade_id=trade_id,
            symbol=symbol,
            fill_price=fill_price,
            profit_loss=profit_loss,
            **kwargs,
        )

    @staticmethod
    def log_order_rejected(bot_id: int, reason: str, **kwargs: Any):
        trade_logger.warning(
            'order_rejected',
            bot_id=bot_id,
            reason=reason,
            **kwargs,
        )

    @staticmethod
    def log_risk_block(bot_id: int, rule: str, details: str, **kwargs: Any):
        risk_logger.warning(
            'risk_rule_blocked_trade',
            bot_id=bot_id,
            rule=rule,
            details=details,
            **kwargs,
        )

    @staticmethod
    def log_nlp_command(user_id: int, raw_command: str,
                         parsed_action: str, **kwargs: Any):
        nlp_logger.info(
            'nlp_command_received',
            user_id=user_id,
            raw_command=raw_command,
            parsed_action=parsed_action,
            **kwargs,
        )
