import os
import io
import uuid
import bleach
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from PIL import Image
from app import db
from app.models import CommunityPost, Comment, CommentReaction, PostUpvote, PostSubscription
from sqlalchemy import func
from app.routes.admin import log_event
from app.ranking import check_auto_badges

community_bp = Blueprint('community', __name__, template_folder='../templates')

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'post_images')
PER_PAGE = 5

ALLOWED_TAGS = [
    'p', 'br', 'strong', 'em', 'u', 's', 'blockquote', 'pre', 'code',
    'h1', 'h2', 'h3', 'ol', 'ul', 'li', 'a', 'img', 'span', 'div',
]
ALLOWED_ATTRS = {
    'a': ['href', 'target', 'rel'],
    'img': ['src', 'alt', 'width', 'height'],
    'span': ['class', 'style'],
    'p': ['class'],
    'div': ['class'],
}

MAX_IMAGE_BYTES = 1 * 1024 * 1024
VALID_REACTIONS = {'like', 'dislike', 'heart', 'haha', 'wow', 'sad'}
VALID_FLAIRS = {'Challenge Discussion', 'Writeups', 'For Beginners', 'Need Help', 'Tutorial'}


def _can_moderate(user, post=None):
    """True if user is admin, moderator, or the original poster."""
    if user.is_admin or user.is_moderator:
        return True
    if post and post.author_id == user.id:
        return True
    return False


def _convert_to_webp(file_storage):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    img = Image.open(file_storage).convert('RGB')
    filename = f'post_{uuid.uuid4().hex}.webp'
    dest = os.path.join(UPLOAD_DIR, filename)
    quality = 85
    while True:
        buf = io.BytesIO()
        img.save(buf, 'WEBP', quality=quality)
        if buf.tell() <= MAX_IMAGE_BYTES or quality <= 20:
            break
        if quality > 40:
            quality -= 15
        else:
            w, h = img.size
            img = img.resize((int(w * 0.85), int(h * 0.85)), Image.LANCZOS)
    with open(dest, 'wb') as f:
        buf.seek(0)
        f.write(buf.read())
    return filename, url_for('static', filename=f'post_images/{filename}')


def _interaction_score(post, comment_counts, reaction_counts):
    return post.upvotes + comment_counts.get(post.id, 0) + reaction_counts.get(post.id, 0)


def _load_interaction_maps(post_ids):
    """Return (comment_counts, reaction_counts) dicts keyed by post_id via SQL."""
    from app.models import Comment, CommentReaction
    cc = dict(db.session.query(Comment.post_id, func.count(Comment.id))
              .filter(Comment.post_id.in_(post_ids)).group_by(Comment.post_id).all())
    rc = dict(db.session.query(Comment.post_id, func.count(CommentReaction.id))
              .join(CommentReaction, CommentReaction.comment_id == Comment.id)
              .filter(Comment.post_id.in_(post_ids)).group_by(Comment.post_id).all())
    return cc, rc


