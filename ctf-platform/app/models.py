"""
Database Models for CTF Platform.

This file defines the structure of your database tables using SQLAlchemy ORM.

TO ADD NEW MODELS:
1. Create a new class inheriting from db.Model
2. Define columns using db.Column()
3. Define relationships using db.relationship()
4. Restart the app - tables are created automatically

TO ADD NEW FIELDS TO EXISTING MODELS:
1. Add the field as a db.Column()
2. For production, use Flask-Migrate for database migrations
"""

from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

@login_manager.user_loader
def load_user(user_id):
    """Required by Flask-Login to load user from session."""
    return User.query.get(int(user_id))


# ========================================
# USER MODEL
# ========================================

class User(UserMixin, db.Model):
    """
    User model for authentication and profile.
    
    UserMixin provides: is_authenticated, is_active, is_anonymous, get_id()
    
    TO ADD NEW USER FIELDS:
    - Add column below (e.g., profile_picture, bio, etc.)
    - Update registration and settings forms
    """
    
    __tablename__ = 'users'
    
    # Core fields
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_hidden_from_scoreboard = db.Column(db.Boolean, default=False)
    has_seen_tour = db.Column(db.Boolean, default=False)
    legendary_rank = db.Column(db.String(60), nullable=True)  # manually assigned legendary title
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Roles
    is_moderator = db.Column(db.Boolean, default=False)  # Community Moderator

    # Moderation
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.String(500), nullable=True)
    banned_at = db.Column(db.DateTime, nullable=True)
    timeout_until = db.Column(db.DateTime, nullable=True)  # community actions blocked until this UTC time

    # Profile fields
    full_name = db.Column(db.String(120), nullable=True)
    affiliation = db.Column(db.String(120), nullable=True)
    age = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(40), nullable=True)
    profile_picture = db.Column(db.String(200), nullable=True)
    bio = db.Column(db.Text, nullable=True)

    # Social media
    github = db.Column(db.String(200), nullable=True)
    linkedin = db.Column(db.String(200), nullable=True)
    facebook = db.Column(db.String(200), nullable=True)
    contact_number = db.Column(db.String(30), nullable=True)
    discord = db.Column(db.String(100), nullable=True)
    
    # Notification preferences (JSON-like booleans stored as columns)
    notif_challenge_solve = db.Column(db.Boolean, default=True)   # own challenge solved
    notif_challenge_sub = db.Column(db.Boolean, default=True)     # subscribed challenge solved
    notif_post_reply = db.Column(db.Boolean, default=True)        # reply on own/subscribed post
    notif_global = db.Column(db.Boolean, default=True)            # global admin notifications
    notif_changelog = db.Column(db.Boolean, default=True)         # version changelog
    notif_new_challenge = db.Column(db.Boolean, default=True)     # new community challenge
    notif_submission_result = db.Column(db.Boolean, default=True) # submission approved/rejected
    notif_badge_earned = db.Column(db.Boolean, default=True)      # badge awarded
    notif_first_blood = db.Column(db.Boolean, default=True)       # first blood on a challenge

    # Relationships
    challenges = db.relationship('Challenge', backref='author', lazy=True)
    solves = db.relationship('UserChallengeSolve', backref='user', lazy=True)
    submissions = db.relationship('ChallengeSubmission', backref='author', lazy=True)
    posts = db.relationship('CommunityPost', backref='author', lazy=True)
    comments = db.relationship('Comment', foreign_keys='Comment.author_id', backref='author', lazy=True)
    badges = db.relationship('UserBadge', backref='user', lazy=True)
    milestones = db.relationship('UserMilestone', backref='user', lazy=True)
    
    def set_password(self, password):
        """Hash and store password securely."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password against stored hash."""
        return check_password_hash(self.password_hash, password)
    
    def get_score(self):
        """Calculate total score from solved challenges."""
        from sqlalchemy import func
        from app import db
        from app.models import UserChallengeSolve, Challenge
        result = db.session.query(func.sum(Challenge.points)).join(
            UserChallengeSolve, UserChallengeSolve.challenge_id == Challenge.id
        ).filter(UserChallengeSolve.user_id == self.id).scalar()
        return result or 0

    def get_top_border(self):
        """Return the highest tier border_style from the user's badges, or None."""
        tier_order = ['tier10','tier9','tier8','tier7','tier6','tier5','tier4','tier3','tier2','tier1']
        owned = {ub.badge.border_style for ub in self.badges if ub.badge.border_style}
        for t in tier_order:
            if t in owned:
                return t
        return None

    def is_timed_out(self):
        """Return True if the user currently has an active community timeout."""
        if self.timeout_until is None:
            return False
        return datetime.utcnow() < self.timeout_until

    def __repr__(self):
        return f'<User {self.username}>'


