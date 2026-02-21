import os
from datetime import timedelta

class Config:
    """
    Main configuration class for the CTF platform.
    
    TO ADD NEW CONFIGURATION:
    1. Add the variable here as a class attribute
    2. Access it in your code with: app.config['VARIABLE_NAME']
    
    Example: To add a max file upload size:
    MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB
    """
    
    # Secret key for session encryption - CHANGE THIS IN PRODUCTION!
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database configuration
    # SQLite is used by default (file-based, simple for small scale)
    # TO USE POSTGRESQL: uncomment the line below and set DATABASE_URL environment variable
    # SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://user:password@localhost/ctfdb'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:////app/instance/ctf.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Flask-Login configuration
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    
    # Application settings
    # TO ADD NEW SETTINGS: Add them here and access via app.config
    CHALLENGES_PER_PAGE = 20
    POSTS_PER_PAGE = 15
    
    # File upload settings (if you add file upload functionality)
    # MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    # UPLOAD_FOLDER = 'uploads'
    # ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip'}
