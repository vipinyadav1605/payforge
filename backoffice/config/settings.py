"""Django settings for the PayForge back-office (staff console).

Design: Django's own tables (users, sessions, admin log) live in a SEPARATE Postgres schema
called 'backoffice'. PayForge's real tables stay in 'public' and are mapped with unmanaged
models, so Django migrations can never touch them (Alembic owns them).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]  # dev only: restrict to your real host names in production

INSTALLED_APPS = [
    "core",  # listed first so its templates override the admin's
    "config.admin_config.BackofficeAdminConfig",  # replaces django.contrib.admin (custom site)
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "payforge"),
        "USER": os.environ.get("POSTGRES_USER", "payforge"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "payforge"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        # Django-owned tables go to the first schema; PayForge's tables are found in 'public'.
        "OPTIONS": {"options": "-c search_path=backoffice,public"},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# How the back-office talks to the PayForge API for staff actions.
PAYFORGE_API_URL = os.environ.get("PAYFORGE_API_URL", "http://api:8000")
PAYFORGE_ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "dev-admin-token-change-me")

# First-run staff account (development only; change it and use real accounts in production).
BACKOFFICE_ADMIN_USER = os.environ.get("BACKOFFICE_ADMIN_USER", "admin")
BACKOFFICE_ADMIN_PASSWORD = os.environ.get("BACKOFFICE_ADMIN_PASSWORD", "admin-change-me")
