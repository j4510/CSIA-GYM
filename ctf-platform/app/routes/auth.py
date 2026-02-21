"""
Authentication Routes Blueprint

Handles user registration, login, and logout.

BLUEPRINT PATTERN:
- Each feature gets its own blueprint (modular design)
- Blueprints are registered in app/__init__.py
- Routes are defined with @blueprint.route() decorator

TO ADD NEW AUTH FEATURES:
- Password reset: Add /forgot-password and /reset-password routes
- Email verification: Add /verify-email route
- OAuth login: Add /login/google, /login/github routes
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app import db
from app.models import User

# Create blueprint
# First argument is the blueprint name (used in url_for)
# template_folder is relative to this file's location
auth_bp = Blueprint('auth', __name__, template_folder='../templates')


@auth_bp.route('/')
def index():
    """
    Homepage route.
    
    Shows landing page if not logged in, redirects to challenges if logged in.
    """
    if current_user.is_authenticated:
        return redirect(url_for('challenges.list'))
    return render_template('index.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    User registration.
    
    GET: Show registration form
    POST: Process registration and create new user
    
    TO EXTEND:
    - Add email verification
    - Add CAPTCHA
    - Add password strength requirements
    - Add username validation (no special chars, etc.)
    """
    
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('challenges.list'))
    
    if request.method == 'POST':
        # Get form data
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not username or not email or not password:
            flash('All fields are required', 'danger')
            return redirect(url_for('auth.register'))
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('auth.register'))
        
        # TO ADD: Password strength validation
        # if len(password) < 8:
        #     flash('Password must be at least 8 characters', 'danger')
        #     return redirect(url_for('auth.register'))
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('auth.register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('auth.register'))
        
        # Create new user
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    
    # GET request - show form
    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    User login.
    
    GET: Show login form
    POST: Authenticate user and create session
    
    TO EXTEND:
    - Add "Remember me" checkbox
    - Add rate limiting (prevent brute force)
    - Add 2FA
    """
    
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('challenges.list'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        
        # Find user
        user = User.query.filter_by(username=username).first()
        
        # Verify credentials
        if user and user.check_password(password):
            # Log user in (creates session)
            login_user(user)
            flash('Login successful!', 'success')
            
            # Redirect to page they were trying to access, or challenges page
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('challenges.list'))
        else:
            flash('Invalid username or password', 'danger')
    
    # GET request - show form
    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    """
    User logout.
    
    Ends the user session and redirects to homepage.
    """
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.index'))


# ========================================
# TO ADD: Additional authentication features
# ========================================

# Password reset example:
# @auth_bp.route('/forgot-password', methods=['GET', 'POST'])
# def forgot_password():
#     if request.method == 'POST':
#         email = request.form.get('email')
#         # Generate reset token and send email
#         pass
#     return render_template('auth/forgot_password.html')

# Email verification example:
# @auth_bp.route('/verify-email/<token>')
# def verify_email(token):
#     # Verify token and activate account
#     pass