# ========================================
# CHALLENGE MODELS
# ========================================

class Challenge(db.Model):
    """
    Challenge model - stores CTF challenges.
    
    TO EXTEND:
    - Add file uploads (store file path)
    - Add hints system
    - Add dynamic scoring
    """
    
    __tablename__ = 'challenges'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)  # web, crypto, pwn, etc.
    difficulty = db.Column(db.String(20), nullable=False)  # easy, medium, hard
    flag = db.Column(db.String(500), nullable=False)
    is_regex = db.Column(db.Boolean, default=False)
    points = db.Column(db.Integer, nullable=False)
    file_attachment = db.Column(db.String(500), nullable=True)
    is_hidden = db.Column(db.Boolean, default=False)  # hidden from players
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    solves = db.relationship('UserChallengeSolve', backref='challenge', lazy=True)
    
    def solve_count(self):
        """Get number of solves for this challenge."""
        from app.models import UserChallengeSolve
        from app import db
        return db.session.query(UserChallengeSolve).filter_by(challenge_id=self.id).count()
    
    def __repr__(self):
        return f'<Challenge {self.title}>'


class UserChallengeSolve(db.Model):
    """
    Tracks which users solved which challenges and when.
    
    This is a many-to-many relationship table between User and Challenge.
    """
    
    __tablename__ = 'user_challenge_solves'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=False)
    solved_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # TO ADD: Track solve attempts
    # attempts = db.Column(db.Integer, default=1)
    
    def __repr__(self):
        return f'<Solve: User {self.user_id} -> Challenge {self.challenge_id}>'


# ========================================
# SUBMISSION MODELS (User-submitted challenges)
# ========================================

class ChallengeSubmission(db.Model):
    """
    User-submitted challenges waiting for admin approval.
    
    Workflow:
    1. User submits challenge -> status='pending'
    2. Admin reviews -> status='approved' or 'rejected'
    3. If approved, admin can create Challenge from this
    """
    
    __tablename__ = 'challenge_submissions'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    flag = db.Column(db.String(500), nullable=False)
    is_regex = db.Column(db.Boolean, default=False)
    points = db.Column(db.Integer, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    web_archive_path = db.Column(db.String(500), nullable=True)  # path to .tar.gz for Web challenges
    nc_binary_path = db.Column(db.String(500), nullable=True)     # path to binary for RE challenges
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    files = db.relationship('SubmissionFile', backref='submission', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Submission {self.title} ({self.status})>'


class SubmissionFile(db.Model):
    """
    Files attached to a challenge submission.
    Each user is limited to 250 MB of pending files total.
    When a submission is approved, its files are freed from the quota.
    """

    __tablename__ = 'submission_files'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('challenge_submissions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    original_name = db.Column(db.String(300), nullable=False)
    stored_name = db.Column(db.String(300), nullable=False)  # UUID-based filename on disk
    file_size = db.Column(db.Integer, nullable=False)  # bytes
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<SubmissionFile {self.original_name} ({self.file_size} bytes)>'


# ========================================
# COMMUNITY MODELS (Posts & Comments)
# ========================================

class CommunityPost(db.Model):
    """
    Community posts for writeups, questions, discussions.
    
    TO EXTEND:
    - Add categories/tags
    - Add voting system
    - Add featured/pinned posts
    """
    
    __tablename__ = 'community_posts'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    upvotes = db.Column(db.Integer, default=0)
    flair = db.Column(db.String(50), nullable=True)
    is_pinned = db.Column(db.Boolean, default=False)
    comments_disabled = db.Column(db.Boolean, default=False)
    reactions_disabled = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')
    
    def comment_count(self):
        """Get number of comments on this post."""
        from app.models import Comment
        from app import db
        return db.session.query(Comment).filter_by(post_id=self.id).count()
    
    def __repr__(self):
        return f'<Post {self.title}>'


class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('community_posts.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    edited_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    edited_at = db.Column(db.DateTime, nullable=True)

    edited_by = db.relationship('User', foreign_keys=[edited_by_id])
    reactions = db.relationship('CommentReaction', backref='comment', lazy=True, cascade='all, delete-orphan')

    def reaction_counts(self):
        counts = {}
        for r in self.reactions:
            counts[r.reaction] = counts.get(r.reaction, 0) + 1
        return counts

    def __repr__(self):
        return f'<Comment on Post {self.post_id}>'


class CommentReaction(db.Model):
    """One reaction per user per comment. Toggled on/off."""
    __tablename__ = 'comment_reactions'

    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reaction = db.Column(db.String(20), nullable=False)  # like, dislike, heart, haha, wow, sad
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PostUpvote(db.Model):
    """One upvote per user per post."""
    __tablename__ = 'post_upvotes'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('community_posts.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class FlagAttempt(db.Model):
    """Tracks every flag submission attempt (right or wrong) per user per challenge."""
    __tablename__ = 'flag_attempts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=False)
    submitted_flag = db.Column(db.String(500), nullable=True)  # what the user submitted
    correct = db.Column(db.Boolean, nullable=False)
    attempted_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('flag_attempts', lazy=True))
    challenge = db.relationship('Challenge', backref=db.backref('flag_attempts', lazy=True))


class ChallengeOpen(db.Model):
    """Tracks when a user opens/views a challenge detail page."""
    __tablename__ = 'challenge_opens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=False)
    opened_at = db.Column(db.DateTime, default=datetime.utcnow)


class WebChallenge(db.Model):
    """
    Stores the web exploit archive path and last-known port for a Web challenge.
    The actual server process is managed by web_runner.py as a subprocess.
    """
    __tablename__ = 'web_challenges'

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=False, unique=True)
    archive_path = db.Column(db.String(500), nullable=False)
    host_port = db.Column(db.Integer, nullable=True)   # last known port (informational)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    challenge = db.relationship('Challenge', backref=db.backref('web_challenge', uselist=False))

    def __repr__(self):
        return f'<WebChallenge challenge_id={self.challenge_id} port={self.host_port}>'


class NcChallenge(db.Model):
    """
    Stores the binary path and last-known port for a Reverse Engineering challenge.
    The actual socat listener is managed by nc_runner.py as a subprocess.
    """
    __tablename__ = 'nc_challenges'

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=False, unique=True)
    binary_path = db.Column(db.String(500), nullable=False)
    host_port = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    challenge = db.relationship('Challenge', backref=db.backref('nc_challenge', uselist=False))

    def __repr__(self):
        return f'<NcChallenge challenge_id={self.challenge_id} port={self.host_port}>'


class DynamicFlag(db.Model):
    """
    Stores the per-user dynamically generated flag for challenges that contain flag.txt.
    Created/replaced each time the user launches a new instance.
    """
    __tablename__ = 'dynamic_flags'

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    flag = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('challenge_id', 'user_id', name='uq_dynamic_flag'),)

    def __repr__(self):
        return f'<DynamicFlag challenge={self.challenge_id} user={self.user_id}>'



class ChallengeVote(db.Model):
    """Up/downvote on a challenge — only solvers can vote."""
    __tablename__ = 'challenge_votes'

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    value = db.Column(db.Integer, nullable=False)  # +1 or -1
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('challenge_id', 'user_id', name='uq_challenge_vote'),)


class BadgeRule(db.Model):
    """Auto-give or claimable-link rule tied to a badge."""
    __tablename__ = 'badge_rules'

    id = db.Column(db.Integer, primary_key=True)
    badge_id = db.Column(db.Integer, db.ForeignKey('badges.id'), nullable=False)
    rule_type = db.Column(db.String(50), nullable=False)
    # rule_type values:
    #   solved_challenge, top_month_post, scoreboard_top_week,
    #   comment_reactions, post_upvotes, community_posts,
    #   approved_submissions, claimable_link
    threshold = db.Column(db.Integer, nullable=True)   # numeric threshold where applicable
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=True)  # for solved_challenge
    claim_token = db.Column(db.String(64), nullable=True, unique=True)  # for claimable_link
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    badge = db.relationship('Badge', backref=db.backref('rules', lazy=True))
    claims = db.relationship('BadgeClaim', backref='rule', lazy=True, cascade='all, delete-orphan')


