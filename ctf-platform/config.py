import os
import secrets
from datetime import timedelta


class Config:
    _sk = os.environ.get('SECRET_KEY')
    if not _sk:
        raise RuntimeError(
            'SECRET_KEY environment variable is not set. '
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    SECRET_KEY = _sk
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:////app/instance/ctf.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') != 'development'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = os.environ.get('FLASK_ENV') != 'development'

    MAX_CONTENT_LENGTH = 300 * 1024 * 1024  # 300 MB hard cap on request body

    # Hostnames shown to players for challenge instances.
    # Set these to DNS-only (unproxied) subdomains so raw TCP/HTTP works.
    CHALLENGE_HOST = os.environ.get('CHALLENGE_HOST') or None
    NC_CHALLENGE_HOST = os.environ.get('NC_CHALLENGE_HOST') or None
    WEB_CHALLENGE_HOST = os.environ.get('WEB_CHALLENGE_HOST') or None

    RUNNER_URL    = os.environ.get('RUNNER_URL', 'http://runner:32526')
    RUNNER_SECRET = os.environ.get('RUNNER_SECRET', '')
