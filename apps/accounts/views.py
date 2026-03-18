# ============================================================
# Auth views: register, login, logout, profile, trading accounts
# ============================================================
import logging
from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

from .models import User, TradingAccount
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    TokenResponseSerializer,
    UserSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
    TradingAccountSerializer,
    TradingAccountCreateSerializer,
)

logger = logging.getLogger('django')


# ── helpers ──────────────────────────────────────────────────
def success_response(data: dict, status_code=status.HTTP_200_OK) -> Response:
    return Response({'success': True, **data}, status=status_code)


def error_response(message: str, status_code=status.HTTP_400_BAD_REQUEST,
                   errors=None) -> Response:
    payload = {'success': False, 'message': message}
    if errors:
        payload['errors'] = errors
    return Response(payload, status=status_code)


# ── Register ──────────────────────────────────────────────────
@method_decorator(ratelimit(key='ip', rate='10/h', method='POST', block=True), name='post')
class RegisterView(generics.CreateAPIView):
    """
    POST /api/v1/auth/register/
    Create a new user account and return JWT tokens immediately.
    Rate-limited to 10 registrations per IP per hour.
    """
    serializer_class   = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'Registration failed.', errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        user   = serializer.save()
        tokens = TokenResponseSerializer.get_tokens(user)

        logger.info(f"New user registered: {user.email}")

        return success_response({
            'message': 'Account created successfully.',
            'user':    UserSerializer(user).data,
            'tokens':  tokens,
        }, status_code=status.HTTP_201_CREATED)


# ── Login ──────────────────────────────────────────────────────
@method_decorator(ratelimit(key='ip', rate='20/h', method='POST', block=True), name='post')
class LoginView(APIView):
    """
    POST /api/v1/auth/login/
    Authenticate with email + password, receive JWT access + refresh tokens.
    Rate-limited to 20 attempts per IP per hour.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return error_response(
                'Login failed.', errors=serializer.errors,
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        user   = serializer.validated_data['user']
        tokens = TokenResponseSerializer.get_tokens(user)

        # Update last_login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        logger.info(f"User logged in: {user.email}")

        return success_response({
            'message': 'Login successful.',
            'user':    UserSerializer(user).data,
            'tokens':  tokens,
        })


# ── Logout ─────────────────────────────────────────────────────
class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Blacklist the provided refresh token.
    Requires: { "refresh": "<token>" }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return error_response('Refresh token is required.')

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info(f"User logged out: {request.user.email}")
            return success_response({'message': 'Logged out successfully.'})
        except TokenError as e:
            return error_response(str(e), status_code=status.HTTP_400_BAD_REQUEST)


# ── Token Refresh ───────────────────────────────────────────────
class TokenRefreshView(APIView):
    """
    POST /api/v1/auth/token/refresh/
    Exchange a refresh token for a new access token.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return error_response('Refresh token is required.')
        try:
            token  = RefreshToken(refresh_token)
            return success_response({
                'access':  str(token.access_token),
                'refresh': str(token),   # rotated
            })
        except TokenError as e:
            return error_response(str(e), status_code=status.HTTP_401_UNAUTHORIZED)


# ── Current User Profile ────────────────────────────────────────
class MeView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/auth/me/   → return current user + profile
    PUT  /api/v1/auth/me/   → update name / profile fields
    PATCH /api/v1/auth/me/  → partial update
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return UserUpdateSerializer
        return UserSerializer

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        serializer = UserSerializer(request.user)
        return success_response({'user': serializer.data})

    def update(self, request, *args, **kwargs):
        partial    = kwargs.pop('partial', False)
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=partial,
            context={'request': request}
        )
        if not serializer.is_valid():
            return error_response('Update failed.', errors=serializer.errors)

        serializer.save()
        return success_response({
            'message': 'Profile updated.',
            'user':    UserSerializer(request.user).data,
        })


