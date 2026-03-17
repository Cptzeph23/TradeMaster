from django.apps import AppConfig
 
 
class TradingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.trading'
 
    def ready(self):
        try:
            import apps.trading.signals  # noqa: F401
        except ImportError:
            pass
 