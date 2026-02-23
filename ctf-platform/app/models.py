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
    is_admin = db.Column(db.Boolean, default=False)  # Admin role flag
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # TO ADD: Additional profile fields
    # bio = db.Column(db.Text, nullable=True)
    # profile_picture = db.Column(db.String(200), nullable=True)
    
    # Relationships - defines connections to other tables
    challenges = db.relationship('Challenge', backref='author', lazy=True)
    solves = db.relationship('UserChallengeSolve', backref='user', lazy=True)
    submissions = db.relationship('ChallengeSubmission', backref='author', lazy=True)
    posts = db.relationship('CommunityPost', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    
    def set_password(self, password):
        """Hash and store password securely."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password against stored hash."""
        return check_password_hash(self.password_hash, password)
    
    def get_score(self):
        """Calculate total score from solved challenges."""
        return sum([solve.challenge.points for solve in self.solves])
    
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
    flag = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    file_attachment = db.Column(db.String(500), nullable=True)  # Path to uploaded file
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # TO ADD: Additional challenge features
    # file_path = db.Column(db.String(300), nullable=True)  # For downloadable files
    # hints = db.relationship('Hint', backref='challenge', lazy=True)
    # max_attempts = db.Column(db.Integer, default=0)  # 0 = unlimited
    
    # Relationships
    solves = db.relationship('UserChallengeSolve', backref='challenge', lazy=True)
    
    def solve_count(self):
        """Get number of solves for this challenge."""
        return len(self.solves)
    
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
    flag = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # TO ADD: Admin feedback
    # admin_notes = db.Column(db.Text, nullable=True)
    # reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # reviewed_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<Submission {self.title} ({self.status})>'


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
    upvotes = db.Column(db.Integer, default=0)  # Vote counter
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # TO ADD: Enhanced features
    # category = db.Column(db.String(50), nullable=True)  # writeup, question, discussion
    # upvotes = db.Column(db.Integer, default=0)
    # is_pinned = db.Column(db.Boolean, default=False)
    # related_challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=True)
    
    # Relationships
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')
    
    def comment_count(self):
        """Get number of comments on this post."""
        return len(self.comments)
    
    def __repr__(self):
        return f'<Post {self.title}>'


class Comment(db.Model):
    """
    Comments on community posts.
    
    TO EXTEND:
    - Add nested replies (parent_comment_id)
    - Add voting
    """
    
    __tablename__ = 'comments'
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('community_posts.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # TO ADD: Nested comments
    # parent_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=True)
    # replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]))
    
    def __repr__(self):
        return f'<Comment on Post {self.post_id}>'


# ========================================
# TO ADD NEW MODELS - EXAMPLE TEMPLATES
# ========================================

# Example: Hint system
# class Hint(db.Model):
#     __tablename__ = 'hints'
#     id = db.Column(db.Integer, primary_key=True)
#     challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'), nullable=False)
#     content = db.Column(db.Text, nullable=False)
#     cost = db.Column(db.Integer, default=0)  # Point cost to unlock hint

# Example: Team system
# class Team(db.Model):
#     __tablename__ = 'teams'
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), unique=True, nullable=False)
#     members = db.relationship('User', backref='team', lazy=True)
