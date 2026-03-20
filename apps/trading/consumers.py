# ============================================================
# Django Channels WebSocket consumers
# ============================================================
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger('trading')


class BotStatusConsumer(AsyncWebsocketConsumer):
    """
    WebSocket: ws://host/ws/bots/<bot_id>/
    Streams real-time bot status, trade signals, and log events.

    Client receives:
      { "type": "bot_status",   "data": {...} }
      { "type": "signal",       "data": {...} }
      { "type": "trade_opened", "data": {...} }
      { "type": "trade_closed", "data": {...} }
      { "type": "bot_log",      "data": {...} }
      { "type": "error",        "message": "..." }

    Client sends:
      { "action": "ping" }
      { "action": "get_status" }
    """

    async def connect(self):
        self.bot_id   = self.scope['url_route']['kwargs']['bot_id']
        self.group_name = f"bot_{self.bot_id}"
        self.user     = self.scope.get('user')

        # Reject unauthenticated connections
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # Verify the user owns this bot
        if not await self._user_owns_bot():
            await self.close(code=4003)
            return

        # Join the bot's channel group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )
        await self.accept()

        # Send current bot status immediately on connect
        status = await self._get_bot_status()
        await self.send(text_data=json.dumps({
            'type': 'bot_status',
            'data': status,
        }))
        logger.debug(
            f"WS connected: user={self.user.email} bot={self.bot_id}"
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name,
        )
        logger.debug(f"WS disconnected: bot={self.bot_id} code={close_code}")

    async def receive(self, text_data):
        """Handle messages sent from the client."""
        try:
            data   = json.loads(text_data)
            action = data.get('action', '')

            if action == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))

            elif action == 'get_status':
                status = await self._get_bot_status()
                await self.send(text_data=json.dumps({
                    'type': 'bot_status',
                    'data': status,
                }))

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type':    'error',
                'message': 'Invalid JSON',
            }))

    # ── Group message handlers (called by channel_layer.group_send) ──
    async def bot_status(self, event):
        await self.send(text_data=json.dumps({
            'type': 'bot_status',
            'data': event['data'],
        }))

    async def signal(self, event):
        await self.send(text_data=json.dumps({
            'type': 'signal',
            'data': event['data'],
        }))

    async def trade_opened(self, event):
        await self.send(text_data=json.dumps({
            'type': 'trade_opened',
            'data': event['data'],
        }))

    async def trade_closed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'trade_closed',
            'data': event['data'],
        }))

    async def bot_log(self, event):
        await self.send(text_data=json.dumps({
            'type': 'bot_log',
            'data': event['data'],
        }))

    async def nlp_result(self, event):
        await self.send(text_data=json.dumps({
            'type': 'nlp_result',
            'data': event['data'],
        }))

    # ── DB helpers ────────────────────────────────────────────
    @database_sync_to_async
    def _user_owns_bot(self) -> bool:
        from apps.trading.models import TradingBot
        return TradingBot.objects.filter(
            pk=self.bot_id,
            user=self.user,
            is_active=True,
        ).exists()

    @database_sync_to_async
    def _get_bot_status(self) -> dict:
        from apps.trading.models import TradingBot, Trade
        from utils.constants import TradeStatus
        try:
            bot = TradingBot.objects.select_related(
                'strategy', 'trading_account'
            ).get(pk=self.bot_id)

            open_trades = Trade.objects.filter(
                bot=bot, status=TradeStatus.OPEN
            ).values('id', 'symbol', 'order_type', 'entry_price',
                     'profit_loss', 'opened_at')

            return {
                'id':             str(bot.id),
                'name':           bot.name,
                'status':         bot.status,
                'strategy':       bot.strategy.name,
                'symbols':        bot.symbols,
                'timeframe':      bot.timeframe,
                'allow_buy':      bot.allow_buy,
                'allow_sell':     bot.allow_sell,
                'total_trades':   bot.total_trades,
                'win_rate':       bot.win_rate,
                'total_pnl':      float(bot.total_profit_loss or 0),
                'drawdown':       float(bot.current_drawdown or 0),
                'open_trades':    [
                    {
                        'id':          str(t['id']),
                        'symbol':      t['symbol'],
                        'order_type':  t['order_type'],
                        'entry_price': float(t['entry_price'] or 0),
                        'pnl':         float(t['profit_loss'] or 0),
                        'opened_at':   t['opened_at'].isoformat() if t['opened_at'] else None,
                    }
                    for t in open_trades
                ],
                'balance':        float(bot.trading_account.balance or 0),
                'started_at':     bot.started_at.isoformat() if bot.started_at else None,
            }
        except ObjectDoesNotExist:
            return {'error': 'Bot not found'}


