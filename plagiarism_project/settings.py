"""
Django settings for plagiarism_project.
Production-ready configuration supporting SQLite, MySQL, and PostgreSQL,
WhiteNoise static serving, Docker, and cloud deployments.
"""
import os
from pathlib import Path

import environ
import dj_database_url

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Environment variables setup
env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, 'django-insecure-change-this-in-production-random-key-64chars!'),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1', 'testserver', '[::1]']),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DATABASE_URL=(str, ''),
    DATABASE_CONN_MAX_AGE=(int, 600),
    MAX_UPLOAD_SIZE_MB=(int, 25),
    MAX_PAGES=(int, 500),
    MAX_WORDS=(int, 100000),
    DEFAULT_SIMILARITY_THRESHOLD=(int, 15),
    MIN_MATCH_WORD_COUNT=(int, 5),
    NGRAM_SIZE=(int, 5),
    PROCESSING_TIMEOUT_SECONDS=(int, 300),
)

env_file = BASE_DIR / '.env'
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*'] if DEBUG else ['localhost', '127.0.0.1', 'testserver', '[::1]'])
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    # Project apps
    'accounts.apps.AccountsConfig',
    'documents.apps.DocumentsConfig',
    'analysis.apps.AnalysisConfig',
    'reports.apps.ReportsConfig',
    'dashboard.apps.DashboardConfig',
    'sources.apps.SourcesConfig',
    'jobs.apps.JobsConfig',
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
    'accounts.middleware.RateLimitMiddleware',
    'accounts.middleware.AuditLogMiddleware',
]

ROOT_URLCONF = 'plagiarism_project.urls'

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

WSGI_APPLICATION = 'plagiarism_project.wsgi.application'
ASGI_APPLICATION = 'plagiarism_project.asgi.application'

# Database Configuration
database_url = env('DATABASE_URL')
conn_max_age = env('DATABASE_CONN_MAX_AGE')

if database_url:
    DATABASES = {
        'default': dj_database_url.parse(database_url, conn_max_age=conn_max_age)
    }
else:
    db_engine = env('DATABASE_ENGINE', default='django.db.backends.sqlite3')
    db_name = env('DATABASE_NAME', default=str(BASE_DIR / 'db.sqlite3'))

    if db_engine == 'django.db.backends.sqlite3':
        DATABASES = {
            'default': {
                'ENGINE': db_engine,
                'NAME': db_name,
            }
        }
    else:
        # Enable PyMySQL fallback for MySQL on systems without mysqlclient C headers
        if 'mysql' in db_engine:
            try:
                import pymysql
                pymysql.install_as_MySQLdb()
            except ImportError:
                pass

        DATABASES = {
            'default': {
                'ENGINE': db_engine,
                'NAME': db_name,
                'USER': env('DATABASE_USER', default=''),
                'PASSWORD': env('DATABASE_PASSWORD', default=''),
                'HOST': env('DATABASE_HOST', default='localhost'),
                'PORT': env('DATABASE_PORT', default='3306'),
                'CONN_MAX_AGE': conn_max_age,
                'OPTIONS': {
                    'charset': 'utf8mb4',
                },
            }
        }

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images) with WhiteNoise storage
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Media files (uploaded documents stored OUTSIDE public web directory)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Uploads directory (secure, not publicly accessible)
UPLOAD_ROOT = BASE_DIR / 'secure_uploads'

# Ensure upload and media directories exist on startup
os.makedirs(MEDIA_ROOT, exist_ok=True)
os.makedirs(UPLOAD_ROOT, exist_ok=True)

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Login settings
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# File Upload Settings
MAX_UPLOAD_SIZE_MB = env('MAX_UPLOAD_SIZE_MB')
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_PAGES = env('MAX_PAGES')
MAX_WORDS = env('MAX_WORDS')
ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.pptx']
ALLOWED_MIME_TYPES = {
    '.pdf': ['application/pdf'],
    '.docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
    '.txt': ['text/plain'],
    '.pptx': ['application/vnd.openxmlformats-officedocument.presentationml.presentation'],
}

# Similarity Settings
DEFAULT_SIMILARITY_THRESHOLD = env('DEFAULT_SIMILARITY_THRESHOLD')
MIN_MATCH_WORD_COUNT = env('MIN_MATCH_WORD_COUNT')
NGRAM_SIZE = env('NGRAM_SIZE')

# Processing Settings
PROCESSING_TIMEOUT_SECONDS = env('PROCESSING_TIMEOUT_SECONDS')

# Analysis Engine Version
ANALYSIS_ENGINE_VERSION = '1.0.0'

# Session and Rate Limiting
SESSION_COOKIE_AGE = 3600  # 1 hour
SESSION_COOKIE_HTTPONLY = True
RATE_LIMIT_REQUESTS = 100  # requests per window
RATE_LIMIT_WINDOW = 3600   # window in seconds

# Data Retention
DOCUMENT_RETENTION_DAYS = 365  # Default: keep documents for 1 year
REPORT_RETENTION_DAYS = 730    # Default: keep reports for 2 years

# Production Security Headers & Reverse Proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)
    SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=False)
    CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=False)
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=0)
    if SECURE_HSTS_SECONDS > 0:
        SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
        SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=True)
