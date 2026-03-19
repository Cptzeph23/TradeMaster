# ============================================================
# ============================================================
from django.urls import path
from .views import (
    RiskRuleView,
    RiskAnalysisView,
    LotSizeCalculatorView,
    DrawdownEventListView,
    PerformanceMetricsView,
)

app_name = 'risk_management'

urlpatterns = [
    # Per-bot risk rules
    path('bots/<uuid:bot_id>/rules/',
         RiskRuleView.as_view(),           name='risk-rules'),

    # Risk analysis dashboard
    path('bots/<uuid:bot_id>/analysis/',
         RiskAnalysisView.as_view(),       name='risk-analysis'),

    # Drawdown event history
    path('bots/<uuid:bot_id>/drawdown-events/',
         DrawdownEventListView.as_view(),  name='drawdown-events'),

    # Performance metrics
    path('bots/<uuid:bot_id>/performance/',
         PerformanceMetricsView.as_view(), name='performance'),

    # Lot size calculator (utility)
    path('calculate/lot-size/',
         LotSizeCalculatorView.as_view(),  name='lot-size-calc'),
]