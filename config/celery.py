# ============================================================
# Celery application — full production configuration
# ============================================================
import os
from celery import Celery
from celery.schedules import crontab
from kombu import Queue, Exchange

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('forex_bot')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks([
    'apps.market_data',
    'apps.trading',
    'workers',
])

# ── Task Queues ──────────────────────────────────────────────
# Each queue maps to a different worker pool / priority
app.conf.task_queues = (
    Queue('default',     Exchange('default'),     routing_key='default',     queue_arguments={'x-max-priority': 5}),
    Queue('trading',     Exchange('trading'),     routing_key='trading',     queue_arguments={'x-max-priority': 10}),
    Queue('orders',      Exchange('orders'),      routing_key='orders',      queue_arguments={'x-max-priority': 10}),
    Queue('backtesting', Exchange('backtesting'), routing_key='backtesting', queue_arguments={'x-max-priority': 3}),
    Queue('data',        Exchange('data'),        routing_key='data',        queue_arguments={'x-max-priority': 5}),
    Queue('commands',    Exchange('commands'),    routing_key='commands',    queue_arguments={'x-max-priority': 7}),
)

app.conf.task_default_queue       = 'default'
app.conf.task_default_exchange    = 'default'
app.conf.task_default_routing_key = 'default'

# ── Task Routing ─────────────────────────────────────────────
app.conf.task_routes = {
    'workers.tasks.run_trading_bot':     {'queue': 'trading'},
    'workers.tasks.execute_order':       {'queue': 'orders'},
    'workers.tasks.process_nlp_command': {'queue': 'commands'},
    'workers.tasks.run_backtest':        {'queue': 'backtesting'},
    'workers.tasks.fetch_market_data':   {'queue': 'data'},
    'apps.market_data.tasks.fetch_and_cache_candles': {'queue': 'data'},
    'apps.market_data.tasks.fetch_all_active_symbols':{'queue': 'data'},
    'apps.market_data.tasks.purge_old_ticks':         {'queue': 'data'},
    'apps.market_data.tasks.sync_account_balance':    {'queue': 'default'},
}

# ── Beat Schedule (periodic tasks) ──────────────────────────
app.conf.beat_schedule = {

    TELEGRAM_BEAT_ENTRY = """
    # Telegram daily report (separate from email report)
    'telegram-daily-report': {
        'task':     'workers.tasks.send_telegram_daily_report',
        'schedule': crontab(hour=0, minute=5),   # 00:05 UTC
        'options':  {'queue': 'commands'},
    },
"""
 

    # ── Market data refresh ───────────────────────────────────
    # Fetch candles for all symbols used by running bots — every minute
    'fetch-active-symbols-every-minute': {
        'task':     'apps.market_data.tasks.fetch_all_active_symbols',
        'schedule': 60.0,   # seconds
        'options':  {'queue': 'data', 'expires': 55},
    },

    # ── Housekeeping ─────────────────────────────────────────
    # Purge live tick data older than 24h — runs every hour
    'purge-old-ticks-hourly': {
        'task':     'apps.market_data.tasks.purge_old_ticks',
        'schedule': crontab(minute=0),   # top of every hour
        'options':  {'queue': 'data'},
    },

    # ── Bot health check ──────────────────────────────────────
    # Restart any bots that crashed (status=running but no Celery task)
    'health-check-bots-every-5-minutes': {
        'task':     'workers.scheduler.health_check_bots',
        'schedule': crontab(minute='*/5'),
        'options':  {'queue': 'default'},
    },

    # ── Account balance sync ──────────────────────────────────
    # Sync balance/equity for all active trading accounts — every 15 min
    'sync-account-balances-15min': {
        'task':     'workers.scheduler.sync_all_account_balances',
        'schedule': crontab(minute='*/15'),
        'options':  {'queue': 'default'},
    },

    # ── Daily summary ─────────────────────────────────────────
    # Generate daily performance report at midnight UTC
    'daily-performance-report': {
        'task':     'workers.scheduler.generate_daily_report',
        'schedule': crontab(hour=0, minute=0),
        'options':  {'queue': 'default'},
    },

    # ── Pre-market data warm-up ────────────────────────────────
    # Pre-fetch H1/H4/D1 candles for major pairs at market open Sunday 22:00 UTC
    'pre-market-warmup': {
        'task':     'workers.scheduler.pre_market_warmup',
        'schedule': crontab(hour=22, minute=0, day_of_week=0),  # Sunday
        'options':  {'queue': 'data'},
    },
}

app.conf.beat_scheduler         = 'django_celery_beat.schedulers:DatabaseScheduler'
app.conf.timezone               = 'UTC'
app.conf.worker_prefetch_multiplier = 1    # fair dispatch — essential for long tasks
app.conf.task_acks_late         = True     # ack after completion, not before
app.conf.task_reject_on_worker_lost = True # requeue if worker dies mid-task


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Celery health check OK — worker={self.request.hostname}')