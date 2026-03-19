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
    """
    try:
        instance.bot.__class__.objects.filter(pk=instance.bot_id).update(
            risk_settings=instance.to_dict()
        )
    except Exception as e:
        import logging
        logging.getLogger('risk_management').error(
            f"sync_risk_settings_to_bot failed: {e}"
        )
 