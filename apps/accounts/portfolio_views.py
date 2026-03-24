# ============================================================
# Portfolio REST API endpoints
# ============================================================
import logging
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers

from .portfolio_models import Portfolio, AccountAllocation
from .models import TradingAccount
from services.trading_engine.multi_account import MultiAccountManager

logger = logging.getLogger('trading')


def ok(data, code=status.HTTP_200_OK):
    return Response({'success': True, **data}, status=code)

def err(msg, code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': msg}, status=code)


# ── Serializers ───────────────────────────────────────────────
class PortfolioCreateSerializer(serializers.ModelSerializer):
    account_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )

    class Meta:
        model  = Portfolio
        fields = ('name', 'description', 'is_default', 'account_ids')

    def validate_name(self, value):
        user = self.context['request'].user
        if Portfolio.objects.filter(user=user, name=value).exists():
            raise serializers.ValidationError(
                f"You already have a portfolio named '{value}'."
            )
        return value


class AllocationSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    broker       = serializers.CharField(source='account.broker', read_only=True)

    class Meta:
        model  = AccountAllocation
        fields = ('id', 'account', 'account_name', 'broker',
                  'allocation_pct', 'max_drawdown_pct', 'is_active')


# ── Views ─────────────────────────────────────────────────────
class PortfolioListCreateView(APIView):
    """
    GET  /api/v1/accounts/portfolios/   — list all portfolios
    POST /api/v1/accounts/portfolios/   — create a portfolio
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        portfolios = Portfolio.objects.filter(
            user=request.user, is_active=True
        )
        manager = MultiAccountManager(request.user)
        data = []
        for p in portfolios:
            summary = manager.get_portfolio_summary(str(p.id))
            data.append({
                'id':          str(p.id),
                'name':        p.name,
                'description': p.description,
                'is_default':  p.is_default,
                'accounts':    p.accounts.count(),
                'balance':     summary.get('total_balance', 0),
                'pnl':         summary.get('total_pnl', 0),
                'running_bots':summary.get('running_bots', 0),
                'open_trades': summary.get('open_trades', 0),
            })
        return ok({'portfolios': data, 'count': len(data)})

    def post(self, request):
        s = PortfolioCreateSerializer(
            data=request.data, context={'request': request}
        )
        if not s.is_valid():
            return err(str(s.errors))

        # If this is set as default, unset others
        if s.validated_data.get('is_default'):
            Portfolio.objects.filter(
                user=request.user, is_default=True
            ).update(is_default=False)

        portfolio   = Portfolio.objects.create(
            user        = request.user,
            name        = s.validated_data['name'],
            description = s.validated_data.get('description', ''),
            is_default  = s.validated_data.get('is_default', False),
        )

        # Attach accounts if provided
        account_ids = s.validated_data.get('account_ids', [])
        for acct_id in account_ids:
            try:
                acct = TradingAccount.objects.get(
                    pk=acct_id, user=request.user
                )
                acct.portfolio = portfolio
                acct.save(update_fields=['portfolio'])
                AccountAllocation.objects.create(
                    portfolio=portfolio, account=acct
                )
            except TradingAccount.DoesNotExist:
                pass

        return ok({
            'message':      'Portfolio created.',
            'portfolio_id': str(portfolio.id),
        }, code=status.HTTP_201_CREATED)


class PortfolioDetailView(APIView):
    """
    GET    /api/v1/accounts/portfolios/<id>/  — full portfolio summary
    PATCH  /api/v1/accounts/portfolios/<id>/  — update name/description
    DELETE /api/v1/accounts/portfolios/<id>/  — delete portfolio
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get(self, pk):
        try:
            return Portfolio.objects.get(
                pk=pk, user=self.request.user, is_active=True
            )
        except Portfolio.DoesNotExist:
            return None

    def get(self, request, pk):
        portfolio = self._get(pk)
        if not portfolio:
            return err('Portfolio not found.', code=status.HTTP_404_NOT_FOUND)

        manager = MultiAccountManager(request.user)
        summary = manager.get_portfolio_summary(str(portfolio.id))
        return ok({'portfolio': summary})

    def patch(self, request, pk):
        portfolio = self._get(pk)
        if not portfolio:
            return err('Portfolio not found.', code=status.HTTP_404_NOT_FOUND)

        if 'name' in request.data:
            portfolio.name = request.data['name']
        if 'description' in request.data:
            portfolio.description = request.data['description']
        if request.data.get('is_default'):
            Portfolio.objects.filter(
                user=request.user, is_default=True
            ).update(is_default=False)
            portfolio.is_default = True
        portfolio.save()
        return ok({'message': 'Portfolio updated.'})

    def delete(self, request, pk):
        portfolio = self._get(pk)
        if not portfolio:
            return err('Portfolio not found.', code=status.HTTP_404_NOT_FOUND)
        portfolio.is_active = False
        portfolio.save(update_fields=['is_active'])
        return ok({'message': 'Portfolio deleted.'})


