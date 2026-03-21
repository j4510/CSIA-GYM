from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, send_file, Response
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image
import base64
import io
import os
import csv
import secrets
from datetime import datetime, timedelta
from sqlalchemy import func, case
from app import db
from app.models import (
    User, Challenge, ChallengeSubmission, SubmissionFile, CommunityPost, Comment,
    Badge, UserBadge, WebChallenge, NcChallenge, Notification, NotificationRead,
    Announcement, BadgeRule, BadgeClaim, BugReport, FlagAttempt, UserChallengeSolve,
    ChallengeOpen, Milestone, UserMilestone
)

SUBMISSION_FILES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'submission_files')

BADGE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'badges')
AVATAR_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'avatars')
AUDIT_LOG = os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'admin_audit.csv')


def _get_ip():
    """Return the real client IP, honouring Cloudflare's CF-Connecting-IP header."""
    return (
        request.headers.get('CF-Connecting-IP')
        or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        or request.remote_addr
        or 'unknown'
    )


def log_event(actor: str, action: str, target: str = '', category: str = 'admin', ip: str = ''):
    """Universal audit log writer. category: admin | auth | challenge | community | submission"""
    os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
    write_header = not os.path.exists(AUDIT_LOG)
    with open(AUDIT_LOG, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['timestamp', 'user', 'action', 'target', 'category', 'ip'])
        writer.writerow([
            datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
            actor,
            action,
            target,
            category,
            ip or _get_ip(),
        ])


def log_action(action: str, target: str = ''):
    """Backward-compat wrapper — logs admin actions under the 'admin' category."""
    log_event(
        actor=current_user.username,
        action=action,
        target=target,
        category='admin',
    )

admin_bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder='../templates')


@admin_bp.before_request
@login_required
def restrict_to_admins():
    if not current_user.is_admin:
        abort(403)


# ========================================
# ADMIN DASHBOARD
# ========================================

@admin_bp.route('/')
def dashboard():
    stats = {
        'total_users': User.query.count(),
        'total_admins': User.query.filter_by(is_admin=True).count(),
        'total_moderators': User.query.filter_by(is_moderator=True).count(),
        'total_challenges': Challenge.query.count(),
        'pending_submissions': ChallengeSubmission.query.filter_by(status='pending').count(),
        'total_posts': CommunityPost.query.count(),
        'total_badges': UserBadge.query.count(),
    }
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
    all_badges = Badge.query.order_by(Badge.title).all()
    return render_template('admin/users.html', users=all_users, all_badges=all_badges)


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
    
    from sqlalchemy import text
    with db.engine.connect() as conn:
        conn.execute(text('DELETE FROM user_notifications WHERE user_id=:u'), {'u': user.id})
        conn.execute(text('DELETE FROM flag_attempts WHERE user_id=:u'), {'u': user.id})
        conn.execute(text('DELETE FROM user_challenge_solves WHERE user_id=:u'), {'u': user.id})
        conn.commit()

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

        if 'avatar' in request.files and request.files['avatar'].filename:
            file = request.files['avatar']
            os.makedirs(AVATAR_DIR, exist_ok=True)
            filename = f'avatar_{user.username}.webp'
            img = Image.open(file).convert('RGB')
            img = img.resize((500, 500))
            img.save(os.path.join(AVATAR_DIR, filename), 'WEBP', quality=85)
            user.profile_picture = filename

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
    limited_count = None
    if is_limited:
        lc = request.form.get('limited_count', '').strip()
        limited_count = int(lc) if lc.isdigit() and int(lc) > 0 else None
    border_style = request.form.get('border_style', 'tier1')
    from_event = 'from_event' in request.form
    is_unattainable = 'is_unattainable' in request.form

    if not title or not description:
        flash('Title and description are required', 'danger')
        return redirect(url_for('admin.badges'))

    cropped_data = request.form.get('cropped_image', '')
    if cropped_data and cropped_data.startswith('data:image'):
        header, b64 = cropped_data.split(',', 1)
        img_bytes = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
    elif 'image' in request.files and request.files['image'].filename:
        img = Image.open(request.files['image']).convert('RGBA')
    else:
        flash('Badge image is required', 'danger')
        return redirect(url_for('admin.badges'))

    os.makedirs(BADGE_DIR, exist_ok=True)
    filename = secure_filename(f'badge_{title.lower().replace(" ", "_")}.webp')
    img = img.resize((500, 500))
    img.save(os.path.join(BADGE_DIR, filename), 'WEBP', quality=85)

    badge = Badge(title=title, description=description, image_filename=filename, is_limited=is_limited, limited_count=limited_count, border_style=border_style, from_event=from_event, is_unattainable=is_unattainable, display_border=('display_border' in request.form), display_shape=request.form.get('display_shape', 'square'))
    db.session.add(badge)
    db.session.commit()
    log_action('create_badge', title)
    flash(f'Badge "{title}" created!', 'success')
    return redirect(url_for('admin.badges'))


