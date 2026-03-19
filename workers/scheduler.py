# ============================================================
# Periodic Celery Beat tasks — health checks, syncs, reports
# ============================================================
import logging
from celery import shared_task
from django.utils import timezone as dj_tz

logger = logging.getLogger('trading')


@shared_task(name='workers.scheduler.health_check_bots')
def health_check_bots():
    """
    Runs every 5 minutes.
    Finds bots with status=RUNNING but whose Celery task
    is no longer active (worker crashed, OOM, etc.)
    and restarts them automatically.
    """
    from apps.trading.models import TradingBot
    from utils.constants import BotStatus
    from config.celery import app as celery_app

    running_bots = TradingBot.objects.filter(
        status=BotStatus.RUNNING,
        is_active=True,
    ).exclude(celery_task_id='')

    restarted = 0
    for bot in running_bots:
        try:
            # Check if the Celery task is still active
            inspect = celery_app.control.inspect(timeout=2)
            active  = inspect.active() or {}

            task_alive = any(
                task['id'] == bot.celery_task_id
                for worker_tasks in active.values()
                for task in worker_tasks
            )

            if not task_alive:
                logger.warning(
                    f"Bot '{bot.name}' (id={bot.id}) has status=RUNNING "
                    f"but task {bot.celery_task_id} is not active — restarting"
                )
                _restart_bot(bot)
                restarted += 1

        except Exception as e:
            logger.error(f"health_check_bots error for bot {bot.id}: {e}")

    logger.info(f"health_check_bots: checked {running_bots.count()} bots, restarted {restarted}")
    return {'checked': running_bots.count(), 'restarted': restarted}


def _restart_bot(bot):
    """Re-queue a bot's Celery task after a crash."""
    from workers.tasks import run_trading_bot
    from utils.constants import BotStatus

    task = run_trading_bot.apply_async(
        args  = [str(bot.id)],
        queue = 'trading',
    )
    bot.celery_task_id = task.id
    bot.save(update_fields=['celery_task_id'])
    logger.info(f"Bot '{bot.name}' restarted — new task_id={task.id}")


@shared_task(name='workers.scheduler.sync_all_account_balances')
def sync_all_account_balances():
    """
    Runs every 15 minutes.
    Syncs balance/equity/margin for all active, verified broker accounts.
    """
    from apps.accounts.models import TradingAccount
    from apps.market_data.tasks import sync_account_balance

    accounts = TradingAccount.objects.filter(
        is_active=True, is_verified=True
    ).values_list('id', flat=True)

    queued = 0
    for account_id in accounts:
        try:
            sync_account_balance.apply_async(
                args=[str(account_id)],
                queue='default',
            )
            queued += 1
        except Exception as e:
            logger.error(f"sync_all_account_balances: failed for {account_id}: {e}")

    logger.info(f"sync_all_account_balances: queued {queued} sync tasks")
    return {'queued': queued}


@shared_task(name='workers.scheduler.generate_daily_report')
def generate_daily_report():
    """
    Runs at midnight UTC daily.
    Generates a performance summary for each user with active bots.
    Sends email if email_alerts is enabled in their profile.
    """
    from apps.trading.models import TradingBot, Trade
    from apps.accounts.models import User
    from utils.constants import BotStatus, TradeStatus
    from datetime import datetime, timezone, timedelta
    from django.core.mail import send_mail
    from django.conf import settings

    yesterday_start = (dj_tz.now() - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    yesterday_end   = yesterday_start + timedelta(days=1)

    users_with_bots = User.objects.filter(
        bots__is_active=True
    ).distinct()

    reports_sent = 0

    for user in users_with_bots:
        try:
            # Yesterday's trades
            trades = Trade.objects.filter(
                bot__user   = user,
                opened_at__gte = yesterday_start,
                opened_at__lt  = yesterday_end,
                status      = TradeStatus.CLOSED,
            )

            total_trades = trades.count()
            if total_trades == 0:
                continue

            pnl_list    = [float(t.profit_loss or 0) for t in trades]
            total_pnl   = sum(pnl_list)
            winners     = sum(1 for p in pnl_list if p > 0)
            win_rate    = round(winners / total_trades * 100, 1) if total_trades else 0

            running_bots = TradingBot.objects.filter(
                user=user, status=BotStatus.RUNNING, is_active=True
            ).count()

            # Send email if alerts enabled
            if (hasattr(user, 'profile') and
                    user.profile.email_alerts and
                    user.profile.email_on_trade):

                subject = (
                    f"Forex Bot Daily Report — "
                    f"{'📈' if total_pnl >= 0 else '📉'} "
                    f"{'+'if total_pnl >= 0 else ''}{total_pnl:.2f} USD"
                )
                body = (
                    f"Daily Trading Summary — {yesterday_start.strftime('%Y-%m-%d')}\n"
                    f"{'='*45}\n"
                    f"Total Trades:    {total_trades}\n"
                    f"Win Rate:        {win_rate}%\n"
                    f"Total P&L:       ${total_pnl:+.2f}\n"
                    f"Running Bots:    {running_bots}\n"
                    f"{'='*45}\n\n"
                    f"Log in to your dashboard for full details.\n"
                )
                send_mail(
                    subject    = subject,
                    message    = body,
                    from_email = settings.DEFAULT_FROM_EMAIL,
                    recipient_list = [user.email],
                    fail_silently  = True,
                )
                reports_sent += 1

        except Exception as e:
            logger.error(f"generate_daily_report error for user {user.id}: {e}")

    logger.info(f"generate_daily_report: sent {reports_sent} reports")
    return {'reports_sent': reports_sent}


@shared_task(name='workers.scheduler.pre_market_warmup')
def pre_market_warmup():
    """
    Runs Sunday 22:00 UTC (forex market open).
    Pre-fetches candle data for all major pairs on H1, H4, D1
    so the first tick of the week has data ready in Redis.
    """
    from apps.market_data.tasks import fetch_and_cache_candles
    from utils.constants import MAJOR_FOREX_PAIRS

    pairs      = MAJOR_FOREX_PAIRS
    timeframes = ['H1', 'H4', 'D1']
    queued     = 0

    for symbol in pairs:
        for tf in timeframes:
            try:
                fetch_and_cache_candles.apply_async(
                    args  = [symbol, tf, 500, 'oanda'],
                    queue = 'data',
                )
                queued += 1
            except Exception as e:
                logger.error(f"pre_market_warmup: failed {symbol}/{tf}: {e}")

    logger.info(f"pre_market_warmup: queued {queued} fetch tasks")
    return {'queued': queued}