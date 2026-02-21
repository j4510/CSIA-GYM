"""
Main application factory for the CTF Platform.

This uses the Flask Application Factory pattern, which allows for:
- Multiple app instances (testing, development, production)
- Better organization and modularity
- Easier testing

TO ADD A NEW FEATURE/SECTION:
1. Create a new blueprint in app/routes/your_feature.py
2. Import it in the "Register blueprints" section below
3. Register it with app.register_blueprint()
4. Add navigation link in templates/base.html
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

# Initialize extensions globally (but don't bind to app yet)
db = SQLAlchemy()
login_manager = LoginManager()

def create_app(config_class=Config):
    """
    Application factory function.
    
    Args:
        config_class: Configuration class to use (default: Config from config.py)
    
    Returns:
        Flask application instance
    """
    
    # Create Flask app
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    
    # Configure Flask-Login
    login_manager.login_view = 'auth.login'  # Redirect unauthorized users here
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # ========================================
    # REGISTER BLUEPRINTS
    # TO ADD NEW SECTIONS: Import and register your blueprint here
    # ========================================
    
    from app.routes.auth import auth_bp
    from app.routes.challenges import challenges_bp
    from app.routes.submissions import submissions_bp
    from app.routes.community import community_bp
    from app.routes.settings import settings_bp
    
    # Register all blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(challenges_bp)
    app.register_blueprint(submissions_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(settings_bp)
    
    # TO ADD NEW BLUEPRINT:
    # from app.routes.your_feature import your_feature_bp
    # app.register_blueprint(your_feature_bp)
    
    # ========================================
    # CREATE DATABASE TABLES
    # ========================================
    
    with app.app_context():
        db.create_all()
        
        # Create default admin user if it doesn't exist
        from app.models import User
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', email='admin@ctf.local')
            admin.set_password('admin123')  # CHANGE THIS IN PRODUCTION!
            db.session.add(admin)
            db.session.commit()
            print("=" * 60)
            print("✅ Admin account created!")
            print("   Username: admin")
            print("   Password: admin123")
            print("   ⚠️  Please change this password after first login!")
            print("=" * 60)
    
    return app
