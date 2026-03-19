
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
            except Exception:
                inst = None
            result.append({
                'slug':               slug,
                'name':               strategy_cls.name,
                'version':            strategy_cls.version,
                'description':        strategy_cls.description,
                'default_parameters': strategy_cls.get_default_parameters(),
                'parameter_schema':   strategy_cls.get_parameter_schema(),
                'required_candles':   inst.get_required_candles() if inst else 0,
            })
        return result