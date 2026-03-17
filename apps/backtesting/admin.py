# ============================================================
# backtesting/admin.py
# Admin interface for BacktestResult and BacktestTrade models
# ============================================================
from django.contrib import admin
from .models import BacktestResult, BacktestTrade


class BacktestTradeInline(admin.TabularInline):
    model   = BacktestTrade
    extra   = 0
    max_num = 50
    fields  = ('trade_index', 'symbol', 'order_type', 'entry_price',
                'exit_price', 'profit_loss', 'exit_reason', 'entry_time')
    readonly_fields = fields
    can_delete  = False


@admin.register(BacktestResult)
class BacktestResultAdmin(admin.ModelAdmin):
    list_display    = ('strategy', 'symbol', 'timeframe', 'start_date', 'end_date',
                       'status', 'progress', 'initial_balance', 'final_balance', 'created_at')
    list_filter     = ('status', 'timeframe', 'symbol')
    search_fields   = ('strategy__name', 'user__email', 'symbol')
    readonly_fields = ('id', 'created_at', 'updated_at', 'started_at', 'completed_at',
                       'celery_task_id', 'progress')
    inlines         = [BacktestTradeInline]


@admin.register(BacktestTrade)
class BacktestTradeAdmin(admin.ModelAdmin):
    list_display    = ('trade_index', 'backtest', 'symbol', 'order_type',
                       'entry_price', 'exit_price', 'profit_loss', 'exit_reason', 'entry_time')
    list_filter     = ('order_type', 'exit_reason', 'symbol')
    readonly_fields = ('id',)