# ============================================================
# Celery tasks for asynchronous processing in the trading bot application.

# ============================================================
import logging
from celery import shared_task
from celery import shared_task
import logging

logger = logging.getLogger('trading')


@shared_task(bind=True, max_retries=0, name='workers.tasks.run_trading_bot')
def run_trading_bot(self, bot_id: str):
    """Main bot runner — unchanged from Phase I."""
    logger.info(f"run_trading_bot: bot_id={bot_id}")
    try:
        from services.trading_engine.engine import TradingEngine
        engine = TradingEngine(bot_id=bot_id)
        engine.run()
        return {'status': 'completed', 'bot_id': bot_id}
    except Exception as e:
        logger.error(f"run_trading_bot failed: {e}", exc_info=True)
        try:
            from apps.trading.models import TradingBot
            from utils.constants import BotStatus
            TradingBot.objects.filter(pk=bot_id).update(
                status=BotStatus.ERROR, error_message=str(e)[:500]
            )
        except Exception:
            pass
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=5,
             name='workers.tasks.execute_order')
def execute_order(self, bot_id: str, signal_data: dict):
    """Execute a single order — unchanged from Phase I."""
    try:
        from apps.trading.models import TradingBot
        from apps.strategies.base import Signal
        bot    = TradingBot.objects.get(pk=bot_id)
        signal = Signal(**signal_data)

        from services.trading_engine.engine import TradingEngine
        engine        = TradingEngine(bot_id=bot_id)
        engine.bot    = bot
        engine.broker = engine._connect_broker()

        account_info  = engine.broker.get_account_info()
        current_price = engine.broker.get_price(signal.symbol)

        from services.trading_engine.signal_processor import SignalProcessor
        from services.trading_engine.executor import OrderExecutor
        processor = SignalProcessor(bot, account_info, current_price)
        processed = processor.process(signal)
        executor  = OrderExecutor(bot, engine.broker)
        return executor.execute(processed)
    except Exception as e:
        logger.error(f"execute_order failed: {e}", exc_info=True)
        self.retry(exc=e)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='workers.tasks.process_nlp_command',
)
def process_nlp_command(self, user_id: str, raw_command: str,
                        bot_id: str = None):
    """
    Full NLP command pipeline:
      1. Load user + optional bot from DB
      2. Create NLPCommand record (status=pending)
      3. Call Claude AI to parse the command
      4. Update record with parsed intent + confidence
      5. Execute parsed actions via NLPCommandExecutor
      6. Return combined result
    """
    logger.info(
        f"process_nlp_command: user={user_id} "
        f"cmd='{raw_command[:60]}'"
    )
    from apps.accounts.models import User
    from apps.trading.models import TradingBot, NLPCommand
    from utils.constants import CommandType
    from services.nlp.parser import NLPCommandParser
    from services.nlp.executor import NLPCommandExecutor
    from django.utils import timezone as dj_tz

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error(f"process_nlp_command: user {user_id} not found")
        return {'success': False, 'error': 'User not found'}

    # ── Resolve target bot ────────────────────────────────────
    bot = None
    if bot_id and bot_id not in ('None', 'null', ''):
        try:
            bot = TradingBot.objects.get(pk=bot_id, user=user)
        except TradingBot.DoesNotExist:
            pass

    # ── Create or find pending NLPCommand record ──────────────
    # (may already exist if created by the API view)
    nlp_cmd = NLPCommand.objects.filter(
        user        = user,
        raw_command = raw_command,
        status      = NLPCommand.Status.PENDING,
    ).order_by('-created_at').first()

    if not nlp_cmd:
        nlp_cmd = NLPCommand.objects.create(
            user        = user,
            bot         = bot,
            raw_command = raw_command,
            status      = NLPCommand.Status.PENDING,
        )

    # ── Build context for the parser ─────────────────────────
    context = {'user_email': user.email}
    if bot:
        context.update({
            'bot_id':      str(bot.id),
            'bot_name':    bot.name,
            'bot_status':  bot.status,
            'symbols':     bot.symbols,
            'timeframe':   bot.timeframe,
            'risk_settings': bot.risk_settings,
        })
    else:
        # Include all bot names so Claude can resolve references
        all_bots = TradingBot.objects.filter(
            user=user, is_active=True
        ).values('id', 'name', 'status')
        context['available_bots'] = [
            {'id': str(b['id']), 'name': b['name'], 'status': b['status']}
            for b in all_bots
        ]

    # ── Parse with Claude ─────────────────────────────────────
    parser     = NLPCommandParser()
    parse_result = parser.parse(raw_command, context)

    actions    = parse_result.get('actions', [])
    first      = actions[0] if actions else {}

    # Determine primary command type
    primary_action = first.get('action', 'unknown')
    command_type   = NLPCommandExecutor.ACTION_TO_COMMAND_TYPE.get(
        primary_action, CommandType.UNKNOWN
    )
    confidence     = first.get('confidence', 0.0)
    explanation    = first.get('explanation', '')

    # Update NLPCommand with parse results
    nlp_cmd.command_type    = command_type
    nlp_cmd.parsed_intent   = {'actions': actions}
    nlp_cmd.ai_explanation  = explanation
    nlp_cmd.confidence      = confidence
    nlp_cmd.model_used      = parse_result.get('model_used', '')
    nlp_cmd.tokens_used     = parse_result.get('tokens_used', 0)
    nlp_cmd.bot             = bot
    nlp_cmd.save(update_fields=[
        'command_type', 'parsed_intent', 'ai_explanation',
        'confidence', 'model_used', 'tokens_used', 'bot',
    ])

    # ── Execute actions ───────────────────────────────────────
    executor = NLPCommandExecutor(user=user, nlp_command=nlp_cmd)
    result   = executor.execute_all(actions)

    logger.info(
        f"NLP command complete: action={primary_action} "
        f"confidence={confidence} success={result['success']}"
    )

    from utils.logger import TradingActivityLogger
    TradingActivityLogger.log_nlp_command(
        user_id      = user.id,
        raw_command  = raw_command,
        parsed_action = primary_action,
        confidence   = confidence,
        success      = result['success'],
    )

    return {
        'success':     result['success'],
        'command_id':  str(nlp_cmd.id),
        'action':      primary_action,
        'confidence':  confidence,
        'explanation': explanation,
        'results':     result['results'],
        'model_used':  parse_result.get('model_used', ''),
    }


