# ============================================================
# DESTINATION: /opt/forex_bot/config/wsgi.py
# WSGI Configuration (used by Gunicorn for non-WS traffic)
# ============================================================
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_wsgi_application()
