# ============================================================
# Strategy plugin registry — auto-discovers all strategy classes
# ============================================================
import importlib
import logging
from typing import Dict, Type
from .base import BaseStrategy

logger = logging.getLogger('trading')


class StrategyRegistry:
    """
    Singleton registry that maps strategy type slugs to their
    plugin classes.

    Strategies are registered either:
      1. Automatically via auto_discover() at app startup
      2. Manually via @StrategyRegistry.register decorator

    Usage:
        cls   = StrategyRegistry.get('ma_crossover')
        inst  = cls(parameters={'fast_period': 50, 'slow_period': 200})
        signal = inst.generate_signal(df, 'EUR_USD')
    """
    _registry: Dict[str, Type[BaseStrategy]] = {}

    @classmethod
    def register(cls, slug: str):
        """
        Decorator to register a strategy class under a slug.

        @StrategyRegistry.register('ma_crossover')
        class MACrossoverStrategy(BaseStrategy):
            ...
        """
        def decorator(strategy_cls: Type[BaseStrategy]):
            if not issubclass(strategy_cls, BaseStrategy):
                raise TypeError(
                    f"{strategy_cls.__name__} must inherit from BaseStrategy"
                )
            cls._registry[slug] = strategy_cls
            logger.debug(f"Strategy registered: '{slug}' → {strategy_cls.__name__}")
            return strategy_cls
        return decorator

    @classmethod
    def get(cls, slug: str) -> Type[BaseStrategy]:
        """Retrieve a strategy class by slug. Raises KeyError if not found."""
        if slug not in cls._registry:
            raise KeyError(
                f"Strategy '{slug}' is not registered. "
                f"Available: {list(cls._registry.keys())}"
            )
        return cls._registry[slug]

    @classmethod
    def get_all(cls) -> Dict[str, Type[BaseStrategy]]:
        """Return all registered strategies."""
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
        Import all strategy plugin modules so their @register
        decorators fire and populate the registry.
        Called once from StrategiesConfig.ready().
        """
        plugin_modules = [
            'apps.strategies.plugins.ma_crossover',
            'apps.strategies.plugins.rsi_reversal',
            'apps.strategies.plugins.breakout',
            'apps.strategies.plugins.mean_reversion',
        ]
        for module_path in plugin_modules:
            try:
                importlib.import_module(module_path)
                logger.info(f"Strategy plugin loaded: {module_path}")
            except ImportError as e:
                logger.error(f"Failed to load strategy plugin {module_path}: {e}")

    @classmethod
    def get_schema_list(cls) -> list:
        """
        Return a list of dicts describing all registered strategies.
        Used by the API to populate the strategy selection UI.
        """
        result = []
        for slug, strategy_cls in cls._registry.items():
            result.append({
                'slug':               slug,
                'name':               strategy_cls.name,
                'version':            strategy_cls.version,
                'description':        strategy_cls.description,
                'default_parameters': strategy_cls.get_default_parameters(),
                'parameter_schema':   strategy_cls.get_parameter_schema(),
                'required_candles':   strategy_cls().get_required_candles(),
            })
        return result

    def __repr__(self):
        return f"<StrategyRegistry strategies={self.list_slugs()}>"