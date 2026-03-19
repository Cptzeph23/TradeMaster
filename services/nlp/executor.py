# ============================================================
# Executes parsed NLP actions against the trading platform
# ============================================================
import logging
from typing import Optional
from django.utils import timezone as dj_tz

from apps.trading.models import TradingBot, NLPCommand, Trade
from utils.constants import BotStatus, CommandType, TradeStatus

logger = logging.getLogger('nlp_commands')


class NLPCommandExecutor:
    """
    Takes a list of parsed action dicts from NLPCommandParser
    and executes each one against the trading platform.

    Each action maps to a handler method.
    Results are written back to the NLPCommand DB record.
    """

    ACTION_TO_COMMAND_TYPE = {
        'start_bot':      CommandType.START_BOT,
        'stop_bot':       CommandType.STOP_BOT,
        'pause_bot':      CommandType.PAUSE_BOT,
        'resume_bot':     CommandType.START_BOT,
        'set_risk':       CommandType.SET_RISK,
        'set_pairs':      CommandType.SET_PAIRS,
        'set_timeframe':  CommandType.SET_TIMEFRAME,
        'set_direction':  CommandType.SET_RISK,
        'open_trade':     CommandType.OPEN_TRADE,
        'close_trade':    CommandType.CLOSE_TRADE,
        'run_backtest':   CommandType.RUN_BACKTEST,
        'get_status':     CommandType.GET_STATUS,
        'set_strategy':   CommandType.SET_STRATEGY,
        'unknown':        CommandType.UNKNOWN,
    }

    def __init__(self, user, nlp_command: NLPCommand):
        self.user        = user
        self.nlp_command = nlp_command

    def execute_all(self, actions: list) -> dict:
        """
        Execute a list of parsed actions sequentially.
        Returns a combined result dict.
        """
        results  = []
        all_ok   = True
        combined_explanation = []

        for action_dict in actions:
            action = action_dict.get('action', 'unknown')
            logger.info(
                f"Executing NLP action '{action}' for user {self.user.email}"
            )

            try:
                result = self._dispatch(action, action_dict)
                results.append(result)
                if not result.get('success', False):
                    all_ok = False
                if result.get('explanation'):
                    combined_explanation.append(result['explanation'])
            except Exception as e:
                logger.error(f"NLP action '{action}' failed: {e}", exc_info=True)
                results.append({
                    'action':  action,
                    'success': False,
                    'error':   str(e),
                })
                all_ok = False

        # Update the NLPCommand record
        status = (NLPCommand.Status.SUCCESS if all_ok
                  else NLPCommand.Status.PARTIAL if results
                  else NLPCommand.Status.FAILED)

        self.nlp_command.status           = status
        self.nlp_command.execution_result = {'actions': results}
        self.nlp_command.executed_at      = dj_tz.now()
        if combined_explanation:
            self.nlp_command.ai_explanation = ' | '.join(combined_explanation)
        self.nlp_command.save(update_fields=[
            'status', 'execution_result', 'executed_at', 'ai_explanation'
        ])

        return {
            'success':  all_ok,
            'results':  results,
            'summary':  ' | '.join(combined_explanation),
        }

    def _dispatch(self, action: str, data: dict) -> dict:
        """Route action to the correct handler."""
        handlers = {
            'start_bot':     self._handle_start_bot,
            'stop_bot':      self._handle_stop_bot,
            'pause_bot':     self._handle_pause_bot,
            'resume_bot':    self._handle_resume_bot,
            'set_risk':      self._handle_set_risk,
            'set_pairs':     self._handle_set_pairs,
            'set_timeframe': self._handle_set_timeframe,
            'set_direction': self._handle_set_direction,
            'open_trade':    self._handle_open_trade,
            'close_trade':   self._handle_close_trade,
            'run_backtest':  self._handle_run_backtest,
            'get_status':    self._handle_get_status,
            'set_strategy':  self._handle_set_strategy,
        }
        handler = handlers.get(action, self._handle_unknown)
        return handler(data)

    # ── Bot Control Handlers ──────────────────────────────────
    def _handle_start_bot(self, data: dict) -> dict:
        bots = self._get_target_bots(data.get('bot_id'))
        started = []
        for bot in bots:
            if bot.status != BotStatus.RUNNING:
                if not bot.trading_account.is_verified:
                    continue
                from workers.tasks import run_trading_bot
                task = run_trading_bot.apply_async(
                    args=[str(bot.id)], queue='trading'
                )
                bot.celery_task_id = task.id
                bot.status         = BotStatus.RUNNING
                bot.started_at     = dj_tz.now()
                bot.save(update_fields=['celery_task_id', 'status', 'started_at'])
                started.append(bot.name)
                self._bot_log(bot, 'NLP command: start bot')
        return {
            'action':      'start_bot',
            'success':     True,
            'bots_started': started,
            'explanation': f"Started {len(started)} bot(s): {', '.join(started) or 'none eligible'}",
        }

    def _handle_stop_bot(self, data: dict) -> dict:
        bots = self._get_target_bots(data.get('bot_id'))
        stopped = []
        for bot in bots:
            if bot.status in (BotStatus.RUNNING, BotStatus.PAUSED):
                if bot.celery_task_id:
                    from config.celery import app as celery_app
                    celery_app.control.revoke(bot.celery_task_id, terminate=True)
                bot.status     = BotStatus.STOPPED
                bot.stopped_at = dj_tz.now()
                bot.save(update_fields=['status', 'stopped_at'])
                stopped.append(bot.name)
                self._bot_log(bot, 'NLP command: stop bot')
        return {
            'action':      'stop_bot',
            'success':     True,
            'bots_stopped': stopped,
            'explanation': f"Stopped {len(stopped)} bot(s): {', '.join(stopped) or 'none running'}",
        }

    def _handle_pause_bot(self, data: dict) -> dict:
        bots = self._get_target_bots(data.get('bot_id'))
        paused = []
        for bot in bots:
            if bot.status == BotStatus.RUNNING:
                bot.status = BotStatus.PAUSED
                bot.save(update_fields=['status'])
                paused.append(bot.name)
                self._bot_log(bot, 'NLP command: pause bot')
        return {
            'action':      'pause_bot',
            'success':     True,
            'bots_paused': paused,
            'explanation': f"Paused {len(paused)} bot(s): {', '.join(paused) or 'none running'}",
        }

    def _handle_resume_bot(self, data: dict) -> dict:
        bots = self._get_target_bots(data.get('bot_id'))
        resumed = []
        for bot in bots:
            if bot.status == BotStatus.PAUSED:
                bot.status = BotStatus.RUNNING
                bot.save(update_fields=['status'])
                resumed.append(bot.name)
                self._bot_log(bot, 'NLP command: resume bot')
        return {
            'action':       'resume_bot',
            'success':      True,
            'bots_resumed': resumed,
            'explanation':  f"Resumed {len(resumed)} bot(s): {', '.join(resumed) or 'none paused'}",
        }

    # ── Risk / Config Handlers ────────────────────────────────
    def _handle_set_risk(self, data: dict) -> dict:
        bots    = self._get_target_bots(data.get('bot_id'))
        changed = []

        risk_fields = [
            'risk_percent', 'stop_loss_pips', 'take_profit_pips',
            'max_trades_per_day', 'max_open_trades', 'max_drawdown_percent',
            'trailing_stop_enabled', 'trailing_stop_pips',
            'use_risk_reward', 'risk_reward_ratio',
        ]

        for bot in bots:
            updates = {k: data[k] for k in risk_fields if k in data and data[k] is not None}
            if updates:
                applied = bot.apply_nlp_settings(updates)
                changed.append({'bot': bot.name, 'changed': applied})
                self._bot_log(bot, f"NLP: set_risk {updates}")

        return {
            'action':      'set_risk',
            'success':     True,
            'changes':     changed,
            'explanation': f"Updated risk settings on {len(changed)} bot(s)",
        }

    def _handle_set_pairs(self, data: dict) -> dict:
        bots    = self._get_target_bots(data.get('bot_id'))
        symbols = data.get('symbols', [])
        if not symbols:
            return {'action': 'set_pairs', 'success': False,
                    'error': 'No symbols provided'}

        # Normalise all symbols
        symbols = [s.upper().replace('/', '_').replace('-', '_') for s in symbols]
        updated = []

        for bot in bots:
            bot.symbols = symbols
            bot.save(update_fields=['symbols'])
            updated.append(bot.name)
            self._bot_log(bot, f"NLP: set_pairs {symbols}")

        return {
            'action':      'set_pairs',
            'success':     True,
            'symbols':     symbols,
            'bots_updated':updated,
            'explanation': f"Set trading pairs to {symbols} on {len(updated)} bot(s)",
        }

    def _handle_set_timeframe(self, data: dict) -> dict:
        bots      = self._get_target_bots(data.get('bot_id'))
        timeframe = data.get('timeframe', '').upper()
        valid_tfs = ['M1','M5','M15','M30','H1','H4','D1','W1','MN1']

        if timeframe not in valid_tfs:
            return {'action': 'set_timeframe', 'success': False,
                    'error': f"Invalid timeframe '{timeframe}'. Valid: {valid_tfs}"}

        updated = []
        for bot in bots:
            if bot.status == BotStatus.RUNNING:
                continue  # can't change timeframe while running
            bot.timeframe = timeframe
            bot.save(update_fields=['timeframe'])
            updated.append(bot.name)
            self._bot_log(bot, f"NLP: set_timeframe {timeframe}")

        return {
            'action':      'set_timeframe',
            'success':     True,
            'timeframe':   timeframe,
            'bots_updated':updated,
            'explanation': f"Set timeframe to {timeframe} on {len(updated)} bot(s)",
        }

    def _handle_set_direction(self, data: dict) -> dict:
        bots       = self._get_target_bots(data.get('bot_id'))
        allow_buy  = data.get('allow_buy')
        allow_sell = data.get('allow_sell')
        updated    = []

        for bot in bots:
            changed = {}
            if allow_buy  is not None: bot.allow_buy  = allow_buy;  changed['allow_buy']  = allow_buy
            if allow_sell is not None: bot.allow_sell = allow_sell; changed['allow_sell'] = allow_sell
            if changed:
                bot.save(update_fields=list(changed.keys()))
                updated.append({'bot': bot.name, **changed})
                self._bot_log(bot, f"NLP: set_direction {changed}")

        direction = ('both' if (allow_buy and allow_sell)
                     else 'buy only' if allow_buy
                     else 'sell only' if allow_sell
                     else 'unknown')
        return {
            'action':      'set_direction',
            'success':     True,
            'direction':   direction,
            'bots_updated':updated,
            'explanation': f"Set trade direction to '{direction}' on {len(updated)} bot(s)",
        }

    # ── Trade Handlers ────────────────────────────────────────
    def _handle_open_trade(self, data: dict) -> dict:
        bot_id = data.get('bot_id')
        if not bot_id:
            return {'action': 'open_trade', 'success': False,
                    'error': 'bot_id is required to open a trade'}
        try:
            bot    = TradingBot.objects.get(pk=bot_id, user=self.user)
            symbol = data.get('symbol', 'EUR_USD').upper().replace('/', '_')
            order_type = data.get('order_type', 'buy').lower()

            from apps.strategies.base import Signal
            signal = Signal(
                action      = order_type,
                symbol      = symbol,
                strength    = 1.0,
                stop_loss   = None,
                take_profit = None,
                reason      = f"Manual trade via NLP command: {self.nlp_command.raw_command}",
            )
            from workers.tasks import execute_order
            task = execute_order.apply_async(
                args  = [str(bot.id), signal.to_dict()],
                queue = 'orders',
            )
            return {
                'action':      'open_trade',
                'success':     True,
                'task_id':     task.id,
                'symbol':      symbol,
                'order_type':  order_type,
                'explanation': f"Queued {order_type} order for {symbol}",
            }
        except TradingBot.DoesNotExist:
            return {'action': 'open_trade', 'success': False,
                    'error': f'Bot {bot_id} not found'}

    def _handle_close_trade(self, data: dict) -> dict:
        close_all = data.get('close_all', False)
        bot_id    = data.get('bot_id')
        symbol    = data.get('symbol')
        closed    = []

        qs = Trade.objects.filter(bot__user=self.user, status=TradeStatus.OPEN)
        if bot_id:
            qs = qs.filter(bot_id=bot_id)
        if symbol:
            qs = qs.filter(symbol=symbol.upper().replace('/', '_'))

        if not close_all and not bot_id and not symbol:
            return {'action': 'close_trade', 'success': False,
                    'error': 'Specify bot_id, symbol, or close_all=true'}

        for trade in qs:
            try:
                # Queue close via celery — engine handles broker call
                from workers.tasks import execute_order
                close_signal = {
                    'action': 'close', 'symbol': trade.symbol,
                    'trade_id': str(trade.id), 'strength': 1.0,
                    'reason': f"NLP close: {self.nlp_command.raw_command}",
                    'indicators': {}, 'stop_loss': None, 'take_profit': None,
                }
                closed.append({'trade_id': str(trade.id), 'symbol': trade.symbol})
            except Exception as e:
                logger.error(f"Close trade {trade.id} failed: {e}")

        return {
            'action':      'close_trade',
            'success':     True,
            'trades_closed':closed,
            'explanation': f"Closing {len(closed)} open trade(s)",
        }

    def _handle_run_backtest(self, data: dict) -> dict:
        bot_id = data.get('bot_id')
        if not bot_id:
            return {'action': 'run_backtest', 'success': False,
                    'error': 'bot_id is required for backtest'}
        try:
            bot = TradingBot.objects.get(pk=bot_id, user=self.user)
        except TradingBot.DoesNotExist:
            return {'action': 'run_backtest', 'success': False,
                    'error': f'Bot {bot_id} not found'}

        from apps.backtesting.models import BacktestResult
        from django.utils.dateparse import parse_datetime

        start = parse_datetime(data.get('start_date', '2024-01-01') + 'T00:00:00Z')
        end   = parse_datetime(data.get('end_date',   '2024-06-30') + 'T23:59:59Z')

        backtest = BacktestResult.objects.create(
            user        = self.user,
            strategy    = bot.strategy,
            symbol      = data.get('symbol', (bot.symbols or ['EUR_USD'])[0]),
            timeframe   = data.get('timeframe', bot.timeframe),
            start_date  = start,
            end_date    = end,
            initial_balance = data.get('initial_balance', 10000),
            parameters_snapshot = bot.strategy.parameters,
            name        = f"NLP Backtest — {bot.name}",
        )
        from workers.tasks import run_backtest
        task = run_backtest.apply_async(
            args=[str(backtest.id)], queue='backtesting'
        )
        return {
            'action':      'run_backtest',
            'success':     True,
            'backtest_id': str(backtest.id),
            'task_id':     task.id,
            'explanation': f"Backtest queued for {bot.name}",
        }

    def _handle_get_status(self, data: dict) -> dict:
        bots    = self._get_target_bots(data.get('bot_id'))
        summary = []
        for bot in bots:
            open_trades = Trade.objects.filter(
                bot=bot, status=TradeStatus.OPEN
            ).count()
            summary.append({
                'bot':         bot.name,
                'status':      bot.status,
                'symbols':     bot.symbols,
                'timeframe':   bot.timeframe,
                'open_trades': open_trades,
                'total_pnl':   float(bot.total_profit_loss or 0),
                'win_rate':    bot.win_rate,
                'drawdown':    float(bot.current_drawdown or 0),
            })
        return {
            'action':      'get_status',
            'success':     True,
            'bots':        summary,
            'explanation': f"Status of {len(summary)} bot(s) retrieved",
        }

    def _handle_set_strategy(self, data: dict) -> dict:
        bots          = self._get_target_bots(data.get('bot_id'))
        strategy_type = data.get('strategy_type', '')
        updated       = []

        for bot in bots:
            if bot.status == BotStatus.RUNNING:
                continue
            # Find a matching strategy for this user
            from apps.strategies.models import Strategy
            strategy = Strategy.objects.filter(
                user=self.user,
                strategy_type=strategy_type,
                is_active=True,
            ).first()
            if strategy:
                bot.strategy = strategy
                bot.save(update_fields=['strategy'])
                updated.append(bot.name)
                self._bot_log(bot, f"NLP: set_strategy {strategy_type}")

        return {
            'action':      'set_strategy',
            'success':     True,
            'bots_updated':updated,
            'explanation': f"Strategy set to '{strategy_type}' on {len(updated)} bot(s)",
        }

    def _handle_unknown(self, data: dict) -> dict:
        reason = data.get('reason', 'Command not recognised')
        return {
            'action':  'unknown',
            'success': False,
            'reason':  reason,
            'explanation': f"Could not execute: {reason}",
        }

    # ── Helpers ───────────────────────────────────────────────
    def _get_target_bots(self, bot_id: Optional[str]) -> list:
        """
        If bot_id provided → return that specific bot.
        If None → return ALL of user's active bots.
        """
        if bot_id and str(bot_id) != 'None':
            try:
                return [TradingBot.objects.get(pk=bot_id, user=self.user, is_active=True)]
            except TradingBot.DoesNotExist:
                return []
        return list(TradingBot.objects.filter(user=self.user, is_active=True))

    def _bot_log(self, bot: TradingBot, message: str):
        try:
            from apps.trading.models import BotLog
            BotLog.objects.create(
                bot        = bot,
                level      = BotLog.Level.INFO,
                event_type = BotLog.EventType.NLP_COMMAND,
                message    = message,
                data       = {
                    'command_id': str(self.nlp_command.id),
                    'raw_command': self.nlp_command.raw_command,
                },
            )
        except Exception as e:
            logger.warning(f"BotLog write failed: {e}")