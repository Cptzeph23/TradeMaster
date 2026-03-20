# ============================================================
# Django views that serve the HTML dashboard templates
# ============================================================
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from utils.constants import MAJOR_FOREX_PAIRS, ALL_FOREX_PAIRS, Timeframe
 
 
def dashboard(request):
    return render(request, 'dashboard/dashboard.html', {
        'major_pairs': MAJOR_FOREX_PAIRS,
        'page':        'dashboard',
    })
 
 
def bots_list(request):
    return render(request, 'dashboard/bots.html', {
        'page': 'bots',
    })
 
 
def bot_detail(request, bot_id):
    return render(request, 'dashboard/bot_detail.html', {
        'bot_id': str(bot_id),
        'page':   'bots',
    })
 
 
def strategies_list(request):
    return render(request, 'dashboard/strategies.html', {
        'page': 'strategies',
    })
 
 
def backtesting_page(request):
    return render(request, 'dashboard/backtesting.html', {
        'pairs':      ALL_FOREX_PAIRS,
        'timeframes': [t.value for t in Timeframe],
        'page':       'backtesting',
    })
 
 
def market_data_page(request):
    return render(request, 'dashboard/market_data.html', {
        'pairs':      MAJOR_FOREX_PAIRS,
        'timeframes': [t.value for t in Timeframe],
        'page':       'market',
    })
 
 
def risk_page(request):
    return render(request, 'dashboard/risk.html', {
        'page': 'risk',
    })
 
 
def login_page(request):
    # If they already have a valid token, go straight to dashboard
    # (checked client-side in login.html JS)
    return render(request, 'accounts/login.html')
 
 
def register_page(request):
    return render(request, 'accounts/register.html')
 