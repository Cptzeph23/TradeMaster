# ============================================================
# Django view that receives Telegram webhook POST requests
# ============================================================
import json
import logging
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings

logger = logging.getLogger('telegram_bot')


@csrf_exempt
@require_POST
def telegram_webhook(request):
    """
    POST /api/v1/telegram/webhook/<secret_token>/
    Telegram sends all updates here as JSON.
    The secret_token in the URL prevents spoofing.
    """
    # Verify secret token
    url_token = request.resolver_match.kwargs.get('secret_token', '')
    expected  = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')

    if expected and url_token != expected:
        logger.warning(f"Telegram webhook: invalid secret token")
        return HttpResponseForbidden("Invalid token")

    try:
        update_data = json.loads(request.body)
        logger.debug(f"Telegram update received: {str(update_data)[:200]}")

        # Process async via Celery to keep webhook response fast
        from workers.tasks import process_telegram_update
        process_telegram_update.apply_async(
            args=[update_data],
            queue='commands',
        )
        return JsonResponse({'ok': True})

    except json.JSONDecodeError:
        logger.error("Telegram webhook: invalid JSON body")
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}", exc_info=True)
        return JsonResponse({'ok': True})   # Always 200 to Telegram