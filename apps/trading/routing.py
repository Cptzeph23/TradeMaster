# ============================================================
# Django Channels WebSocket URL routing
# ============================================================
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Individual bot status stream
    re_path(
        r'^ws/bots/(?P<bot_id>[0-9a-f-]+)/$',
        consumers.BotStatusConsumer.as_asgi(),
        name='ws-bot-status',
    ),

    # Live price ticker for a forex symbol
    re_path(
        r'^ws/prices/(?P<symbol>[A-Z_]+)/$',
        consumers.LivePriceConsumer.as_asgi(),
        name='ws-live-price',
    ),

    # Main dashboard aggregated feed
    re_path(
        r'^ws/dashboard/$',
        consumers.DashboardConsumer.as_asgi(),
        name='ws-dashboard',
    ),
]