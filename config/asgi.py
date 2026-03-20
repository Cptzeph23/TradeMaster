# ============================================================
# FIXED — removes AllowedHostsOriginValidator for development
# The validator was blocking all WS connections with HTTP 403
# because localhost was not matching ALLOWED_HOSTS strictly.
# ============================================================
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Must initialise Django BEFORE importing anything else
django_asgi_app = get_asgi_application()


def get_application():
    from channels.routing import ProtocolTypeRouter, URLRouter
    from channels.auth import AuthMiddlewareStack
    from apps.trading.routing import websocket_urlpatterns
    from config.ws_middleware import JWTAuthMiddleware

    return ProtocolTypeRouter({
        # Standard HTTP — handled by Django/Daphne
        'http': django_asgi_app,

        # WebSocket — JWT authenticated
        # NOTE: AllowedHostsOriginValidator removed for development.
        # Add it back in production with a real domain in ALLOWED_HOSTS.
        'websocket': JWTAuthMiddleware(
            AuthMiddlewareStack(
                URLRouter(websocket_urlpatterns)
            )
        ),
    })


application = get_application()