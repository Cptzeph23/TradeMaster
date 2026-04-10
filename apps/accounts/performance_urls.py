# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/apps/accounts/performance_urls.py
# ============================================================
from django.urls import path
from .performance_views import (
    AccountPerformanceView,
    PerformanceHistoryView,
    PerformanceSymbolView,
    PerformanceCompareView,
    PerformanceSummaryView,
)

performance_urlpatterns = [
    # All accounts summary
    path('summary/',
         PerformanceSummaryView.as_view(),
         name='perf-summary'),

    # Compare across accounts
    path('compare/',
         PerformanceCompareView.as_view(),
         name='perf-compare'),

    # All accounts list
    path('accounts/',
         AccountPerformanceView.as_view(),
         name='perf-accounts'),

    # Single account detail
    path('accounts/<uuid:account_id>/',
         AccountPerformanceView.as_view(),
         name='perf-account-detail'),

    # Force recalculate
    path('accounts/<uuid:account_id>/recalculate/',
         AccountPerformanceView.as_view(),
         name='perf-recalculate'),

    # Equity / daily history
    path('accounts/<uuid:account_id>/history/',
         PerformanceHistoryView.as_view(),
         name='perf-history'),

    # Per-symbol breakdown
    path('accounts/<uuid:account_id>/symbols/',
         PerformanceSymbolView.as_view(),
         name='perf-symbols'),
]

# ── Add to config/urls.py ─────────────────────────────────────
# from apps.accounts.performance_urls import performance_urlpatterns
# path('api/v1/performance/',
#      include((performance_urlpatterns, 'performance'))),