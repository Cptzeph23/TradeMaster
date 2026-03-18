
import logging
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

from .models import Strategy
from .registry import StrategyRegistry
from .serializers import (
    StrategySerializer,
    StrategyCreateSerializer,
    StrategyPluginListSerializer,
)

logger = logging.getLogger('trading')


def ok(data, code=status.HTTP_200_OK):
    return Response({'success': True, **data}, status=code)

def err(msg, code=status.HTTP_400_BAD_REQUEST, errors=None):
    r = {'success': False, 'message': msg}
    if errors:
        r['errors'] = errors
    return Response(r, status=code)


# ── List available strategy plugins ─────────────────────────
class StrategyPluginListView(APIView):
    """
    GET /api/v1/strategies/plugins/
    Returns all registered strategy types with parameter schemas.
    Used by the frontend to render dynamic strategy creation forms.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        plugins = StrategyRegistry.get_schema_list()
        return ok({'plugins': plugins, 'count': len(plugins)})


# ── User strategy CRUD ────────────────────────────────────────
class StrategyListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/strategies/         → list user's strategies
    POST /api/v1/strategies/         → create new strategy
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return StrategyCreateSerializer if self.request.method == 'POST' else StrategySerializer

    def get_queryset(self):
        qs = Strategy.objects.filter(
            is_active=True
        ).filter(
            # Own strategies + public strategies from others
            user=self.request.user
        ).order_by('-created_at')

        strategy_type = self.request.query_params.get('type')
        if strategy_type:
            qs = qs.filter(strategy_type=strategy_type)
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        # Also include public strategies from other users
        public = Strategy.objects.filter(
            is_public=True, is_active=True
        ).exclude(user=request.user)

        own_data    = StrategySerializer(qs, many=True).data
        public_data = StrategySerializer(public, many=True).data

        return ok({
            'own':    own_data,
            'public': public_data,
            'count':  len(own_data) + len(public_data),
        })

    def create(self, request, *args, **kwargs):
        serializer = StrategyCreateSerializer(
            data=request.data, context={'request': request}
        )
        if not serializer.is_valid():
            return err('Strategy creation failed.', errors=serializer.errors)
        strategy = serializer.save()
        return ok(
            {'message': 'Strategy created.', 'strategy': StrategySerializer(strategy).data},
            code=status.HTTP_201_CREATED
        )


class StrategyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/strategies/<id>/   → strategy detail
    PUT    /api/v1/strategies/<id>/   → full update
    PATCH  /api/v1/strategies/<id>/   → partial update
    DELETE /api/v1/strategies/<id>/   → soft delete
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Strategy.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return StrategyCreateSerializer
        return StrategySerializer

    def retrieve(self, request, *args, **kwargs):
        return ok({'strategy': StrategySerializer(self.get_object()).data})

    def update(self, request, *args, **kwargs):
        partial    = kwargs.pop('partial', False)
        serializer = StrategyCreateSerializer(
            self.get_object(), data=request.data,
            partial=partial, context={'request': request}
        )
        if not serializer.is_valid():
            return err('Update failed.', errors=serializer.errors)
        strategy = serializer.save()
        return ok({'message': 'Strategy updated.', 'strategy': StrategySerializer(strategy).data})

    def destroy(self, request, *args, **kwargs):
        strategy = self.get_object()
        if strategy.bots.filter(is_active=True).exists():
            return err(
                'Cannot delete a strategy that is assigned to active bots.',
                code=status.HTTP_409_CONFLICT
            )
        strategy.is_active = False
        strategy.save(update_fields=['is_active'])
        return ok({'message': 'Strategy deleted.'})


# ── Test / preview a signal ──────────────────────────────────
@method_decorator(ratelimit(key='user', rate='30/h', method='POST', block=True), name='post')
class StrategyPreviewView(APIView):
    """
    POST /api/v1/strategies/<id>/preview/
    Runs the strategy against the last N candles of live market data
    and returns what signal it would generate RIGHT NOW.
    Useful for testing strategy parameters before deploying a bot.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            strategy = Strategy.objects.get(pk=pk, user=request.user)
        except Strategy.DoesNotExist:
            return err('Strategy not found.', code=status.HTTP_404_NOT_FOUND)

        symbol    = request.data.get('symbol', 'EUR_USD')
        timeframe = request.data.get('timeframe', strategy.timeframe)

        try:
            # Fetch live candles
            from apps.market_data.cache import get_cached_candles
            df = get_cached_candles(symbol, timeframe, count=500)

            if df is None or df.empty:
                return err(f"No market data available for {symbol}/{timeframe}")

            # Instantiate and run the strategy
            instance = strategy.instantiate()
            signal   = instance.generate_signal(df, symbol)

            return ok({
                'symbol':    symbol,
                'timeframe': timeframe,
                'signal':    signal.to_dict(),
                'strategy':  strategy.name,
                'candles_used': len(df),
            })

        except Exception as e:
            logger.error(f"Strategy preview failed: {e}", exc_info=True)
            return err(f"Preview failed: {str(e)}", code=status.HTTP_500_INTERNAL_SERVER_ERROR)