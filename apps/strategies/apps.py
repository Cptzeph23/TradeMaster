from django.apps import AppConfig
import logging
 
logger = logging.getLogger('trading')
 
 
class StrategiesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name               = 'apps.strategies'
    verbose_name       = 'Trading Strategies'
 
    def ready(self):
        """
        Import all strategy plugins so they register themselves
        via @StrategyRegistry.register() decorator.
        """
        try:
            from .registry import StrategyRegistry
            StrategyRegistry.auto_discover()
        except Exception as e:
            logger.error(f"Failed to auto-discover strategy plugins: {e}")
 
