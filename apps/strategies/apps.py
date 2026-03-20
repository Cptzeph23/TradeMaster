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
        plugins = [
            # Phase D originals
            '.plugins.ma_crossover',
            '.plugins.rsi_reversal',
            '.plugins.breakout',
            '.plugins.mean_reversion',
            # Phase N additions
            '.plugins.ichimoku',
            '.plugins.macd_divergence',
            '.plugins.stochastic',
            '.plugins.ema_ribbon',
            '.plugins.atr_breakout',
        ]
 
        for plugin in plugins:
            try:
                from django.apps import apps
                app = apps.get_app_config('strategies')
                __import__(f'apps.strategies{plugin}', fromlist=['_'])
                logger.info(f"Strategy plugin loaded: apps.strategies{plugin}")
            except Exception as e:
                logger.error(f"Failed to load strategy plugin {plugin}: {e}")
 