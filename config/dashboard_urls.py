# ============================================================
# Add these URL patterns to config/urls.py
# ============================================================
from django.urls import path
from apps.trading.dashboard_views import (
    dashboard, bots_list, bot_detail,
    strategies_list, backtesting_page,
    market_data_page, risk_page,
    login_page, register_page,
)

# Add these to the urlpatterns list in config/urls.py:
dashboard_urlpatterns = [
    path('',              login_page,       name='home'),
    path('dashboard/',    dashboard,        name='dashboard'),
    path('bots/',         bots_list,        name='bots'),
    path('bots/<uuid:bot_id>/', bot_detail, name='bot-detail'),
    path('strategies/',   strategies_list,  name='strategies'),
    path('backtesting/',  backtesting_page, name='backtesting'),
    path('market-data/',  market_data_page, name='market-data'),
    path('risk/',         risk_page,        name='risk'),
    path('accounts/login/',    login_page,    name='login'),
    path('accounts/register/', register_page, name='register'),
]