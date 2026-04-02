from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, send_from_directory, jsonify, Response
from flask_login import login_required, current_user
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError
import os
from app import db, csrf
from app.models import User
from app.identicon import generate_identicon
from app.image_utils import encode_avatar

AVATAR_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'avatars')
BADGE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'badges')
MILESTONE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'milestones')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB

settings_bp = Blueprint('settings', __name__, template_folder='../templates')


def _safe_filename(filename: str) -> str:
    """Strip all path components, allow only safe characters."""
    from werkzeug.utils import secure_filename as _sf
    return _sf(os.path.basename(filename))


@settings_bp.route('/avatar/<username>')
@login_required
def serve_avatar(username):
    if not current_user.is_authenticated:
        abort(401)
    filename = _safe_filename(f'avatar_{username}.webp')
    real_avatar_dir = os.path.realpath(AVATAR_DIR)
    if not os.path.exists(os.path.join(real_avatar_dir, filename)):
        user = User.query.filter_by(username=username).first()
        if not user or not user.profile_picture:
            generate_identicon(username)
    return send_from_directory(real_avatar_dir, filename)


@settings_bp.route('/badge-img/<filename>')
@login_required
def serve_badge(filename):
    if not current_user.is_authenticated:
        abort(401)
    filename = _safe_filename(filename)
    real_badge_dir = os.path.realpath(BADGE_DIR)
    if os.path.exists(os.path.join(real_badge_dir, filename)):
        return send_from_directory(real_badge_dir, filename)
    static_dir = os.path.realpath(
        os.path.join(os.path.dirname(__file__), '..', 'static', 'badges')
    )
    if os.path.exists(os.path.join(static_dir, filename)):
        return send_from_directory(static_dir, filename)
    abort(404)


@settings_bp.route('/milestone-img/<filename>')
@login_required
def serve_milestone(filename):
    if not current_user.is_authenticated:
        abort(401)
    filename = _safe_filename(filename)
    real_milestone_dir = os.path.realpath(MILESTONE_DIR)
    if not os.path.exists(os.path.join(real_milestone_dir, filename)):
        abort(404)
    return send_from_directory(real_milestone_dir, filename)


@settings_bp.route('/robots.txt')
def robots_txt():
    return Response("User-agent: *\nDisallow: /\n", mimetype='text/plain')


@settings_bp.route('/badges')
def badges():
    from app.models import Badge
    all_badges = Badge.query.order_by(Badge.created_at.asc()).all()
    border_map = {
        'tier1':  'border:3px solid #4a4a4a;',
        'tier2':  'border:3px solid #b0b8c8;box-shadow:0 0 5px rgba(176,184,200,0.4),0 0 12px rgba(176,184,200,0.2);',
        'tier3':  'border:3px solid #4ade80;box-shadow:0 0 7px rgba(74,222,128,0.55),0 0 14px rgba(74,222,128,0.2);',
        'tier4':  'border:3px solid #60a5fa;box-shadow:0 0 9px rgba(96,165,250,0.65),0 0 20px rgba(96,165,250,0.2);',
        'tier5':  'border:3px solid #a78bfa;box-shadow:0 0 12px rgba(167,139,250,0.65),0 0 24px rgba(167,139,250,0.2);',
        'tier6':  'border:3px solid #f472b6;box-shadow:0 0 12px rgba(244,114,182,0.85),0 0 26px rgba(244,114,182,0.35);',
        'tier7':  'border:3px solid #fb923c;box-shadow:0 0 10px rgba(251,146,60,0.8),0 0 22px rgba(251,146,60,0.35);',
        'tier8':  'border:3px solid #facc15;box-shadow:0 0 14px rgba(250,204,21,0.85),0 0 30px rgba(250,204,21,0.35),inset 0 0 10px rgba(250,204,21,0.2);',
        'tier9':  'border:3px solid #f87171;box-shadow:0 0 14px rgba(248,113,113,0.9),0 0 32px rgba(248,113,113,0.45),0 0 60px rgba(248,113,113,0.15);',
        'tier10': 'border:3px solid transparent;',
    }
    return render_template('badges.html', badges=all_badges, border_map=border_map)


@settings_bp.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
@csrf.exempt
def mark_notification_read(notif_id):
    from app.models import Notification, NotificationRead
    Notification.query.get_or_404(notif_id)
    if not NotificationRead.query.filter_by(notification_id=notif_id, user_id=current_user.id).first():
        db.session.add(NotificationRead(notification_id=notif_id, user_id=current_user.id))
        db.session.commit()
    return jsonify(ok=True)


@settings_bp.route('/api/notifications/read-all', methods=['POST'])
@login_required
@csrf.exempt
def mark_all_notifications_read():
    from app.models import Notification, NotificationRead
    read_ids = {r.notification_id for r in
                NotificationRead.query.filter_by(user_id=current_user.id).all()}
    for n in Notification.query.all():
        if n.id not in read_ids:
            db.session.add(NotificationRead(notification_id=n.id, user_id=current_user.id))
    db.session.commit()
    return jsonify(ok=True)



@settings_bp.route('/ranks')
def ranks():
    from app.ranking import (
        RANK_TIERS, RANK_CSS, RANK_KEYFRAMES, RANK_DESCRIPTIONS,
        LEGENDARY_TIERS, LEGENDARY_CSS, LEGENDARY_DESCRIPTIONS, get_user_rank,
    )
    tiers = list(reversed(RANK_TIERS))
    current_rank_title = None
    if current_user.is_authenticated:
        _, current_rank_title = get_user_rank(current_user)
    return render_template('ranks.html',
                           tiers=tiers,
                           rank_css=RANK_CSS,
                           rank_keyframes=RANK_KEYFRAMES,
                           rank_descriptions=RANK_DESCRIPTIONS,
                           legendary_tiers=LEGENDARY_TIERS,
                           legendary_css=LEGENDARY_CSS,
                           legendary_descriptions=LEGENDARY_DESCRIPTIONS,
                           current_rank_title=current_rank_title)


@settings_bp.route('/api/ghost-unlock', methods=['POST'])
@login_required
@csrf.exempt
def ghost_unlock():
    from app.ranking import GHOST_COMMAND, LEGENDARY_TIERS
    data = request.get_json(silent=True) or {}
    if data.get('command') != GHOST_COMMAND:
        return jsonify(ok=False), 403
    if current_user.legendary_rank in ('Zero-Day Deity', 'Singularity Architect', 'Ghost in the Core'):
        return jsonify(ok=True, already=True)
    current_user.legendary_rank = 'Ghost in the Core'
    db.session.commit()
    return jsonify(ok=True, rank='Ghost in the Core')


@settings_bp.route('/api/radar')
@login_required
def api_radar():
    from app.ranking import get_category_radar_data
    ids = request.args.getlist('uid', type=int)[:4]
    users = [User.query.get(uid) for uid in ids]
    users = [u for u in users if u and not u.is_hidden_from_scoreboard]
    all_cats, datasets = get_category_radar_data(users)
    avatar_urls = {u.id: url_for('settings.serve_avatar', username=u.username) for u in users}
    return jsonify(categories=all_cats, datasets=datasets, avatars=avatar_urls)


def _rank_context(user):
    """Shared helper for account and public_profile — avoids duplicated imports."""
    from app.ranking import get_user_rank, ALL_RANK_CSS, RANK_KEYFRAMES, get_category_radar_data, compute_all_scores
    from app.models import ChallengeSubmission, FlagAttempt
    percentile, rank_title = get_user_rank(user)
    rank_style = ALL_RANK_CSS.get(rank_title, '')
    all_cats, radar_datasets = get_category_radar_data([user])
    all_users = db.session.query(User.id, User.username).filter_by(
        is_hidden_from_scoreboard=False).order_by(User.username).all()
    accepted = ChallengeSubmission.query.filter_by(author_id=user.id, status='approved').count()
    rejected = ChallengeSubmission.query.filter_by(author_id=user.id, status='rejected').count()
    wrong_attempts = FlagAttempt.query.filter_by(user_id=user.id, correct=False).count()
    from app.models import UserMilestone
    user_milestones = UserMilestone.query.filter_by(user_id=user.id).order_by(UserMilestone.awarded_at).all()
    scores = compute_all_scores()
    user_xp = round(scores.get(user.id, 0.0))
    return dict(
        rank_title=rank_title, rank_style=rank_style,
        rank_percentile=percentile, rank_keyframes=RANK_KEYFRAMES,
        radar_categories=all_cats, radar_datasets=radar_datasets,
        all_users=all_users,
        accepted=accepted, rejected=rejected, wrong_attempts=wrong_attempts,
        top_border=user.get_top_border(),
        user_milestones=user_milestones,
        user_xp=user_xp,
    )


@settings_bp.route('/account')
@login_required
def account():
    return render_template('account.html', **_rank_context(current_user))


