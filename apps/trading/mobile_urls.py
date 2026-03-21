from django.urls import path
from .mobile_views import (
    MobileDashboardView,
    MobileBotsView,
    MobileBotControlView,
    MobileTradesView,
    MobileStatsView,
    MobileNLPView,
    MobilePriceView,
)
 
mobile_urlpatterns = [
    # One-shot dashboard snapshot
    path('dashboard/',                    MobileDashboardView.as_view(),   name='mobile-dashboard'),
 
    # Bot management
    path('bots/',                         MobileBotsView.as_view(),        name='mobile-bots'),
    path('bots/<uuid:bot_id>/<str:action>/', MobileBotControlView.as_view(), name='mobile-bot-control'),
 
    # Trade history
    path('trades/',                       MobileTradesView.as_view(),      name='mobile-trades'),
 
    # Performance stats
    path('stats/',                        MobileStatsView.as_view(),       name='mobile-stats'),
 
    # NLP command
    path('command/',                      MobileNLPView.as_view(),         name='mobile-command'),
 
    # Live prices
    path('prices/',                       MobilePriceView.as_view(),       name='mobile-prices'),
]