@community_bp.route('/community/upload-image', methods=['POST'])
@login_required
def upload_image():
    file = request.files.get('image')
    if not file or not file.filename:
        return jsonify({'error': 'No file'}), 400
    try:
        _, url = _convert_to_webp(file)
        return jsonify({'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@community_bp.route('/community')
@login_required
def list():
    sort = request.args.get('sort', 'hot')
    flair = request.args.get('flair', '')
    page = max(1, request.args.get('page', 1, type=int))
    now = datetime.utcnow()

    query = CommunityPost.query.filter_by(is_archived=False)
    if flair and flair in VALID_FLAIRS:
        query = query.filter(CommunityPost.flair == flair)

    if sort == 'new':
        all_posts = query.order_by(CommunityPost.created_at.desc()).all()
    elif sort == 'week':
        since = now - timedelta(days=7)
        candidates = query.filter(CommunityPost.created_at >= since).all()
        cc, rc = _load_interaction_maps([p.id for p in candidates])
        all_posts = sorted(candidates, key=lambda p: _interaction_score(p, cc, rc), reverse=True)
    elif sort == 'alltime':
        candidates = query.all()
        cc, rc = _load_interaction_maps([p.id for p in candidates])
        all_posts = sorted(candidates, key=lambda p: _interaction_score(p, cc, rc), reverse=True)
    else:  # hot — today
        since = now - timedelta(days=1)
        candidates = query.filter(CommunityPost.created_at >= since).all()
        if not candidates:
            candidates = query.all()
        cc, rc = _load_interaction_maps([p.id for p in candidates])
        all_posts = sorted(candidates, key=lambda p: _interaction_score(p, cc, rc), reverse=True)

    pinned = CommunityPost.query.filter_by(is_pinned=True, is_archived=False)\
        .order_by(CommunityPost.created_at.desc()).limit(10).all()

    if not flair:
        pinned_ids = {p.id for p in pinned}
        all_posts = [p for p in all_posts if p.id not in pinned_ids]

    total = len(all_posts)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    posts = all_posts[(page - 1) * PER_PAGE: page * PER_PAGE]

    return render_template('community/list.html',
                           posts=posts, sort=sort, flair=flair,
                           pinned=pinned,
                           page=page, total_pages=total_pages, total=total,
                           valid_flairs=VALID_FLAIRS)


@community_bp.route('/community/new', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        if current_user.is_timed_out():
            flash(f'You are timed out until {current_user.timeout_until.strftime("%Y-%m-%d %H:%M UTC")} and cannot post.', 'danger')
            return redirect(url_for('community.list'))
        title = request.form.get('title', '').strip()
        raw_content = request.form.get('content', '').strip()
        flair = request.form.get('flair', '').strip() or None
        if flair and flair not in VALID_FLAIRS:
            flair = None
        if not title or not raw_content:
            flash('Title and content are required', 'danger')
            return redirect(url_for('community.new_post'))
        content = bleach.clean(raw_content, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
        post = CommunityPost(title=title, content=content, author_id=current_user.id, flair=flair)
        db.session.add(post)
        db.session.commit()
        check_auto_badges(current_user.id)
        log_event(actor=current_user.username, action='post_create', target=title, category='community')
        flash('Post created successfully!', 'success')
        return redirect(url_for('community.view_post', post_id=post.id))
    return render_template('community/new.html', valid_flairs=VALID_FLAIRS)


@community_bp.route('/community/<int:post_id>')
@login_required
def view_post(post_id):
    post = CommunityPost.query.get_or_404(post_id)
    user_reactions = {
        (r.comment_id, r.reaction)
        for r in CommentReaction.query.filter_by(user_id=current_user.id).all()
    }
    user_upvoted = PostUpvote.query.filter_by(post_id=post_id, user_id=current_user.id).first() is not None
    is_subscribed = PostSubscription.query.filter_by(post_id=post_id, user_id=current_user.id).first() is not None
    can_moderate = _can_moderate(current_user, post)
    from app.ranking import get_user_rank, RANK_CSS, RANK_KEYFRAMES, LEGENDARY_CSS
    all_rank_css = {**RANK_CSS, **LEGENDARY_CSS}
    def rank_info(u):
        _, t = get_user_rank(u)
        return t, all_rank_css.get(t, '')
    post_rank_title, post_rank_style = rank_info(post.author)
    comment_ranks = {c.id: rank_info(c.author) for c in post.comments}
    return render_template('community/view.html', post=post,
                           user_reactions=user_reactions,
                           user_upvoted=user_upvoted,
                           is_subscribed=is_subscribed,
                           can_moderate=can_moderate,
                           post_rank_title=post_rank_title,
                           post_rank_style=post_rank_style,
                           comment_ranks=comment_ranks,
                           rank_keyframes=RANK_KEYFRAMES)


@community_bp.route('/community/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = CommunityPost.query.get_or_404(post_id)
    if not _can_moderate(current_user, post):
        abort(403)
    db.session.delete(post)
    db.session.commit()
    log_event(actor=current_user.username, action='delete_post', target=f'post:{post_id}', category='community')
    flash('Post deleted.', 'info')
    return redirect(url_for('community.list'))


@community_bp.route('/community/<int:post_id>/edit', methods=['POST'])
@login_required
def edit_post(post_id):
    post = CommunityPost.query.get_or_404(post_id)
    if not _can_moderate(current_user, post):
        abort(403)
    title = request.form.get('title', '').strip()
    raw_content = request.form.get('content', '').strip()
    if not title or not raw_content:
        flash('Title and content are required.', 'danger')
        return redirect(url_for('community.view_post', post_id=post_id))
    post.title = title
    post.content = bleach.clean(raw_content, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
    db.session.commit()
    log_event(actor=current_user.username, action='edit_post', target=f'post:{post_id}', category='community')
    flash('Post updated.', 'success')
    return redirect(url_for('community.view_post', post_id=post_id))


@community_bp.route('/community/<int:post_id>/pin', methods=['POST'])
@login_required
def pin_post(post_id):
    if not current_user.is_admin and not current_user.is_moderator:
        abort(403)
    post = CommunityPost.query.get_or_404(post_id)
    post.is_pinned = True
    db.session.commit()
    log_event(actor=current_user.username, action='pin_post', target=f'post:{post_id}', category='community')
    flash(f'"{post.title}" is now pinned.', 'success')
    return redirect(url_for('community.view_post', post_id=post_id))


@community_bp.route('/community/<int:post_id>/unpin', methods=['POST'])
@login_required
def unpin_post(post_id):
    if not current_user.is_admin and not current_user.is_moderator:
        abort(403)
    post = CommunityPost.query.get_or_404(post_id)
    post.is_pinned = False
    db.session.commit()
    log_event(actor=current_user.username, action='unpin_post', target=f'post:{post_id}', category='community')
    flash('Post unpinned.', 'info')
    return redirect(url_for('community.view_post', post_id=post_id))


@community_bp.route('/community/<int:post_id>/toggle-comments', methods=['POST'])
@login_required
def toggle_comments(post_id):
    post = CommunityPost.query.get_or_404(post_id)
    if not _can_moderate(current_user, post):
        abort(403)
    post.comments_disabled = not post.comments_disabled
    db.session.commit()
    log_event(actor=current_user.username, action='toggle_comments',
              target=f'post:{post_id}', category='community')
    return redirect(url_for('community.view_post', post_id=post_id))


@community_bp.route('/community/<int:post_id>/toggle-reactions', methods=['POST'])
@login_required
def toggle_reactions(post_id):
    post = CommunityPost.query.get_or_404(post_id)
    if not _can_moderate(current_user, post):
        abort(403)
    post.reactions_disabled = not post.reactions_disabled
    db.session.commit()
    log_event(actor=current_user.username, action='toggle_reactions',
              target=f'post:{post_id}', category='community')
    return redirect(url_for('community.view_post', post_id=post_id))


@community_bp.route('/community/<int:post_id>/archive', methods=['POST'])
@login_required
def archive_post(post_id):
    post = CommunityPost.query.get_or_404(post_id)
    if not _can_moderate(current_user, post):
        abort(403)
    post.is_archived = not post.is_archived
    db.session.commit()
    log_event(actor=current_user.username, action='archive_post',
              target=f'post:{post_id}', category='community')
    flash('Post archived.' if post.is_archived else 'Post unarchived.', 'info')
    return redirect(url_for('community.view_post', post_id=post_id))


@community_bp.route('/community/comment/<int:comment_id>/edit', methods=['POST'])
@login_required
def edit_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.author_id != current_user.id and not current_user.is_admin and not current_user.is_moderator:
        abort(403)
    content = request.form.get('content', '').strip()
    if not content:
        flash('Comment cannot be empty.', 'danger')
        return redirect(url_for('community.view_post', post_id=comment.post_id))
    comment.content = content
    # Only record edited_by if a mod/admin edited someone else's comment
    if current_user.id != comment.author_id:
        comment.edited_by_id = current_user.id
        comment.edited_at = datetime.utcnow()
    else:
        comment.edited_at = datetime.utcnow()
    db.session.commit()
    log_event(actor=current_user.username, action='edit_comment',
              target=f'comment:{comment_id}', category='community')
    flash('Comment updated.', 'success')
    return redirect(url_for('community.view_post', post_id=comment.post_id))


@community_bp.route('/community/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    post = CommunityPost.query.get_or_404(comment.post_id)
    if not _can_moderate(current_user, post) and comment.author_id != current_user.id:
        abort(403)
    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    log_event(actor=current_user.username, action='delete_comment',
              target=f'comment:{comment_id}', category='community')
    flash('Comment deleted.', 'info')
    return redirect(url_for('community.view_post', post_id=post_id))


@community_bp.route('/community/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    if current_user.is_timed_out():
        flash(f'You are timed out until {current_user.timeout_until.strftime("%Y-%m-%d %H:%M UTC")} and cannot comment.', 'danger')
        return redirect(url_for('community.view_post', post_id=post_id))
    post = CommunityPost.query.get_or_404(post_id)
    if post.comments_disabled and not _can_moderate(current_user, post):
        flash('Comments are disabled on this post.', 'danger')
        return redirect(url_for('community.view_post', post_id=post_id))
    content = request.form.get('content', '').strip()
    if not content:
        flash('Comment cannot be empty', 'danger')
        return redirect(url_for('community.view_post', post_id=post_id))
    db.session.add(Comment(content=content, author_id=current_user.id, post_id=post_id))
    db.session.commit()
    log_event(actor=current_user.username, action='comment_add', target=f'post:{post_id}', category='community')
    from app.notifs import notify_post_subscribers
    notify_post_subscribers(current_user.id, post, content)
    if not PostSubscription.query.filter_by(post_id=post_id, user_id=current_user.id).first():
        db.session.add(PostSubscription(post_id=post_id, user_id=current_user.id))
        db.session.commit()
    flash('Comment added!', 'success')
    return redirect(url_for('community.view_post', post_id=post_id))


@community_bp.route('/community/comment/<int:comment_id>/react/<reaction>', methods=['POST'])
@login_required
def react_comment(comment_id, reaction):
    if current_user.is_timed_out():
        return jsonify({'error': f'Timed out until {current_user.timeout_until.strftime("%Y-%m-%d %H:%M UTC")}'}), 403
    if reaction not in VALID_REACTIONS:
        return jsonify({'error': 'invalid'}), 400
    comment = Comment.query.get_or_404(comment_id)
    post = CommunityPost.query.get_or_404(comment.post_id)
    if post.reactions_disabled and not _can_moderate(current_user, post):
        return jsonify({'error': 'reactions disabled'}), 403
    existing = CommentReaction.query.filter_by(
        comment_id=comment_id, user_id=current_user.id, reaction=reaction
    ).first()
    if existing:
        db.session.delete(existing)
        active = False
    else:
        CommentReaction.query.filter_by(comment_id=comment_id, user_id=current_user.id).delete()
        db.session.add(CommentReaction(comment_id=comment_id, user_id=current_user.id, reaction=reaction))
        active = True
    db.session.commit()
    all_counts = {}
    for r in CommentReaction.query.filter_by(comment_id=comment_id).all():
        all_counts[r.reaction] = all_counts.get(r.reaction, 0) + 1
    check_auto_badges(comment.author_id)
    if active:
        from app.notifs import notify_comment_reaction
        notify_comment_reaction(comment.author_id, current_user.username, reaction, comment.post_id)
    return jsonify({'active': active, 'reaction': reaction, 'all_counts': all_counts})


@community_bp.route('/community/<int:post_id>/upvote', methods=['POST'])
@login_required
def upvote_post(post_id):
    if current_user.is_timed_out():
        flash(f'You are timed out until {current_user.timeout_until.strftime("%Y-%m-%d %H:%M UTC")} and cannot upvote.', 'danger')
        return redirect(url_for('community.view_post', post_id=post_id))
    post = CommunityPost.query.get_or_404(post_id)
    existing = PostUpvote.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    if not existing:
        db.session.add(PostUpvote(post_id=post_id, user_id=current_user.id))
        post.upvotes += 1
        db.session.commit()
        log_event(actor=current_user.username, action='upvote_post', target=f'post:{post_id}', category='community')
        check_auto_badges(post.author_id)
        from app.notifs import notify_upvote_milestone
        notify_upvote_milestone(post.author_id, post, post.upvotes)
    return redirect(url_for('community.view_post', post_id=post_id))


@community_bp.route('/community/<int:post_id>/subscribe', methods=['POST'])
@login_required
def toggle_post_subscribe(post_id):
    CommunityPost.query.get_or_404(post_id)
    existing = PostSubscription.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify(ok=True, subscribed=False)
    db.session.add(PostSubscription(post_id=post_id, user_id=current_user.id))
    db.session.commit()
    return jsonify(ok=True, subscribed=True)
