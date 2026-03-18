from django.apps import AppConfig
 
 
class StrategiesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name               = 'apps.strategies'
    verbose_name       = 'Strategies'
 
    def ready(self):
        # Load all plugin modules so @StrategyRegistry.register decorators fire
        from apps.strategies.registry import StrategyRegistry
        StrategyRegistry.auto_discover()
 
        import apps.strategies.signals  # noqa: F401
 