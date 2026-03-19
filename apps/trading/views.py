# ============================================================
# TradingBot CRUD + control endpoints (start/stop/pause)
# ============================================================
import logging
from django.utils import timezone as dj_tz
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from .models import TradingBot, Trade, BotLog, NLPCommand
from .serializers import (
    TradingBotSerializer, TradingBotCreateSerializer,
    TradeSerializer, BotLogSerializer,
    NLPCommandSerializer, NLPCommandCreateSerializer,
)
from utils.constants import BotStatus
from utils.decorators import require_bot_owner

logger = logging.getLogger('trading')


def ok(data, code=status.HTTP_200_OK):
    return Response({'success': True,  **data}, status=code)

def err(msg, code=status.HTTP_400_BAD_REQUEST, errors=None):
    r = {'success': False, 'message': msg}
    if errors: r['errors'] = errors
    return Response(r, status=code)


# ── Bot CRUD ─────────────────────────────────────────────────
class BotListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/trading/bots/    → list user's bots
    POST /api/v1/trading/bots/    → create new bot
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, OrderingFilter]
    filterset_fields   = ['status', 'broker']
    ordering_fields    = ['created_at', 'total_profit_loss']
    ordering           = ['-created_at']

    def get_serializer_class(self):
        return TradingBotCreateSerializer if self.request.method == 'POST' \
               else TradingBotSerializer

    def get_queryset(self):
        return TradingBot.objects.filter(
            user=self.request.user, is_active=True
        ).select_related('strategy', 'trading_account')

    def list(self, request, *args, **kwargs):
        qs   = self.filter_queryset(self.get_queryset())
        data = TradingBotSerializer(qs, many=True).data
        return ok({'bots': data, 'count': len(data)})

    def create(self, request, *args, **kwargs):
        s = TradingBotCreateSerializer(
            data=request.data, context={'request': request}
        )
        if not s.is_valid():
            return err('Bot creation failed.', errors=s.errors)
        bot = s.save()
        return ok(
            {'message': 'Bot created.', 'bot': TradingBotSerializer(bot).data},
            code=status.HTTP_201_CREATED,
        )


class BotDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/trading/bots/<id>/
    PATCH  /api/v1/trading/bots/<id>/
    DELETE /api/v1/trading/bots/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TradingBot.objects.filter(
            user=self.request.user, is_active=True
        )

    def get_serializer_class(self):
        return TradingBotCreateSerializer if self.request.method in ('PUT','PATCH') \
               else TradingBotSerializer

    def retrieve(self, request, *args, **kwargs):
        return ok({'bot': TradingBotSerializer(self.get_object()).data})

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        bot     = self.get_object()
        if bot.status == BotStatus.RUNNING:
            return err(
                'Cannot edit a running bot. Stop it first.',
                code=status.HTTP_409_CONFLICT
            )
        s = TradingBotCreateSerializer(
            bot, data=request.data, partial=partial,
            context={'request': request}
        )
        if not s.is_valid():
            return err('Update failed.', errors=s.errors)
        bot = s.save()
        return ok({'message': 'Bot updated.', 'bot': TradingBotSerializer(bot).data})

    def destroy(self, request, *args, **kwargs):
        bot = self.get_object()
        if bot.status == BotStatus.RUNNING:
            return err('Stop the bot before deleting.', code=status.HTTP_409_CONFLICT)
        bot.is_active = False
        bot.save(update_fields=['is_active'])
        return ok({'message': 'Bot deleted.'})


# ── Bot Control ───────────────────────────────────────────────
class BotStartView(APIView):
    """POST /api/v1/trading/bots/<id>/start/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            bot = TradingBot.objects.get(
                pk=pk, user=request.user, is_active=True
            )
        except TradingBot.DoesNotExist:
            return err('Bot not found.', code=status.HTTP_404_NOT_FOUND)

        if bot.status == BotStatus.RUNNING:
            return err('Bot is already running.')

        if not bot.trading_account.is_verified:
            return err(
                'Broker account is not verified. '
                'Verify it at /api/v1/auth/trading-accounts/<id>/verify/'
            )

        # Queue the bot runner Celery task
        from workers.tasks import run_trading_bot
        task = run_trading_bot.apply_async(
            args  = [str(bot.id)],
            queue = 'trading',
        )
        bot.celery_task_id = task.id
        bot.status         = BotStatus.RUNNING
        bot.started_at     = dj_tz.now()
        bot.error_message  = ''
        bot.save(update_fields=['celery_task_id','status','started_at','error_message'])

        logger.info(f"Bot {bot.name} started by {request.user.email} task={task.id}")
        return ok({
            'message': f"Bot '{bot.name}' started.",
            'task_id': task.id,
            'bot':     TradingBotSerializer(bot).data,
        })


class BotStopView(APIView):
    """POST /api/v1/trading/bots/<id>/stop/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            bot = TradingBot.objects.get(pk=pk, user=request.user, is_active=True)
        except TradingBot.DoesNotExist:
            return err('Bot not found.', code=status.HTTP_404_NOT_FOUND)

        bot.status     = BotStatus.STOPPED
        bot.stopped_at = dj_tz.now()
        bot.save(update_fields=['status','stopped_at'])

        # Revoke Celery task if running
        if bot.celery_task_id:
            from config.celery import app as celery_app
            celery_app.control.revoke(bot.celery_task_id, terminate=True)

        return ok({'message': f"Bot '{bot.name}' stopped.",
                   'bot': TradingBotSerializer(bot).data})


