# ============================================================
# Tracks open positions and syncs with broker state
# ============================================================
import logging
from typing import List, Optional, Dict
from django.utils import timezone as dj_tz

from apps.trading.models import Trade, TradingBot
from utils.constants import TradeStatus

logger = logging.getLogger('trading')


class PositionTracker:
    """
    Keeps track of all open positions for a bot and reconciles
    them against the live broker state.

    Responsibilities:
      - Count open trades per symbol
      - Detect stale positions (open in DB but closed at broker)
      - Check trailing stop conditions
      - Provide position summary for risk manager
    """

    def __init__(self, bot: TradingBot, broker):
        self.bot    = bot
        self.broker = broker

    def get_open_trades_db(self) -> List[Trade]:
        """All open trades for this bot from the database."""
        return list(
            Trade.objects.filter(
                bot=self.bot, status=TradeStatus.OPEN
            ).select_related('bot')
        )

    def get_open_count(self) -> int:
        return Trade.objects.filter(
            bot=self.bot, status=TradeStatus.OPEN
        ).count()

    def get_open_count_for_symbol(self, symbol: str) -> int:
        return Trade.objects.filter(
            bot=self.bot, status=TradeStatus.OPEN, symbol=symbol
        ).count()

    def sync_with_broker(self) -> Dict:
        """
        Compare DB open trades with broker open positions.
        Close any trades in DB that are no longer open at broker
        (closed by SL/TP at broker side).
        Returns summary of what was synced.
        """
        synced = {'closed': 0, 'updated': 0, 'errors': 0}

        try:
            broker_trades = {
                t['trade_id']: t
                for t in self.broker.get_open_trades()
            }
        except Exception as e:
            logger.error(f"PositionTracker: broker fetch failed: {e}")
            return synced

        db_trades = self.get_open_trades_db()

        for db_trade in db_trades:
            broker_id = db_trade.broker_trade_id

            if not broker_id:
                continue

            if broker_id not in broker_trades:
                # Trade closed at broker (SL/TP or manual close)
                self._mark_closed_by_broker(db_trade)
                synced['closed'] += 1
            else:
                # Update unrealised P&L
                broker_t = broker_trades[broker_id]
                try:
                    db_trade.profit_loss = broker_t.get('unrealized_pl', 0)
                    db_trade.save(update_fields=['profit_loss'])
                    synced['updated'] += 1
                except Exception as e:
                    logger.warning(f"Could not update P&L for trade {db_trade.id}: {e}")
                    synced['errors'] += 1

        return synced

    def check_trailing_stops(self, current_prices: Dict[str, Dict]) -> List[str]:
        """
        Check if any open trades need trailing stop adjustments.
        Returns list of trade IDs that were updated.
        """
        if not self.bot.risk_settings.get('trailing_stop_enabled', False):
            return []

        updated = []
        trail_pips = self.bot.risk_settings.get('trailing_stop_pips', 20)

        for trade in self.get_open_trades_db():
            price_data = current_prices.get(trade.symbol)
            if not price_data or not trade.entry_price:
                continue

            pip_size    = 0.01 if 'JPY' in trade.symbol else 0.0001
            trail_price = trail_pips * pip_size

            if trade.order_type == 'buy':
                current_bid  = float(price_data.get('bid', 0))
                new_sl       = round(current_bid - trail_price, 5)
                current_sl   = float(trade.stop_loss or 0)
                if new_sl > current_sl:
                    try:
                        trade.stop_loss = new_sl
                        trade.save(update_fields=['stop_loss'])
                        updated.append(str(trade.id))
                        logger.debug(
                            f"Trailing stop updated: {trade.symbol} "
                            f"SL {current_sl:.5f} → {new_sl:.5f}"
                        )
                    except Exception as e:
                        logger.warning(f"Trailing stop update failed: {e}")

            elif trade.order_type == 'sell':
                current_ask = float(price_data.get('ask', 0))
                new_sl      = round(current_ask + trail_price, 5)
                current_sl  = float(trade.stop_loss or 999)
                if new_sl < current_sl:
                    try:
                        trade.stop_loss = new_sl
                        trade.save(update_fields=['stop_loss'])
                        updated.append(str(trade.id))
                    except Exception as e:
                        logger.warning(f"Trailing stop update failed: {e}")

        return updated

    def _mark_closed_by_broker(self, trade: Trade):
        """Mark a trade as closed when broker reports it no longer open."""
        try:
            trade.status    = TradeStatus.CLOSED
            trade.closed_at = dj_tz.now()
            trade.save(update_fields=['status', 'closed_at'])

            from apps.trading.models import BotLog
            BotLog.objects.create(
                bot        = self.bot,
                trade      = trade,
                level      = BotLog.Level.INFO,
                event_type = BotLog.EventType.ORDER_CLOSED,
                message    = (
                    f"Trade {trade.symbol} closed by broker "
                    f"(SL/TP/manual) — synced from broker state"
                ),
                data = {'broker_trade_id': trade.broker_trade_id},
            )
            logger.info(
                f"Trade {trade.id} ({trade.symbol}) marked closed — "
                f"no longer open at broker"
            )
        except Exception as e:
            logger.error(f"_mark_closed_by_broker failed: {e}")

    def get_summary(self) -> Dict:
        """Summary of current positions for risk manager."""
        open_trades = self.get_open_trades_db()
        total_pnl   = sum(float(t.profit_loss or 0) for t in open_trades)
        by_symbol   = {}
        for t in open_trades:
            by_symbol[t.symbol] = by_symbol.get(t.symbol, 0) + 1

        return {
            'open_count':    len(open_trades),
            'total_pnl':     round(total_pnl, 2),
            'by_symbol':     by_symbol,
            'trade_ids':     [str(t.id) for t in open_trades],
        }