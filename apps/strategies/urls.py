
from django.urls import path
from .views import (
    StrategyPluginListView,
    StrategyListCreateView,
    StrategyDetailView,
    StrategyPreviewView,
)

app_name = 'strategies'

urlpatterns = [
    # Available strategy types / plugins
    path('plugins/',                        StrategyPluginListView.as_view(),  name='plugin-list'),

    # User strategy CRUD
    path('',                                StrategyListCreateView.as_view(),  name='strategy-list'),
    path('<uuid:pk>/',                      StrategyDetailView.as_view(),      name='strategy-detail'),

    # Live signal preview
    path('<uuid:pk>/preview/',              StrategyPreviewView.as_view(),     name='strategy-preview'),
]