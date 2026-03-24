# ============================================================
# Add to config/urls.py:
#   from apps.accounts.portfolio_urls import portfolio_urlpatterns
#   path('api/v1/accounts/', include((portfolio_urlpatterns, 'portfolios'))),
# ============================================================
from django.urls import path
from .portfolio_views import (
    PortfolioListCreateView,
    PortfolioDetailView,
    PortfolioBotControlView,
    PortfolioAccountsView,
    PortfolioMirrorView,
)

portfolio_urlpatterns = [
    path('portfolios/',
         PortfolioListCreateView.as_view(),          name='portfolio-list'),
    path('portfolios/<uuid:pk>/',
         PortfolioDetailView.as_view(),              name='portfolio-detail'),
    path('portfolios/<uuid:pk>/<str:action>/',
         PortfolioBotControlView.as_view(),          name='portfolio-control'),
    path('portfolios/<uuid:pk>/accounts/',
         PortfolioAccountsView.as_view(),            name='portfolio-accounts'),
    path('portfolios/<uuid:pk>/accounts/<str:action>/',
         PortfolioAccountsView.as_view(),            name='portfolio-accounts-action'),
    path('portfolios/<uuid:pk>/mirror/',
         PortfolioMirrorView.as_view(),              name='portfolio-mirror'),
]