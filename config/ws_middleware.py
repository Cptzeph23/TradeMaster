# ============================================================
# JWT Authentication middleware for WebSocket connections
# Reads Bearer token from query string: ?token=<jwt>
# ============================================================
import logging
from urllib.parse import parse_qs
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger('django')


@database_sync_to_async
def get_user_from_token(token: str):
    """Validate JWT token and return the associated User."""
    from rest_framework_simplejwt.tokens import AccessToken
    from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
    from apps.accounts.models import User

    if not token:
        return AnonymousUser()
    try:
        validated = AccessToken(token)
        user_id   = validated['user_id']
        return User.objects.get(pk=user_id, is_active=True)
    except (TokenError, InvalidToken, User.DoesNotExist, KeyError) as e:
        logger.debug(f"WS JWT auth failed: {e}")
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Channels middleware that authenticates WebSocket connections
    using a JWT access token passed as a query parameter.

    Usage from client:
        const ws = new WebSocket(
            `ws://localhost:8001/ws/bots/${botId}/?token=${accessToken}`
        );

    Or from JavaScript fetch-first pattern:
        const ws = new WebSocket(`ws://host/ws/dashboard/?token=${jwt}`);
    """

    async def __call__(self, scope, receive, send):
        # Extract token from query string
        query_string = scope.get('query_string', b'').decode('utf-8')
        params       = parse_qs(query_string)
        token_list   = params.get('token', [])
        token        = token_list[0] if token_list else ''

        # Also check Authorization header (for testing)
        headers = dict(scope.get('headers', []))
        auth_header = headers.get(b'authorization', b'').decode('utf-8')
        if not token and auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]

        scope['user'] = await get_user_from_token(token)

        return await super().__call__(scope, receive, send)