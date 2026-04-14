
import importlib
import logging
import traceback
from typing import Dict, Type
from .base import BaseStrategy

logger = logging.getLogger('trading')


class StrategyRegistry:
    _registry: Dict[str, Type[BaseStrategy]] = {}

    @classmethod
    def register(cls, slug: str):
        def decorator(strategy_cls: Type[BaseStrategy]):
            if not issubclass(strategy_cls, BaseStrategy):
                raise TypeError(f"{strategy_cls.__name__} must inherit from BaseStrategy")
            cls._registry[slug] = strategy_cls
            logger.debug(f"Strategy registered: '{slug}' → {strategy_cls.__name__}")
            return strategy_cls
        return decorator

    @classmethod
    def get(cls, slug: str) -> Type[BaseStrategy]:
        if slug not in cls._registry:
            raise KeyError(
                f"Strategy '{slug}' is not registered. "
                f"Available: {list(cls._registry.keys())}"
            )
        return cls._registry[slug]

    @classmethod
    def get_all(cls) -> Dict[str, Type[BaseStrategy]]:
        return dict(cls._registry)

    @classmethod
    def list_slugs(cls) -> list:
        return list(cls._registry.keys())

    @classmethod
    def exists(cls, slug: str) -> bool:
        return slug in cls._registry

    @classmethod
    def auto_discover(cls):
        """
        Import all plugin modules using relative-style dotted paths.
        Each module's @StrategyRegistry.register decorator fires on import.
        Errors are printed in full so misconfigured plugins are visible.
        """
        plugin_modules = [
            'apps.strategies.plugins.ma_crossover',
            'apps.strategies.plugins.rsi_reversal',
            'apps.strategies.plugins.breakout',
            'apps.strategies.plugins.mean_reversion',
            'apps.strategies.plugins.ichimoku',        
            'apps.strategies.plugins.macd_divergence',  
            'apps.strategies.plugins.stochastic',      
            'apps.strategies.plugins.ema_ribbon',       
            'apps.strategies.plugins.atr_breakout',    
            'apps.strategies.plugins.gold_xauusd',
        ]
        for module_path in plugin_modules:
            try:
                importlib.import_module(module_path)
                logger.info(f"Strategy plugin loaded: {module_path}")
            except Exception:
                # Print the FULL traceback so plugin errors are visible
                logger.error(
                    f"FAILED to load strategy plugin '{module_path}':\n"
                    + traceback.format_exc()
                )


    @classmethod
    def get_schema_list(cls) -> list:
        result = []
        for slug, strategy_cls in cls._registry.items():
            try:
               
                inst = strategy_cls()
                
                
                result.append({
                    'slug':               slug,
                    'name':               strategy_cls.name,
                    'version':            strategy_cls.version,
                    'description':        strategy_cls.description,
                    'default_parameters': inst.get_default_parameters(),  # Changed from strategy_cls
                    'parameter_schema':   inst.get_parameter_schema(),    # Changed from strategy_cls
                    'required_candles':   inst.get_required_candles(),
                })
            except Exception as e:
               
                logger.error(f"Failed to generate schema for '{slug}': {str(e)}")
                continue 
        return result