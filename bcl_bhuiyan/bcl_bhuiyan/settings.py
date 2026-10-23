"""IELTS platform settings: local SQLite and environment-driven PostgreSQL deployment."""
from pathlib import Path
from decouple import config, Csv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = config('DJANGO_SECRET_KEY', default='')
if len(SECRET_KEY) < 32:
    raise ImproperlyConfigured('Set DJANGO_SECRET_KEY to a unique random value of at least 32 characters.')
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('DJANGO_ALLOWED_HOSTS', default='127.0.0.1,localhost', cast=Csv())
if not DEBUG and (not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS):
    raise ImproperlyConfigured('Production requires explicit DJANGO_ALLOWED_HOSTS (no wildcard).')
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'axes', 'django_otp', 'django_otp.plugins.otp_totp', 'bcl.apps.BclConfig',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'axes.middleware.AxesMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'bcl.security_middleware.StaffMFAMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'bcl_bhuiyan.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'bcl_bhuiyan.wsgi.application'
ASGI_APPLICATION = 'bcl_bhuiyan.asgi.application'
DB_ENGINE = config('DB_ENGINE', default='sqlite3').strip().lower()
if DB_ENGINE in ('sqlite3', 'sqlite'):
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
                             'NAME': BASE_DIR / config('DB_NAME', default='db.sqlite3')}}
elif DB_ENGINE in ('postgresql', 'postgres'):
    required = {key: config(key, default='') for key in ('DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST')}
    if not all(required.values()):
        raise ImproperlyConfigured('PostgreSQL requires DB_NAME, DB_USER, DB_PASSWORD and DB_HOST.')
    DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql',
                             'NAME': required['DB_NAME'], 'USER': required['DB_USER'],
                             'PASSWORD': required['DB_PASSWORD'], 'HOST': required['DB_HOST'],
                             'PORT': config('DB_PORT', default='5432'),
                             'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=60, cast=int),
                             'OPTIONS': {'sslmode': config('DB_SSLMODE', default='require')},
                             'TEST': {
                                'NAME': config('DB_TEST_NAME', default='ielts_test'),
                                'TEMPLATE': 'template0',
                             },
                             }}
else:
    raise ImproperlyConfigured('DB_ENGINE must be sqlite3 or postgresql.')
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = config('LANGUAGE_CODE', default='en-us')
TIME_ZONE = config('TIME_ZONE', default='Asia/Dhaka')
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# Only enable proxy headers behind a trusted proxy that overwrites client-supplied headers.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if config('TRUST_PROXY_SSL_HEADER', default=False, cast=bool) else None
SECURE_SSL_REDIRECT = config('DJANGO_SECURE_SSL_REDIRECT', default=not DEBUG, cast=bool)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_HSTS_SECONDS = config('DJANGO_HSTS_SECONDS', default=0, cast=int) if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('DJANGO_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool) if not DEBUG else False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
CSRF_TRUSTED_ORIGINS = config('DJANGO_CSRF_TRUSTED_ORIGINS', default='', cast=Csv())
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000
LOGGING = {'version': 1, 'disable_existing_loggers': False,
           'handlers': {'console': {'class': 'logging.StreamHandler'}},
           'loggers': {'django.security': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False}}}

# Authentication defense: django-axes uses database-backed counters shared across workers.
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]
AXES_FAILURE_LIMIT = config('AXES_FAILURE_LIMIT', default=5, cast=int)
AXES_COOLOFF_TIME = config('AXES_COOLOFF_HOURS', default=1, cast=int)
AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']
AXES_RESET_ON_SUCCESS = True
AXES_ENABLED = True
SESSION_COOKIE_AGE = config('SESSION_COOKIE_AGE', default=3600, cast=int)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Authentication routing
LOGIN_URL = 'bcl:login'
LOGIN_REDIRECT_URL = 'bcl:dashboard'
LOGOUT_REDIRECT_URL = 'bcl:login'
