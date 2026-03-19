from django.apps import AppConfig
 
 
class BacktestingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name               = 'apps.backtesting'
    verbose_name       = 'Backtesting'
 
    def ready(self):
        try:
            import apps.backtesting.signals  # noqa: F401
        except ImportError:
            pass
 