class PortfolioBotControlView(APIView):
    """
    POST /api/v1/accounts/portfolios/<id>/start/  — start all bots
    POST /api/v1/accounts/portfolios/<id>/stop/   — stop all bots
    POST /api/v1/accounts/portfolios/<id>/sync/   — sync all balances
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, action):
        try:
            Portfolio.objects.get(
                pk=pk, user=request.user, is_active=True
            )
        except Portfolio.DoesNotExist:
            return err('Portfolio not found.', code=status.HTTP_404_NOT_FOUND)

        manager = MultiAccountManager(request.user)

        if action == 'start':
            result = manager.start_all_portfolio_bots(str(pk))
        elif action == 'stop':
            result = manager.stop_all_portfolio_bots(str(pk))
        elif action == 'sync':
            result = manager.sync_all_balances(str(pk))
        else:
            return err(f'Unknown action: {action}')

        return ok(result)


class PortfolioAccountsView(APIView):
    """
    GET  /api/v1/accounts/portfolios/<id>/accounts/         — list accounts
    POST /api/v1/accounts/portfolios/<id>/accounts/add/     — add account
    POST /api/v1/accounts/portfolios/<id>/accounts/remove/  — remove account
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            portfolio = Portfolio.objects.get(
                pk=pk, user=request.user, is_active=True
            )
        except Portfolio.DoesNotExist:
            return err('Portfolio not found.', code=status.HTTP_404_NOT_FOUND)

        allocations = AccountAllocation.objects.filter(
            portfolio=portfolio
        ).select_related('account')

        data = AllocationSerializer(allocations, many=True).data
        return ok({'accounts': data, 'count': len(data)})

    def post(self, request, pk, action):
        try:
            portfolio = Portfolio.objects.get(
                pk=pk, user=request.user, is_active=True
            )
        except Portfolio.DoesNotExist:
            return err('Portfolio not found.', code=status.HTTP_404_NOT_FOUND)

        account_id = request.data.get('account_id')
        if not account_id:
            return err('account_id is required.')

        try:
            account = TradingAccount.objects.get(
                pk=account_id, user=request.user
            )
        except TradingAccount.DoesNotExist:
            return err('Trading account not found.')

        if action == 'add':
            alloc, created = AccountAllocation.objects.get_or_create(
                portfolio=portfolio,
                account=account,
                defaults={
                    'allocation_pct':  request.data.get('allocation_pct', 100.0),
                    'max_drawdown_pct':request.data.get('max_drawdown_pct', 20.0),
                }
            )
            if not created:
                alloc.is_active = True
                alloc.save(update_fields=['is_active'])
            return ok({'message': f"Account '{account.name}' added to portfolio."})

        elif action == 'remove':
            AccountAllocation.objects.filter(
                portfolio=portfolio, account=account
            ).update(is_active=False)
            return ok({'message': f"Account '{account.name}' removed from portfolio."})

        return err(f'Unknown action: {action}')


class PortfolioMirrorView(APIView):
    """
    POST /api/v1/accounts/portfolios/<id>/mirror/
    Mirror a signal from one account to others in the portfolio.
    Body: {source_account_id, target_account_ids, signal_data, lot_scale}
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        source_id  = request.data.get('source_account_id')
        target_ids = request.data.get('target_account_ids', [])
        signal     = request.data.get('signal_data', {})
        lot_scale  = float(request.data.get('lot_scale', 1.0))

        if not source_id or not target_ids or not signal:
            return err('source_account_id, target_account_ids, and signal_data are required.')

        manager = MultiAccountManager(request.user)
        result  = manager.mirror_signal_to_accounts(
            signal_data        = signal,
            source_account_id  = source_id,
            target_account_ids = target_ids,
            lot_scale          = lot_scale,
        )
        return ok(result)