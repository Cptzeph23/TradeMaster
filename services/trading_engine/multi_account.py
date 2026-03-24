# ============================================================
# Multi-account manager — orchestrates bots across accounts
# ============================================================
import logging
from typing import List, Dict, Optional
from django.utils import timezone as dj_tz

logger = logging.getLogger('trading')


class MultiAccountManager:
    """
    Manages starting, stopping, and monitoring bots across
    multiple TradingAccounts simultaneously.

    Key responsibilities:
    1. Start bots on multiple accounts with one command
    2. Aggregate P&L and stats across all accounts
    3. Portfolio-level drawdown enforcement
    4. Sync account balances in parallel
    5. Copy trading — mirror signals from one account to others

    Usage:
        manager = MultiAccountManager(user)
        manager.start_all_portfolio_bots(portfolio_id)
        manager.get_portfolio_summary(portfolio_id)
    """

    def __init__(self, user):
        self.user = user

    # ── Portfolio bot control ─────────────────────────────────
    def start_all_portfolio_bots(self, portfolio_id: str) -> dict:
        """
        Start all idle/stopped bots in a portfolio simultaneously.
        Each bot gets its own Celery task on the trading queue.
        """
        from apps.accounts.portfolio_models import Portfolio
        from apps.trading.models import TradingBot
        from utils.constants import BotStatus
        from workers.tasks import run_trading_bot

        try:
            portfolio = Portfolio.objects.get(
                pk=portfolio_id, user=self.user, is_active=True
            )
        except Portfolio.DoesNotExist:
            return {'success': False, 'error': 'Portfolio not found'}

        bots = TradingBot.objects.filter(
            trading_account__in=portfolio.accounts,
            is_active=True,
        ).exclude(status=BotStatus.RUNNING)

        started = []
        errors  = []

        for bot in bots:
            try:
                if not bot.trading_account.is_verified:
                    errors.append(f"{bot.name}: account not verified")
                    continue

                task = run_trading_bot.apply_async(
                    args=[str(bot.id)], queue='trading'
                )
                bot.celery_task_id = task.id
                bot.status         = BotStatus.RUNNING
                bot.started_at     = dj_tz.now()
                bot.save(update_fields=['celery_task_id', 'status', 'started_at'])
                started.append(bot.name)
                logger.info(
                    f"MultiAccount: started bot '{bot.name}' "
                    f"on account '{bot.trading_account.name}'"
                )
            except Exception as e:
                errors.append(f"{bot.name}: {str(e)}")

        return {
            'success':  True,
            'started':  started,
            'errors':   errors,
            'count':    len(started),
        }

    def stop_all_portfolio_bots(self, portfolio_id: str) -> dict:
        """Stop all running bots in a portfolio."""
        from apps.accounts.portfolio_models import Portfolio
        from apps.trading.models import TradingBot
        from utils.constants import BotStatus
        from config.celery import app as celery_app

        try:
            portfolio = Portfolio.objects.get(
                pk=portfolio_id, user=self.user, is_active=True
            )
        except Portfolio.DoesNotExist:
            return {'success': False, 'error': 'Portfolio not found'}

        bots = TradingBot.objects.filter(
            trading_account__in=portfolio.accounts,
            status__in=[BotStatus.RUNNING, BotStatus.PAUSED],
            is_active=True,
        )

        stopped = []
        for bot in bots:
            if bot.celery_task_id:
                try:
                    celery_app.control.revoke(bot.celery_task_id, terminate=True)
                except Exception:
                    pass
            bot.status     = BotStatus.STOPPED
            bot.stopped_at = dj_tz.now()
            bot.save(update_fields=['status', 'stopped_at'])
            stopped.append(bot.name)

        return {'success': True, 'stopped': stopped, 'count': len(stopped)}

    # ── Portfolio analytics ───────────────────────────────────
    def get_portfolio_summary(self, portfolio_id: str) -> dict:
        """
        Full portfolio snapshot — aggregated across all accounts.
        Returns one dict suitable for the dashboard overview card.
        """
        from apps.accounts.portfolio_models import Portfolio
        from apps.trading.models import TradingBot, Trade
        from utils.constants import BotStatus, TradeStatus
        from apps.risk_management.calculator import RiskCalculator
        from datetime import datetime, timezone

        try:
            portfolio = Portfolio.objects.get(
                pk=portfolio_id, user=self.user, is_active=True
            )
        except Portfolio.DoesNotExist:
            return {}

        accounts = list(portfolio.accounts)

        # All closed trades across portfolio
        all_trades = Trade.objects.filter(
            bot__trading_account__in=accounts,
            status=TradeStatus.CLOSED,
        )
        pnl_list    = [float(t.profit_loss or 0) for t in all_trades]
        total_pnl   = round(sum(pnl_list), 2)
        win_rate    = RiskCalculator.win_rate(pnl_list)
        pf          = RiskCalculator.profit_factor(pnl_list)

        # All bots across portfolio
        all_bots = TradingBot.objects.filter(
            trading_account__in=accounts, is_active=True
        )
        running  = all_bots.filter(status=BotStatus.RUNNING).count()

        # Open trades
        open_trades = Trade.objects.filter(
            bot__trading_account__in=accounts,
            status=TradeStatus.OPEN,
        ).count()

        # Today's P&L
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_pnl = round(sum(
            float(t.profit_loss or 0)
            for t in Trade.objects.filter(
                bot__trading_account__in=accounts,
                status=TradeStatus.CLOSED,
                closed_at__gte=today_start,
            )
        ), 2)

        # Per-account breakdown
        account_breakdown = []
        for acct in accounts:
            acct_bots  = all_bots.filter(trading_account=acct)
            acct_pnl   = sum(
                float(t.profit_loss or 0)
                for t in Trade.objects.filter(
                    bot__trading_account=acct,
                    status=TradeStatus.CLOSED,
                )
            )
            account_breakdown.append({
                'id':       str(acct.id),
                'name':     acct.name,
                'broker':   acct.broker,
                'type':     acct.account_type,
                'balance':  float(acct.balance or 0),
                'equity':   float(acct.equity or 0),
                'pnl':      round(acct_pnl, 2),
                'bots':     acct_bots.count(),
                'running':  acct_bots.filter(status=BotStatus.RUNNING).count(),
                'verified': acct.is_verified,
            })

        return {
            'portfolio_id':   str(portfolio.id),
            'portfolio_name': portfolio.name,
            'total_balance':  portfolio.total_balance,
            'total_equity':   portfolio.total_equity,
            'total_pnl':      total_pnl,
            'today_pnl':      today_pnl,
            'win_rate':       win_rate,
            'profit_factor':  pf,
            'total_trades':   len(pnl_list),
            'running_bots':   running,
            'total_bots':     all_bots.count(),
            'open_trades':    open_trades,
            'accounts':       account_breakdown,
            'equity_curve':   portfolio.get_equity_curve()[-100:],
        }

    # ── Parallel balance sync ─────────────────────────────────
    def sync_all_balances(self, portfolio_id: str) -> dict:
        """
        Sync balance/equity for all accounts in a portfolio
        by queuing individual sync tasks in parallel.
        """
        from apps.accounts.portfolio_models import Portfolio
        from apps.market_data.tasks import sync_account_balance

        try:
            portfolio = Portfolio.objects.get(
                pk=portfolio_id, user=self.user, is_active=True
            )
        except Portfolio.DoesNotExist:
            return {'success': False, 'error': 'Portfolio not found'}

        queued = 0
        for acct in portfolio.accounts:
            sync_account_balance.apply_async(
                args=[str(acct.id)], queue='default'
            )
            queued += 1

        return {'success': True, 'synced': queued}

    # ── Copy trading ──────────────────────────────────────────
    def mirror_signal_to_accounts(
        self,
        signal_data: dict,
        source_account_id: str,
        target_account_ids: List[str],
        lot_scale: float = 1.0,
    ) -> dict:
        """
        Copy a trade signal from one account's bot to other accounts.
        Scales lot size proportionally to each account's balance.

        Used for copy trading across demo → live or across multiple
        live accounts with different risk allocations.
        """
        from apps.accounts.models import TradingAccount
        from apps.strategies.base import Signal
        from workers.tasks import execute_order
        from apps.risk_management.calculator import RiskCalculator

        results = []

        try:
            source = TradingAccount.objects.get(
                pk=source_account_id, user=self.user
            )
            source_balance = float(source.balance or 10000)
        except TradingAccount.DoesNotExist:
            return {'success': False, 'error': 'Source account not found'}

        for acct_id in target_account_ids:
            try:
                target  = TradingAccount.objects.get(
                    pk=acct_id, user=self.user, is_active=True
                )
                if not target.is_verified:
                    results.append({'account': acct_id, 'status': 'skipped', 'reason': 'not verified'})
                    continue

                # Find a running bot on this target account
                from apps.trading.models import TradingBot
                from utils.constants import BotStatus
                bot = TradingBot.objects.filter(
                    trading_account=target,
                    status=BotStatus.RUNNING,
                    is_active=True,
                ).first()

                if not bot:
                    results.append({'account': target.name, 'status': 'skipped', 'reason': 'no running bot'})
                    continue

                # Scale lot size proportionally to target account balance
                target_balance = float(target.balance or 10000)
                scale_factor   = (target_balance / source_balance) * lot_scale
                scaled_signal  = {
                    **signal_data,
                    'lot_size': round(
                        signal_data.get('lot_size', 0.01) * scale_factor, 2
                    ),
                    'reason': f"[Mirror from {source.name}] {signal_data.get('reason', '')}",
                }

                task = execute_order.apply_async(
                    args=[str(bot.id), scaled_signal],
                    queue='orders',
                )
                results.append({
                    'account':    target.name,
                    'status':     'queued',
                    'task_id':    task.id,
                    'lot_scaled': scaled_signal['lot_size'],
                })
                logger.info(
                    f"Mirror trade: {source.name} → {target.name}, "
                    f"lot={scaled_signal['lot_size']}"
                )

            except Exception as e:
                results.append({'account': acct_id, 'status': 'error', 'reason': str(e)})

        return {'success': True, 'results': results}