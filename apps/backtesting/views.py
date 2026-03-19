# ============================================================
# Backtesting REST API endpoints
# ============================================================
import logging
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from .models import BacktestResult, BacktestTrade
from .serializers import (
    BacktestCreateSerializer,
    BacktestResultSerializer,
    BacktestResultSummarySerializer,
    BacktestTradeSerializer,
)
from utils.constants import BacktestStatus

logger = logging.getLogger('backtesting')


def ok(data, code=status.HTTP_200_OK):
    return Response({'success': True, **data}, status=code)

def err(msg, code=status.HTTP_400_BAD_REQUEST, errors=None):
    r = {'success': False, 'message': msg}
    if errors: r['errors'] = errors
    return Response(r, status=code)


class BacktestListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/backtesting/          → list user's backtests
    POST /api/v1/backtesting/          → create and queue a new backtest
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, OrderingFilter]
    filterset_fields   = ['status', 'symbol', 'timeframe']
    ordering           = ['-created_at']

    def get_queryset(self):
        return BacktestResult.objects.filter(
            user=self.request.user
        ).select_related('strategy')

    def get_serializer_class(self):
        return BacktestCreateSerializer if self.request.method == 'POST' \
               else BacktestResultSummarySerializer

    def list(self, request, *args, **kwargs):
        qs   = self.filter_queryset(self.get_queryset())
        data = BacktestResultSummarySerializer(qs, many=True).data
        return ok({'backtests': data, 'count': len(data)})

    def create(self, request, *args, **kwargs):
        # Limit concurrent running backtests
        running = BacktestResult.objects.filter(
            user=request.user, status=BacktestStatus.RUNNING
        ).count()
        if running >= 3:
            return err(
                'You already have 3 backtests running. Wait for one to complete.',
                code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        s = BacktestCreateSerializer(
            data=request.data, context={'request': request}
        )
        if not s.is_valid():
            return err('Backtest creation failed.', errors=s.errors)

        backtest = s.save()

        # Queue Celery task
        from workers.tasks import run_backtest
        task = run_backtest.apply_async(
            args  = [str(backtest.id)],
            queue = 'backtesting',
        )
        BacktestResult.objects.filter(pk=backtest.id).update(
            celery_task_id=task.id,
            status=BacktestStatus.QUEUED,
        )

        return ok({
            'message':     'Backtest queued.',
            'backtest_id': str(backtest.id),
            'task_id':     task.id,
        }, code=status.HTTP_202_ACCEPTED)


class BacktestDetailView(generics.RetrieveDestroyAPIView):
    """
    GET    /api/v1/backtesting/<id>/   → full results with equity curve
    DELETE /api/v1/backtesting/<id>/   → delete backtest
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return BacktestResult.objects.filter(
            user=self.request.user
        ).select_related('strategy')

    def retrieve(self, request, *args, **kwargs):
        bt   = self.get_object()
        data = BacktestResultSerializer(bt).data
        return ok({'backtest': data})

    def destroy(self, request, *args, **kwargs):
        bt = self.get_object()
        if bt.status == BacktestStatus.RUNNING:
            return err('Cannot delete a running backtest.')
        bt.delete()
        return ok({'message': 'Backtest deleted.'})


class BacktestStatusView(APIView):
    """
    GET /api/v1/backtesting/<id>/status/
    Lightweight endpoint for polling progress during execution.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            bt = BacktestResult.objects.get(pk=pk, user=request.user)
        except BacktestResult.DoesNotExist:
            return err('Backtest not found.', code=status.HTTP_404_NOT_FOUND)

        return ok({
            'id':          str(bt.id),
            'status':      bt.status,
            'progress':    bt.progress,
            'error':       bt.error_message,
            'started_at':  bt.started_at,
            'completed_at':bt.completed_at,
        })


class BacktestCancelView(APIView):
    """
    POST /api/v1/backtesting/<id>/cancel/
    Cancels a queued or running backtest.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            bt = BacktestResult.objects.get(pk=pk, user=request.user)
        except BacktestResult.DoesNotExist:
            return err('Backtest not found.', code=status.HTTP_404_NOT_FOUND)

        if bt.status not in (BacktestStatus.QUEUED, BacktestStatus.RUNNING):
            return err(f'Cannot cancel a {bt.status} backtest.')

        if bt.celery_task_id:
            from config.celery import app as celery_app
            celery_app.control.revoke(bt.celery_task_id, terminate=True)

        bt.status = BacktestStatus.FAILED
        bt.error_message = 'Cancelled by user.'
        bt.save(update_fields=['status', 'error_message'])

        return ok({'message': 'Backtest cancelled.'})


class BacktestTradeListView(generics.ListAPIView):
    """
    GET /api/v1/backtesting/<bt_id>/trades/
    Paginated list of simulated trades for a completed backtest.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = BacktestTradeSerializer
    filter_backends    = [DjangoFilterBackend, OrderingFilter]
    filterset_fields   = ['order_type', 'exit_reason']
    ordering           = ['entry_time']

    def get_queryset(self):
        return BacktestTrade.objects.filter(
            backtest__user=self.request.user,
            backtest_id=self.kwargs['bt_id'],
        )

    def list(self, request, *args, **kwargs):
        qs   = self.filter_queryset(self.get_queryset())
        data = BacktestTradeSerializer(qs, many=True).data
        return ok({'trades': data, 'count': len(data)})


class BacktestQuickRunView(APIView):
    """
    POST /api/v1/backtesting/quick-run/
    Runs a backtest synchronously (blocks) on a small date range.
    Max 90 days. Returns results immediately without Celery.
    Used for quick strategy parameter testing from the dashboard.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = BacktestCreateSerializer(
            data=request.data, context={'request': request}
        )
        if not s.is_valid():
            return err('Invalid parameters.', errors=s.errors)

        # Validate date range ≤ 90 days for sync run
        start = s.validated_data['start_date']
        end   = s.validated_data['end_date']
        if (end - start).days > 90:
            return err(
                'Quick run is limited to 90 days. '
                'Use POST /api/v1/backtesting/ for longer periods.'
            )

        backtest = s.save()

        try:
            from apps.backtesting.engine import BacktestEngine
            engine = BacktestEngine(backtest_id=str(backtest.id))
            result = engine.run()

            backtest.refresh_from_db()
            return ok({
                'message':  'Quick backtest complete.',
                'backtest': BacktestResultSerializer(backtest).data,
                'elapsed':  result.get('elapsed', 0),
            })
        except Exception as e:
            return err(
                f'Backtest failed: {str(e)}',
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )