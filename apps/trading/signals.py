from django.db.models.signals import post_save
from django.dispatch import receiver
 
 
@receiver(post_save, sender='trading.Trade')
def update_bot_drawdown(sender, instance, **kwargs):
    """
    After every trade save, recalculate the bot's current drawdown.
    """
    if not instance.bot_id:
        return
    try:
        bot = instance.bot
        if float(bot.peak_balance or 0) > 0:
            current = float(bot.trading_account.balance or 0)
            peak    = float(bot.peak_balance)
            dd      = round((peak - current) / peak * 100, 2)
            bot.__class__.objects.filter(pk=bot.pk).update(
                current_drawdown=max(0, dd)
            )
    except Exception:
        pass