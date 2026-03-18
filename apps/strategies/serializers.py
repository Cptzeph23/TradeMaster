
from rest_framework import serializers
from .models import Strategy
from .registry import StrategyRegistry
from utils.constants import StrategyType, Timeframe


class StrategySerializer(serializers.ModelSerializer):
    win_rate       = serializers.FloatField(source='last_win_rate',      read_only=True)
    profit_factor  = serializers.FloatField(source='last_profit_factor', read_only=True)
    sharpe         = serializers.FloatField(source='last_sharpe',        read_only=True)
    plugin_available = serializers.SerializerMethodField()

    class Meta:
        model  = Strategy
        fields = (
            'id', 'name', 'description', 'strategy_type', 'plugin_path',
            'parameters', 'symbols', 'timeframe',
            'is_active', 'is_public',
            'win_rate', 'profit_factor', 'sharpe', 'backtest_count',
            'plugin_available', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'backtest_count', 'win_rate', 'profit_factor',
            'sharpe', 'created_at', 'updated_at',
        )

    def get_plugin_available(self, obj) -> bool:
        return StrategyRegistry.exists(obj.strategy_type)


class StrategyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Strategy
        fields = (
            'name', 'description', 'strategy_type',
            'parameters', 'symbols', 'timeframe',
            'is_active', 'is_public',
        )

    def validate_strategy_type(self, value):
        if not StrategyRegistry.exists(value):
            raise serializers.ValidationError(
                f"Strategy type '{value}' has no registered plugin. "
                f"Available: {StrategyRegistry.list_slugs()}"
            )
        return value

    def validate(self, attrs):
        strategy_type = attrs.get('strategy_type')
        parameters    = attrs.get('parameters', {})
        if strategy_type and StrategyRegistry.exists(strategy_type):
            cls = StrategyRegistry.get(strategy_type)
            try:
                cls(parameters=parameters)   # triggers validate_parameters()
            except ValueError as e:
                raise serializers.ValidationError({'parameters': str(e)})
        return attrs

    def create(self, validated_data):
        strategy_type = validated_data['strategy_type']
        # Auto-set the plugin_path from the registry
        cls = StrategyRegistry.get(strategy_type)
        validated_data['plugin_path'] = f"{cls.__module__}.{cls.__name__}"
        validated_data['user'] = self.context['request'].user
        return Strategy.objects.create(**validated_data)


class StrategyPluginListSerializer(serializers.Serializer):
    """Lists all available strategy plugins from the registry."""
    slug               = serializers.CharField()
    name               = serializers.CharField()
    version            = serializers.CharField()
    description        = serializers.CharField()
    default_parameters = serializers.DictField()
    parameter_schema   = serializers.DictField()
    required_candles   = serializers.IntegerField()