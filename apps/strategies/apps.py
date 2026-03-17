from django.apps import AppConfig
 
 
class StrategiesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.strategies'
 
    def ready(self):
        try:
            import apps.strategies.signals  # noqa: F401
        except ImportError:
            pass
 