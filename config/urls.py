# ============================================================
# DESTINATION: /opt/forex_bot/config/urls.py
# Master URL Configuration
# ============================================================
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

# API version prefix
API_V1 = 'api/v1/'

urlpatterns = [
    # ── Django Admin ──────────────────────────────────────────
    path('admin/', admin.site.urls),

    # ── API Apps ──────────────────────────────────────────────
    path(API_V1 + 'auth/',          include('apps.accounts.urls')),
    path(API_V1 + 'trading/',       include('apps.trading.urls')),
    path(API_V1 + 'strategies/',    include('apps.strategies.urls')),
    path(API_V1 + 'backtesting/',   include('apps.backtesting.urls')),
    path(API_V1 + 'market-data/',   include('apps.market_data.urls')),
    path(API_V1 + 'risk/',          include('apps.risk_management.urls')),

    # ── OpenAPI / Swagger ─────────────────────────────────────
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/',   SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Customise admin site headers
admin.site.site_header = 'Forex Bot Admin'
admin.site.site_title = 'Forex Bot Admin Portal'
admin.site.index_title = 'Trading Platform Administration'
