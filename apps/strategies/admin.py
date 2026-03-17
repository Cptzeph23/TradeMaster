# ============================================================
# strategies/admin.py
# Admin interface for Strategy model
# ============================================================
from django.contrib import admin
from .models import Strategy


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display    = ('name', 'user', 'strategy_type', 'timeframe',
                       'last_win_rate', 'last_profit_factor', 'last_sharpe',
                       'backtest_count', 'is_active', 'is_public')
    list_filter     = ('strategy_type', 'timeframe', 'is_active', 'is_public')
    search_fields   = ('name', 'user__email', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at',
                       'last_win_rate', 'last_profit_factor', 'last_sharpe', 'backtest_count')
    filter_horizontal = ()

    fieldsets = (
        ('Identity', {
            'fields': ('id', 'name', 'description', 'strategy_type', 'plugin_path')
        }),
        ('Configuration', {
            'fields': ('parameters', 'symbols', 'timeframe')
        }),
        ('Status', {
            'fields': ('is_active', 'is_public')
        }),
        ('Performance', {
            'fields': ('last_win_rate', 'last_profit_factor', 'last_sharpe', 'backtest_count'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )