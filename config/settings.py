# ============================================================
# DESTINATION: /opt/forex_bot/config/settings.py
# Master Django settings file for Forex Trading Bot Platform
# ============================================================
import os
from pathlib import Path
from datetime import timedelta
import environ

# ── Base Directory ───────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ── Load Environment Variables ───────────────────────────────
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1']),
)
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# ── Core Settings ────────────────────────────────────────────
SECRET_KEY = env('DJANGO_SECRET_KEY')
DEBUG = env('DJANGO_DEBUG', default=False)
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

# ── Application Definition ───────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    # REST Framework
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'corsheaders',
    'django_filters',

    # Async / Workers
    'channels',
    'celery',
    'django_celery_beat',
    'django_celery_results',

    # Utilities
    'django_extensions',
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.trading',
    'apps.strategies',
    'apps.backtesting',
    'apps.market_data',
    'apps.risk_management',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware ───────────────────────────────────────────────
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'utils.decorators.RequestLoggingMiddleware',   # custom
]

ROOT_URLCONF = 'config.urls'

# ── Templates ────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ── ASGI / WSGI ─────────────────────────────────────────────
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ── Database ─────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME', default='forex_bot_db'),
        'USER': env('DB_USER', default='forex_user'),
        'PASSWORD': env('DB_PASSWORD', default=''),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# ── Cache / Redis ────────────────────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('CACHE_BACKEND', default='redis://localhost:6379/3'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'TIMEOUT': 300,
    }
}

# ── Auth Password Validators ─────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTH_USER_MODEL = 'accounts.User'

# ── Password Hashers ─────────────────────────────────────────
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

# ── Internationalisation ─────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ── Static & Media Files ─────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Django REST Framework ────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'trading': '200/hour',       # custom scope for order endpoints
        'commands': '100/hour',      # custom scope for NLP command endpoints
    },
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'EXCEPTION_HANDLER': 'utils.helpers.custom_exception_handler',
}

# ── JWT Settings ─────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=env.int('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', default=60)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=env.int('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}

# ── CORS ─────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8080',
])
CORS_ALLOW_CREDENTIALS = True

# ── Django Channels ──────────────────────────────────────────
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [(
                env('CHANNEL_LAYERS_HOST', default='localhost'),
                env.int('CHANNEL_LAYERS_PORT', default=6379)
            )],
        },
    },
}

# ── Celery ───────────────────────────────────────────────────
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://localhost:6379/1')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default='redis://localhost:6379/2')
CELERY_RESULT_EXTENDED = True
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60        # 30 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60   # 25 minutes soft limit
CELERY_WORKER_PREFETCH_MULTIPLIER = 1   # fair dispatch for long-running tasks
CELERY_TASK_ROUTES = {
    'workers.tasks.run_trading_bot': {'queue': 'trading'},
    'workers.tasks.execute_order': {'queue': 'orders'},
    'workers.tasks.run_backtest': {'queue': 'backtesting'},
    'workers.tasks.fetch_market_data': {'queue': 'data'},
    'workers.tasks.process_nlp_command': {'queue': 'commands'},
}

# ── DRF Spectacular (OpenAPI) ────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'Forex Trading Bot API',
    'DESCRIPTION': 'Production-grade automated forex trading platform with AI command interface.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# ── Broker API Settings ──────────────────────────────────────
OANDA_API_KEY = env('OANDA_API_KEY', default='')
OANDA_ACCOUNT_ID = env('OANDA_ACCOUNT_ID', default='')
OANDA_ENVIRONMENT = env('OANDA_ENVIRONMENT', default='practice')

MT5_LOGIN = env('MT5_LOGIN', default='')
MT5_PASSWORD = env('MT5_PASSWORD', default='')
MT5_SERVER = env('MT5_SERVER', default='')

ALPHA_VANTAGE_API_KEY = env('ALPHA_VANTAGE_API_KEY', default='')

# ── AI / NLP Command Interface ───────────────────────────────
ANTHROPIC_API_KEY = env('ANTHROPIC_API_KEY', default='')
OPENAI_API_KEY = env('OPENAI_API_KEY', default='')
NLP_MODEL = 'claude-3-5-sonnet-20241022'     # Model used for command parsing

# ── Encryption ───────────────────────────────────────────────
ENCRYPTION_KEY = env('ENCRYPTION_KEY', default='')

# ── App-specific Settings ────────────────────────────────────
MAX_BOTS_PER_USER = env.int('MAX_BOTS_PER_USER', default=10)
MAX_TRADES_PER_DAY = env.int('MAX_TRADES_PER_DAY', default=50)
DEFAULT_RISK_PERCENT = env.float('DEFAULT_RISK_PERCENT', default=1.0)

# ── Logging ──────────────────────────────────────────────────
LOG_LEVEL = env('LOG_LEVEL', default='INFO')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {process:d} {thread:d} | {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{asctime}] {levelname} {message}',
            'style': '{',
        },
        'json': {
            '()': 'structlog.stdlib.ProcessorFormatter',
            'processor': 'structlog.dev.ConsoleRenderer',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file_general': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'file_trading': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'trading.log',
            'maxBytes': 1024 * 1024 * 50,  # 50MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'file_errors': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'errors.log',
            'maxBytes': 1024 * 1024 * 10,
            'backupCount': 5,
            'formatter': 'verbose',
            'level': 'ERROR',
        },
    },
    'root': {
        'handlers': ['console', 'file_general'],
        'level': LOG_LEVEL,
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_general'],
            'level': 'INFO',
            'propagate': False,
        },
        'trading': {
            'handlers': ['console', 'file_trading'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'trading.orders': {
            'handlers': ['file_trading', 'file_errors'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'celery': {
            'handlers': ['console', 'file_general'],
            'level': 'INFO',
        },
    },
}

# ── Sentry ───────────────────────────────────────────────────
SENTRY_DSN = env('SENTRY_DSN', default=None)
if SENTRY_DSN and SENTRY_DSN.strip() and SENTRY_DSN.startswith('http'):
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

# ── Security (production) ────────────────────────────────────
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