# ── Change Password ──────────────────────────────────────────────
class ChangePasswordView(APIView):
    """
    POST /api/v1/auth/change-password/
    Body: { old_password, new_password, confirm_password }
    Rotates refresh tokens after change.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return error_response('Password change failed.', errors=serializer.errors)

        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()

        # Issue new tokens (old refresh tokens now invalid)
        tokens = TokenResponseSerializer.get_tokens(user)
        logger.info(f"Password changed for: {user.email}")

        return success_response({
            'message': 'Password changed successfully.',
            'tokens':  tokens,
        })


# ── Trading Accounts ─────────────────────────────────────────────
class TradingAccountListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/auth/trading-accounts/         → list user's broker accounts
    POST /api/v1/auth/trading-accounts/         → add a new broker account
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TradingAccountCreateSerializer
        return TradingAccountSerializer

    def get_queryset(self):
        return TradingAccount.objects.filter(
            user=self.request.user,
            is_active=True
        ).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        qs         = self.get_queryset()
        serializer = TradingAccountSerializer(qs, many=True)
        return success_response({
            'count':   qs.count(),
            'results': serializer.data,
        })

    def create(self, request, *args, **kwargs):
        # Enforce per-user account limit
        existing = TradingAccount.objects.filter(
            user=request.user, is_active=True
        ).count()
        if existing >= 10:
            return error_response(
                'Maximum of 10 trading accounts allowed per user.',
                status_code=status.HTTP_403_FORBIDDEN
            )

        serializer = TradingAccountCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return error_response('Account creation failed.', errors=serializer.errors)

        account = serializer.save()
        return success_response({
            'message': 'Trading account added.',
            'account': TradingAccountSerializer(account).data,
        }, status_code=status.HTTP_201_CREATED)


class TradingAccountDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/auth/trading-accounts/<id>/   → account details
    PUT    /api/v1/auth/trading-accounts/<id>/   → update (including re-keying)
    DELETE /api/v1/auth/trading-accounts/<id>/   → soft-delete (sets is_active=False)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return TradingAccountCreateSerializer
        return TradingAccountSerializer

    def get_queryset(self):
        return TradingAccount.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        account    = self.get_object()
        serializer = TradingAccountSerializer(account)
        return success_response({'account': serializer.data})

    def update(self, request, *args, **kwargs):
        partial    = kwargs.pop('partial', False)
        account    = self.get_object()
        serializer = TradingAccountCreateSerializer(
            account, data=request.data, partial=partial,
            context={'request': request}
        )
        if not serializer.is_valid():
            return error_response('Update failed.', errors=serializer.errors)
        account = serializer.save()
        return success_response({
            'message': 'Account updated.',
            'account': TradingAccountSerializer(account).data,
        })

    def destroy(self, request, *args, **kwargs):
        account           = self.get_object()
        account.is_active = False
        account.save(update_fields=['is_active'])
        return success_response(
            {'message': 'Trading account removed.'},
            status_code=status.HTTP_200_OK
        )


# ── Verify Broker Connection ─────────────────────────────────────
class VerifyBrokerConnectionView(APIView):
    """
    POST /api/v1/auth/trading-accounts/<id>/verify/
    Tests the stored API credentials against the live broker API.
    Updates is_verified, balance, equity on success.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            account = TradingAccount.objects.get(
                pk=pk, user=request.user, is_active=True
            )
        except TradingAccount.DoesNotExist:
            return error_response('Account not found.', status_code=status.HTTP_404_NOT_FOUND)

        try:
            result = self._test_connection(account)
        except Exception as e:
            account.is_verified = False
            account.save(update_fields=['is_verified'])
            logger.error(f"Broker connection test failed for account {pk}: {e}")
            return error_response(
                f'Connection failed: {str(e)}',
                status_code=status.HTTP_502_BAD_GATEWAY
            )

        # Update account with verified data
        account.is_verified = True
        account.balance     = result.get('balance', account.balance)
        account.equity      = result.get('equity', account.equity)
        account.currency    = result.get('currency', account.currency)
        account.last_synced = timezone.now()
        account.save(update_fields=[
            'is_verified', 'balance', 'equity', 'currency', 'last_synced'
        ])

        return success_response({
            'message':    'Connection verified successfully.',
            'account_id': result.get('account_id', account.account_id),
            'balance':    float(account.balance),
            'currency':   account.currency,
        })

    def _test_connection(self, account: TradingAccount) -> dict:
        """Delegate to the appropriate broker API connector."""
        from services.broker_api.oanda import OandaBroker
        from services.broker_api.metatrader5 import MT5Broker

        api_key = account.get_api_key()

        if account.broker == 'oanda':
            broker = OandaBroker(
                api_key=api_key,
                account_id=account.account_id,
                environment=account.account_type,
            )
        elif account.broker == 'metatrader5':
            broker = MT5Broker(
                login=account.account_id,
                password=api_key,
                server=account.get_api_secret(),
            )
        else:
            raise ValueError(f"Unsupported broker: {account.broker}")

        return broker.get_account_info()