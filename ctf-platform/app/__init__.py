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
    from app.routes.admin import admin_bp
    
    # Register all blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(challenges_bp)
    app.register_blueprint(submissions_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(admin_bp)
    
    # TO ADD NEW BLUEPRINT:
    # from app.routes.your_feature import your_feature_bp
    # app.register_blueprint(your_feature_bp)

    # ========================================
    # MOBILE BLOCK
    # ========================================

    import re
    MOBILE_UA_RE = re.compile(
        r'(iPhone|Android.*Mobile|Android.*Firefox)',
        re.IGNORECASE
    )

    from flask import request, render_template

    @app.before_request
    def block_mobile():
        ua = request.headers.get('User-Agent', '')
        if MOBILE_UA_RE.search(ua):
            if request.endpoint not in ('static', 'challenges.scoreboard'):
                return render_template('mobile.html'), 200

    # ========================================
    # ERROR HANDLERS
    # ========================================

    @app.errorhandler(400)
    def bad_request(e):
        return render_template('error.html', code=400, title='Bad Request', message='The server could not understand your request.'), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html', code=403, title='Access Forbidden', message='You do not have permission to access this page.'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', code=404, title='Page Not Found', message='The page you are looking for does not exist or has been moved.'), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return render_template('error.html', code=405, title='Method Not Allowed', message='This action is not allowed on the requested resource.'), 405

    @app.errorhandler(500)
    def internal_error(e):
        return render_template('error.html', code=500, title='Server Error', message='Something went wrong on our end. Please try again later.'), 500

    # ========================================
    # CREATE DATABASE TABLES
    # ========================================
    
    with app.app_context():
        db.create_all()

        # ----------------------------------------
        # INLINE MIGRATIONS
        # Safely add new columns to existing tables
        # ----------------------------------------
        from sqlalchemy import text, inspect
        inspector = inspect(db.engine)

        existing_user_cols = [c['name'] for c in inspector.get_columns('users')]
        new_user_cols = {
            'full_name':   'ALTER TABLE users ADD COLUMN full_name VARCHAR(120)',
            'affiliation': 'ALTER TABLE users ADD COLUMN affiliation VARCHAR(120)',
            'age':         'ALTER TABLE users ADD COLUMN age INTEGER',
            'gender':      'ALTER TABLE users ADD COLUMN gender VARCHAR(40)',
            'profile_picture': 'ALTER TABLE users ADD COLUMN profile_picture VARCHAR(200)',
        }
        with db.engine.connect() as conn:
            for col, stmt in new_user_cols.items():
                if col not in existing_user_cols:
                    conn.execute(text(stmt))
            conn.commit()

        # Create default admin user if it doesn't exist
        from app.models import User
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', email='admin@ctf.local', is_admin=True)
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
