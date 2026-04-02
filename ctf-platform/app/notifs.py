"""
Notification helpers — send targeted UserNotification rows.
All functions are fire-and-forget; they silently swallow errors.
"""
from app import db
from app.models import UserNotification, User, ChallengeSubscription, PostSubscription
from sqlalchemy.exc import SQLAlchemyError


def _pref(user, pref_col):
    return getattr(user, pref_col, True)


def push(user_id: int, title: str, body: str, category: str = 'system', link: str = None):
    """Insert a single UserNotification for one user."""
    try:
        db.session.add(UserNotification(
            user_id=user_id, title=title, body=body,
            category=category, link=link,
        ))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()


def push_global(title: str, body: str, category: str = 'system',
                link: str = None, pref_col: str = 'notif_global'):
    """Send a UserNotification to every user who has the given pref enabled."""
    try:
        user_ids = [r[0] for r in db.session.query(User.id).filter(
            getattr(User, pref_col) == True  # noqa: E712
        ).all()]
        for uid in user_ids:
            db.session.add(UserNotification(
                user_id=uid, title=title, body=body,
                category=category, link=link,
            ))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()


def notify_challenge_solve(solver_id: int, challenge):
    """Notify the challenge author that their challenge was solved."""
    try:
        author = User.query.get(challenge.author_id)
        solver = User.query.get(solver_id)
        if author and author.id != solver_id and _pref(author, 'notif_challenge_solve'):
            push(
                author.id,
                f'Your challenge was solved!',
                f'{solver.username} just solved "{challenge.title}".',
                category='challenge',
                link=f'/challenges/{challenge.id}',
            )
    except (AttributeError, RuntimeError):
        pass


def notify_challenge_subscribers(solver_id: int, challenge):
    """Notify users subscribed to a challenge when someone solves it."""
    try:
        solver = User.query.get(solver_id)
        subs = ChallengeSubscription.query.filter_by(challenge_id=challenge.id).all()
        for sub in subs:
            if sub.user_id == solver_id:
                continue
            u = User.query.get(sub.user_id)
            if u and _pref(u, 'notif_challenge_sub'):
                db.session.add(UserNotification(
                    user_id=u.id,
                    title=f'Challenge solved: {challenge.title}',
                    body=f'{solver.username} solved "{challenge.title}".',
                    category='challenge',
                    link=f'/challenges/{challenge.id}',
                ))
        db.session.commit()
    except (AttributeError, SQLAlchemyError):
        db.session.rollback()


def notify_post_subscribers(commenter_id: int, post, comment_preview: str):
    """Notify post author + subscribers when a new comment is added."""
    try:
        commenter = User.query.get(commenter_id)
        notified = set()

        if post.author_id != commenter_id:
            author = User.query.get(post.author_id)
            if author and _pref(author, 'notif_post_reply'):
                db.session.add(UserNotification(
                    user_id=author.id,
                    title=f'New reply on your post',
                    body=f'{commenter.username} replied to "{post.title}": {comment_preview[:80]}',
                    category='community',
                    link=f'/community/{post.id}',
                ))
                notified.add(author.id)

        from app.models import PostSubscription
        subs = PostSubscription.query.filter_by(post_id=post.id).all()
        for sub in subs:
            if sub.user_id in notified or sub.user_id == commenter_id:
                continue
            u = User.query.get(sub.user_id)
            if u and _pref(u, 'notif_post_reply'):
                db.session.add(UserNotification(
                    user_id=u.id,
                    title=f'New reply on "{post.title}"',
                    body=f'{commenter.username}: {comment_preview[:80]}',
                    category='community',
                    link=f'/community/{post.id}',
                ))
        db.session.commit()
    except (AttributeError, SQLAlchemyError):
        db.session.rollback()


def notify_new_challenge(challenge):
    """Notify all users about a newly published challenge."""
    push_global(
        title=f'New challenge: {challenge.title}',
        body=f'A new {challenge.difficulty} {challenge.category} challenge is now live!',
        category='challenge',
        link=f'/challenges/{challenge.id}',
        pref_col='notif_new_challenge',
    )


def notify_changelog(version: str, summary: str):
    """Notify all users about a new version changelog."""
    push_global(
        title=f'Platform updated to {version}',
        body=summary,
        category='system',
        link='/whats-new',
        pref_col='notif_changelog',
    )


def notify_submission_result(user_id: int, title: str, approved: bool):
    """Notify a user that their challenge submission was approved or rejected."""
    try:
        u = User.query.get(user_id)
        if u and _pref(u, 'notif_submission_result'):
            if approved:
                push(user_id, f'Submission approved: {title}',
                     f'Your challenge "{title}" has been approved and is now live!',
                     category='submission', link='/challenges')
            else:
                push(user_id, f'Submission rejected: {title}',
                     f'Your challenge "{title}" was not approved. Check the community for feedback.',
                     category='submission')
    except (AttributeError, RuntimeError):
        pass


def notify_badge_earned(user_id: int, badge_title: str):
    """Notify a user that they earned a badge."""
    try:
        u = User.query.get(user_id)
        if u and _pref(u, 'notif_badge_earned'):
            push(user_id, f'Badge earned: {badge_title}',
                 f'You earned the "{badge_title}" badge!',
                 category='system', link='/badges')
    except (AttributeError, RuntimeError):
        pass


def notify_first_blood(solver_id: int, challenge):
    """Notify the first solver of a challenge about their first blood."""
    try:
        u = User.query.get(solver_id)
        if u and _pref(u, 'notif_first_blood'):
            push(solver_id, f'🩸 First Blood: {challenge.title}',
                 f'You are the first to solve "{challenge.title}"! Legendary.',
                 category='challenge', link=f'/challenges/{challenge.id}')
    except (AttributeError, RuntimeError):
        pass


def notify_upvote_milestone(post_author_id: int, post, count: int):
    """Notify post author when their post hits an upvote milestone."""
    try:
        if count in (10, 25, 50, 100):
            u = User.query.get(post_author_id)
            if u and _pref(u, 'notif_global'):
                push(post_author_id, f'Your post hit {count} upvotes!',
                     f'"{post.title}" just reached {count} upvotes. Keep it up!',
                     category='community', link=f'/community/{post.id}')
    except (AttributeError, RuntimeError):
        pass


def notify_comment_reaction(comment_author_id: int, reactor_username: str, reaction: str, post_id: int):
    """Notify a comment author when someone reacts to their comment."""
    try:
        u = User.query.get(comment_author_id)
        if u and _pref(u, 'notif_post_reply'):
            push(comment_author_id, f'Someone reacted to your comment',
                 f'{reactor_username} reacted with {reaction} to your comment.',
                 category='community', link=f'/community/{post_id}')
    except (AttributeError, RuntimeError):
        pass
