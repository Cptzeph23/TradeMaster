# ============================================================
# COMPLETE — all routes including logout, bots/new, ws silencer
# ============================================================
from services.telegram.webhook_view import telegram_webhook
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.http import JsonResponse
from drf_spectacular.views import (
    SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView,
)
from apps.trading.dashboard_views import (
    dashboard, bots_list, bot_detail, strategies_list,
    backtesting_page, market_data_page, risk_page,
    login_page, register_page,
)

API_V1 = 'api/v1/'


def logout_view(request):
    """Client-side logout — clears JWT in localStorage via JS redirect."""
    return RedirectView.as_view(url='/accounts/login/')(request)


def ws_unavailable(request, path=''):
    """
    Friendly JSON response when WS routes are hit over HTTP.
    Only happens when running manage.py runserver instead of Daphne.
    """
    return JsonResponse({
        'error': 'WebSocket not available over HTTP.',
        'fix':   'Start Daphne: daphne -b 127.0.0.1 -p 8001 config.asgi:application',
    }, status=426)  # 426 Upgrade Required


urlpatterns = [
    # ── Admin ──────────────────────────────────────────────────
    path(getattr(settings, 'ADMIN_URL', 'admin/'), admin.site.urls),

    # ── Favicon ────────────────────────────────────────────────
    path('favicon.ico',
         RedirectView.as_view(url='/static/images/favicon.svg', permanent=True)),

    # ── Dashboard pages ────────────────────────────────────────
    path('',                         login_page,       name='home'),
    path('dashboard/',               dashboard,        name='dashboard'),
    path('bots/',                    bots_list,        name='bots'),
    path('bots/new/',                bots_list,        name='bots-new'),  # handled by JS modal
    path('bots/<uuid:bot_id>/',      bot_detail,       name='bot-detail'),
    path('strategies/',              strategies_list,  name='strategies'),
    path('backtesting/',             backtesting_page, name='backtesting'),
    path('market-data/',             market_data_page, name='market-data'),
    path('risk/',                    risk_page,        name='risk'),

    # ── Auth pages ─────────────────────────────────────────────
    path('accounts/login/',          login_page,       name='login'),
    path('accounts/register/',       register_page,    name='register'),
    path('accounts/logout/',         logout_view,      name='logout'),

    # ── REST API ───────────────────────────────────────────────
    path(API_V1 + 'auth/',           include('apps.accounts.urls')),
    path(API_V1 + 'trading/',        include('apps.trading.urls')),
    path(API_V1 + 'strategies/',     include('apps.strategies.urls')),
    path(API_V1 + 'backtesting/',    include('apps.backtesting.urls')),
    path(API_V1 + 'market-data/',    include('apps.market_data.urls')),
    path(API_V1 + 'risk/',           include('apps.risk_management.urls')),

    # ── OpenAPI ────────────────────────────────────────────────
    path('api/schema/', SpectacularAPIView.as_view(),   name='schema'),
    path('api/docs/',   SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/',  SpectacularRedocView.as_view(url_name='schema'),   name='redoc'),

    # ── WebSocket fallback (HTTP only — stops 404 spam) ────────
    # When running manage.py runserver (no Daphne), return helpful error
    path('ws/<path:path>', ws_unavailable, name='ws-fallback'),
    path('api/v1/telegram/webhook/<str:secret_token>/',
        telegram_webhook,
       name='telegram-webhook'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,  document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

admin.site.site_header  = 'ForexBot Admin'
admin.site.site_title   = 'ForexBot Admin Portal'
admin.site.index_title  = 'Trading Platform Administration'



TELEGRAM_URL_ENTRY = """
    # Telegram webhook
    path('api/v1/telegram/webhook/<str:secret_token>/',
         telegram_webhook,
         name='telegram-webhook'),
"""