@admin_bp.route('/badges/<int:badge_id>/rules/create', methods=['POST'])
def create_badge_rule(badge_id):
    Badge.query.get_or_404(badge_id)
    rule_type = request.form.get('rule_type', '').strip()
    threshold = request.form.get('threshold', '').strip()
    challenge_id = request.form.get('challenge_id', '').strip()
    threshold_val = int(threshold) if threshold.isdigit() else None
    ch_id = int(challenge_id) if challenge_id.isdigit() else None
    token = secrets.token_hex(32) if rule_type == 'claimable_link' else None
    rule = BadgeRule(
        badge_id=badge_id,
        rule_type=rule_type,
        threshold=threshold_val,
        challenge_id=ch_id,
        claim_token=token,
    )
    db.session.add(rule)
    db.session.commit()
    log_action('create_badge_rule', f'badge={badge_id} type={rule_type}')
    flash('Badge rule created!', 'success')
    return redirect(url_for('admin.badge_rules', badge_id=badge_id))


@admin_bp.route('/badges/<int:badge_id>/rules')
def badge_rules(badge_id):
    badge = Badge.query.get_or_404(badge_id)
    all_challenges = Challenge.query.order_by(Challenge.title).all()
    return render_template('admin/badge_rules.html', badge=badge,
                           rules=badge.rules, all_challenges=all_challenges)


@admin_bp.route('/badges/rules/<int:rule_id>/delete', methods=['POST'])
def delete_badge_rule(rule_id):
    rule = BadgeRule.query.get_or_404(rule_id)
    badge_id = rule.badge_id
    db.session.delete(rule)
    db.session.commit()
    log_action('delete_badge_rule', str(rule_id))
    return redirect(url_for('admin.badge_rules', badge_id=badge_id))


@admin_bp.route('/badges/rules/<int:rule_id>/toggle', methods=['POST'])
def toggle_badge_rule(rule_id):
    rule = BadgeRule.query.get_or_404(rule_id)
    rule.is_active = not rule.is_active
    db.session.commit()
    log_action('toggle_badge_rule', f'rule:{rule_id} -> {"active" if rule.is_active else "inactive"}')
    return redirect(url_for('admin.badge_rules', badge_id=rule.badge_id))


@admin_bp.route('/badges/<int:badge_id>/delete', methods=['POST'])
def delete_badge(badge_id):
    badge = Badge.query.get_or_404(badge_id)
    db.session.delete(badge)
    db.session.commit()
    log_action('delete_badge', badge.title)
    flash(f'Badge "{badge.title}" deleted', 'info')
    return redirect(url_for('admin.badges'))


@admin_bp.route('/users/<int:user_id>/make-moderator', methods=['POST'])
def make_moderator(user_id):
    """Assign Community Moderator role."""
    user = User.query.get_or_404(user_id)
    user.is_moderator = True
    db.session.commit()
    log_action('make_moderator', user.username)
    flash(f'{user.username} is now a Community Moderator.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/remove-moderator', methods=['POST'])
def remove_moderator(user_id):
    """Remove Community Moderator role."""
    user = User.query.get_or_404(user_id)
    user.is_moderator = False
    db.session.commit()
    log_action('remove_moderator', user.username)
    flash(f'{user.username} is no longer a Community Moderator.', 'info')
    return redirect(url_for('admin.users'))


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


@admin_bp.route('/users/<int:user_id>/ban', methods=['POST'])
def ban_user(user_id):
    """Ban a user — blocks login and archives their profile."""
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot ban yourself.', 'danger')
        return redirect(url_for('admin.users'))
    reason = request.form.get('ban_reason', '').strip() or 'Violation of platform rules.'
    user.is_banned = True
    user.ban_reason = reason
    user.banned_at = datetime.utcnow()
    db.session.commit()
    log_action('ban_user', f'{user.username} — {reason}')
    flash(f'{user.username} has been banned.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/unban', methods=['POST'])
def unban_user(user_id):
    """Lift a ban from a user."""
    user = User.query.get_or_404(user_id)
    user.is_banned = False
    user.ban_reason = None
    user.banned_at = None
    db.session.commit()
    log_action('unban_user', user.username)
    flash(f'{user.username} has been unbanned.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/timeout', methods=['POST'])
