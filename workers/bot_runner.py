# ============================================================
# Bot runner — entry point for the trading engine Celery task
# Also supports running a bot directly from the command line
# ============================================================
import os
import sys
import logging
import argparse

logger = logging.getLogger('trading')


def run_bot_direct(bot_id: str):
    """
    Run a bot directly (outside Celery) — useful for debugging.
    Usage: python workers/bot_runner.py --bot-id <uuid>
    """
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

    from services.trading_engine.engine import TradingEngine
    logger.info(f"Starting bot {bot_id} directly (no Celery)")
    engine = TradingEngine(bot_id=bot_id)
    engine.run()


def run_bot_via_celery(bot_id: str):
    """Queue the bot via Celery."""
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

    from workers.tasks import run_trading_bot
    task = run_trading_bot.apply_async(
        args=[bot_id], queue='trading'
    )
    print(f"Bot {bot_id} queued — task_id={task.id}")
    return task.id


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Forex Bot Runner')
    parser.add_argument('--bot-id', required=True, help='TradingBot UUID')
    parser.add_argument('--direct', action='store_true',
                        help='Run directly without Celery (for debugging)')
    args = parser.parse_args()

    if args.direct:
        run_bot_direct(args.bot_id)
    else:
        run_bot_via_celery(args.bot_id)