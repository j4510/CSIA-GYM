import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:////app/instance/ctf.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_DURATION = timedelta(days=7)

    MAX_CONTENT_LENGTH = 300 * 1024 * 1024  # 300 MB hard cap on request body

    # Hostnames shown to players for challenge instances.
    # Set these to DNS-only (unproxied) subdomains so raw TCP/HTTP works.
    CHALLENGE_HOST = os.environ.get('CHALLENGE_HOST') or None       # fallback for both
    NC_CHALLENGE_HOST = os.environ.get('NC_CHALLENGE_HOST') or None  # nc/RE challenges
    WEB_CHALLENGE_HOST = os.environ.get('WEB_CHALLENGE_HOST') or None  # web challenges
