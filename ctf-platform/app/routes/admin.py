"""
Admin Routes Blueprint

Centralized admin panel for managing the entire CTF platform.

Features:
- User management (view, delete, promote to admin)
- Challenge approval (approve/reject user submissions)
- Community moderation (edit/delete posts)
- Statistics dashboard

SECURITY:
All routes under /admin are automatically protected by the before_request
decorator - only users with is_admin=True can access them.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image
import os
import csv
from datetime import datetime
from app import db
from app.models import User, Challenge, ChallengeSubmission, CommunityPost, Comment, Badge, UserBadge

BADGE_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'badges')
AVATAR_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'avatars')
AUDIT_LOG = os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'admin_audit.csv')


def log_action(action: str, target: str = ''):
    """Append a line to the admin audit CSV log."""
    os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
    write_header = not os.path.exists(AUDIT_LOG)
    with open(AUDIT_LOG, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['timestamp', 'admin', 'action', 'target'])
        writer.writerow([
            datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
            current_user.username,
            action,
            target,
        ])

# Create admin blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder='../templates')


@admin_bp.before_request
@login_required
def restrict_to_admins():
    """
    Automatically check admin status before EVERY admin route.
    
    This runs before any @admin_bp.route() is executed.
    If user is not admin, show 403 Forbidden error.
    """
    if not current_user.is_admin:
        abort(403)  # Forbidden


# ========================================
# ADMIN DASHBOARD
# ========================================

@admin_bp.route('/')
def dashboard():
    """
    Main admin dashboard with overview statistics.
    
    Shows:
    - Total users, challenges, posts
    - Pending challenge submissions
    - Recent activity
    """
    stats = {
        'total_users': User.query.count(),
        'total_admins': User.query.filter_by(is_admin=True).count(),
        'total_challenges': Challenge.query.count(),
        'pending_submissions': ChallengeSubmission.query.filter_by(status='pending').count(),
        'total_posts': CommunityPost.query.count(),
    }
    
    # Recent pending submissions
    pending = ChallengeSubmission.query.filter_by(status='pending').order_by(
        ChallengeSubmission.created_at.desc()
    ).limit(5).all()
    
    return render_template('admin/dashboard.html', stats=stats, pending=pending)


# ========================================
# USER MANAGEMENT
# ========================================

@admin_bp.route('/users')
def users():
    """View all users."""
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/users/<int:user_id>/promote', methods=['POST'])
def promote_user(user_id):
    """Promote a user to admin."""
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        flash(f'{user.username} is already an admin', 'info')
    else:
        user.is_admin = True
        db.session.commit()
        log_action('promote_to_admin', user.username)
        flash(f'{user.username} promoted to admin!', 'success')
    
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/demote', methods=['POST'])
def demote_user(user_id):
    """Remove admin privileges from a user."""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot demote yourself!', 'danger')
        return redirect(url_for('admin.users'))
    
    user.is_admin = False
    db.session.commit()
    log_action('demote_from_admin', user.username)
    flash(f'{user.username} demoted to regular user', 'info')
    
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    """Delete a user account."""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot delete your own account!', 'danger')
        return redirect(url_for('admin.users'))
    
    log_action('delete_user', user.username)
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} deleted', 'info')
    
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
def edit_user(user_id):
    """Edit any user's profile including password."""
    user = User.query.get_or_404(user_id)
    all_badges = Badge.query.all()
    user_badge_ids = {ub.badge_id for ub in user.badges}

    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_email = request.form.get('email', '').strip()
        new_full_name = request.form.get('full_name', '').strip() or None
        new_affiliation = request.form.get('affiliation', '').strip() or None
        age_val = request.form.get('age', '').strip()
        new_age = int(age_val) if age_val.isdigit() else None
        new_gender = request.form.get('gender', '').strip() or None
        new_password = request.form.get('new_password', '').strip()

        if new_username and new_username != user.username:
            if User.query.filter_by(username=new_username).first():
                flash('Username already taken', 'danger')
                return redirect(url_for('admin.edit_user', user_id=user_id))
            user.username = new_username

        if new_email and new_email != user.email:
            if User.query.filter_by(email=new_email).first():
                flash('Email already registered', 'danger')
                return redirect(url_for('admin.edit_user', user_id=user_id))
            user.email = new_email

        user.full_name = new_full_name
        user.affiliation = new_affiliation
        user.age = new_age
        user.gender = new_gender

        if new_password:
            user.set_password(new_password)

        # Handle profile picture upload
        if 'avatar' in request.files and request.files['avatar'].filename:
            file = request.files['avatar']
            os.makedirs(AVATAR_DIR, exist_ok=True)
            filename = f'avatar_{user.username}.webp'
            img = Image.open(file).convert('RGB')
            img = img.resize((500, 500))
            img.save(os.path.join(AVATAR_DIR, filename), 'WEBP', quality=85)
            user.profile_picture = filename

        # Handle badge assignments
        selected_badge_ids = set(int(x) for x in request.form.getlist('badges'))
        for ub in list(user.badges):
            if ub.badge_id not in selected_badge_ids:
                db.session.delete(ub)
        for bid in selected_badge_ids:
            if bid not in user_badge_ids:
                db.session.add(UserBadge(user_id=user.id, badge_id=bid))

        db.session.commit()
        log_action('edit_user', user.username)
        flash(f'{user.username} updated successfully', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/edit_user.html', user=user, all_badges=all_badges, user_badge_ids=user_badge_ids)


# ========================================
# BADGE MANAGEMENT
# ========================================

@admin_bp.route('/badges')
def badges():
    all_badges = Badge.query.order_by(Badge.created_at.desc()).all()
    return render_template('admin/badges.html', badges=all_badges)


@admin_bp.route('/badges/create', methods=['POST'])
def create_badge():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    is_limited = 'is_limited' in request.form

    if not title or not description or 'image' not in request.files:
        flash('Title, description, and image are required', 'danger')
        return redirect(url_for('admin.badges'))

    file = request.files['image']
    if not file.filename:
        flash('No image selected', 'danger')
        return redirect(url_for('admin.badges'))

    os.makedirs(BADGE_DIR, exist_ok=True)
    filename = secure_filename(f'badge_{title.lower().replace(" ", "_")}.webp')
    img = Image.open(file).convert('RGBA')
    img = img.resize((500, 500))
    img.save(os.path.join(BADGE_DIR, filename), 'WEBP', quality=85)

    badge = Badge(title=title, description=description, image_filename=filename, is_limited=is_limited)
    db.session.add(badge)
    db.session.commit()
    log_action('create_badge', title)
    flash(f'Badge "{title}" created!', 'success')
    return redirect(url_for('admin.badges'))


@admin_bp.route('/badges/<int:badge_id>/delete', methods=['POST'])
def delete_badge(badge_id):
    badge = Badge.query.get_or_404(badge_id)
    db.session.delete(badge)
    db.session.commit()
    log_action('delete_badge', badge.title)
    flash(f'Badge "{badge.title}" deleted', 'info')
    return redirect(url_for('admin.badges'))


@admin_bp.route('/users/<int:user_id>/hide', methods=['POST'])
def hide_from_scoreboard(user_id):
    """Hide a user from appearing on the scoreboard."""
    user = User.query.get_or_404(user_id)
    
    if user.is_hidden_from_scoreboard:
        flash(f'{user.username} is already hidden from scoreboard', 'info')
    else:
        user.is_hidden_from_scoreboard = True
        db.session.commit()
        log_action('hide_from_scoreboard', user.username)
        flash(f'{user.username} is now hidden from scoreboard', 'success')
    
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/show', methods=['POST'])
def show_on_scoreboard(user_id):
    """Show a user on the scoreboard again."""
    user = User.query.get_or_404(user_id)
    
    if not user.is_hidden_from_scoreboard:
        flash(f'{user.username} is already visible on scoreboard', 'info')
    else:
        user.is_hidden_from_scoreboard = False
        db.session.commit()
        log_action('show_on_scoreboard', user.username)
        flash(f'{user.username} is now visible on scoreboard', 'success')
    
    return redirect(url_for('admin.users'))


@admin_bp.route('/audit-log')
def audit_log():
    """Download the admin audit log as a CSV."""
    from flask import send_file, Response
    if os.path.exists(AUDIT_LOG):
        return send_file(AUDIT_LOG, mimetype='text/csv', as_attachment=True,
                         download_name=f'admin_audit_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv')
    # Return empty CSV if no actions yet
    return Response('timestamp,admin,action,target\n', mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=admin_audit.csv'})


# ========================================
# CHALLENGE MANAGEMENT
# ========================================

@admin_bp.route('/challenges')
def challenges():
    """View all user-submitted challenges pending approval."""
    pending = ChallengeSubmission.query.filter_by(status='pending').all()
    approved = ChallengeSubmission.query.filter_by(status='approved').all()
    rejected = ChallengeSubmission.query.filter_by(status='rejected').all()
    
    return render_template('admin/challenges.html', 
                         pending=pending, 
                         approved=approved, 
                         rejected=rejected)


@admin_bp.route('/challenges/<int:submission_id>/approve', methods=['POST'])
def approve_challenge(submission_id):
    """
    Approve a user-submitted challenge and create it as an active challenge.
    """
    submission = ChallengeSubmission.query.get_or_404(submission_id)
    
    if submission.status == 'approved':
        flash('This challenge is already approved', 'info')
        return redirect(url_for('admin.challenges'))
    
    # Create the challenge
    challenge = Challenge(
        title=submission.title,
        description=submission.description,
        category=submission.category,
        difficulty=submission.difficulty,
        flag=submission.flag,
        points=submission.points,
        author_id=submission.author_id
    )
    
    # Mark submission as approved
    submission.status = 'approved'
    
    db.session.add(challenge)
    db.session.commit()
    
    log_action('approve_challenge', challenge.title)
    flash(f'Challenge "{challenge.title}" approved and published!', 'success')
    return redirect(url_for('admin.challenges'))


@admin_bp.route('/challenges/<int:submission_id>/reject', methods=['POST'])
def reject_challenge(submission_id):
    """Reject a user-submitted challenge."""
    submission = ChallengeSubmission.query.get_or_404(submission_id)
    submission.status = 'rejected'
    db.session.commit()
    
    log_action('reject_challenge', submission.title)
    flash(f'Challenge "{submission.title}" rejected', 'info')
    return redirect(url_for('admin.challenges'))


@admin_bp.route('/challenges/<int:challenge_id>/delete', methods=['POST'])
def delete_challenge(challenge_id):
    """Delete a live challenge."""
    challenge = Challenge.query.get_or_404(challenge_id)
    db.session.delete(challenge)
    db.session.commit()
    
    log_action('delete_challenge', challenge.title)
    flash(f'Challenge "{challenge.title}" deleted', 'info')
    return redirect(url_for('challenges.list'))


# ========================================
# COMMUNITY POST MANAGEMENT
# ========================================

@admin_bp.route('/posts')
def posts():
    """View all community posts."""
    all_posts = CommunityPost.query.order_by(CommunityPost.created_at.desc()).all()
    return render_template('admin/posts.html', posts=all_posts)


@admin_bp.route('/posts/<int:post_id>/delete', methods=['POST'])
def delete_post(post_id):
    """Delete a community post."""
    post = CommunityPost.query.get_or_404(post_id)
    db.session.delete(post)  # Comments are deleted automatically (cascade)
    db.session.commit()
    
    log_action('delete_post', str(post.id))
    flash('Post deleted', 'info')
    return redirect(url_for('admin.posts'))


@admin_bp.route('/posts/<int:post_id>/edit', methods=['GET', 'POST'])
def edit_post(post_id):
    """Edit a community post."""
    post = CommunityPost.query.get_or_404(post_id)
    
    if request.method == 'POST':
        post.title = request.form.get('title')
        post.content = request.form.get('content')
        db.session.commit()
        
        log_action('edit_post', str(post.id))
        flash('Post updated', 'success')
        return redirect(url_for('admin.posts'))
    
    return render_template('admin/edit_post.html', post=post)
