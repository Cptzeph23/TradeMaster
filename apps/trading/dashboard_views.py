# ============================================================
# Django views that serve the HTML dashboard templates
# ============================================================
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from utils.constants import MAJOR_FOREX_PAIRS, ALL_FOREX_PAIRS, Timeframe


@login_required
def dashboard(request):
    return render(request, 'dashboard/dashboard.html', {
        'major_pairs': MAJOR_FOREX_PAIRS,
        'page':        'dashboard',
    })


@login_required
def bots_list(request):
    return render(request, 'dashboard/bots.html', {
        'page': 'bots',
    })


@login_required
def bot_detail(request, bot_id):
    return render(request, 'dashboard/bot_detail.html', {
        'bot_id': bot_id,
        'page':   'bots',
    })


@login_required
def strategies_list(request):
    return render(request, 'dashboard/strategies.html', {
        'page': 'strategies',
    })


@login_required
def backtesting_page(request):
    return render(request, 'dashboard/backtesting.html', {
        'pairs':      ALL_FOREX_PAIRS,
        'timeframes': [t.value for t in Timeframe],
        'page':       'backtesting',
    })


@login_required
def market_data_page(request):
    return render(request, 'dashboard/market_data.html', {
        'pairs':      MAJOR_FOREX_PAIRS,
        'timeframes': [t.value for t in Timeframe],
        'page':       'market',
    })


@login_required
def risk_page(request):
    return render(request, 'dashboard/risk.html', {
        'page': 'risk',
    })


def login_page(request):
    if request.user.is_authenticated:
        return redirect('/dashboard/')
    return render(request, 'accounts/login.html')


def register_page(request):
    if request.user.is_authenticated:
        return redirect('/dashboard/')
    return render(request, 'accounts/register.html')