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
from app import db
from app.models import User, Challenge, ChallengeSubmission, CommunityPost, Comment

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
    flash(f'{user.username} demoted to regular user', 'info')
    
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    """Delete a user account."""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot delete your own account!', 'danger')
        return redirect(url_for('admin.users'))
    
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} deleted', 'info')
    
    return redirect(url_for('admin.users'))


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
    
    flash(f'Challenge "{challenge.title}" approved and published!', 'success')
    return redirect(url_for('admin.challenges'))


@admin_bp.route('/challenges/<int:submission_id>/reject', methods=['POST'])
def reject_challenge(submission_id):
    """Reject a user-submitted challenge."""
    submission = ChallengeSubmission.query.get_or_404(submission_id)
    submission.status = 'rejected'
    db.session.commit()
    
    flash(f'Challenge "{submission.title}" rejected', 'info')
    return redirect(url_for('admin.challenges'))


@admin_bp.route('/challenges/<int:challenge_id>/delete', methods=['POST'])
def delete_challenge(challenge_id):
    """Delete a live challenge."""
    challenge = Challenge.query.get_or_404(challenge_id)
    db.session.delete(challenge)
    db.session.commit()
    
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
        
        flash('Post updated', 'success')
        return redirect(url_for('admin.posts'))
    
    return render_template('admin/edit_post.html', post=post)
