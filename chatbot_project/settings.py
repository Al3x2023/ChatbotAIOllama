from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name, default=''):
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(',') if item.strip()]


SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-dev-only-change-me')
DEBUG = env_bool('DJANGO_DEBUG', True)
ENVIRONMENT = os.getenv('DJANGO_ENV', 'development').strip().lower()

ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost')
VPS_PUBLIC_IP = os.getenv('VPS_PUBLIC_IP', '').strip()
if VPS_PUBLIC_IP and VPS_PUBLIC_IP not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(VPS_PUBLIC_IP)
if '*' in ALLOWED_HOSTS and ENVIRONMENT == 'production':
    ALLOWED_HOSTS = [h for h in ALLOWED_HOSTS if h != '*']
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS', '')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'chat',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'chatbot_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'chatbot_project.wsgi.application'

DB_ENGINE = os.getenv('DB_ENGINE', 'sqlite').strip().lower()
if DB_ENGINE == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', 'dbpreguntas'),
            'USER': os.getenv('DB_USER', 'udbpreguntas'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'bQt#9$2s'),
            'HOST': os.getenv('DB_HOST', 'bases.dev.uaemex.mx'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
            'OPTIONS': {'charset': 'utf8mb4'},
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.getenv('SQLITE_PATH', str(BASE_DIR / 'db.sqlite3')),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-mx'
TIME_ZONE = os.getenv('DJANGO_TIME_ZONE', 'America/Mexico_City')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434')
MODEL_NAME = os.getenv('MODEL_NAME', 'llama3.2:latest')
BASE_MODEL = os.getenv('BASE_MODEL', 'llama3.2:latest')
UAEMEX_BASE_URL = os.getenv('UAEMEX_BASE_URL', 'https://www.uaemex.mx/')
UAEMEX_PDF_URLS = env_list('UAEMEX_PDF_URLS', '')
UAEMEX_SEED_URLS = env_list(
    'UAEMEX_SEED_URLS',
    'https://www.uaemex.mx/,https://www.uaemex.mx/admision-y-oferta-educativa.html,https://nuevoingreso.uaemex.mx/,https://www.uaemex.mx/convocatorias.html'
)
SCRAPER_MAX_PAGES = int(os.getenv('SCRAPER_MAX_PAGES', '120'))
SCRAPER_TIMEOUT_SECONDS = int(os.getenv('SCRAPER_TIMEOUT_SECONDS', '10'))
SCRAPER_MAX_LINKS_PER_PAGE = int(os.getenv('SCRAPER_MAX_LINKS_PER_PAGE', '60'))
UAEMEX_ADMISSION_EXAM_COST_MXN = int(os.getenv('UAEMEX_ADMISSION_EXAM_COST_MXN', '702'))
UAEMEX_ADMISSION_EXAM_COST_YEAR = os.getenv('UAEMEX_ADMISSION_EXAM_COST_YEAR', '2026')
UAEMEX_ADMISSION_EXAM_SOURCE_URL = os.getenv('UAEMEX_ADMISSION_EXAM_SOURCE_URL', 'https://nuevoingreso.uaemex.mx/')

CACHE_TIMEOUT_SECONDS = int(os.getenv('CACHE_TIMEOUT_SECONDS', '900'))
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': os.getenv('CACHE_LOCATION', 'ollama-cache'),
        'TIMEOUT': CACHE_TIMEOUT_SECONDS,
        'OPTIONS': {
            'MAX_ENTRIES': int(os.getenv('CACHE_MAX_ENTRIES', '2000')),
            'CULL_FREQUENCY': int(os.getenv('CACHE_CULL_FREQUENCY', '3')),
        },
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOG_LEVEL = os.getenv('DJANGO_LOG_LEVEL', 'INFO').upper()
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {'format': '%(asctime)s %(levelname)s %(name)s %(message)s'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'standard'},
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'standard',
            'filename': str(LOG_DIR / 'chatbot.log'),
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
        },
    },
    'root': {'handlers': ['console', 'file'], 'level': LOG_LEVEL},
}

if not DEBUG or ENVIRONMENT == 'production':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', True)
    SECURE_HSTS_PRELOAD = env_bool('DJANGO_SECURE_HSTS_PRELOAD', True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