@settings_bp.route('/user/<int:user_id>')
def public_profile(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_hidden_from_scoreboard:
        abort(404)
    return render_template('public_profile.html', user=user, **_rank_context(user))


def _save_avatar(file_storage, dest_path: str) -> None:
    """Read uploaded file, encode as 500x500 WebP, write to dest_path."""
    try:
        data = file_storage.read()
    finally:
        file_storage.close()
    with open(dest_path, 'wb') as f:
        f.write(encode_avatar(data))


@settings_bp.route('/settings/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    if not current_user.is_authenticated:
        abort(401)
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        abort(403)
        flash('No file selected', 'danger')
        return redirect(url_for('settings.index'))
    file = request.files['avatar']
    if not file.filename:
        flash('No file selected', 'danger')
        return redirect(url_for('settings.index'))
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        flash('Invalid file type', 'danger')
        return redirect(url_for('settings.index'))
    os.makedirs(AVATAR_DIR, exist_ok=True)
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_AVATAR_BYTES:
        flash('Avatar must be 5 MB or smaller.', 'danger')
        return redirect(url_for('settings.index'))
    import re as _re
    safe_username = _re.sub(r'[^A-Za-z0-9_-]', '_', current_user.username)[:64]
    filename = f'avatar_{safe_username}.webp'
    real_avatar_dir = os.path.realpath(AVATAR_DIR)
    _save_avatar(file, os.path.join(real_avatar_dir, filename))
    current_user.profile_picture = filename
    db.session.commit()
    flash('Profile picture updated!', 'success')
    return redirect(url_for('settings.index'))


@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name', '').strip() or None
        current_user.affiliation = request.form.get('affiliation', '').strip() or None
        age_val = request.form.get('age', '').strip()
        current_user.age = int(age_val) if age_val.isdigit() else None
        current_user.gender = request.form.get('gender', '').strip() or None
        current_user.bio = request.form.get('bio', '').strip() or None
        current_user.github = request.form.get('github', '').strip() or None
        current_user.linkedin = request.form.get('linkedin', '').strip() or None
        current_user.facebook = request.form.get('facebook', '').strip() or None
        current_user.contact_number = request.form.get('contact_number', '').strip() or None
        current_user.discord = request.form.get('discord', '').strip() or None

        new_username = request.form.get('username', '').strip()
        if new_username and new_username != current_user.username:
            if User.query.filter_by(username=new_username).first():
                flash('Username already taken', 'danger')
            else:
                current_user.username = new_username

        new_email = request.form.get('email', '').strip()
        if new_email and new_email != current_user.email:
            if User.query.filter_by(email=new_email).first():
                flash('Email already registered', 'danger')
            else:
                current_user.email = new_email

        new_password = request.form.get('new_password')
        if new_password:
            if not current_user.check_password(request.form.get('current_password')):
                flash('Current password is incorrect', 'danger')
            elif new_password != request.form.get('confirm_password'):
                flash('New passwords do not match', 'danger')
            else:
                current_user.set_password(new_password)

        db.session.commit()
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('settings.index'))

    return render_template('settings.html')


@settings_bp.route('/bug-report', methods=['GET', 'POST'])
@login_required
def bug_report():
    from app.models import BugReport
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        page_url = request.form.get('page_url', '').strip() or None
        severity = request.form.get('severity', 'medium')
        if severity not in ('low', 'medium', 'high', 'critical'):
            severity = 'medium'
        if not title or not description:
            flash('Title and description are required.', 'danger')
            return redirect(url_for('settings.bug_report'))
        db.session.add(BugReport(
            reporter_id=current_user.id,
            title=title,
            description=description,
            page_url=page_url,
            severity=severity,
        ))
        db.session.commit()
        flash('Bug report submitted. Thank you!', 'success')
        return redirect(url_for('challenges.list'))
    return render_template('bug_report.html')


@settings_bp.route('/api/user-notifications/<int:notif_id>/read', methods=['POST'])
@login_required
@csrf.exempt
def mark_user_notification_read(notif_id):
    from app.models import UserNotification
    n = UserNotification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    n.is_read = True
    db.session.commit()
    return jsonify(ok=True)


@settings_bp.route('/api/user-notifications/read-all', methods=['POST'])
@login_required
@csrf.exempt
def mark_all_user_notifications_read():
    from app.models import UserNotification
    UserNotification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify(ok=True)


@settings_bp.route('/settings/notifications', methods=['POST'])
@login_required
def save_notification_prefs():
    if not current_user.is_authenticated:
        abort(401)
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        abort(403)
    current_user.notif_challenge_solve   = 'notif_challenge_solve' in request.form
    current_user.notif_challenge_sub     = 'notif_challenge_sub' in request.form
    current_user.notif_post_reply        = 'notif_post_reply' in request.form
    current_user.notif_global            = 'notif_global' in request.form
    current_user.notif_changelog         = 'notif_changelog' in request.form
    current_user.notif_new_challenge     = 'notif_new_challenge' in request.form
    current_user.notif_submission_result = 'notif_submission_result' in request.form
    current_user.notif_badge_earned      = 'notif_badge_earned' in request.form
    current_user.notif_first_blood       = 'notif_first_blood' in request.form
    db.session.commit()
    flash('Notification preferences saved.', 'success')
    return redirect(url_for('settings.index'))
