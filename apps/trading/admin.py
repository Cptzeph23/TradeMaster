# ============================================================
# trading/admin.py
# Admin interface for TradingBot, Trade, BotLog, NLPCommand models
# ============================================================
from django.contrib import admin
from django.utils.html import format_html
from .models import TradingBot, Trade, BotLog, NLPCommand


class TradeInline(admin.TabularInline):
    model   = Trade
    extra   = 0
    max_num = 20
    fields  = ('symbol', 'order_type', 'status', 'lot_size',
                'entry_price', 'exit_price', 'profit_loss', 'opened_at')
    readonly_fields = fields
    can_delete  = False
    show_change_link = True


@admin.register(TradingBot)
class TradingBotAdmin(admin.ModelAdmin):
    list_display    = ('name', 'user', 'strategy', 'broker', 'status_badge',
                       'total_trades', 'win_rate', 'total_profit_loss', 'created_at')
    list_filter     = ('status', 'broker', 'is_active')
    search_fields   = ('name', 'user__email', 'strategy__name')
    readonly_fields = ('id', 'win_rate', 'celery_task_id', 'created_at', 'updated_at',
                       'started_at', 'stopped_at', 'last_signal_at')
    inlines         = [TradeInline]

    @admin.display(description='Status')
    def status_badge(self, obj):
        colours = {
            'running': '#22c55e', 'idle': '#94a3b8',
            'paused': '#f59e0b', 'stopped': '#64748b',
            'error': '#ef4444', 'backtesting': '#3b82f6',
        }
        colour = colours.get(obj.status, '#94a3b8')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:12px;font-size:11px">{}</span>',
            colour, obj.status.upper()
        )


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display    = ('id', 'bot', 'symbol', 'order_type', 'status',
                       'lot_size', 'entry_price', 'exit_price', 'profit_loss', 'opened_at')
    list_filter     = ('status', 'order_type', 'symbol')
    search_fields   = ('symbol', 'bot__name', 'broker_order_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    date_hierarchy  = 'opened_at'


@admin.register(BotLog)
class BotLogAdmin(admin.ModelAdmin):
    list_display    = ('timestamp', 'bot', 'level', 'event_type', 'short_message')
    list_filter     = ('level', 'event_type')
    search_fields   = ('message', 'bot__name')
    readonly_fields = ('id', 'timestamp')
    date_hierarchy  = 'timestamp'

    @admin.display(description='Message')
    def short_message(self, obj):
        return obj.message[:80] + '…' if len(obj.message) > 80 else obj.message


@admin.register(NLPCommand)
class NLPCommandAdmin(admin.ModelAdmin):
    list_display    = ('created_at', 'user', 'bot', 'command_type',
                       'status', 'confidence', 'short_command')
    list_filter     = ('command_type', 'status')
    search_fields   = ('raw_command', 'user__email')
    readonly_fields = ('id', 'created_at', 'executed_at', 'model_used', 'tokens_used')

    @admin.display(description='Command')
    def short_command(self, obj):
        return obj.raw_command[:60] + '…' if len(obj.raw_command) > 60 else obj.raw_command