def timeout_user(user_id):
    """Temporarily restrict a user from community interactions."""
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot timeout yourself.', 'danger')
        return redirect(url_for('admin.users'))
    hours = request.form.get('timeout_hours', '').strip()
    try:
        hours = max(1, int(hours))
    except (ValueError, TypeError):
        hours = 24
    user.timeout_until = datetime.utcnow() + timedelta(hours=hours)
    db.session.commit()
    log_action('timeout_user', f'{user.username} for {hours}h')
    flash(f'{user.username} timed out for {hours} hour(s).', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/untimeout', methods=['POST'])
def untimeout_user(user_id):
    """Remove a community timeout from a user."""
    user = User.query.get_or_404(user_id)
    user.timeout_until = None
    db.session.commit()
    log_action('untimeout_user', user.username)
    flash(f'{user.username}\'s timeout has been lifted.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/audit-log')
def audit_log():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 100
    entries = []
    total = 0
    if os.path.exists(AUDIT_LOG):
        with open(AUDIT_LOG, newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            row.setdefault('category', 'admin')
            row.setdefault('ip', '')
            if 'user' not in row and 'admin' in row:
                row['user'] = row['admin']
        rows.reverse()
        total = len(rows)
        entries = rows[(page - 1) * per_page: page * per_page]
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template('admin/audit_log.html', entries=entries,
                           page=page, total_pages=total_pages, total=total)


@admin_bp.route('/audit-log/download')
def audit_log_download():
    if os.path.exists(AUDIT_LOG):
        return send_file(AUDIT_LOG, mimetype='text/csv', as_attachment=True,
                         download_name=f'admin_audit_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv')
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
    live = Challenge.query.order_by(Challenge.created_at.desc()).all()

    return render_template('admin/challenges.html',
                         pending=pending,
                         approved=approved,
                         rejected=rejected,
                         live=live)


@admin_bp.route('/challenges/<int:submission_id>/approve', methods=['POST'])
def approve_challenge(submission_id):
    submission = ChallengeSubmission.query.get_or_404(submission_id)
    if submission.status == 'approved':
        flash('This challenge is already approved', 'info')
        return redirect(url_for('admin.challenges'))
    challenge = Challenge(
        title=submission.title,
        description=submission.description,
        category=submission.category,
        difficulty=submission.difficulty,
        flag=submission.flag,
        is_regex=submission.is_regex if hasattr(submission, 'is_regex') else False,
        points=submission.points,
        author_id=submission.author_id
    )
    submission.status = 'approved'
    db.session.add(challenge)
    db.session.commit()  # commit first to get challenge.id
    if getattr(submission, 'web_archive_path', None):
        db.session.add(WebChallenge(challenge_id=challenge.id, archive_path=submission.web_archive_path))
    if getattr(submission, 'nc_binary_path', None):
        db.session.add(NcChallenge(challenge_id=challenge.id, binary_path=submission.nc_binary_path))
    db.session.commit()
    log_action('approve_challenge', challenge.title)
    from app.ranking import check_auto_badges
    from app.notifs import notify_new_challenge, notify_submission_result
    check_auto_badges(submission.author_id)
    notify_new_challenge(challenge)
    notify_submission_result(submission.author_id, challenge.title, approved=True)
    flash(f'Challenge "{challenge.title}" approved and published!', 'success')
    return redirect(url_for('admin.challenges'))


@admin_bp.route('/challenges/<int:submission_id>/reject', methods=['POST'])
def reject_challenge(submission_id):
    """Reject a user-submitted challenge and permanently delete its attached files."""
    submission = ChallengeSubmission.query.get_or_404(submission_id)

    for sf in list(submission.files):
        disk_path = os.path.join(SUBMISSION_FILES_DIR, sf.stored_name)
        if os.path.exists(disk_path):
            os.remove(disk_path)
        db.session.delete(sf)

    submission.status = 'rejected'
    db.session.commit()

    log_action('reject_challenge', submission.title)
    from app.notifs import notify_submission_result
    notify_submission_result(submission.author_id, submission.title, approved=False)
    flash(f'Challenge "{submission.title}" rejected', 'info')
    return redirect(url_for('admin.challenges'))


@admin_bp.route('/challenges/<int:challenge_id>/delete', methods=['POST'])
def delete_challenge(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    title = challenge.title
    if challenge.category == 'Web' and challenge.web_challenge:
        try:
            from app.web_runner import cleanup_serve_dir
            cleanup_serve_dir(challenge_id)
        except Exception:
            pass
    if challenge.category == 'Binary Exploitation' and challenge.nc_challenge:
        try:
            from app.nc_runner import cleanup_nc_dir
            cleanup_nc_dir(challenge_id)
        except Exception:
            pass
    db.session.delete(challenge)
    db.session.commit()
    log_action('delete_challenge', title)
    flash(f'Challenge "{title}" deleted', 'info')
    return redirect(url_for('admin.challenges'))


@admin_bp.route('/challenges/<int:challenge_id>/edit', methods=['GET', 'POST'])
def edit_challenge(challenge_id):
    """Edit a live challenge."""
    challenge = Challenge.query.get_or_404(challenge_id)
    if request.method == 'POST':
        challenge.title = request.form.get('title', '').strip()
        challenge.description = request.form.get('description', '').strip()
        challenge.category = request.form.get('category', '').strip()
        challenge.difficulty = request.form.get('difficulty', '').strip()
        challenge.flag = request.form.get('flag', '').strip()
        challenge.is_regex = 'is_regex' in request.form
        points_val = request.form.get('points', '').strip()
        if points_val.isdigit():
            challenge.points = int(points_val)
        db.session.commit()
        log_action('edit_challenge', challenge.title)
        flash(f'Challenge "{challenge.title}" updated', 'success')
        return redirect(url_for('admin.challenges'))
    return render_template('admin/edit_challenge.html', challenge=challenge)


@admin_bp.route('/challenges/<int:challenge_id>/toggle-visibility', methods=['POST'])
def toggle_challenge_visibility(challenge_id):
    """Hide or unhide a live challenge from players."""
    challenge = Challenge.query.get_or_404(challenge_id)
    challenge.is_hidden = not challenge.is_hidden
    db.session.commit()
    state = 'hidden' if challenge.is_hidden else 'visible'
    log_action('toggle_challenge_visibility', f'{challenge.title} -> {state}')
    flash(f'"{challenge.title}" is now {state}.', 'info')
    return redirect(url_for('admin.challenges'))


@admin_bp.route('/challenges/<int:challenge_id>/unofficial', methods=['POST'])
def mark_unofficial(challenge_id):
    """Mark a challenge as unofficial/community by reassigning to original submitter."""
    challenge = Challenge.query.get_or_404(challenge_id)
    submission = ChallengeSubmission.query.filter_by(title=challenge.title, status='approved').first()
    if submission:
        challenge.author_id = submission.author_id
        db.session.commit()
        log_action('mark_unofficial', challenge.title)
        flash(f'"{challenge.title}" marked as unofficial/community', 'info')
    else:
        flash('Could not find original submission to reassign author', 'danger')
    return redirect(url_for('admin.challenges'))


# ========================================
# LEGENDARY RANK MANAGEMENT
# ========================================

@admin_bp.route('/users/<int:user_id>/legendary', methods=['POST'])
def assign_legendary(user_id):
    from app.ranking import ADMIN_ASSIGNABLE_LEGENDARY
    user = User.query.get_or_404(user_id)
    rank = request.form.get('legendary_rank', '').strip()
    if rank and rank not in ADMIN_ASSIGNABLE_LEGENDARY:
        flash('You do not have permission to assign that rank.', 'danger')
        return redirect(url_for('admin.edit_user', user_id=user_id))
    # Protect dev-only ranks from being overwritten by admins
    if user.legendary_rank in ('Zero-Day Deity', 'Singularity Architect', 'Ghost in the Core'):
        flash('This user holds a rank that cannot be modified by administrators.', 'danger')
        return redirect(url_for('admin.edit_user', user_id=user_id))
    user.legendary_rank = rank or None
    db.session.commit()
    log_action('assign_legendary_rank', f'{user.username} -> {rank or "(removed)"}')
    flash(f'Legendary rank updated for {user.username}.', 'success')
    return redirect(url_for('admin.edit_user', user_id=user_id))


# ========================================
# NOTIFICATIONS & ANNOUNCEMENTS
# ========================================

@admin_bp.route('/notifications')
def notifications():
    all_notifs = Notification.query.order_by(Notification.created_at.desc()).all()
    all_announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template('admin/notifications.html',
                           notifications=all_notifs,
                           announcements=all_announcements)


@admin_bp.route('/notifications/create', methods=['POST'])
def create_notification():
    title = request.form.get('title', '').strip()
    body = request.form.get('body', '').strip()
    if not title or not body:
        flash('Title and body are required', 'danger')
        return redirect(url_for('admin.notifications'))
    db.session.add(Notification(title=title, body=body, created_by=current_user.id))
    db.session.commit()
    log_action('create_notification', title)
    flash('Notification sent!', 'success')
    return redirect(url_for('admin.notifications'))


@admin_bp.route('/notifications/<int:notif_id>/delete', methods=['POST'])
def delete_notification(notif_id):
    n = Notification.query.get_or_404(notif_id)
    db.session.delete(n)
    db.session.commit()
    log_action('delete_notification', str(notif_id))
    return redirect(url_for('admin.notifications'))


@admin_bp.route('/announcements/create', methods=['POST'])
def create_announcement():
    message = request.form.get('message', '').strip()
    color = request.form.get('color', 'red')
    starts_at_str = request.form.get('starts_at', '').strip()
    ends_at_str = request.form.get('ends_at', '').strip()
    if not message or not starts_at_str or not ends_at_str:
        flash('Message, start time, and end time are required', 'danger')
        return redirect(url_for('admin.notifications'))
    try:
        starts_at = datetime.fromisoformat(starts_at_str)
        ends_at = datetime.fromisoformat(ends_at_str)
    except ValueError:
        flash('Invalid date format', 'danger')
        return redirect(url_for('admin.notifications'))
    db.session.add(Announcement(message=message, color=color,
                                starts_at=starts_at, ends_at=ends_at,
                                created_by=current_user.id))
    db.session.commit()
    log_action('create_announcement', message[:60])
    flash('Announcement scheduled!', 'success')
    return redirect(url_for('admin.notifications'))


@admin_bp.route('/announcements/<int:ann_id>/delete', methods=['POST'])
def delete_announcement(ann_id):
    a = Announcement.query.get_or_404(ann_id)
    db.session.delete(a)
    db.session.commit()
    log_action('delete_announcement', str(ann_id))
    return redirect(url_for('admin.notifications'))


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
    db.session.delete(post)
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


# ========================================
# BUG REPORTS
# ========================================

@admin_bp.route('/bug-reports')
def bug_reports():
    reports = BugReport.query.order_by(BugReport.created_at.desc()).all()
    return render_template('admin/bug_reports.html', reports=reports)


@admin_bp.route('/bug-reports/<int:report_id>/status', methods=['POST'])
def update_bug_status(report_id):
    report = BugReport.query.get_or_404(report_id)
    new_status = request.form.get('status', 'open')
    report.status = new_status
    db.session.commit()
    log_action('update_bug_status', f'#{report_id} -> {new_status}')
    return redirect(url_for('admin.bug_reports'))


@admin_bp.route('/bug-reports/<int:report_id>/delete', methods=['POST'])
def delete_bug_report(report_id):
    report = BugReport.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()
    log_action('delete_bug_report', f'#{report_id}')
    return redirect(url_for('admin.bug_reports'))


# ========================================
# FLAG SUBMISSIONS DASHBOARD
# ========================================

@admin_bp.route('/flag-submissions')
def flag_submissions():
    challenge_id = request.args.get('challenge_id', type=int)
    correct_filter = request.args.get('correct', '')
    query = FlagAttempt.query
    if challenge_id:
        query = query.filter_by(challenge_id=challenge_id)
    if correct_filter == '1':
        query = query.filter_by(correct=True)
    elif correct_filter == '0':
        query = query.filter_by(correct=False)
    attempts = query.order_by(FlagAttempt.attempted_at.desc()).all()
    live_challenges = Challenge.query.order_by(Challenge.title).all()
    return render_template('admin/flag_submissions.html',
                           attempts=attempts,
                           live_challenges=live_challenges,
                           selected_challenge=challenge_id,
                           correct_filter=correct_filter)


@admin_bp.route('/flag-submissions/<int:attempt_id>/accept', methods=['POST'])
def accept_flag_submission(attempt_id):
    attempt = FlagAttempt.query.get_or_404(attempt_id)
    already = UserChallengeSolve.query.filter_by(
        user_id=attempt.user_id, challenge_id=attempt.challenge_id).first()
    if already:
        flash('User has already solved this challenge.', 'info')
        return redirect(url_for('admin.flag_submissions'))
    db.session.add(UserChallengeSolve(
        user_id=attempt.user_id, challenge_id=attempt.challenge_id))
    attempt.correct = True
    db.session.commit()
    log_action('accept_flag_submission', f'attempt:{attempt_id} user:{attempt.user_id}')
    flash('Submission accepted and solve recorded.', 'success')
    return redirect(url_for('admin.flag_submissions'))


@admin_bp.route('/flag-submissions/<int:attempt_id>/delete', methods=['POST'])
def delete_flag_submission(attempt_id):
    """Delete a correct flag submission: remove solve record, revert points, remove first blood."""
    from sqlalchemy import text
    attempt = FlagAttempt.query.get_or_404(attempt_id)
    if not attempt.correct:
        flash('Only correct submissions can be deleted.', 'danger')
        return redirect(url_for('admin.flag_submissions'))

    user_id = attempt.user_id
    challenge_id = attempt.challenge_id

    # Use raw SQL to avoid ORM flush issues with NOT NULL constraints
    with db.engine.connect() as conn:
        conn.execute(text(
            'DELETE FROM user_challenge_solves WHERE user_id=:u AND challenge_id=:c'
        ), {'u': user_id, 'c': challenge_id})
        conn.execute(text(
            'DELETE FROM user_notifications WHERE user_id=:u AND category=:cat AND title LIKE :t AND link LIKE :l'
        ), {'u': user_id, 'cat': 'challenge', 't': '%First Blood%', 'l': f'%/challenges/{challenge_id}%'})
        conn.execute(text('DELETE FROM flag_attempts WHERE id=:id'), {'id': attempt_id})
        conn.commit()

    log_action('delete_flag_submission', f'attempt:{attempt_id} user:{user_id} challenge:{challenge_id}')
    flash('Submission deleted, solve reverted, and first blood removed (if applicable).', 'success')
    return redirect(url_for('admin.flag_submissions'))


# ========================================
# EXTENDED DASHBOARD STATS
# ========================================

@admin_bp.route('/stats')
def stats():
    from app.ranking import get_user_rank

    unique_ips = set()
    if os.path.exists(AUDIT_LOG):
        with open(AUDIT_LOG, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                ip = row.get('ip', '').strip()
                if ip and ip != 'unknown':
                    unique_ips.add(ip)

    total_points = db.session.query(
        func.sum(Challenge.points)
    ).join(UserChallengeSolve, UserChallengeSolve.challenge_id == Challenge.id).scalar() or 0

    total_badges = UserBadge.query.count()

    # Score buckets via SQL — no Python loop over all users
    score_sq = (
        db.session.query(
            UserChallengeSolve.user_id,
            func.sum(Challenge.points).label('score')
        ).join(Challenge, UserChallengeSolve.challenge_id == Challenge.id)
        .group_by(UserChallengeSolve.user_id)
        .subquery()
    )
    bucket_rows = db.session.query(
        case(
            (score_sq.c.score == 0, '0'),
            (score_sq.c.score <= 100, '1-100'),
            (score_sq.c.score <= 500, '101-500'),
            (score_sq.c.score <= 1000, '501-1000'),
            else_='1000+'
        ).label('bucket'),
        func.count().label('cnt')
    ).group_by('bucket').all()
    score_buckets = {'0': 0, '1-100': 0, '101-500': 0, '501-1000': 0, '1000+': 0}
    for bucket, cnt in bucket_rows:
        score_buckets[bucket] = cnt
    # Users with zero solves fall into the '0' bucket
    zero_solvers = User.query.filter_by(is_hidden_from_scoreboard=False).count() - sum(score_buckets.values())
    score_buckets['0'] += max(zero_solvers, 0)

    # Lowest percentile user (non-legendary, non-hidden)
    all_users = User.query.filter_by(is_hidden_from_scoreboard=False).filter(
        User.legendary_rank.is_(None)).all()
    lowest_pct = None
    lowest_user = None
    for u in all_users:
        pct, _ = get_user_rank(u)
        if lowest_pct is None or pct < lowest_pct:
            lowest_pct = pct
            lowest_user = u

    solve_counts = db.session.query(
        Challenge.id, Challenge.title, func.count(UserChallengeSolve.id).label('cnt')
    ).outerjoin(UserChallengeSolve, UserChallengeSolve.challenge_id == Challenge.id
    ).group_by(Challenge.id).all()

    most_solved = max(solve_counts, key=lambda r: r.cnt, default=None)
    least_solved = min(solve_counts, key=lambda r: r.cnt, default=None)
    solve_chart = sorted(solve_counts, key=lambda r: r.cnt, reverse=True)[:15]

    total_users_count = User.query.count() or 1
    solve_pct = [{'title': r.title[:20], 'pct': round(r.cnt / total_users_count * 100, 1)} for r in solve_counts]

    correct_count = FlagAttempt.query.filter_by(correct=True).count()
    wrong_count = FlagAttempt.query.filter_by(correct=False).count()

    cat_rows = db.session.query(
        Challenge.category, func.count(UserChallengeSolve.id)
    ).outerjoin(UserChallengeSolve, UserChallengeSolve.challenge_id == Challenge.id
    ).group_by(Challenge.category).all()

    cat_pts_rows = db.session.query(
        Challenge.category, func.sum(Challenge.points)
    ).group_by(Challenge.category).all()

    opens_count = ChallengeOpen.query.count()
    attempts_count = FlagAttempt.query.count()

    return render_template('admin/stats.html',
        unique_ips=len(unique_ips),
        total_points=total_points,
        total_badges=total_badges,
        lowest_pct=round(lowest_pct, 2) if lowest_pct is not None else 'N/A',
        lowest_user=lowest_user,
        most_solved=most_solved,
        least_solved=least_solved,
        solve_chart=solve_chart,
        score_buckets=score_buckets,
        solve_pct=solve_pct,
        correct_count=correct_count,
        wrong_count=wrong_count,
        cat_rows=cat_rows,
        cat_pts_rows=cat_pts_rows,
        opens_count=opens_count,
        attempts_count=attempts_count,
    )


# ========================================
# BULK ACTIONS
# ========================================

@admin_bp.route('/users/bulk', methods=['POST'])
def bulk_users():
    ids = request.form.getlist('user_ids', type=int)
    action = request.form.get('bulk_action', '')
    if not ids or not action:
        flash('No users or action selected.', 'danger')
        return redirect(url_for('admin.users'))
    users_list = User.query.filter(User.id.in_(ids)).all()
    for u in users_list:
        if u.id == current_user.id:
            continue
        if action == 'ban':
            u.is_banned = True
            u.ban_reason = request.form.get('ban_reason', 'Bulk ban.')
            u.banned_at = datetime.utcnow()
        elif action == 'unban':
            u.is_banned = False
            u.ban_reason = None
            u.banned_at = None
        elif action == 'delete':
            db.session.delete(u)
            continue
        elif action == 'reset_password':
            new_pw = request.form.get('new_password', '').strip()
            if new_pw:
                u.set_password(new_pw)
        elif action == 'set_affiliation':
            u.affiliation = request.form.get('affiliation', '').strip() or None
        elif action == 'assign_badge':
            bid = request.form.get('badge_id', type=int)
            if bid and not UserBadge.query.filter_by(user_id=u.id, badge_id=bid).first():
                db.session.add(UserBadge(user_id=u.id, badge_id=bid))
        elif action == 'timeout':
            hours = int(request.form.get('timeout_hours', 24))
            u.timeout_until = datetime.utcnow() + timedelta(hours=hours)
        elif action == 'make_moderator':
            u.is_moderator = True
        elif action == 'remove_moderator':
            u.is_moderator = False
    db.session.commit()
    log_action(f'bulk_{action}', f'{len(ids)} users')
    flash(f'Bulk action "{action}" applied to {len(ids)} user(s).', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/challenges/bulk', methods=['POST'])
def bulk_challenges():
    ids = request.form.getlist('challenge_ids', type=int)
    action = request.form.get('bulk_action', '')
    if not ids or not action:
        flash('No challenges or action selected.', 'danger')
        return redirect(url_for('admin.challenges'))
    chs = Challenge.query.filter(Challenge.id.in_(ids)).all()
    for ch in chs:
        if action == 'delete':
            db.session.delete(ch)
            continue
        elif action == 'set_category':
            ch.category = request.form.get('category', ch.category)
        elif action == 'set_difficulty':
            ch.difficulty = request.form.get('difficulty', ch.difficulty)
        elif action == 'set_points':
            pts = request.form.get('points', type=int)
            if pts is not None:
                ch.points = pts
        elif action == 'hide':
            ch.is_hidden = True
        elif action == 'unhide':
            ch.is_hidden = False
    db.session.commit()
    log_action(f'bulk_{action}', f'{len(ids)} challenges')
    flash(f'Bulk action "{action}" applied to {len(ids)} challenge(s).', 'success')
    return redirect(url_for('admin.challenges'))


@admin_bp.route('/posts/bulk', methods=['POST'])
def bulk_posts():
    ids = request.form.getlist('post_ids', type=int)
    action = request.form.get('bulk_action', '')
    if not ids or not action:
        flash('No posts or action selected.', 'danger')
        return redirect(url_for('admin.posts'))
    posts_list = CommunityPost.query.filter(CommunityPost.id.in_(ids)).all()
    for p in posts_list:
        if action == 'delete':
            db.session.delete(p)
            continue
        elif action == 'disable_comments':
            p.comments_disabled = True
        elif action == 'enable_comments':
            p.comments_disabled = False
        elif action == 'disable_reactions':
            p.reactions_disabled = True
        elif action == 'enable_reactions':
            p.reactions_disabled = False
        elif action == 'archive':
            p.is_archived = True
        elif action == 'unarchive':
            p.is_archived = False
    db.session.commit()
    log_action(f'bulk_{action}', f'{len(ids)} posts')
    flash(f'Bulk action "{action}" applied to {len(ids)} post(s).', 'success')
    return redirect(url_for('admin.posts'))


# ========================================
# COMMENT & REACTION MANAGEMENT (admin)
# ========================================

@admin_bp.route('/comments/<int:comment_id>/delete', methods=['POST'])
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    log_action('delete_comment', f'comment:{comment_id} post:{post_id}')
    flash('Comment deleted.', 'info')
    return redirect(url_for('admin.posts'))


@admin_bp.route('/posts/<int:post_id>/toggle-comments', methods=['POST'])
def admin_toggle_comments(post_id):
    post = CommunityPost.query.get_or_404(post_id)
    post.comments_disabled = not post.comments_disabled
    db.session.commit()
    log_action('toggle_comments', f'post:{post_id}')
    return redirect(url_for('admin.posts'))


@admin_bp.route('/posts/<int:post_id>/toggle-reactions', methods=['POST'])
def admin_toggle_reactions(post_id):
    post = CommunityPost.query.get_or_404(post_id)
    post.reactions_disabled = not post.reactions_disabled
    db.session.commit()
    log_action('toggle_reactions', f'post:{post_id}')
    return redirect(url_for('admin.posts'))


# ========================================
# MILESTONE MANAGEMENT
# ========================================

MILESTONE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'milestones')


def _award_milestone_to_user(milestone, user):
    from app.models import UserNotification
    if UserMilestone.query.filter_by(user_id=user.id, milestone_id=milestone.id).first():
        return False
    db.session.add(UserMilestone(user_id=user.id, milestone_id=milestone.id))
    db.session.add(UserNotification(
        user_id=user.id,
        title='Milestone Unlocked!',
        body=f'You earned the milestone: {milestone.title}',
        category='system',
    ))
    return True


def _check_milestone_for_user(milestone, user):
    if not milestone.is_active:
        return False
    rt = milestone.rule_type
    th = milestone.threshold or 0
    if rt == 'manual':
        return False
    elif rt == 'solved_n_challenges':
        eligible = len(user.solves) >= th
    elif rt == 'reached_score':
        eligible = user.get_score() >= th
    elif rt == 'community_posts':
        eligible = len(user.posts) >= th
    elif rt == 'approved_submissions':
        from app.models import ChallengeSubmission
        eligible = ChallengeSubmission.query.filter_by(author_id=user.id, status='approved').count() >= th
    else:
        eligible = False
    if eligible:
        return _award_milestone_to_user(milestone, user)
    return False


def check_milestones_for_user(user_id: int):
    user = User.query.get(user_id)
    if not user:
        return
    for m in Milestone.query.filter_by(is_active=True).all():
        _check_milestone_for_user(m, user)
    db.session.commit()


@admin_bp.route('/milestones')
def milestones():
    all_milestones = Milestone.query.order_by(Milestone.created_at.desc()).all()
    return render_template('admin/milestones.html', milestones=all_milestones)


@admin_bp.route('/milestones/create', methods=['POST'])
def create_milestone():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    rule_type = request.form.get('rule_type', 'manual').strip()
    threshold_raw = request.form.get('threshold', '').strip()
    threshold = int(threshold_raw) if threshold_raw.isdigit() else None

    if not title or not description:
        flash('Title and description are required', 'danger')
        return redirect(url_for('admin.milestones'))

    cropped_data = request.form.get('cropped_image', '')
    if cropped_data and cropped_data.startswith('data:image'):
        header, b64 = cropped_data.split(',', 1)
        img_bytes = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
    elif 'image' in request.files and request.files['image'].filename:
        img = Image.open(request.files['image']).convert('RGBA')
    else:
        flash('Milestone image is required', 'danger')
        return redirect(url_for('admin.milestones'))

    os.makedirs(MILESTONE_DIR, exist_ok=True)
    filename = secure_filename(f'milestone_{title.lower().replace(" ", "_")}.webp')
    img = img.resize((500, 500))
    img.save(os.path.join(MILESTONE_DIR, filename), 'WEBP', quality=85)

    milestone = Milestone(title=title, description=description,
                          image_filename=filename, rule_type=rule_type,
                          threshold=threshold)
    db.session.add(milestone)
    db.session.commit()

    awarded = 0
    if rule_type != 'manual':
        for user in User.query.all():
            if _check_milestone_for_user(milestone, user):
                awarded += 1
        db.session.commit()

    log_action('create_milestone', title)
    flash(f'Milestone "{title}" created and auto-awarded to {awarded} user(s).', 'success')
    return redirect(url_for('admin.milestones'))


@admin_bp.route('/milestones/<int:milestone_id>/award', methods=['POST'])
def award_milestone(milestone_id):
    milestone = Milestone.query.get_or_404(milestone_id)
    username = request.form.get('username', '').strip()
    user = User.query.filter_by(username=username).first()
    if not user:
        flash(f'User "{username}" not found.', 'danger')
        return redirect(url_for('admin.milestones'))
    if _award_milestone_to_user(milestone, user):
        db.session.commit()
        log_action('award_milestone', f'{milestone.title} -> {user.username}')
        flash(f'Milestone awarded to {user.username}.', 'success')
    else:
        flash(f'{user.username} already has this milestone.', 'info')
    return redirect(url_for('admin.milestones'))


@admin_bp.route('/milestones/<int:milestone_id>/toggle', methods=['POST'])
def toggle_milestone(milestone_id):
    milestone = Milestone.query.get_or_404(milestone_id)
    milestone.is_active = not milestone.is_active
    db.session.commit()
    log_action('toggle_milestone', f'{milestone.title} -> {"active" if milestone.is_active else "inactive"}')
    return redirect(url_for('admin.milestones'))


@admin_bp.route('/milestones/<int:milestone_id>/delete', methods=['POST'])
def delete_milestone(milestone_id):
    milestone = Milestone.query.get_or_404(milestone_id)
    title = milestone.title
    db.session.delete(milestone)
    db.session.commit()
    log_action('delete_milestone', title)
    flash(f'Milestone "{title}" deleted.', 'info')
    return redirect(url_for('admin.milestones'))

