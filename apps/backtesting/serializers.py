# ============================================================
# ============================================================
from rest_framework import serializers
from .models import BacktestResult, BacktestTrade
from apps.strategies.models import Strategy
from utils.constants import Timeframe, BacktestStatus


class BacktestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BacktestResult
        fields = (
            'strategy', 'symbol', 'timeframe',
            'start_date', 'end_date',
            'initial_balance', 'commission_per_lot', 'spread_pips',
            'name',
        )

    def validate_strategy(self, value):
        user = self.context['request'].user
        if value.user != user and not value.is_public:
            raise serializers.ValidationError(
                "You don't have access to this strategy."
            )
        return value

    def validate(self, attrs):
        if attrs['start_date'] >= attrs['end_date']:
            raise serializers.ValidationError(
                {'start_date': 'start_date must be before end_date.'}
            )
        # Max 5-year range
        delta = attrs['end_date'] - attrs['start_date']
        if delta.days > 365 * 5:
            raise serializers.ValidationError(
                'Date range cannot exceed 5 years.'
            )
        return attrs

    def create(self, validated_data):
        user     = self.context['request'].user
        strategy = validated_data['strategy']
        # Snapshot parameters at time of backtest
        validated_data['parameters_snapshot'] = {
            **strategy.parameters,
            'risk_percent':     1.0,
            'stop_loss_pips':   50,
            'take_profit_pips': 100,
        }
        validated_data['user'] = user
        return BacktestResult.objects.create(**validated_data)


class BacktestResultSerializer(serializers.ModelSerializer):
    strategy_name  = serializers.CharField(source='strategy.name', read_only=True)
    duration_secs  = serializers.IntegerField(source='duration_seconds', read_only=True)

    class Meta:
        model  = BacktestResult
        fields = (
            'id', 'name', 'strategy', 'strategy_name',
            'symbol', 'timeframe', 'start_date', 'end_date',
            'initial_balance', 'final_balance',
            'commission_per_lot', 'spread_pips',
            'status', 'progress', 'error_message',
            'metrics', 'equity_curve',
            'duration_secs', 'started_at', 'completed_at', 'created_at',
        )
        read_only_fields = (
            'id', 'status', 'progress', 'error_message',
            'metrics', 'equity_curve', 'final_balance',
            'started_at', 'completed_at', 'created_at',
        )


class BacktestResultSummarySerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views — no equity curve."""
    strategy_name = serializers.CharField(source='strategy.name', read_only=True)

    class Meta:
        model  = BacktestResult
        fields = (
            'id', 'name', 'strategy_name', 'symbol', 'timeframe',
            'start_date', 'end_date', 'initial_balance', 'final_balance',
            'status', 'progress', 'metrics', 'created_at',
        )
        read_only_fields = fields


class BacktestTradeSerializer(serializers.ModelSerializer):
    is_winner = serializers.BooleanField(read_only=True)
    duration_hours = serializers.FloatField(read_only=True)

    class Meta:
        model  = BacktestTrade
        fields = (
            'id', 'trade_index', 'symbol', 'order_type',
            'entry_price', 'exit_price', 'stop_loss', 'take_profit',
            'lot_size', 'profit_loss', 'profit_pips',
            'exit_reason', 'indicators',
            'is_winner', 'duration_hours',
            'entry_time', 'exit_time',
        )
        read_only_fields = fields