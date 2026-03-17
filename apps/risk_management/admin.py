# ============================================================
# risk_management/admin.py
# Admin interface for RiskRule and DrawdownEvent models
# ============================================================
from django.contrib import admin
from .models import RiskRule, DrawdownEvent


@admin.register(RiskRule)
class RiskRuleAdmin(admin.ModelAdmin):
    list_display    = ('bot', 'risk_percent', 'stop_loss_pips', 'take_profit_pips',
                       'max_drawdown_percent', 'max_trades_per_day', 'max_open_trades')
    search_fields   = ('bot__name',)
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(DrawdownEvent)
class DrawdownEventAdmin(admin.ModelAdmin):
    list_display    = ('bot', 'event_type', 'drawdown_percent',
                       'balance_at_event', 'peak_balance', 'timestamp')
    list_filter     = ('event_type',)
    search_fields   = ('bot__name',)
    readonly_fields = ('id', 'timestamp')
    date_hierarchy  = 'timestamp'