class BadgeClaim(db.Model):
    """Tracks who has already claimed/received a badge via a rule."""
    __tablename__ = 'badge_claims'

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('badge_rules.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    claimed_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('rule_id', 'user_id', name='uq_badge_claim'),)


class Badge(db.Model):
    __tablename__ = 'badges'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    image_filename = db.Column(db.String(200), nullable=False)
    is_limited = db.Column(db.Boolean, default=False)
    limited_count = db.Column(db.Integer, nullable=True)
    border_style = db.Column(db.String(30), default='tier1')
    display_border = db.Column(db.Boolean, default=True)   # show/hide border
    display_shape = db.Column(db.String(20), default='square')  # square|circle|triangle|pentagon|seal-spike|seal-hanko
    from_event = db.Column(db.Boolean, default=False)
    is_unattainable = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    recipients = db.relationship('UserBadge', backref='badge', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Badge {self.title}>'


class UserBadge(db.Model):
    __tablename__ = 'user_badges'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badges.id'), nullable=False)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<UserBadge user={self.user_id} badge={self.badge_id}>'


class Notification(db.Model):
    """Admin-created global notification shown in the navbar dropdown per user."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reads = db.relationship('NotificationRead', backref='notification', lazy=True, cascade='all, delete-orphan')


class NotificationRead(db.Model):
    """Tracks which users have read which global notifications."""
    __tablename__ = 'notification_reads'

    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey('notifications.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    read_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserNotification(db.Model):
    """Per-user targeted notification (challenge solves, subscriptions, etc.)."""
    __tablename__ = 'user_notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    # category: challenge | community | submission | system
    category = db.Column(db.String(30), default='system')
    link = db.Column(db.String(300), nullable=True)  # optional click-through URL
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('user_notifications', lazy=True))


class ChallengeBookmark(db.Model):
    """User-saved/bookmarked challenges."""
    __tablename__ = 'challenge_bookmarks'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'challenge_id', name='uq_bookmark'),)

    challenge = db.relationship('Challenge', backref=db.backref('bookmarks', lazy=True))


class ChallengeSubscription(db.Model):
    """User subscribed to a challenge — notified when others solve it."""
    __tablename__ = 'challenge_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'challenge_id', name='uq_ch_sub'),)


class PostSubscription(db.Model):
    """User subscribed to a community post — notified on new replies."""
    __tablename__ = 'post_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('community_posts.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='uq_post_sub'),)


class BugReport(db.Model):
    """User-submitted bug reports."""
    __tablename__ = 'bug_reports'

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # nullable = anonymous
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    page_url = db.Column(db.String(300), nullable=True)
    severity = db.Column(db.String(20), default='medium')  # low | medium | high | critical
    status = db.Column(db.String(20), default='open')  # open | in_progress | resolved | wontfix
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reporter = db.relationship('User', backref=db.backref('bug_reports', lazy=True))


# ========================================
# MILESTONE MODELS
# ========================================

class Milestone(db.Model):
    """Admin-created milestone with auto-award rules."""
    __tablename__ = 'milestones'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    image_filename = db.Column(db.String(200), nullable=False)
    # rule_type: solved_n_challenges | reached_score | community_posts | approved_submissions | manual
    rule_type = db.Column(db.String(50), nullable=False, default='manual')
    threshold = db.Column(db.Integer, nullable=True)   # numeric threshold
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    recipients = db.relationship('UserMilestone', backref='milestone', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Milestone {self.title}>'


class UserMilestone(db.Model):
    __tablename__ = 'user_milestones'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    milestone_id = db.Column(db.Integer, db.ForeignKey('milestones.id'), nullable=False)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'milestone_id', name='uq_user_milestone'),)

    def __repr__(self):
        return f'<UserMilestone user={self.user_id} milestone={self.milestone_id}>'


class Announcement(db.Model):
    """Timed banner shown on all pages between starts_at and ends_at (UTC)."""
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    color = db.Column(db.String(20), default='red')  # red | yellow | green | blue
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_active(self):
        now = datetime.utcnow()
        return self.starts_at <= now <= self.ends_at



