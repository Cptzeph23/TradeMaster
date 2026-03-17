# ============================================================
# DESTINATION: /opt/forex_bot/config/celery.py
# Celery Application Configuration
# ============================================================
import os
from celery import Celery
from celery.signals import setup_logging
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('forex_bot')

# Load config from Django settings, namespace='CELERY'
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# ── Define task queues ───────────────────────────────────────
from kombu import Queue, Exchange

app.conf.task_queues = (
    Queue('default',    Exchange('default'),    routing_key='default'),
    Queue('trading',    Exchange('trading'),    routing_key='trading'),
    Queue('orders',     Exchange('orders'),     routing_key='orders'),
    Queue('backtesting',Exchange('backtesting'),routing_key='backtesting'),
    Queue('data',       Exchange('data'),       routing_key='data'),
    Queue('commands',   Exchange('commands'),   routing_key='commands'),
)

app.conf.task_default_queue = 'default'
app.conf.task_default_exchange = 'default'
app.conf.task_default_routing_key = 'default'

# ── Beat Schedule (populated further in Phase I) ─────────────
app.conf.beat_schedule = {}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Celery health-check task."""
    print(f'Request: {self.request!r}')
