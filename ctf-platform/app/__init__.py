import os
import re
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, logout_user
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()

# Read version once at import time — not on every request
_VERSION = 'v?'
try:
    _md = os.path.join(os.path.dirname(__file__), '..', 'WHATS-NEW.md')
    with open(_md, encoding='utf-8') as _f:
        _m = re.search(r'v[\d.]+', _f.readline())
        if _m:
            _VERSION = _m.group(0)
except Exception:
    pass


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    from app.routes.auth import auth_bp
    from app.routes.challenges import challenges_bp
    from app.routes.submissions import submissions_bp
    from app.routes.community import community_bp
    from app.routes.settings import settings_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(challenges_bp)
    app.register_blueprint(submissions_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from datetime import datetime
        ctx = {'app_version': _VERSION}
        try:
            if current_user.is_authenticated:
                from app.models import Notification, NotificationRead, Announcement, UserNotification
                now = datetime.utcnow()
                # Global admin notifications
                all_global = Notification.query.order_by(Notification.created_at.desc()).all()
                read_ids = {r.notification_id for r in
                            NotificationRead.query.filter_by(user_id=current_user.id).all()}
                # Per-user targeted notifications
                user_notifs = UserNotification.query.filter_by(
                    user_id=current_user.id
                ).order_by(UserNotification.created_at.desc()).limit(30).all()
                # Merge: user_notifs first, then global
                ctx['notifications'] = user_notifs
                ctx['global_notifications'] = all_global
                ctx['unread_count'] = (
                    sum(1 for n in user_notifs if not n.is_read) +
                    sum(1 for n in all_global if n.id not in read_ids)
                )
                ctx['read_notification_ids'] = read_ids
                ctx['active_announcements'] = Announcement.query.filter(
                    Announcement.starts_at <= now,
                    Announcement.ends_at >= now
                ).order_by(Announcement.created_at.desc()).all()
                ctx['user_top_border'] = current_user.get_top_border()
            else:
                ctx['notifications'] = []
                ctx['global_notifications'] = []
                ctx['unread_count'] = 0
                ctx['read_notification_ids'] = set()
                ctx['active_announcements'] = []
                ctx['user_top_border'] = None
        except Exception:
            ctx['notifications'] = []
            ctx['global_notifications'] = []
            ctx['unread_count'] = 0
            ctx['read_notification_ids'] = set()
            ctx['active_announcements'] = []
            ctx['user_top_border'] = None
        return ctx

    _MOBILE_RE = re.compile(r'(iPhone|Android.*Mobile|Android.*Firefox|Mobile.*Safari|Opera Mini|IEMobile)', re.IGNORECASE)
    # Endpoints fully accessible on mobile
    _MOBILE_ALLOWED = {
        'static',
        'auth.index', 'auth.login', 'auth.register', 'auth.logout', 'auth.whats_new',
        'challenges.scoreboard',
        'community.list', 'community.detail', 'community.new_post',
        'settings.account', 'settings.index', 'settings.serve_avatar',
        'settings.public_profile', 'settings.badges', 'settings.ranks',
    }
    from flask import request, render_template

    @app.before_request
    def enforce_ban():
        from flask_login import current_user
        from flask import request, redirect, url_for, render_template
        if current_user.is_authenticated and current_user.is_banned:
            if request.endpoint not in ('auth.logout', 'static'):
                reason = current_user.ban_reason or 'No reason provided.'
                logout_user()
                return render_template('error.html', code=403,
                    title='Account Banned',
                    message=f'Your account has been banned. Reason: {reason}'), 403

    @app.before_request
    def restrict_mobile():
        ua = request.headers.get('User-Agent', '')
        if _MOBILE_RE.search(ua):
            if request.endpoint not in _MOBILE_ALLOWED:
                return render_template('mobile.html'), 200

    @app.errorhandler(400)
    def bad_request(e):
        return render_template('error.html', code=400, title='Bad Request',
                               message='The server could not understand your request.'), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html', code=403, title='Access Forbidden',
                               message='You do not have permission to access this page.'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', code=404, title='Page Not Found',
                               message='The page you are looking for does not exist or has been moved.'), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return render_template('error.html', code=405, title='Method Not Allowed',
                               message='This action is not allowed on the requested resource.'), 405

    @app.errorhandler(500)
    def internal_error(e):
        return render_template('error.html', code=500, title='Server Error',
                               message='Something went wrong on our end. Please try again later.'), 500

    with app.app_context():
        from sqlalchemy import text

        db.create_all()

        with db.engine.connect() as conn:
            # users base table
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS users "
                "(id INTEGER PRIMARY KEY, username VARCHAR(80), "
                "email VARCHAR(120), password_hash VARCHAR(255), "
                "is_admin BOOLEAN DEFAULT 0, "
                "is_hidden_from_scoreboard BOOLEAN DEFAULT 0, "
                "created_at DATETIME)"
            ))
            conn.commit()

            # Single PRAGMA read for users — reused for all user column checks
            user_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}

            for col, stmt in {
                'full_name':       'ALTER TABLE users ADD COLUMN full_name VARCHAR(120)',
                'affiliation':     'ALTER TABLE users ADD COLUMN affiliation VARCHAR(120)',
                'age':             'ALTER TABLE users ADD COLUMN age INTEGER',
                'gender':          'ALTER TABLE users ADD COLUMN gender VARCHAR(40)',
                'profile_picture': 'ALTER TABLE users ADD COLUMN profile_picture VARCHAR(200)',
                'bio':             'ALTER TABLE users ADD COLUMN bio TEXT',
                'github':          'ALTER TABLE users ADD COLUMN github VARCHAR(200)',
                'linkedin':        'ALTER TABLE users ADD COLUMN linkedin VARCHAR(200)',
                'facebook':        'ALTER TABLE users ADD COLUMN facebook VARCHAR(200)',
                'contact_number':  'ALTER TABLE users ADD COLUMN contact_number VARCHAR(30)',
                'discord':         'ALTER TABLE users ADD COLUMN discord VARCHAR(100)',
                'has_seen_tour':   'ALTER TABLE users ADD COLUMN has_seen_tour BOOLEAN DEFAULT 0',
                'legendary_rank':  'ALTER TABLE users ADD COLUMN legendary_rank VARCHAR(60)',
                'is_banned':       'ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT 0',
                'ban_reason':      'ALTER TABLE users ADD COLUMN ban_reason VARCHAR(500)',
                'banned_at':       'ALTER TABLE users ADD COLUMN banned_at DATETIME',
                'timeout_until':   'ALTER TABLE users ADD COLUMN timeout_until DATETIME',
            }.items():
                if col not in user_cols:
                    conn.execute(text(stmt))
            conn.commit()

            # submission_files
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS submission_files "
                "(id INTEGER PRIMARY KEY, submission_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, original_name VARCHAR(300) NOT NULL, "
                "stored_name VARCHAR(300) NOT NULL, file_size INTEGER NOT NULL, "
                "uploaded_at DATETIME, "
                "FOREIGN KEY(submission_id) REFERENCES challenge_submissions(id), "
                "FOREIGN KEY(user_id) REFERENCES users(id))"
            ))
            conn.commit()

            # comment_reactions
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS comment_reactions "
                "(id INTEGER PRIMARY KEY, comment_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, reaction VARCHAR(20) NOT NULL, "
                "created_at DATETIME, "
                "FOREIGN KEY(comment_id) REFERENCES comments(id), "
                "FOREIGN KEY(user_id) REFERENCES users(id))"
            ))
            conn.commit()

            # flag_attempts
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS flag_attempts "
                "(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "challenge_id INTEGER NOT NULL, correct BOOLEAN NOT NULL, "
                "attempted_at DATETIME, "
                "FOREIGN KEY(user_id) REFERENCES users(id), "
                "FOREIGN KEY(challenge_id) REFERENCES challenges(id))"
            ))
            conn.commit()

            # post_upvotes
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS post_upvotes "
                "(id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, created_at DATETIME, "
                "FOREIGN KEY(post_id) REFERENCES community_posts(id), "
                "FOREIGN KEY(user_id) REFERENCES users(id))"
            ))
            conn.commit()

            # community_posts extra columns
            post_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(community_posts)"))}
            for col, stmt in {
                'flair':     'ALTER TABLE community_posts ADD COLUMN flair VARCHAR(50)',
                'is_pinned': 'ALTER TABLE community_posts ADD COLUMN is_pinned BOOLEAN DEFAULT 0',
            }.items():
                if col not in post_cols:
                    conn.execute(text(stmt))
            conn.commit()

            # challenges extra columns
            ch_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(challenges)"))}
            if 'is_regex' not in ch_cols:
                conn.execute(text('ALTER TABLE challenges ADD COLUMN is_regex BOOLEAN DEFAULT 0'))
            conn.commit()

            # challenge_submissions extra columns
            sub_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(challenge_submissions)"))}
            for col, stmt in {
                'is_regex':         'ALTER TABLE challenge_submissions ADD COLUMN is_regex BOOLEAN DEFAULT 0',
                'web_archive_path': 'ALTER TABLE challenge_submissions ADD COLUMN web_archive_path VARCHAR(500)',
                'nc_binary_path':   'ALTER TABLE challenge_submissions ADD COLUMN nc_binary_path VARCHAR(500)',
            }.items():
                if col not in sub_cols:
                    conn.execute(text(stmt))
            conn.commit()

            # web_challenges (subprocess-based, no image_built/container_id)
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS web_challenges "
                "(id INTEGER PRIMARY KEY, challenge_id INTEGER NOT NULL UNIQUE, "
                "archive_path VARCHAR(500) NOT NULL, "
                "host_port INTEGER, "
                "created_at DATETIME, "
                "FOREIGN KEY(challenge_id) REFERENCES challenges(id))"
            ))
            conn.commit()

            # nc_challenges (socat-based RE binary listener)
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS nc_challenges "
                "(id INTEGER PRIMARY KEY, challenge_id INTEGER NOT NULL UNIQUE, "
                "binary_path VARCHAR(500) NOT NULL, "
                "host_port INTEGER, "
                "created_at DATETIME, "
                "FOREIGN KEY(challenge_id) REFERENCES challenges(id))"
            ))
            conn.commit()

            # dynamic_flags (per-user generated flags for flag.txt challenges)
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS dynamic_flags "
                "(id INTEGER PRIMARY KEY, challenge_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, flag VARCHAR(200) NOT NULL, "
                "created_at DATETIME, "
                "UNIQUE(challenge_id, user_id), "
                "FOREIGN KEY(challenge_id) REFERENCES challenges(id), "
                "FOREIGN KEY(user_id) REFERENCES users(id))"
            ))
            conn.commit()

            # badges extra columns
            badge_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(badges)"))}
            for col, stmt in {
                'limited_count':  'ALTER TABLE badges ADD COLUMN limited_count INTEGER',
                'border_style':   "ALTER TABLE badges ADD COLUMN border_style VARCHAR(30) DEFAULT 'tier1'",
                'from_event':     'ALTER TABLE badges ADD COLUMN from_event BOOLEAN DEFAULT 0',
                'is_unattainable':'ALTER TABLE badges ADD COLUMN is_unattainable BOOLEAN DEFAULT 0',
            }.items():
                if col not in badge_cols:
                    conn.execute(text(stmt))
            conn.commit()

            # notifications
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS notifications "
                "(id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, "
                "body TEXT NOT NULL, created_by INTEGER NOT NULL, "
                "created_at DATETIME, "
                "FOREIGN KEY(created_by) REFERENCES users(id))"
            ))
            conn.commit()

            # notification_reads
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS notification_reads "
                "(id INTEGER PRIMARY KEY, notification_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, read_at DATETIME, "
                "FOREIGN KEY(notification_id) REFERENCES notifications(id), "
                "FOREIGN KEY(user_id) REFERENCES users(id))"
            ))
            conn.commit()

            # challenge_votes
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS challenge_votes "
                "(id INTEGER PRIMARY KEY, challenge_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, value INTEGER NOT NULL, "
                "created_at DATETIME, "
                "UNIQUE(challenge_id, user_id), "
                "FOREIGN KEY(challenge_id) REFERENCES challenges(id), "
                "FOREIGN KEY(user_id) REFERENCES users(id))"
            ))
            conn.commit()

            # badge_rules
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS badge_rules "
                "(id INTEGER PRIMARY KEY, badge_id INTEGER NOT NULL, "
                "rule_type VARCHAR(50) NOT NULL, threshold INTEGER, "
                "challenge_id INTEGER, claim_token VARCHAR(64) UNIQUE, "
                "is_active BOOLEAN DEFAULT 1, created_at DATETIME, "
                "FOREIGN KEY(badge_id) REFERENCES badges(id), "
                "FOREIGN KEY(challenge_id) REFERENCES challenges(id))"
            ))
            conn.commit()

            # badge_claims
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS badge_claims "
                "(id INTEGER PRIMARY KEY, rule_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, claimed_at DATETIME, "
                "UNIQUE(rule_id, user_id), "
                "FOREIGN KEY(rule_id) REFERENCES badge_rules(id), "
                "FOREIGN KEY(user_id) REFERENCES users(id))"
            ))
            conn.commit()

            # announcements
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS announcements "
                "(id INTEGER PRIMARY KEY, message TEXT NOT NULL, "
                "color VARCHAR(20) DEFAULT 'red', "
                "starts_at DATETIME NOT NULL, ends_at DATETIME NOT NULL, "
                "created_by INTEGER NOT NULL, created_at DATETIME, "
                "FOREIGN KEY(created_by) REFERENCES users(id))"
            ))
            conn.commit()

            # user_notifications (per-user targeted)
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS user_notifications "
                "(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "title VARCHAR(200) NOT NULL, body TEXT NOT NULL, "
                "category VARCHAR(30) DEFAULT 'system', "
                "link VARCHAR(300), is_read BOOLEAN DEFAULT 0, "
                "created_at DATETIME, "
                "FOREIGN KEY(user_id) REFERENCES users(id))"
            ))
            conn.commit()

            # challenge_bookmarks
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS challenge_bookmarks "
                "(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "challenge_id INTEGER NOT NULL, created_at DATETIME, "
                "UNIQUE(user_id, challenge_id), "
                "FOREIGN KEY(user_id) REFERENCES users(id), "
                "FOREIGN KEY(challenge_id) REFERENCES challenges(id))"
            ))
            conn.commit()

            # challenge_subscriptions
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS challenge_subscriptions "
                "(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "challenge_id INTEGER NOT NULL, created_at DATETIME, "
                "UNIQUE(user_id, challenge_id), "
                "FOREIGN KEY(user_id) REFERENCES users(id), "
                "FOREIGN KEY(challenge_id) REFERENCES challenges(id))"
            ))
            conn.commit()

            # post_subscriptions
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS post_subscriptions "
                "(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "post_id INTEGER NOT NULL, created_at DATETIME, "
                "UNIQUE(user_id, post_id), "
                "FOREIGN KEY(user_id) REFERENCES users(id), "
                "FOREIGN KEY(post_id) REFERENCES community_posts(id))"
            ))
            conn.commit()

            # bug_reports
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS bug_reports "
                "(id INTEGER PRIMARY KEY, reporter_id INTEGER, "
                "title VARCHAR(200) NOT NULL, description TEXT NOT NULL, "
                "page_url VARCHAR(300), severity VARCHAR(20) DEFAULT 'medium', "
                "status VARCHAR(20) DEFAULT 'open', created_at DATETIME, "
                "FOREIGN KEY(reporter_id) REFERENCES users(id))"
            ))
            conn.commit()

            # notification preference columns on users
            user_cols2 = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
            for col, stmt in {
                'notif_challenge_solve': 'ALTER TABLE users ADD COLUMN notif_challenge_solve BOOLEAN DEFAULT 1',
                'notif_challenge_sub':   'ALTER TABLE users ADD COLUMN notif_challenge_sub BOOLEAN DEFAULT 1',
                'notif_post_reply':      'ALTER TABLE users ADD COLUMN notif_post_reply BOOLEAN DEFAULT 1',
                'notif_global':          'ALTER TABLE users ADD COLUMN notif_global BOOLEAN DEFAULT 1',
                'notif_changelog':       'ALTER TABLE users ADD COLUMN notif_changelog BOOLEAN DEFAULT 1',
                'notif_new_challenge':      'ALTER TABLE users ADD COLUMN notif_new_challenge BOOLEAN DEFAULT 1',
                'notif_submission_result':   'ALTER TABLE users ADD COLUMN notif_submission_result BOOLEAN DEFAULT 1',
                'notif_badge_earned':        'ALTER TABLE users ADD COLUMN notif_badge_earned BOOLEAN DEFAULT 1',
                'notif_first_blood':         'ALTER TABLE users ADD COLUMN notif_first_blood BOOLEAN DEFAULT 1',
                'is_moderator':              'ALTER TABLE users ADD COLUMN is_moderator BOOLEAN DEFAULT 0',
            }.items():
                if col not in user_cols2:
                    conn.execute(text(stmt))
            conn.commit()

            # challenges extra columns (is_hidden)
            ch_cols2 = {row[1] for row in conn.execute(text("PRAGMA table_info(challenges)"))}
            if 'is_hidden' not in ch_cols2:
                conn.execute(text('ALTER TABLE challenges ADD COLUMN is_hidden BOOLEAN DEFAULT 0'))
            conn.commit()

            # community_posts extra columns
            post_cols2 = {row[1] for row in conn.execute(text("PRAGMA table_info(community_posts)"))}
            for col, stmt in {
                'comments_disabled':  'ALTER TABLE community_posts ADD COLUMN comments_disabled BOOLEAN DEFAULT 0',
                'reactions_disabled': 'ALTER TABLE community_posts ADD COLUMN reactions_disabled BOOLEAN DEFAULT 0',
                'is_archived':        'ALTER TABLE community_posts ADD COLUMN is_archived BOOLEAN DEFAULT 0',
            }.items():
                if col not in post_cols2:
                    conn.execute(text(stmt))
            conn.commit()

            # flag_attempts extra column (submitted_flag)
            fa_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(flag_attempts)"))}
            if 'submitted_flag' not in fa_cols:
                conn.execute(text('ALTER TABLE flag_attempts ADD COLUMN submitted_flag VARCHAR(500)'))
            conn.commit()

            # challenge_opens
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS challenge_opens "
                "(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "challenge_id INTEGER NOT NULL, opened_at DATETIME, "
                "FOREIGN KEY(user_id) REFERENCES users(id), "
                "FOREIGN KEY(challenge_id) REFERENCES challenges(id))"
            ))
            conn.commit()

        from app.models import User
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@ctf.local', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("=" * 60)
            print("✅ Admin account created!")
            print("   Username: admin  |  Password: admin123")
            print("   ⚠️  Change this password after first login!")
            print("=" * 60)

    return app
