"""Development settings for the Studio business management system."""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-local-development-key")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.common.apps.CommonConfig",
    "apps.audit.apps.AuditConfig",
    "apps.organizations.apps.OrganizationsConfig",
    "apps.identity.apps.IdentityConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.expenses.apps.ExpensesConfig",
    "apps.files.apps.FilesConfig",
    "apps.inventory.apps.InventoryConfig",
    "apps.currencies.apps.CurrenciesConfig",
    "apps.purchasing.apps.PurchasingConfig",
    "apps.payments.apps.PaymentsConfig",
    "apps.sales.apps.SalesConfig",
    "apps.orders.apps.OrdersConfig",
    "apps.reports.apps.ReportsConfig",
    "apps.search.apps.SearchConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.chat.apps.ChatConfig",
    "apps.public_site.apps.PublicSiteConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DATABASE_URL", "sqlite:///db.sqlite3"),
        conn_max_age=60,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Monrovia"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# Sessions: HttpOnly cookie, 12-hour lifetime, ends when the browser closes.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", str(12 * 60 * 60)))
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SAMESITE = "Lax"
# The SPA reads the CSRF cookie and sends it back as X-CSRFToken.
CSRF_COOKIE_HTTPONLY = False
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
if not DEBUG:
    if SECRET_KEY.startswith("unsafe") or SECRET_KEY.startswith("local-only"):
        raise RuntimeError("Set DJANGO_SECRET_KEY to a strong secret before running with DJANGO_DEBUG=false.")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "true").lower() == "true"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Start low; raise to 31536000 (1 year) once HTTPS is confirmed working for the domain.
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "false").lower() == "true"
    SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "false").lower() == "true"
    # Subdomain and preload HSTS are deliberate owner decisions (other subdomains may not use HTTPS),
    # so `check --deploy` should not warn while they are off. Every other deploy warning still fails CI.
    SILENCED_SYSTEM_CHECKS = [
        *([] if SECURE_HSTS_INCLUDE_SUBDOMAINS else ["security.W005"]),
        *([] if SECURE_HSTS_PRELOAD else ["security.W021"]),
    ]
    localhost_only = set(ALLOWED_HOSTS) <= {"localhost", "127.0.0.1", ""}
    if localhost_only and os.getenv("DJANGO_ALLOW_LOCALHOST_ONLY", "false").lower() != "true":
        raise RuntimeError("Set DJANGO_ALLOWED_HOSTS to the site's domain before running with DJANGO_DEBUG=false.")
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"login": "5/minute"},
}
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["password_reset"] = "3/hour"
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["chat"] = "30/minute"
# Public website: generous for browsing, tight for forms and order lookups (stops guessing order numbers).
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["public_read"] = "120/minute"
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["public_request"] = "5/hour"
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["public_track"] = "20/hour"
# Which organization the public website shows (blank: the only one with its website enabled).
PUBLIC_SITE_ORGANIZATION_ID = os.getenv("PUBLIC_SITE_ORGANIZATION_ID", "")
# Behind a reverse proxy (Caddy) set to 1 so rate limits use the visitor's address from X-Forwarded-For
# (Caddy replaces any client-sent value), not the proxy's address shared by everyone.
if os.getenv("TRUSTED_PROXY_COUNT"):
    REST_FRAMEWORK["NUM_PROXIES"] = int(os.environ["TRUSTED_PROXY_COUNT"])
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:5173" if DEBUG else "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "StudioSuite <no-reply@localhost>")
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "false").lower() == "true"

STATIC_URL = "/static/"
STATIC_ROOT = Path(os.getenv("STATIC_ROOT", str(BASE_DIR / "staticfiles")))
ADMIN_URL = os.getenv("DJANGO_ADMIN_URL", "admin/")

# Errors are emailed to ADMINS ("Name <email>, Other <email>") when SMTP is configured.
ADMINS = [tuple(part.strip().rsplit(" ", 1)) for part in os.getenv("DJANGO_ADMINS", "").split(",") if part.strip()]
ADMINS = [(name, email.strip("<>")) for name, email in ADMINS] if ADMINS and all(len(a) == 2 for a in ADMINS) else []
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.common.logging.RequestIDFilter"},
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
    },
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s [req %(request_id)s] %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain", "filters": ["request_id"]},
        "mail_admins": {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR", "filters": ["require_debug_false"]},
    },
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
    "loggers": {"django.request": {"handlers": ["console", "mail_admins"], "level": "WARNING", "propagate": False}},
}

# Private uploads (receipt photos, product images). Never served directly: downloads go through
# /api/v1/attachments/<id>/file/, which checks permissions. Point PRIVATE_MEDIA_ROOT at a backed-up
# volume in production (or swap the backend for object storage).
PRIVATE_MEDIA_ROOT = Path(os.getenv("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private_media")))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "private": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": str(PRIVATE_MEDIA_ROOT), "base_url": None},
    },
}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
