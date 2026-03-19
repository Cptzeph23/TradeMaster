# ============================================================
# urls.py
# URL patterns for market data API
# ============================================================
from django.urls import path
from .views import (
    CandleListView,
    LivePriceView,
    MultiPriceView,
    SupportedPairsView,
    FetchTriggerView,
    DataFetchLogView,
)

app_name = 'market_data'

urlpatterns = [
    path('candles/',    CandleListView.as_view(),    name='candles'),
    path('price/',      LivePriceView.as_view(),     name='live-price'),
    path('prices/',     MultiPriceView.as_view(),    name='multi-price'),
    path('pairs/',      SupportedPairsView.as_view(),name='pairs'),
    path('fetch/',      FetchTriggerView.as_view(),  name='fetch-trigger'),
    path('fetch-log/',  DataFetchLogView.as_view(),  name='fetch-log'),
]