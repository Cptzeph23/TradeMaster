# ============================================================
# Sync RiskRule → TradingBot.risk_settings JSON on every save
# ============================================================
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='risk_management.RiskRule')
def sync_risk_settings_to_bot(sender, instance, **kwargs):
    """
    Whenever a RiskRule is saved, push the serialised dict
    into the linked TradingBot.risk_settings JSON field.
    This keeps the fast-access JSON in sync with the DB record.
    """
    bot = instance.bot
    bot.risk_settings = instance.to_dict()
    # Only update this field — avoid triggering full bot save signal
    bot.__class__.objects.filter(pk=bot.pk).update(
        risk_settings=instance.to_dict()
    )