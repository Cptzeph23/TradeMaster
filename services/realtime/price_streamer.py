# ============================================================
# Background task that polls live prices and broadcasts via WS
# ============================================================
import logging
import time
from django.conf import settings

logger = logging.getLogger('market_data')


def stream_prices_for_bot(bot_id: str, interval_seconds: float = 1.0):
    """
    Fetch live prices for all symbols in a bot's watchlist
    and broadcast them to the WebSocket price channel.

    Called by the trading engine each tick cycle.
    Runs as part of the bot loop — NOT a separate process.
    """
    from apps.trading.models import TradingBot
    from services.data_feed.feed_manager import FeedManager
    from services.realtime.broadcaster import broadcast_price_tick
    from apps.market_data.models import LiveTick
    from django.utils import timezone as dj_tz

    try:
        bot     = TradingBot.objects.get(pk=bot_id)
        symbols = bot.symbols or []

        for symbol in symbols:
            try:
                price = FeedManager.fetch_live_price(symbol, bot.broker)
                if not price:
                    continue

                # Save to LiveTick table
                LiveTick.objects.create(
                    symbol    = symbol,
                    broker    = bot.broker,
                    bid       = price['bid'],
                    ask       = price['ask'],
                    spread    = price.get('spread', 0),
                    timestamp = dj_tz.now(),
                )

                # Broadcast to WebSocket subscribers
                broadcast_price_tick(symbol, {
                    'symbol':    symbol,
                    'bid':       price['bid'],
                    'ask':       price['ask'],
                    'mid':       price.get('mid', (price['bid'] + price['ask']) / 2),
                    'spread':    price.get('spread', 0),
                    'timestamp': dj_tz.now().isoformat(),
                })

            except Exception as e:
                logger.debug(f"Price stream error for {symbol}: {e}")

    except Exception as e:
        logger.error(f"stream_prices_for_bot failed: {e}")