# ============================================================
# serializers.py
# DRF serializers for market data API
# ============================================================
from rest_framework import serializers
from .models import MarketData, LiveTick, DataFetchLog


class MarketDataSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MarketData
        fields = (
            'id', 'symbol', 'timeframe', 'broker', 'timestamp',
            'open', 'high', 'low', 'close', 'volume', 'is_complete',
        )
        read_only_fields = fields


class LivePriceSerializer(serializers.Serializer):
    symbol  = serializers.CharField()
    bid     = serializers.FloatField()
    ask     = serializers.FloatField()
    mid     = serializers.FloatField()
    spread  = serializers.FloatField()
    time    = serializers.CharField(allow_null=True)


class CandleRequestSerializer(serializers.Serializer):
    symbol    = serializers.CharField()
    timeframe = serializers.CharField(default='H1')
    count     = serializers.IntegerField(default=200, min_value=10, max_value=5000)
    broker    = serializers.CharField(default='oanda')
    refresh   = serializers.BooleanField(default=False)


class DataFetchLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DataFetchLog
        fields = (
            'id', 'symbol', 'timeframe', 'broker', 'source',
            'fetch_from', 'fetch_to', 'candles_fetched',
            'success', 'error_msg', 'created_at',
        )
        read_only_fields = fields