# ============================================================
# TradingBot, Trade, BotLog, NLPCommand serializers
# ============================================================
from rest_framework import serializers
from .models import TradingBot, Trade, BotLog, NLPCommand
from apps.strategies.models import Strategy
from apps.accounts.models import TradingAccount
from utils.constants import BotStatus, Timeframe


class TradingBotCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = TradingBot
        fields = (
            'name', 'description', 'trading_account', 'strategy',
            'broker', 'symbols', 'timeframe', 'risk_settings',
            'allow_buy', 'allow_sell',
        )

    def validate_trading_account(self, value):
        if value.user != self.context['request'].user:
            raise serializers.ValidationError("You don't own this trading account.")
        if not value.is_active:
            raise serializers.ValidationError("Trading account is inactive.")
        return value

    def validate_strategy(self, value):
        user = self.context['request'].user
        if value.user != user and not value.is_public:
            raise serializers.ValidationError("You don't have access to this strategy.")
        return value

    def validate(self, attrs):
        user     = self.context['request'].user
        existing = TradingBot.objects.filter(user=user, is_active=True).count()
        from django.conf import settings
        if existing >= getattr(settings, 'MAX_BOTS_PER_USER', 10):
            raise serializers.ValidationError(
                f"Maximum {settings.MAX_BOTS_PER_USER} bots allowed per user."
            )
        return attrs

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        # Set broker from trading account
        if 'trading_account' in validated_data and 'broker' not in validated_data:
            validated_data['broker'] = validated_data['trading_account'].broker
        return TradingBot.objects.create(**validated_data)


class TradingBotSerializer(serializers.ModelSerializer):
    strategy_name   = serializers.CharField(source='strategy.name',            read_only=True)
    account_name    = serializers.CharField(source='trading_account.name',     read_only=True)
    win_rate        = serializers.FloatField(read_only=True)
    open_trades     = serializers.SerializerMethodField()

    class Meta:
        model  = TradingBot
        fields = (
            'id', 'name', 'description', 'strategy', 'strategy_name',
            'trading_account', 'account_name', 'broker',
            'symbols', 'timeframe', 'risk_settings', 'status',
            'allow_buy', 'allow_sell', 'error_message',
            'total_trades', 'winning_trades', 'win_rate',
            'total_profit_loss', 'current_drawdown', 'peak_balance',
            'open_trades', 'celery_task_id',
            'started_at', 'stopped_at', 'last_signal_at',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'status', 'error_message', 'celery_task_id',
            'total_trades', 'winning_trades', 'total_profit_loss',
            'current_drawdown', 'peak_balance',
            'started_at', 'stopped_at', 'last_signal_at',
            'created_at', 'updated_at',
        )

    def get_open_trades(self, obj) -> int:
        return obj.trades.filter(status='open').count()


class TradeSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.IntegerField(read_only=True)
    is_profitable    = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Trade
        fields = (
            'id', 'bot', 'symbol', 'order_type', 'status',
            'lot_size', 'units', 'entry_price', 'exit_price',
            'stop_loss', 'take_profit', 'profit_loss', 'profit_loss_pips',
            'commission', 'swap', 'signal_data',
            'broker_order_id', 'broker_trade_id',
            'is_profitable', 'duration_seconds',
            'opened_at', 'closed_at', 'created_at',
        )
        read_only_fields = fields


class BotLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BotLog
        fields = (
            'id', 'bot', 'trade', 'level', 'event_type',
            'message', 'data', 'timestamp',
        )
        read_only_fields = fields


class NLPCommandSerializer(serializers.ModelSerializer):
    class Meta:
        model  = NLPCommand
        fields = (
            'id', 'bot', 'raw_command', 'command_type',
            'parsed_intent', 'ai_explanation', 'confidence',
            'status', 'execution_result', 'error_detail',
            'model_used', 'tokens_used',
            'created_at', 'executed_at',
        )
        read_only_fields = (
            'id', 'command_type', 'parsed_intent', 'ai_explanation',
            'confidence', 'status', 'execution_result', 'error_detail',
            'model_used', 'tokens_used', 'created_at', 'executed_at',
        )


class NLPCommandCreateSerializer(serializers.Serializer):
    """Input serializer for submitting a natural language command."""
    command  = serializers.CharField(
        max_length = 1000,
        help_text  = "Natural language trading command, e.g. "
                     "'Set stop loss to 30 pips and only trade EUR/USD'"
    )
    bot_id   = serializers.UUIDField(
        required  = False,
        allow_null = True,
        help_text  = "Target bot UUID. Null = applies to all bots."
    )