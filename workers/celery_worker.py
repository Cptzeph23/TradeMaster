# ============================================================
# Celery worker entry point and configuration helpers
# ============================================================
import os
import logging

logger = logging.getLogger('trading')

# Import the Celery app so this module can be used as entry point
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from config.celery import app  # noqa: F401 — exposes 'app' for celery CLI


def get_worker_config(queue: str) -> dict:
    """
    Returns recommended worker config per queue type.
    Used by Supervisor config generator.
    """
    configs = {
        'trading': {
            'concurrency':  4,
            'max_tasks_per_child': 50,
            'prefetch_multiplier': 1,
            'description': 'Long-running bot loops',
        },
        'orders': {
            'concurrency':  8,
            'max_tasks_per_child': 200,
            'prefetch_multiplier': 1,
            'description': 'Fast order execution — low latency critical',
        },
        'data': {
            'concurrency':  4,
            'max_tasks_per_child': 100,
            'prefetch_multiplier': 2,
            'description': 'Market data fetching',
        },
        'backtesting': {
            'concurrency':  2,
            'max_tasks_per_child': 10,
            'prefetch_multiplier': 1,
            'description': 'CPU-intensive backtesting',
        },
        'commands': {
            'concurrency':  4,
            'max_tasks_per_child': 100,
            'prefetch_multiplier': 1,
            'description': 'NLP command processing',
        },
        'default': {
            'concurrency':  4,
            'max_tasks_per_child': 100,
            'prefetch_multiplier': 2,
            'description': 'General tasks',
        },
    }
    return configs.get(queue, configs['default'])