# ============================================================
# Celery tasks for periodic market data fetching and maintenance
# ============================================================
import logging
from datetime import datetime, timezone, timedelta
from celery import shared_task
from django.conf import settings

logger = logging.getLogger('market_data')


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_and_cache_candles(
    self,
    symbol: str,
    timeframe: str,
    count: int = 500,
    broker: str = 'oanda',
):
    """
    Celery task: fetch latest candles from broker and store in
    both PostgreSQL and Redis cache.

    Called by:
      - Periodic beat schedule (every N minutes per timeframe)
      - Bot runner before each signal check
      - Manual API trigger from dashboard
    """
    try:
        from services.data_feed.feed_manager import FeedManager
        from services.data_feed.normalizer import CandleNormalizer
        from apps.market_data.cache import _save_to_db, _set_cache, _cache_key
        from apps.market_data.models import DataFetchLog

        start = datetime.now(timezone.utc)
        raw   = FeedManager.fetch_candles(symbol, timeframe, count, broker)

        if not raw:
            logger.warning(f"fetch_and_cache_candles: no data returned for {symbol}/{timeframe}")
            return {'success': False, 'reason': 'no_data'}

        df = CandleNormalizer.normalize(raw, symbol=symbol, timeframe=timeframe)

        if df.empty:
            return {'success': False, 'reason': 'normalization_failed'}

        # Save to DB
        _save_to_db(df, symbol, timeframe, broker)

        # Update Redis cache
        key = _cache_key(symbol, timeframe, count)
        from apps.market_data.cache import _serialize
        from django.core.cache import cache
        from apps.market_data.cache import CACHE_TTL, DEFAULT_TTL
        ttl = CACHE_TTL.get(timeframe, DEFAULT_TTL)
        cache.set(key, _serialize(df), timeout=ttl)

        # Log the fetch
        DataFetchLog.objects.create(
            symbol          = symbol,
            timeframe       = timeframe,
            broker          = broker,
            source          = broker,
            fetch_from      = df.index[0],
            fetch_to        = df.index[-1],
            candles_fetched = len(df),
            success         = True,
        )

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        logger.info(
            f"fetch_and_cache_candles: {symbol}/{timeframe} "
            f"{len(df)} candles in {elapsed:.2f}s"
        )
        return {
            'success':  True,
            'symbol':   symbol,
            'timeframe':timeframe,
            'candles':  len(df),
            'elapsed':  elapsed,
        }

    except Exception as exc:
        logger.error(f"fetch_and_cache_candles failed: {exc}", exc_info=True)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            from apps.market_data.models import DataFetchLog
            DataFetchLog.objects.create(
                symbol=symbol, timeframe=timeframe, broker=broker,
                source=broker,
                fetch_from=datetime.now(timezone.utc),
                fetch_to=datetime.now(timezone.utc),
                candles_fetched=0,
                success=False,
                error_msg=str(exc),
            )
            return {'success': False, 'error': str(exc)}


@shared_task
def fetch_all_active_symbols():
    """
    Periodic task: fetch candles for all symbols used by running bots.
    Scheduled every minute by Celery Beat (configured in Phase I).
    """
    try:
        from apps.trading.models import TradingBot
        from utils.constants import BotStatus

        running_bots = TradingBot.objects.filter(
            status=BotStatus.RUNNING, is_active=True
        ).values('symbols', 'timeframe', 'broker')

        tasks_queued = 0
        seen = set()

        for bot in running_bots:
            broker    = bot['broker']
            timeframe = bot['timeframe']
            for symbol in (bot['symbols'] or []):
                key = f"{symbol}:{timeframe}:{broker}"
                if key not in seen:
                    seen.add(key)
                    fetch_and_cache_candles.apply_async(
                        args=[symbol, timeframe, 200, broker],
                        queue='data',
                    )
                    tasks_queued += 1

        logger.info(f"fetch_all_active_symbols: queued {tasks_queued} fetch tasks")
        return {'tasks_queued': tasks_queued}

    except Exception as e:
        logger.error(f"fetch_all_active_symbols failed: {e}", exc_info=True)
        return {'error': str(e)}


@shared_task
def purge_old_ticks():
    """
    Periodic task: delete LiveTick rows older than 24 hours.
    Prevents the live_tick table from growing unbounded.
    Scheduled to run every hour.
    """
    try:
        from apps.market_data.models import LiveTick
        cutoff  = datetime.now(timezone.utc) - timedelta(hours=24)
        deleted, _ = LiveTick.objects.filter(timestamp__lt=cutoff).delete()
        logger.info(f"purge_old_ticks: deleted {deleted} old tick records")
        return {'deleted': deleted}
    except Exception as e:
        logger.error(f"purge_old_ticks failed: {e}")
        return {'error': str(e)}


@shared_task
def sync_account_balance(trading_account_id: str):
    """
    Fetch latest balance/equity from broker and update TradingAccount.
    Called after every trade close.
    """
    try:
        from apps.accounts.models import TradingAccount
        from django.utils import timezone as dj_tz

        account = TradingAccount.objects.get(pk=trading_account_id, is_active=True)
        api_key = account.get_api_key()

        if account.broker == 'oanda':
            from services.broker_api.oanda import OandaBroker
            broker = OandaBroker(
                api_key     = api_key,
                account_id  = account.account_id,
                environment = account.account_type,
            )
        else:
            logger.warning(f"sync_account_balance: unsupported broker {account.broker}")
            return

        info = broker.get_account_info()
        account.balance     = info['balance']
        account.equity      = info['equity']
        account.margin_used = info['margin_used']
        account.margin_free = info['margin_free']
        account.last_synced = dj_tz.now()
        account.save(update_fields=['balance','equity','margin_used','margin_free','last_synced'])

        logger.info(f"Account {account.name} synced: balance={info['balance']}")
        return info

    except Exception as e:
        logger.error(f"sync_account_balance failed: {e}", exc_info=True)
        return {'error': str(e)}