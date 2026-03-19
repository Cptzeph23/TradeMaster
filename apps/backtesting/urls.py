# ============================================================
# ============================================================
from django.urls import path
from .views import (
    BacktestListCreateView,
    BacktestDetailView,
    BacktestStatusView,
    BacktestCancelView,
    BacktestTradeListView,
    BacktestQuickRunView,
)

app_name = 'backtesting'

urlpatterns = [
    # Backtest CRUD
    path('',                         BacktestListCreateView.as_view(), name='list'),
    path('<uuid:pk>/',               BacktestDetailView.as_view(),     name='detail'),
    path('<uuid:pk>/status/',        BacktestStatusView.as_view(),     name='status'),
    path('<uuid:pk>/cancel/',        BacktestCancelView.as_view(),     name='cancel'),

    # Simulated trade history
    path('<uuid:bt_id>/trades/',     BacktestTradeListView.as_view(),  name='trades'),

    # Synchronous quick run (≤90 days)
    path('quick-run/',               BacktestQuickRunView.as_view(),   name='quick-run'),
]