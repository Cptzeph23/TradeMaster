# ============================================================
# All authentication and account management endpoints
# ============================================================
from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    LogoutView,
    TokenRefreshView,
    MeView,
    ChangePasswordView,
    TradingAccountListCreateView,
    TradingAccountDetailView,
    VerifyBrokerConnectionView,
)

app_name = 'accounts'

urlpatterns = [
    # ── Authentication ────────────────────────────────────────
    path('register/',               RegisterView.as_view(),      name='register'),
    path('login/',                  LoginView.as_view(),         name='login'),
    path('logout/',                 LogoutView.as_view(),        name='logout'),
    path('token/refresh/',          TokenRefreshView.as_view(),  name='token-refresh'),

    # ── Current User ──────────────────────────────────────────
    path('me/',                     MeView.as_view(),            name='me'),
    path('me/change-password/',     ChangePasswordView.as_view(),name='change-password'),

    # ── Trading Accounts (Broker connections) ─────────────────
    path('trading-accounts/',
         TradingAccountListCreateView.as_view(),
         name='trading-account-list'),

    path('trading-accounts/<uuid:pk>/',
         TradingAccountDetailView.as_view(),
         name='trading-account-detail'),

    path('trading-accounts/<uuid:pk>/verify/',
         VerifyBrokerConnectionView.as_view(),
         name='trading-account-verify'),
]