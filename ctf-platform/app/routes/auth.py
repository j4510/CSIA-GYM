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

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_user, logout_user, current_user, login_required
import os, re
from urllib.parse import urlparse
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError
from app import db, csrf
from app.models import User
from app.identicon import generate_identicon
from app.routes.admin import log_event

WHATS_NEW_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'WHATS-NEW.md')


def get_version():
    try:
        with open(WHATS_NEW_PATH, encoding='utf-8') as f:
            first_line = re.sub(r'[^\x20-\x7E]', '', f.readline())[:200]
        match = re.search(r'v[\d.]+', first_line)
        return match.group(0) if match else 'v?'
    except (OSError, AttributeError):
        return 'v?'

# Create blueprint
# First argument is the blueprint name (used in url_for)
# template_folder is relative to this file's location
auth_bp = Blueprint('auth', __name__, template_folder='../templates')


@auth_bp.route('/whats-new')
def whats_new():
    try:
        with open(WHATS_NEW_PATH, encoding='utf-8') as f:
            content = f.read()
    except OSError:
        content = 'Could not load changelog.'
    version = get_version()
    return render_template('whats_new.html', content=content, version=version)


@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('challenges.list'))
    from app.models import User, Challenge, UserChallengeSolve, CommunityPost
    stats = {
        'users':      User.query.count(),
        'challenges': Challenge.query.filter_by(is_hidden=False).count(),
        'solves':     UserChallengeSolve.query.count(),
        'posts':      CommunityPost.query.count(),
    }
    return render_template('index.html', stats=stats)


@auth_bp.route('/register', methods=['GET', 'POST'])
@csrf.exempt
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
        try:
            validate_csrf(request.form.get('csrf_token'))
        except ValidationError:
            abort(403)
        # Get form data
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not username or not email or not full_name or not password:
            flash('All fields are required', 'danger')
            return redirect(url_for('auth.register'))

        if not re.match(r'^[A-Za-z0-9_]{1,32}$', username):
            flash('Username must be 1–32 characters and contain only letters, numbers, and underscores (no spaces or symbols).', 'danger')
            return redirect(url_for('auth.register'))

        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('auth.register'))

        # Check if user exists
        if User.query.filter_by(username=username).first():
            import random
            suggestions = []
            for _ in range(3):
                candidate = username[:28] + str(random.randint(10, 9999))
                while User.query.filter_by(username=candidate).first():
                    candidate = username[:28] + str(random.randint(10, 9999))
                suggestions.append(candidate)
            flash(f'Username already taken. Try: {", ".join(suggestions)}', 'danger')
            return redirect(url_for('auth.register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('auth.register'))
        
        # Create new user
        user = User(username=username, email=email, full_name=full_name)
        user.set_password(password)
        user.profile_picture = generate_identicon(username)
        db.session.add(user)
        db.session.commit()
        log_event(actor=username, action='register', target=email, category='auth')
        # Send welcome + latest changelog notification
        try:
            from app.notifs import push
            version = get_version()
            push(user.id, f'Welcome to CSIA GYM, {username}!',
                 f'You\'re now part of the platform. Check out the challenges and community!',
                 category='system', link='/challenges')
            push(user.id, f'Latest update: {version}',
                 'Check out what\'s new on the platform.',
                 category='system', link='/whats-new')
        except (ImportError, RuntimeError):
            pass
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    
    # GET request - show form
    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@csrf.exempt
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
        try:
            validate_csrf(request.form.get('csrf_token'))
        except ValidationError:
            abort(403)
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        
        # Find user
        user = User.query.filter_by(username=username).first()
        
        # Verify credentials
        if user and user.check_password(password):
            if user.is_banned:
                reason = user.ban_reason or 'No reason provided.'
                log_event(actor=username, action='login_blocked_banned', target=reason, category='auth')
                flash(f'Your account has been banned. Reason: {reason}', 'danger')
                return redirect(url_for('auth.login'))
            remember = 'remember' in request.form
            from datetime import timedelta
            login_user(user, remember=remember, duration=timedelta(days=30))
            log_event(actor=username, action='login_success', category='auth')
            flash('Login successful!', 'success')
            
            # Redirect to page they were trying to access, or challenges page
            next_page = request.args.get('next', '')
            parsed = urlparse(next_page)
            if next_page and not parsed.scheme and not parsed.netloc:
                return redirect(next_page)
            return redirect(url_for('challenges.list'))
        else:
            log_event(actor=username or '(unknown)', action='login_failed', target='bad credentials', category='auth')
            flash('Invalid username or password', 'danger')
    
    # GET request - show form
    return render_template('auth/login.html')


@auth_bp.route('/tour-done', methods=['POST'])
@csrf.exempt
def tour_done():
   
    if current_user.is_authenticated:
        User.query.filter_by(id=current_user.id).update({'has_seen_tour': True})
        db.session.commit()
        
    return '', 204


@auth_bp.route('/logout')
def logout():
    if current_user.is_authenticated:
        log_event(actor=current_user.username, action='logout', category='auth')
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
