# ============================================================
# Django management command for local dev polling mode
# Usage: python manage.py telegram_poll
# ============================================================
from django.core.management.base import BaseCommand
import logging
import time

logger = logging.getLogger('telegram_bot')


class Command(BaseCommand):
    help = 'Start Telegram bot in polling mode (development only)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval', type=float, default=2.0,
            help='Polling interval in seconds (default: 2)'
        )

    def handle(self, *args, **options):
        from services.telegram.bot import get_telegram_bot
        from django.conf import settings

        bot      = get_telegram_bot()
        interval = options['interval']

        if not bot.is_configured():
            self.stderr.write(
                self.style.ERROR(
                    'TELEGRAM_BOT_TOKEN not set in .env\n'
                    'Run: bash setup_telegram.sh'
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'\n🤖 Telegram bot polling started (interval={interval}s)\n'
                f'Send /help to your bot to test\n'
                f'Press Ctrl+C to stop\n'
            )
        )

        tg_bot  = bot._get_bot()
        offset  = None

        try:
            while True:
                try:
                    updates = tg_bot.get_updates(
                        offset=offset,
                        timeout=30,
                        allowed_updates=['message'],
                    )

                    for update in updates:
                        offset = update.update_id + 1
                        bot.handle_update(update.to_dict())

                except Exception as e:
                    logger.debug(f"Polling error: {e}")

                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write('\n✅ Polling stopped')