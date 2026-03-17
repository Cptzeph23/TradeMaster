# ============================================================
# market_data/admin.py
# Admin interface for MarketData, LiveTick, and DataFetchLog models
# ============================================================
from django.contrib import admin
from .models import MarketData, LiveTick, DataFetchLog


@admin.register(MarketData)
class MarketDataAdmin(admin.ModelAdmin):
    list_display    = ('symbol', 'timeframe', 'broker', 'timestamp',
                       'open', 'high', 'low', 'close', 'volume', 'is_complete')
    list_filter     = ('symbol', 'timeframe', 'broker', 'is_complete')
    search_fields   = ('symbol',)
    readonly_fields = ('id', 'created_at')
    date_hierarchy  = 'timestamp'


@admin.register(DataFetchLog)
class DataFetchLogAdmin(admin.ModelAdmin):
    list_display    = ('symbol', 'timeframe', 'broker', 'source',
                       'candles_fetched', 'success', 'created_at')
    list_filter     = ('success', 'broker', 'source', 'symbol')
    readonly_fields = ('id', 'created_at')


@admin.register(LiveTick)
class LiveTickAdmin(admin.ModelAdmin):
    list_display    = ('symbol', 'broker', 'bid', 'ask', 'spread', 'timestamp')
    list_filter     = ('symbol', 'broker')
    readonly_fields = ('id',)