# ============================================================
# accounts/admin.py
# Admin interface for User and TradingAccount models
# ============================================================
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User, UserProfile, TradingAccount


class UserProfileInline(admin.StackedInline):
    model   = UserProfile
    extra   = 0
    fields  = ('timezone', 'currency', 'email_alerts', 'nlp_enabled', 'dashboard_theme')


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines         = [UserProfileInline]
    list_display    = ('email', 'full_name', 'is_active', 'is_verified', 'is_staff', 'date_joined')
    list_filter     = ('is_active', 'is_verified', 'is_staff', 'date_joined')
    search_fields   = ('email', 'first_name', 'last_name')
    ordering        = ('-date_joined',)
    readonly_fields = ('id', 'date_joined', 'last_login')

    fieldsets = (
        (None,           {'fields': ('id', 'email', 'password')}),
        ('Personal',     {'fields': ('first_name', 'last_name')}),
        ('Status',       {'fields': ('is_active', 'is_verified', 'is_staff', 'is_superuser')}),
        ('Permissions',  {'fields': ('groups', 'user_permissions')}),
        ('Timestamps',   {'fields': ('date_joined', 'last_login'), 'classes': ('collapse',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2'),
        }),
    )


@admin.register(TradingAccount)
class TradingAccountAdmin(admin.ModelAdmin):
    list_display    = ('name', 'user', 'broker', 'account_type', 'balance', 'currency',
                       'is_active', 'is_verified', 'last_synced')
    list_filter     = ('broker', 'account_type', 'is_active', 'is_verified')
    search_fields   = ('name', 'user__email', 'account_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    # API keys are excluded from admin display entirely for security
    exclude         = ('_api_key_encrypted', '_api_secret_encrypted')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')