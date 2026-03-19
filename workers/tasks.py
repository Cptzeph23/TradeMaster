# ============================================================
# All Celery task definitions for the trading platform
# ============================================================
import logging
from celery import shared_task

logger = logging.getLogger('trading')


@shared_task(bind=True, max_retries=0, name='workers.tasks.run_trading_bot')
def run_trading_bot(self, bot_id: str):
    """
    Main bot runner task.
    Spawns a TradingEngine instance and runs the bot loop.
    This task runs until the bot is stopped/paused/errors.
    Queue: 'trading'
    """
    logger.info(f"run_trading_bot started: bot_id={bot_id}")
    try:
        from services.trading_engine.engine import TradingEngine
        engine = TradingEngine(bot_id=bot_id)
        engine.run()
        logger.info(f"run_trading_bot completed: bot_id={bot_id}")
        return {'status': 'completed', 'bot_id': bot_id}
    except Exception as e:
        logger.error(f"run_trading_bot failed: bot_id={bot_id} error={e}", exc_info=True)
        # Mark bot as errored in DB
        try:
            from apps.trading.models import TradingBot
            from utils.constants import BotStatus
            TradingBot.objects.filter(pk=bot_id).update(
                status=BotStatus.ERROR,
                error_message=str(e)[:500],
            )
        except Exception:
            pass
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=5,
             name='workers.tasks.execute_order')
def execute_order(self, bot_id: str, signal_data: dict):
    """
    Execute a single order outside the main bot loop.
    Used for manual trades triggered from the dashboard/NLP.
    Queue: 'orders'
    """
    try:
        from apps.trading.models import TradingBot
        from apps.strategies.base import Signal
        bot = TradingBot.objects.get(pk=bot_id)

        # Reconstruct signal from dict
        signal = Signal(**signal_data)

        # Connect broker
        from services.trading_engine.engine import TradingEngine
        engine = TradingEngine(bot_id=bot_id)
        engine.bot    = bot
        engine.broker = engine._connect_broker()

        account_info  = engine.broker.get_account_info()
        current_price = engine.broker.get_price(signal.symbol)

        from services.trading_engine.signal_processor import SignalProcessor
        from services.trading_engine.executor import OrderExecutor

        processor = SignalProcessor(bot, account_info, current_price)
        processed = processor.process(signal)
        executor  = OrderExecutor(bot, engine.broker)
        result    = executor.execute(processed)

        return result
    except Exception as e:
        logger.error(f"execute_order failed: {e}", exc_info=True)
        self.retry(exc=e)


@shared_task(bind=True, max_retries=2, name='workers.tasks.process_nlp_command')
def process_nlp_command(self, user_id: str, raw_command: str, bot_id: str = None):
    """
    Parse and execute a natural language trading command.
    Full implementation in Phase K.
    Queue: 'commands'
    """
    logger.info(f"process_nlp_command: user={user_id} cmd='{raw_command[:60]}'")
    try:
        # Phase K fills this in with the full NLP pipeline
        from apps.trading.models import NLPCommand
        from apps.accounts.models import User
        from utils.constants import CommandType

        user = User.objects.get(pk=user_id)
        bot  = None
        if bot_id and bot_id != 'None':
            from apps.trading.models import TradingBot
            try:
                bot = TradingBot.objects.get(pk=bot_id, user=user)
            except TradingBot.DoesNotExist:
                pass

        # Create pending record
        cmd = NLPCommand.objects.create(
            user        = user,
            bot         = bot,
            raw_command = raw_command,
            status      = NLPCommand.Status.PENDING,
        )

        # Phase K: call AI parser here
        # For now, return pending status
        return {
            'command_id': str(cmd.id),
            'status':     'pending',
            'message':    'NLP processing will be fully active in Phase K',
        }

    except Exception as e:
        logger.error(f"process_nlp_command failed: {e}", exc_info=True)
        self.retry(exc=e)


@shared_task(name='workers.tasks.run_backtest')
def run_backtest(backtest_id: str):
    """
    Run a backtest asynchronously.
    Full implementation in Phase H.
    Queue: 'backtesting'
    """
    logger.info(f"run_backtest: {backtest_id}")
    try:
        from apps.backtesting.engine import BacktestEngine
        engine = BacktestEngine(backtest_id=backtest_id)
        return engine.run()
    except Exception as e:
        logger.error(f"run_backtest failed: {e}", exc_info=True)
        from apps.backtesting.models import BacktestResult
        from utils.constants import BacktestStatus
        BacktestResult.objects.filter(pk=backtest_id).update(
            status=BacktestStatus.FAILED,
            error_message=str(e)[:500],
        )
        raise


@shared_task(name='workers.tasks.fetch_market_data')
def fetch_market_data(symbol: str, timeframe: str,
                      count: int = 500, broker: str = 'oanda'):
    """Wrapper — delegates to market_data app task."""
    from apps.market_data.tasks import fetch_and_cache_candles
    return fetch_and_cache_candles(symbol, timeframe, count, broker)