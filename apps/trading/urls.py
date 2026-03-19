# ============================================================
# ============================================================
from django.urls import path
from .views import (
    BotListCreateView, BotDetailView,
    BotStartView, BotStopView, BotPauseView, BotResumeView,
    TradeListView, BotLogListView,
    NLPCommandView, NLPCommandHistoryView,
)

app_name = 'trading'

urlpatterns = [
    # ── Bot CRUD ──────────────────────────────────────────────
    path('bots/',                           BotListCreateView.as_view(), name='bot-list'),
    path('bots/<uuid:pk>/',                 BotDetailView.as_view(),     name='bot-detail'),

    # ── Bot Controls ──────────────────────────────────────────
    path('bots/<uuid:pk>/start/',           BotStartView.as_view(),      name='bot-start'),
    path('bots/<uuid:pk>/stop/',            BotStopView.as_view(),       name='bot-stop'),
    path('bots/<uuid:pk>/pause/',           BotPauseView.as_view(),      name='bot-pause'),
    path('bots/<uuid:pk>/resume/',          BotResumeView.as_view(),     name='bot-resume'),

    # ── Trade History ─────────────────────────────────────────
    path('bots/<uuid:bot_id>/trades/',      TradeListView.as_view(),     name='trade-list'),

    # ── Bot Logs ──────────────────────────────────────────────
    path('bots/<uuid:bot_id>/logs/',        BotLogListView.as_view(),    name='bot-log-list'),

    # ── NLP Commands ──────────────────────────────────────────
    path('command/',                        NLPCommandView.as_view(),        name='nlp-command'),
    path('commands/',                       NLPCommandHistoryView.as_view(), name='nlp-history'),
]