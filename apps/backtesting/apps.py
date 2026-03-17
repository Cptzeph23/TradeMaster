from django.apps import AppConfig
 
 
class BacktestingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.backtesting'
 
    def ready(self):
        try:
            import apps.backtesting.signals  # noqa: F401
        except ImportError:
            pass
