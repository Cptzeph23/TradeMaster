# ============================================================
# FINAL — includes dashboard routes, favicon, admin URL from env
# ============================================================
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

# Dashboard views
from apps.trading.dashboard_views import (
    dashboard, bots_list, bot_detail,
    strategies_list, backtesting_page,
    market_data_page, risk_page,
    login_page, register_page,
)

API_V1 = 'api/v1/'

urlpatterns = [
    # ── Admin ─────────────────────────────────────────────────
    path(getattr(settings, 'ADMIN_URL', 'admin/'), admin.site.urls),

    # ── Favicon ───────────────────────────────────────────────
    path('favicon.ico',
         RedirectView.as_view(url='/static/images/favicon.svg', permanent=True),
         name='favicon'),

    # ── Dashboard pages ───────────────────────────────────────
    path('',                        login_page,       name='home'),
    path('dashboard/',              dashboard,        name='dashboard'),
    path('bots/',                   bots_list,        name='bots'),
    path('bots/<uuid:bot_id>/',     bot_detail,       name='bot-detail'),
    path('strategies/',             strategies_list,  name='strategies'),
    path('backtesting/',            backtesting_page, name='backtesting'),
    path('market-data/',            market_data_page, name='market-data'),
    path('risk/',                   risk_page,        name='risk'),
    path('accounts/login/',         login_page,       name='login'),
    path('accounts/register/',      register_page,    name='register'),

    # ── REST API ──────────────────────────────────────────────
    path(API_V1 + 'auth/',          include('apps.accounts.urls')),
    path(API_V1 + 'trading/',       include('apps.trading.urls')),
    path(API_V1 + 'strategies/',    include('apps.strategies.urls')),
    path(API_V1 + 'backtesting/',   include('apps.backtesting.urls')),
    path(API_V1 + 'market-data/',   include('apps.market_data.urls')),
    path(API_V1 + 'risk/',          include('apps.risk_management.urls')),

    # ── OpenAPI / Swagger ─────────────────────────────────────
    path('api/schema/', SpectacularAPIView.as_view(),   name='schema'),
    path('api/docs/',   SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/',  SpectacularRedocView.as_view(url_name='schema'),   name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,  document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Admin cosmetics
admin.site.site_header  = 'ForexBot Admin'
admin.site.site_title   = 'ForexBot Admin Portal'
admin.site.index_title  = 'Trading Platform Administration'