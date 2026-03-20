# ============================================================
# ASGI Configuration — HTTP + WebSocket via Django Channels
# ============================================================
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Must initialise Django before importing channel middleware
django_asgi_app = get_asgi_application()


def get_application():
    """
    Deferred build so Django is fully initialised before
    importing JWT middleware and routing.
    """
    from apps.trading.routing import websocket_urlpatterns
    from channels.auth import AuthMiddlewareStack
    from .ws_middleware import JWTAuthMiddleware

    return ProtocolTypeRouter({
        # Standard HTTP — handled by Django
        'http': django_asgi_app,

        # WebSocket — JWT authenticated, Channels-routed
        'websocket': AllowedHostsOriginValidator(
            JWTAuthMiddleware(
                AuthMiddlewareStack(
                    URLRouter(websocket_urlpatterns)
                )
            )
        ),
    })


application = get_application()