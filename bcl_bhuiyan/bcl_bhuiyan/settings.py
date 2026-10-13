
"""
Django settings for bcl_bhuiyan project.

IELTS Mock Test Platform
Development Configuration
"""

from pathlib import Path
from decouple import config, Csv
from django.core.exceptions import ImproperlyConfigured


# ==========================================
# 1. BASE DIRECTORY
# ==========================================

BASE_DIR = Path(__file__).resolve().parent.parent


# ==========================================
# 2. SECURITY CONFIGURATION
# ==========================================

SECRET_KEY = config(
    'DJANGO_SECRET_KEY',
    default=''
)

if not SECRET_KEY or SECRET_KEY == '':
    raise ImproperlyConfigured(
        "Set a valid DJANGO_SECRET_KEY in your .env file."
    )

DEBUG = config(
    'DJANGO_DEBUG',
    default=False,
    cast=bool
)

ALLOWED_HOSTS = config(
    'DJANGO_ALLOWED_HOSTS',
    default='127.0.0.1,localhost',
    cast=Csv()
)


# ==========================================
# 3. APPLICATION DEFINITION
# ==========================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Local apps
    'bcl',
]


# ==========================================
# 4. MIDDLEWARE
# ==========================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',

    'django.middleware.common.CommonMiddleware',

    'django.middleware.csrf.CsrfViewMiddleware',

    'django.contrib.auth.middleware.AuthenticationMiddleware',

    'django.contrib.messages.middleware.MessageMiddleware',

    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ==========================================
# 5. URL CONFIGURATION
# ==========================================

ROOT_URLCONF = 'bcl_bhuiyan.urls'


# ==========================================
# 6. TEMPLATE CONFIGURATION
# ==========================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',

        'DIRS': [
            BASE_DIR / 'templates',
        ],

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


# ==========================================
# 7. WSGI CONFIGURATION
# ==========================================

WSGI_APPLICATION = 'bcl_bhuiyan.wsgi.application'


# ==========================================
# 8. DATABASE CONFIGURATION
# ==========================================

DB_ENGINE = config(
    'DB_ENGINE',
    default='sqlite3'
)

if DB_ENGINE == 'sqlite3':

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',

            'NAME': BASE_DIR / config(
                'DB_NAME',
                default='db.sqlite3'
            ),
        }
    }

else:
    raise ImproperlyConfigured(
        "Unsupported DB_ENGINE. "
        "Currently configured for SQLite3."
    )


# ==========================================
# 9. PASSWORD VALIDATION
# ==========================================

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': (
            'django.contrib.auth.password_validation.'
            'UserAttributeSimilarityValidator'
        ),
    },
    {
        'NAME': (
            'django.contrib.auth.password_validation.'
            'MinimumLengthValidator'
        ),
    },
    {
        'NAME': (
            'django.contrib.auth.password_validation.'
            'CommonPasswordValidator'
        ),
    },
    {
        'NAME': (
            'django.contrib.auth.password_validation.'
            'NumericPasswordValidator'
        ),
    },
]


# ==========================================
# 10. LANGUAGE & TIMEZONE
# ==========================================

LANGUAGE_CODE = config(
    'LANGUAGE_CODE',
    default='en-us'
)

TIME_ZONE = config(
    'TIME_ZONE',
    default='Asia/Dhaka'
)

USE_I18N = True

USE_TZ = True


# ==========================================
# 11. STATIC FILE CONFIGURATION
# ==========================================

STATIC_URL = 'static/'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

STATIC_ROOT = BASE_DIR / 'staticfiles'


# ==========================================
# 12. MEDIA FILE CONFIGURATION
# ==========================================

MEDIA_URL = 'media/'

MEDIA_ROOT = BASE_DIR / 'media'


# ==========================================
# 13. DEFAULT PRIMARY KEY
# ==========================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==========================================
# 16. APP CONFIGURATION
# ==========================================

APP_NAME = config(
    'APP_NAME',
    default='IELTS Mock Test Platform'
)
