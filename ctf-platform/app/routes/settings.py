"""
Settings Routes Blueprint

Handles user account settings and profile management.

TO EXTEND THIS SECTION:
- Add profile picture upload
- Add bio/description field
- Add notification preferences
- Add privacy settings
- Add account deletion
- Add API key management
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db

# Create blueprint
settings_bp = Blueprint('settings', __name__, template_folder='../templates')


@settings_bp.route('/account')
@login_required
def account():
    """
    User account page - view account information.
    
    Displays:
    - Username
    - Email
    - Account statistics
    - Registration date
    """
    return render_template('account.html')


@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def index():
    """
    User settings page.
    
    Allows users to update:
    - Username
    - Email
    - Password
    
    TO EXTEND:
    - Add profile picture upload
    - Add bio
    - Add notification preferences
    - Add two-factor authentication
    - Add connected accounts (OAuth)
    """
    
    if request.method == 'POST':
        updated = False
        
        # ========================================
        # Update Username
        # ========================================
        new_username = request.form.get('username', '').strip()
        if new_username and new_username != current_user.username:
            from app.models import User
            
            # Check if username is taken
            if User.query.filter_by(username=new_username).first():
                flash('Username already taken', 'danger')
            else:
                current_user.username = new_username
                updated = True
        
        # ========================================
        # Update Email
        # ========================================
        new_email = request.form.get('email', '').strip()
        if new_email and new_email != current_user.email:
            from app.models import User
            
            # Check if email is taken
            if User.query.filter_by(email=new_email).first():
                flash('Email already registered', 'danger')
            else:
                current_user.email = new_email
                updated = True
                
                # TO ADD: Send verification email to new address
                # send_verification_email(new_email)
        
        # ========================================
        # Update Password
        # ========================================
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password:
            # Verify current password
            if not current_user.check_password(current_password):
                flash('Current password is incorrect', 'danger')
            elif new_password != confirm_password:
                flash('New passwords do not match', 'danger')
            else:
                # TO ADD: Password strength validation
                # if len(new_password) < 8:
                #     flash('Password must be at least 8 characters', 'danger')
                # else:
                current_user.set_password(new_password)
                updated = True
        
        # Save changes
        if updated:
            db.session.commit()
            flash('Settings updated successfully!', 'success')
        
        return redirect(url_for('settings.index'))
    
    # GET - show settings form
    return render_template('settings.html')


# ========================================
# TO ADD: Additional settings features
# ========================================

# Profile picture upload:
# @settings_bp.route('/settings/upload-avatar', methods=['POST'])
# @login_required
# def upload_avatar():
#     from werkzeug.utils import secure_filename
#     import os
#     
#     if 'avatar' not in request.files:
#         flash('No file uploaded', 'danger')
#         return redirect(url_for('settings.index'))
#     
#     file = request.files['avatar']
#     if file.filename == '':
#         flash('No file selected', 'danger')
#         return redirect(url_for('settings.index'))
#     
#     # Validate file type
#     allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
#     if not ('.' in file.filename and 
#             file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
#         flash('Invalid file type', 'danger')
#         return redirect(url_for('settings.index'))
#     
#     # Save file
#     filename = secure_filename(f"{current_user.id}_{file.filename}")
#     filepath = os.path.join('app/static/avatars', filename)
#     file.save(filepath)
#     
#     # Update user record
#     current_user.profile_picture = filename
#     db.session.commit()
#     
#     flash('Profile picture updated!', 'success')
#     return redirect(url_for('settings.index'))

# Account deletion:
# @settings_bp.route('/settings/delete-account', methods=['POST'])
# @login_required
# def delete_account():
#     password = request.form.get('password')
#     
#     if not current_user.check_password(password):
#         flash('Incorrect password', 'danger')
#         return redirect(url_for('settings.index'))
#     
#     # Delete user and all associated data
#     from flask_login import logout_user
#     db.session.delete(current_user)
#     db.session.commit()
#     logout_user()
#     
#     flash('Account deleted successfully', 'info')
#     return redirect(url_for('auth.index'))

# Notification preferences:
# @settings_bp.route('/settings/notifications', methods=['GET', 'POST'])
# @login_required
# def notifications():
#     if request.method == 'POST':
#         current_user.email_notifications = 'email_notifications' in request.form
#         current_user.challenge_notifications = 'challenge_notifications' in request.form
#         db.session.commit()
#         flash('Notification preferences updated', 'success')
#     
#     return render_template('settings/notifications.html')
