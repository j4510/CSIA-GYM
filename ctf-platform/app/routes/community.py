"""
Community Routes Blueprint

Handles community posts (writeups, questions, discussions) and comments.

TO EXTEND THIS SECTION:
- Add categories/tags for posts
- Add search functionality
- Add voting/likes system
- Add markdown rendering
- Add post editing
- Add nested comments/replies
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import CommunityPost, Comment

# Create blueprint
community_bp = Blueprint('community', __name__, template_folder='../templates')


@community_bp.route('/community')
@login_required
def list():
    """
    Display all community posts.
    
    TO EXTEND:
    - Add pagination
    - Add filtering by category/tag
    - Add sorting (newest, popular, unanswered)
    - Add search
    """
    
    # Get all posts, newest first
    posts = CommunityPost.query.order_by(CommunityPost.created_at.desc()).all()
    
    # TO ADD: Pagination example
    # page = request.args.get('page', 1, type=int)
    # posts = CommunityPost.query.order_by(
    #     CommunityPost.created_at.desc()
    # ).paginate(page=page, per_page=15)
    
    # TO ADD: Filtering example
    # category = request.args.get('category')
    # if category:
    #     posts = posts.filter_by(category=category)
    
    return render_template('community/list.html', posts=posts)


@community_bp.route('/community/new', methods=['GET', 'POST'])
@login_required
def new_post():
    """
    Create a new community post.
    
    TO EXTEND:
    - Add rich text/markdown editor
    - Add post categories
    - Add tags
    - Add draft saving
    - Add image uploads
    - Add preview before posting
    """
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        
        # Validation
        if not title or not content:
            flash('Title and content are required', 'danger')
            return redirect(url_for('community.new_post'))
        
        # TO ADD: Additional validation
        # - Min/max title length
        # - Min content length
        # - Profanity filter
        # - Spam detection
        
        # Create post
        post = CommunityPost(
            title=title,
            content=content,
            author_id=current_user.id
        )
        
        # TO ADD: Set category if implemented
        # post.category = request.form.get('category')
        
        db.session.add(post)
        db.session.commit()
        
        flash('Post created successfully!', 'success')
        return redirect(url_for('community.view_post', post_id=post.id))
    
    # GET - show form
    return render_template('community/new.html')


@community_bp.route('/community/<int:post_id>')
@login_required
def view_post(post_id):
    """
    View a single post with all comments.
    
    TO EXTEND:
    - Add markdown rendering
    - Add syntax highlighting for code blocks
    - Add voting
    - Add "mark as solution" for question posts
    """
    
    post = CommunityPost.query.get_or_404(post_id)
    
    # Comments are loaded via relationship: post.comments
    # They're ordered by creation time in the template
    
    return render_template('community/view.html', post=post)


@community_bp.route('/community/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    """
    Add a comment to a post.
    
    TO EXTEND:
    - Add markdown support
    - Add @mentions
    - Add comment editing
    - Add nested replies
    """
    
    post = CommunityPost.query.get_or_404(post_id)
    content = request.form.get('content', '').strip()
    
    # Validation
    if not content:
        flash('Comment cannot be empty', 'danger')
        return redirect(url_for('community.view_post', post_id=post_id))
    
    # TO ADD: Additional validation
    # - Min/max length
    # - Rate limiting
    
    # Create comment
    comment = Comment(
        content=content,
        author_id=current_user.id,
        post_id=post_id
    )
    
    db.session.add(comment)
    db.session.commit()
    
    flash('Comment added!', 'success')
    return redirect(url_for('community.view_post', post_id=post_id))


# ========================================
# TO ADD: Additional community features
# ========================================

# Edit post:
# @community_bp.route('/community/<int:post_id>/edit', methods=['GET', 'POST'])
# @login_required
# def edit_post(post_id):
#     post = CommunityPost.query.get_or_404(post_id)
#     
#     # Only author can edit
#     if post.author_id != current_user.id:
#         flash('You can only edit your own posts', 'danger')
#         return redirect(url_for('community.view_post', post_id=post_id))
#     
#     if request.method == 'POST':
#         post.title = request.form.get('title')
#         post.content = request.form.get('content')
#         db.session.commit()
#         flash('Post updated!', 'success')
#         return redirect(url_for('community.view_post', post_id=post_id))
#     
#     return render_template('community/edit.html', post=post)

# Delete post:
# @community_bp.route('/community/<int:post_id>/delete', methods=['POST'])
# @login_required
# def delete_post(post_id):
#     post = CommunityPost.query.get_or_404(post_id)
#     
#     # Only author can delete
#     if post.author_id != current_user.id:
#         flash('You can only delete your own posts', 'danger')
#         return redirect(url_for('community.view_post', post_id=post_id))
#     
#     db.session.delete(post)  # Comments will be deleted too (cascade)
#     db.session.commit()
#     flash('Post deleted', 'info')
#     return redirect(url_for('community.list'))

# Vote on post:
# @community_bp.route('/community/<int:post_id>/vote', methods=['POST'])
# @login_required
# def vote_post(post_id):
#     post = CommunityPost.query.get_or_404(post_id)
#     vote_type = request.form.get('type')  # 'up' or 'down'
#     
#     # Check if user already voted
#     # Add/remove vote
#     # Update post.upvotes
#     
#     return redirect(url_for('community.view_post', post_id=post_id))


@community_bp.route('/community/<int:post_id>/upvote', methods=['POST'])
@login_required
def upvote_post(post_id):
    """Upvote a community post."""
    post = CommunityPost.query.get_or_404(post_id)
    post.upvotes += 1
    db.session.commit()
    return redirect(url_for('community.view_post', post_id=post_id))