@shared_task(name='workers.tasks.run_backtest')
def run_backtest(backtest_id: str):
    """Run a backtest — unchanged from Phase I."""
    logger.info(f"run_backtest: {backtest_id}")
    try:
        from apps.backtesting.engine import BacktestEngine
        return BacktestEngine(backtest_id=backtest_id).run()
    except Exception as e:
        logger.error(f"run_backtest failed: {e}", exc_info=True)
        from apps.backtesting.models import BacktestResult
        from utils.constants import BacktestStatus
        BacktestResult.objects.filter(pk=backtest_id).update(
            status=BacktestStatus.FAILED, error_message=str(e)[:500]
        )
        raise


@shared_task(name='workers.tasks.fetch_market_data')
def fetch_market_data(symbol: str, timeframe: str,
                      count: int = 500, broker: str = 'oanda'):
    """Fetch market data — unchanged from Phase I."""
    from apps.market_data.tasks import fetch_and_cache_candles
    return fetch_and_cache_candles(symbol, timeframe, count, broker)



@shared_task(name='workers.tasks.process_telegram_update')
def process_telegram_update(update_data: dict):
    """
    Process an incoming Telegram update (command from trader).
    Runs in Celery so the webhook returns 200 instantly.
    """
    try:
        from services.telegram.bot import get_telegram_bot
        bot = get_telegram_bot()
        bot.handle_update(update_data)
    except Exception as e:
        logger.error(f"process_telegram_update failed: {e}", exc_info=True)
 
 
@shared_task(name='workers.tasks.send_telegram_daily_report')
def send_telegram_daily_report():
    """
    Triggered by Celery Beat at midnight UTC.
    Computes daily stats and sends Telegram summary.
    """
    from datetime import datetime, timezone, timedelta
    from apps.trading.models import TradingBot, Trade
    from utils.constants import TradeStatus, BotStatus
    from services.telegram.alerts import send_daily_report
 
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
 
    trades = Trade.objects.filter(
        status=TradeStatus.CLOSED,
        closed_at__gte=today_start,
    )
 
    pnl_list = [float(t.profit_loss or 0) for t in trades]
    winners  = [p for p in pnl_list if p > 0]
    losers   = [p for p in pnl_list if p <= 0]
    total_pnl= sum(pnl_list)
    win_rate = round(len(winners)/len(pnl_list)*100, 1) if pnl_list else 0
 
    running_bots = TradingBot.objects.filter(
        status=BotStatus.RUNNING, is_active=True
    ).count()
 
    stats = {
        'total_trades': len(pnl_list),
        'winners':      len(winners),
        'losers':       len(losers),
        'total_pnl':    total_pnl,
        'win_rate':     win_rate,
        'best_trade':   max(pnl_list) if pnl_list else 0,
        'worst_trade':  min(pnl_list) if pnl_list else 0,
        'running_bots': running_bots,
    }
 
    date_str = today_start.strftime('%Y-%m-%d')
    send_daily_report(date_str, stats)
    return stats
 

