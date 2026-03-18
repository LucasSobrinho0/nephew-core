import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(env_path):
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, value = line.split('=', 1)
        key = key.strip()
        if key.startswith('export '):
            key = key[7:].strip()

        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def env(key, default=None):
    return os.getenv(key, default)


def env_bool(key, default=False):
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_int(key, default=0):
    value = os.getenv(key)
    if value is None:
        return default
    return int(value)


def env_list(key, default=''):
    value = os.getenv(key, default)
    return [item.strip() for item in value.split(',') if item.strip()]


load_env_file(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY', 'django-insecure-phkcri1tr5i4cgopgn^%r)8%2-_hhjlyjp^@h_k63rc+pbzip$')
DEBUG = env_bool('DEBUG', True)
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', '127.0.0.1,localhost,testserver')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'common',
    'accounts',
    'organizations',
    'dashboard',
    'integrations',
    'companies',
    'people',
    'apollo_integration',
    'bot_conversa',
    'gmail_integration',
    'hubspot_integration',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'common.middleware.ActiveOrganizationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'common.context_processors.active_organization',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

DB_ENGINE = env('DB_ENGINE', '').strip().lower()

if DB_ENGINE not in {'postgres', 'postgresql'}:
    raise ImproperlyConfigured(
        'DB_ENGINE must be set to "postgres" or "postgresql" in the environment.'
    )

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME', ''),
        'USER': env('DB_USER', ''),
        'PASSWORD': env('DB_PASSWORD', ''),
        'HOST': env('DB_HOST', '127.0.0.1'),
        'PORT': env('DB_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = env('TIME_ZONE', 'America/Cuiaba')

USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = '/var/www/html/nephew-core/staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'

FIELD_ENCRYPTION_KEY = env('FIELD_ENCRYPTION_KEY')
EMAIL_LOOKUP_KEY = env('EMAIL_LOOKUP_KEY')
APP_CREDENTIAL_ENCRYPTION_KEY = env('APP_CREDENTIAL_ENCRYPTION_KEY')
BOT_CONVERSA_API_BASE_URL = env('BOT_CONVERSA_API_BASE_URL', 'https://backend.botconversa.com.br')
BOT_CONVERSA_API_TIMEOUT = env_int('BOT_CONVERSA_API_TIMEOUT', 30)
BOT_CONVERSA_API_AUTH_HEADER = env('BOT_CONVERSA_API_AUTH_HEADER', 'API-KEY')

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'organizations:onboarding'
LOGOUT_REDIRECT_URL = 'accounts:login'
