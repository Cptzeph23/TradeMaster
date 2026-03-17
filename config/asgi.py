# ============================================================
# DESTINATION: /opt/forex_bot/config/asgi.py
# ASGI Configuration — supports HTTP + WebSocket via Channels
# ============================================================
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Import websocket URL patterns (defined in Phase L)
# Deferred import to avoid circular imports during Phase A
def get_websocket_urlpatterns():
    try:
        from apps.trading import routing as trading_routing
        return trading_routing.websocket_urlpatterns
    except (ImportError, AttributeError):
        return []

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(get_websocket_urlpatterns())
        )
    ),
})