class LivePriceConsumer(AsyncWebsocketConsumer):
    """
    WebSocket: ws://host/ws/prices/<symbol>/
    Streams live bid/ask price ticks for a forex symbol.

    Broadcasts a new price every time the market data layer
    publishes an update via channel_layer.group_send.

    Client receives:
      { "type": "price_tick", "data": {"symbol": "EUR_USD",
        "bid": 1.09234, "ask": 1.09236, "spread": 0.00002,
        "timestamp": "..."} }
    """

    async def connect(self):
        self.symbol     = self.scope['url_route']['kwargs']['symbol'].upper()
        self.group_name = f"prices_{self.symbol}"
        self.user       = self.scope.get('user')

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )
        await self.accept()

        # Send last known price immediately
        price = await self._get_last_price()
        if price:
            await self.send(text_data=json.dumps({
                'type': 'price_tick',
                'data': price,
            }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name,
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get('action') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except json.JSONDecodeError:
            pass

    async def price_tick(self, event):
        await self.send(text_data=json.dumps({
            'type': 'price_tick',
            'data': event['data'],
        }))

    @database_sync_to_async
    def _get_last_price(self):
        from apps.market_data.models import LiveTick
        tick = LiveTick.objects.filter(
            symbol=self.symbol
        ).order_by('-timestamp').first()
        if tick:
            return {
                'symbol':    tick.symbol,
                'bid':       float(tick.bid),
                'ask':       float(tick.ask),
                'spread':    float(tick.spread),
                'timestamp': tick.timestamp.isoformat(),
            }
        return None


class DashboardConsumer(AsyncWebsocketConsumer):
    """
    WebSocket: ws://host/ws/dashboard/
    Streams aggregated updates for ALL of a user's bots.
    Powers the main dashboard live feed.

    Client receives:
      { "type": "dashboard_update", "data": { bots: [...], summary: {...} } }
      { "type": "notification",     "data": { level, message, bot_name } }
      { "type": "trade_alert",      "data": { trade details } }
    """

    async def connect(self):
        self.user = self.scope.get('user')

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        self.group_name = f"dashboard_{self.user.id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )
        await self.accept()

        # Send full dashboard snapshot on connect
        snapshot = await self._get_dashboard_snapshot()
        await self.send(text_data=json.dumps({
            'type': 'dashboard_update',
            'data': snapshot,
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name,
        )

    async def receive(self, text_data):
        try:
            data   = json.loads(text_data)
            action = data.get('action', '')
            if action == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
            elif action == 'refresh':
                snapshot = await self._get_dashboard_snapshot()
                await self.send(text_data=json.dumps({
                    'type': 'dashboard_update',
                    'data': snapshot,
                }))
        except json.JSONDecodeError:
            pass

    async def dashboard_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'dashboard_update',
            'data': event['data'],
        }))

    async def notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'data': event['data'],
        }))

    async def trade_alert(self, event):
        await self.send(text_data=json.dumps({
            'type': 'trade_alert',
            'data': event['data'],
        }))

    async def nlp_result(self, event):
        await self.send(text_data=json.dumps({
            'type': 'nlp_result',
            'data': event['data'],
        }))

    @database_sync_to_async
    def _get_dashboard_snapshot(self) -> dict:
        from apps.trading.models import TradingBot, Trade
        from utils.constants import BotStatus, TradeStatus
        from apps.market_data.models import LiveTick

        bots = TradingBot.objects.filter(
            user=self.user, is_active=True
        ).select_related('strategy', 'trading_account')

        bots_data = []
        total_pnl = 0.0

        for bot in bots:
            open_count = Trade.objects.filter(
                bot=bot, status=TradeStatus.OPEN
            ).count()
            pnl = float(bot.total_profit_loss or 0)
            total_pnl += pnl
            bots_data.append({
                'id':          str(bot.id),
                'name':        bot.name,
                'status':      bot.status,
                'strategy':    bot.strategy.name,
                'symbols':     bot.symbols,
                'open_trades': open_count,
                'pnl':         pnl,
                'win_rate':    bot.win_rate,
                'drawdown':    float(bot.current_drawdown or 0),
            })

        running = sum(1 for b in bots_data if b['status'] == BotStatus.RUNNING)

        return {
            'bots':    bots_data,
            'summary': {
                'total_bots':    len(bots_data),
                'running_bots':  running,
                'total_pnl':     round(total_pnl, 2),
                'total_trades':  sum(
                    bot.total_trades for bot in bots
                ),
            },
        }