class BotPauseView(APIView):
    """POST /api/v1/trading/bots/<id>/pause/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            bot = TradingBot.objects.get(pk=pk, user=request.user, is_active=True)
        except TradingBot.DoesNotExist:
            return err('Bot not found.', code=status.HTTP_404_NOT_FOUND)

        if bot.status != BotStatus.RUNNING:
            return err('Bot is not running.')
        bot.status = BotStatus.PAUSED
        bot.save(update_fields=['status'])
        return ok({'message': f"Bot '{bot.name}' paused.",
                   'bot': TradingBotSerializer(bot).data})


class BotResumeView(APIView):
    """POST /api/v1/trading/bots/<id>/resume/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            bot = TradingBot.objects.get(pk=pk, user=request.user, is_active=True)
        except TradingBot.DoesNotExist:
            return err('Bot not found.', code=status.HTTP_404_NOT_FOUND)

        if bot.status != BotStatus.PAUSED:
            return err('Bot is not paused.')
        bot.status = BotStatus.RUNNING
        bot.save(update_fields=['status'])
        return ok({'message': f"Bot '{bot.name}' resumed.",
                   'bot': TradingBotSerializer(bot).data})


# ── Trade History ─────────────────────────────────────────────
class TradeListView(generics.ListAPIView):
    """GET /api/v1/trading/bots/<bot_id>/trades/"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = TradeSerializer
    filter_backends    = [DjangoFilterBackend, OrderingFilter]
    filterset_fields   = ['status', 'symbol', 'order_type']
    ordering           = ['-opened_at']

    def get_queryset(self):
        return Trade.objects.filter(
            bot__user=self.request.user,
            bot_id=self.kwargs['bot_id'],
        )

    def list(self, request, *args, **kwargs):
        qs   = self.filter_queryset(self.get_queryset())
        data = TradeSerializer(qs, many=True).data
        return ok({'trades': data, 'count': len(data)})


# ── Bot Logs ──────────────────────────────────────────────────
class BotLogListView(generics.ListAPIView):
    """GET /api/v1/trading/bots/<bot_id>/logs/"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = BotLogSerializer
    filter_backends    = [DjangoFilterBackend, OrderingFilter]
    filterset_fields   = ['level', 'event_type']
    ordering           = ['-timestamp']

    def get_queryset(self):
        return BotLog.objects.filter(
            bot__user=self.request.user,
            bot_id=self.kwargs['bot_id'],
        )[:200]

    def list(self, request, *args, **kwargs):
        qs   = self.filter_queryset(self.get_queryset())
        data = BotLogSerializer(qs, many=True).data
        return ok({'logs': data, 'count': len(data)})


# ── NLP Command ───────────────────────────────────────────────
class NLPCommandView(APIView):
    """
    POST /api/v1/trading/command/
    Send a natural language command to control a bot.

    Examples:
      "Set stop loss to 30 pips on my EUR/USD bot"
      "Stop all bots immediately"
      "Trade only EUR/USD and GBP/USD with 1.5% risk"
      "Pause the bot until I say resume"
      "Increase take profit to 80 pips"
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = NLPCommandCreateSerializer(data=request.data)
        if not s.is_valid():
            return err('Invalid command.', errors=s.errors)

        raw_command = s.validated_data['command']
        bot_id      = s.validated_data.get('bot_id')

        # Queue NLP processing task (Phase K fills this out fully)
        from workers.tasks import process_nlp_command
        task = process_nlp_command.apply_async(
            args  = [str(request.user.id), raw_command, str(bot_id) if bot_id else None],
            queue = 'commands',
        )

        return ok({
            'message': 'Command received and queued for processing.',
            'task_id': task.id,
            'command': raw_command,
        }, code=status.HTTP_202_ACCEPTED)


class NLPCommandHistoryView(generics.ListAPIView):
    """GET /api/v1/trading/commands/"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = NLPCommandSerializer

    def get_queryset(self):
        return NLPCommand.objects.filter(
            user=self.request.user
        ).order_by('-created_at')[:50]

    def list(self, request, *args, **kwargs):
        qs   = self.get_queryset()
        data = NLPCommandSerializer(qs, many=True).data
        return ok({'commands': data, 'count': len(data)})