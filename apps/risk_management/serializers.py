# ============================================================
# ============================================================
from rest_framework import serializers
from .models import RiskRule, DrawdownEvent
from .calculator import RiskCalculator


class RiskRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RiskRule
        fields = (
            'id', 'bot',
            # Position sizing
            'risk_percent', 'max_lot_size', 'min_lot_size',
            # SL / TP
            'stop_loss_pips', 'take_profit_pips',
            'risk_reward_ratio', 'use_risk_reward',
            # Trailing stop
            'trailing_stop_enabled', 'trailing_stop_pips', 'trailing_step_pips',
            # Daily limits
            'max_trades_per_day', 'max_daily_loss', 'max_daily_profit',
            # Drawdown
            'max_drawdown_percent', 'drawdown_pause_percent',
            # Position limits
            'max_open_trades', 'max_trades_per_symbol',
            # Filters
            'max_spread_pips',
            'trade_start_hour', 'trade_end_hour',
            'avoid_news_events', 'news_buffer_minutes',
            # Timestamps
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'bot', 'created_at', 'updated_at')

    def validate(self, attrs):
        # Ensure risk_percent is sensible
        rp = attrs.get('risk_percent', 1.0)
        if not 0.01 <= rp <= 10.0:
            raise serializers.ValidationError(
                {'risk_percent': 'Must be between 0.01 and 10.0'}
            )
        # Ensure SL is set
        sl = attrs.get('stop_loss_pips', 50)
        if sl < 1:
            raise serializers.ValidationError(
                {'stop_loss_pips': 'Must be at least 1 pip'}
            )
        return attrs


class RiskRuleUpdateSerializer(serializers.ModelSerializer):
    """Allows partial updates to risk rules."""
    class Meta:
        model   = RiskRule
        exclude = ('bot',)
        read_only_fields = ('id', 'created_at', 'updated_at')


class DrawdownEventSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DrawdownEvent
        fields = (
            'id', 'bot', 'event_type',
            'drawdown_percent', 'balance_at_event',
            'peak_balance', 'triggered_by', 'notes', 'timestamp',
        )
        read_only_fields = fields


class RiskAnalysisSerializer(serializers.Serializer):
    """
    Computed risk analysis for a bot — returned by the
    GET /api/v1/risk/bots/<id>/analysis/ endpoint.
    """
    bot_id              = serializers.UUIDField()
    bot_name            = serializers.CharField()
    current_drawdown    = serializers.FloatField()
    peak_balance        = serializers.FloatField()
    current_balance     = serializers.FloatField()
    daily_pnl           = serializers.FloatField()
    daily_trades        = serializers.IntegerField()
    open_trades         = serializers.IntegerField()
    win_rate            = serializers.FloatField()
    profit_factor       = serializers.FloatField()
    sharpe_ratio        = serializers.FloatField()
    expectancy          = serializers.FloatField()
    rules               = RiskRuleSerializer()
    drawdown_events     = DrawdownEventSerializer(many=True)
    alerts              = serializers.ListField(child=serializers.DictField())


class LotSizeCalculatorSerializer(serializers.Serializer):
    """Input for the lot size calculator endpoint."""
    account_balance  = serializers.FloatField(min_value=1)
    risk_percent     = serializers.FloatField(min_value=0.01, max_value=10)
    stop_loss_pips   = serializers.FloatField(min_value=1)
    symbol           = serializers.CharField(max_length=20)

    def calculate(self) -> dict:
        data     = self.validated_data
        lot_size = RiskCalculator.lot_size(
            account_balance  = data['account_balance'],
            risk_percent     = data['risk_percent'],
            stop_loss_pips   = data['stop_loss_pips'],
            symbol           = data['symbol'],
        )
        risk_amount = RiskCalculator.risk_amount(
            data['account_balance'], data['risk_percent']
        )
        return {
            'lot_size':     lot_size,
            'risk_amount':  risk_amount,
            'risk_percent': data['risk_percent'],
            'units':        int(lot_size * 100_000),
        }