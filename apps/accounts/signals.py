# ============================================================
# Auto-create UserProfile + send welcome email on registration
# ============================================================
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from .models import User, UserProfile

logger = logging.getLogger('django')


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create a UserProfile for every new User."""
    if created:
        UserProfile.objects.get_or_create(user=instance)
        logger.info(f"UserProfile auto-created for {instance.email}")


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Keep profile in sync when user is saved."""
    if hasattr(instance, 'profile'):
        instance.profile.save()


@receiver(post_save, sender=User)
def send_welcome_email(sender, instance, created, **kwargs):
    """Send a welcome email to newly registered users."""
    if not created:
        return
    try:
        send_mail(
            subject='Welcome to Forex Bot Platform',
            message=(
                f"Hi {instance.first_name or 'Trader'},\n\n"
                "Your account has been created successfully.\n\n"
                "You can now:\n"
                "  • Create and manage trading strategies\n"
                "  • Connect your broker accounts\n"
                "  • Run automated trading bots\n"
                "  • Use natural language commands to control your bots\n\n"
                "Get started at your dashboard.\n\n"
                "— Forex Bot Platform"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[instance.email],
            fail_silently=True,   # don't crash registration if email fails
        )
    except Exception as e:
        logger.warning(f"Welcome email failed for {instance.email}: {e}")