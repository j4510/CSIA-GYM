"""
Ranking engine — percentile-based titles with CSS styling.

All DB queries are batched once in compute_all_scores() and cached on
Flask's g object so multiple callers in the same request pay zero extra cost.
"""

from app.models import (
    User, Challenge, UserChallengeSolve, ChallengeSubmission,
    FlagAttempt, CommunityPost, PostUpvote
)

DIFFICULTY_WEIGHT = {'easy': 1.0, 'medium': 2.2, 'hard': 4.5}

LEGENDARY_TIERS = [
    'Omninet Ambassador',
    'Omninet Sovereign',
    'Ghost in the Core',
    'Zero-Day Deity',
    'Singularity Architect',
]

ADMIN_ASSIGNABLE_LEGENDARY = {'Omninet Ambassador', 'Omninet Sovereign'}
GHOST_COMMAND = 'I4mGroot'

RANK_TIERS = [
    (99.9, 'Master of the Nexus'),
    (99.0, 'Digital Overlord'),
    (97.0, 'Grid Phantom'),
    (94.0, 'System Sage'),
    (90.0, 'Quantum Hacker'),
    (80.0, 'Cipher Hunter'),
    (65.0, 'Scriptblade'),
    (50.0, 'Packet Rogue'),
    (25.0, 'Firewall Adept'),
    (0.0,  'Neo Initiate'),
]

LEGENDARY_CSS = {
    'Omninet Ambassador': (
        'font-weight:900;'
        'background:linear-gradient(90deg,#00b4d8,#0077b6,#48cae4,#90e0ef,#00b4d8);'
        'background-size:300% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:legendAmbassador 3s linear infinite;'
        'filter:drop-shadow(0 0 6px #00b4d8) drop-shadow(0 0 14px #0077b6);'
        'letter-spacing:0.06em;'
    ),
    'Omninet Sovereign': (
        'font-weight:900;'
        'background:linear-gradient(90deg,#7b2ff7,#e040fb,#7b2ff7,#b000e0,#e040fb);'
        'background-size:300% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:legendSovereign 2.4s linear infinite;'
        'filter:drop-shadow(0 0 8px #e040fb) drop-shadow(0 0 20px #7b2ff7);'
        'letter-spacing:0.07em;'
    ),
    'Ghost in the Core': (
        'font-weight:900;'
        'background:linear-gradient(90deg,#00fff7,#00e5ff,#18ffff,#84ffff,#00fff7);'
        'background-size:300% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:legendGhost 2s linear infinite,legendGhostFlicker 4s steps(1) infinite;'
        'filter:drop-shadow(0 0 10px #00fff7) drop-shadow(0 0 24px #00bcd4);'
        'letter-spacing:0.1em;'
    ),
    'Zero-Day Deity': (
        'font-weight:900;'
        'background:linear-gradient(90deg,#ff0040,#ff6600,#ffcc00,#ff0040,#ff6600);'
        'background-size:400% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:legendDeity 1.6s linear infinite;'
        'filter:drop-shadow(0 0 12px #ff0040) drop-shadow(0 0 28px #ff6600);'
        'letter-spacing:0.08em;'
    ),
    'Singularity Architect': (
        'font-weight:900;'
        'background:linear-gradient(90deg,#ffffff,#c0c0ff,#ffffff,#a0a0ff,#ffffff,#e0e0ff,#ffffff);'
        'background-size:400% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:legendSingularity 1.2s linear infinite;'
        'filter:drop-shadow(0 0 16px #ffffff) drop-shadow(0 0 32px #8080ff) drop-shadow(0 0 48px #4040cc);'
        'letter-spacing:0.12em;'
    ),
}

RANK_CSS = {
    'Neo Initiate': 'color:#c0c0c0;font-weight:900;',
    'Firewall Adept': (
        'color:#ff2222;font-weight:900;'
        'animation:rankPulse 1.4s ease-in-out infinite;'
        'text-shadow:0 0 8px #ff0000,0 0 18px #cc0000;'
    ),
    'Packet Rogue': (
        'font-weight:900;'
        'background:linear-gradient(90deg,#ff4500,#ff0000,#ff6600,#ff2200);'
        'background-size:200% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:rankFire 1.8s linear infinite;'
    ),
    'Scriptblade': (
        'color:#e8e8e8;font-weight:900;'
        'background:linear-gradient(90deg,#aaa,#fff,#ccc,#fff,#aaa);'
        'background-size:300% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:rankShine 2.2s linear infinite;'
    ),
    'Cipher Hunter': (
        'color:#00aaff;font-weight:900;'
        'text-shadow:0 0 6px #0088ff,0 0 14px #0044cc;'
        'animation:rankCryptic 3s steps(1) infinite;'
        'letter-spacing:0.08em;'
    ),
    'Quantum Hacker': (
        'font-weight:900;'
        'background:linear-gradient(90deg,#cc0000,#ff0000,#880000,#ff2200);'
        'background-size:200% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:rankFire 1.4s linear infinite;'
        'letter-spacing:0.06em;'
        'filter:drop-shadow(0 0 4px #cc0000);'
    ),
    'System Sage': (
        'font-weight:900;'
        'background:linear-gradient(90deg,#00c853,#69f0ae,#00e676,#1de9b6,#00c853);'
        'background-size:300% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:rankShine 2s linear infinite;'
        'filter:drop-shadow(0 0 5px #00c853);'
    ),
    'Grid Phantom': (
        'font-weight:900;'
        'background:linear-gradient(135deg,#2d0057,#6a0dad,#1a0030,#9b30ff);'
        'background-size:300% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:rankShine 3s linear infinite;'
        'filter:drop-shadow(0 0 8px rgba(106,13,173,0.9)) drop-shadow(2px 2px 4px #000);'
    ),
    'Digital Overlord': (
        'font-weight:900;'
        'background:linear-gradient(90deg,#ff0000,#ff7700,#ffff00,#00ff00,#0000ff,#8b00ff,#ff0000);'
        'background-size:400% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:rankRainbow 2s linear infinite;'
        'letter-spacing:0.05em;'
    ),
    'Master of the Nexus': (
        'font-weight:900;'
        'background:linear-gradient(90deg,#b8860b,#ffd700,#fffacd,#ffd700,#daa520,#ffd700);'
        'background-size:300% auto;'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
        'animation:rankShine 1.6s linear infinite;'
        'filter:drop-shadow(0 0 6px #ffd700) drop-shadow(0 0 14px #b8860b);'
        'letter-spacing:0.04em;'
    ),
}

ALL_RANK_CSS = {**RANK_CSS, **LEGENDARY_CSS}

RANK_KEYFRAMES = """
@keyframes legendAmbassador {
  0%   { background-position:0% center; }
  100% { background-position:300% center; }
}
@keyframes legendSovereign {
  0%   { background-position:0% center; }
  100% { background-position:300% center; }
}
@keyframes legendGhost {
  0%   { background-position:0% center; }
  100% { background-position:300% center; }
}
@keyframes legendGhostFlicker {
  0%,100% { opacity:1; }
  10%      { opacity:0.3; }
  12%      { opacity:1; }
  55%      { opacity:1; }
  57%      { opacity:0.15; }
  59%      { opacity:1; }
}
@keyframes legendDeity {
  0%   { background-position:0% center; }
  100% { background-position:400% center; }
}
@keyframes legendSingularity {
  0%   { background-position:0% center; filter:drop-shadow(0 0 16px #fff) drop-shadow(0 0 32px #8080ff) drop-shadow(0 0 48px #4040cc); }
  50%  { background-position:200% center; filter:drop-shadow(0 0 24px #fff) drop-shadow(0 0 48px #a0a0ff) drop-shadow(0 0 72px #6060dd); }
  100% { background-position:400% center; filter:drop-shadow(0 0 16px #fff) drop-shadow(0 0 32px #8080ff) drop-shadow(0 0 48px #4040cc); }
}
@keyframes rankPulse {
  0%,100% { opacity:1; text-shadow:0 0 8px #ff0000,0 0 18px #cc0000; }
  50%      { opacity:0.6; text-shadow:0 0 2px #ff0000; }
}
@keyframes rankFire {
  0%   { background-position:0% center; }
  100% { background-position:200% center; }
}
@keyframes rankShine {
  0%   { background-position:0% center; }
  100% { background-position:300% center; }
}
@keyframes rankRainbow {
  0%   { background-position:0% center; }
  100% { background-position:400% center; }
}
@keyframes rankCryptic {
  0%  { letter-spacing:0.08em; opacity:1; }
  20% { letter-spacing:0.14em; opacity:0.7; }
  40% { letter-spacing:0.04em; opacity:1; }
  60% { letter-spacing:0.10em; opacity:0.85; }
  80% { letter-spacing:0.06em; opacity:1; }
}
"""

LEGENDARY_DESCRIPTIONS = {
    'Omninet Ambassador': (
        'A chosen voice of the Omninet. Ambassadors are recognized by the administration '
        'for their outstanding representation of the community — bridging players, fostering '
        'culture, and carrying the platform\'s identity beyond its walls.'
    ),
    'Omninet Sovereign': (
        'The master of the nexus bows here. Sovereigns are those who have demonstrated '
        'relentless, sustained mastery and activity — pillars of the platform whose presence '
        'shapes the very fabric of the Omninet. Granted only by administrators to the most '
        'dedicated architects of the community.'
    ),
    'Ghost in the Core': (
        'You found the signal buried in the noise. The Ghost in the Core exists between '
        'layers — a phantom who discovered the hidden frequency and answered the call. '
        'This rank cannot be given. It can only be found.'
    ),
    'Zero-Day Deity': (
        'Before the patch. Before the disclosure. Before anyone knew the vulnerability existed — '
        'you were already there. The Zero-Day Deity operates at a level that transcends the platform '
        'itself. Reserved for those who built what others can only use.'
    ),
    'Singularity Architect': '???',
}

RANK_DESCRIPTIONS = {
    'Neo Initiate': (
        'The beginning of the journey. You\'ve just stepped into the arena — '
        'every challenge solved is a step forward.'
    ),
    'Firewall Adept': (
        'You\'ve broken through the first wall. Your skills are sharpening and '
        'the community is starting to notice your presence.'
    ),
    'Packet Rogue': (
        'A rogue on the network. You move fast, think faster, and leave traces '
        'that others struggle to follow.'
    ),
    'Scriptblade': (
        'Your scripts cut clean. You\'ve mastered the art of automation and '
        'precision — a blade forged from pure code.'
    ),
    'Cipher Hunter': (
        'Cryptography bends to your will. You hunt ciphers like prey, '
        'decoding what others cannot even read.'
    ),
    'Quantum Hacker': (
        'Operating at a level beyond conventional logic. Your approach to '
        'problems is unpredictable, powerful, and devastating.'
    ),
    'System Sage': (
        'Deep system knowledge flows through you. You understand the machine '
        'at its core — kernel, memory, and everything beneath.'
    ),
    'Grid Phantom': (
        'You exist between the lines of the grid. Silent, invisible, and '
        'lethal — a ghost that leaves no trace.'
    ),
    'Digital Overlord': (
        'You dominate the digital realm. Few have reached this tier; fewer '
        'still can challenge your authority over the platform.'
    ),
    'Master of the Nexus': (
        'The apex. You are the Nexus itself — a living legend whose mastery '
        'of every domain is unmatched. The platform bows to your name.'
    ),
}


def check_auto_badges(user_id: int):
    """Evaluate all active auto-give badge rules for a user and award if eligible."""
    from datetime import datetime, timedelta
    from app.models import (
        User, UserChallengeSolve, ChallengeSubmission, CommunityPost,
        PostUpvote, CommentReaction, Comment, BadgeRule, BadgeClaim, UserBadge
    )
    from app import db

    user = User.query.get(user_id)
    if not user:
        return

    rules = BadgeRule.query.filter_by(is_active=True).all()
    for rule in rules:
        if rule.rule_type == 'claimable_link':
            continue
        if BadgeClaim.query.filter_by(rule_id=rule.id, user_id=user_id).first():
            continue
        badge = rule.badge
        if badge.is_limited and badge.limited_count:
            if len(badge.recipients) >= badge.limited_count:
                continue

        eligible = False
        if rule.rule_type == 'solved_challenge' and rule.challenge_id:
            eligible = UserChallengeSolve.query.filter_by(
                user_id=user_id, challenge_id=rule.challenge_id).first() is not None
        elif rule.rule_type == 'community_posts':
            eligible = len(user.posts) >= (rule.threshold or 1)
        elif rule.rule_type == 'approved_submissions':
            eligible = ChallengeSubmission.query.filter_by(
                author_id=user_id, status='approved').count() >= (rule.threshold or 1)
        elif rule.rule_type == 'post_upvotes':
            total = (PostUpvote.query.join(CommunityPost, PostUpvote.post_id == CommunityPost.id)
                     .filter(CommunityPost.author_id == user_id).count())
            eligible = total >= (rule.threshold or 1)
        elif rule.rule_type == 'comment_reactions':
            total = (CommentReaction.query.join(Comment, CommentReaction.comment_id == Comment.id)
                     .filter(Comment.author_id == user_id).count())
            eligible = total >= (rule.threshold or 1)
        elif rule.rule_type == 'scoreboard_top_week':
            scores = compute_all_scores()
            if scores:
                eligible = (max(scores, key=lambda k: scores[k]) == user_id)
        elif rule.rule_type == 'top_month_post':
            since = datetime.utcnow() - timedelta(days=30)
            top = CommunityPost.query.filter(CommunityPost.created_at >= since
                  ).order_by(CommunityPost.upvotes.desc()).first()
            eligible = top is not None and top.author_id == user_id

        if eligible:
            db.session.add(BadgeClaim(rule_id=rule.id, user_id=user_id))
            if not UserBadge.query.filter_by(user_id=user_id, badge_id=badge.id).first():
                db.session.add(UserBadge(user_id=user_id, badge_id=badge.id))
                try:
                    from app.notifs import notify_badge_earned
                    notify_badge_earned(user_id, badge.title)
                except Exception:
                    pass
    db.session.commit()


def compute_all_scores() -> dict:
    """
    Return {user_id: raw_score} for all non-hidden, non-admin users.
    Cached on Flask g for the duration of the request.

    Score components:
      - solve_score:       rarity × difficulty × points weight
      - blood_bonus:       first blood +15, second +8, third +4 (low weight)
      - cat_score:         category breadth
      - post_score:        community posts
      - submission_score:  accepted (+8) / rejected (-1.5) submissions
      - vote_score:        net challenge votes received (medium weight: +3/-2 per vote)
      - reaction_score:    post upvotes received
      - comment_score:     comments made
      - attempt_penalty:   wrong flag attempts
    """
    from flask import g
    if hasattr(g, '_rank_scores'):
        return g._rank_scores

    users = User.query.filter_by(is_hidden_from_scoreboard=False, is_admin=False).all()
    if not users:
        g._rank_scores = {}
        return {}

    from sqlalchemy import func
    from app.models import CommunityPost, PostUpvote, ChallengeVote

    # Batch: solve counts per challenge
    solve_counts: dict[int, int] = {}
    for s in UserChallengeSolve.query.all():
        solve_counts[s.challenge_id] = solve_counts.get(s.challenge_id, 0) + 1

    # Batch: challenge metadata
    challenges: dict[int, Challenge] = {c.id: c for c in Challenge.query.all()}

    # Batch: category totals
    cat_totals: dict[str, int] = {}
    for c in challenges.values():
        cat_totals[c.category] = cat_totals.get(c.category, 0) + 1

    # Batch: first/second/third blood per challenge (sorted by solved_at)
    blood_map: dict[int, dict[int, int]] = {}  # challenge_id -> {user_id: blood_pos}
    all_solves_ordered = (
        UserChallengeSolve.query
        .order_by(UserChallengeSolve.challenge_id, UserChallengeSolve.solved_at)
        .all()
    )
    _ch_seen: dict[int, int] = {}
    for sv in all_solves_ordered:
        pos = _ch_seen.get(sv.challenge_id, 0) + 1
        _ch_seen[sv.challenge_id] = pos
        if pos <= 3:
            blood_map.setdefault(sv.challenge_id, {})[sv.user_id] = pos

    # Batch: submission counts per user
    accepted_counts: dict[int, int] = {}
    rejected_counts: dict[int, int] = {}
    for sub in ChallengeSubmission.query.with_entities(
            ChallengeSubmission.author_id, ChallengeSubmission.status).all():
        if sub.status == 'approved':
            accepted_counts[sub.author_id] = accepted_counts.get(sub.author_id, 0) + 1
        elif sub.status == 'rejected':
            rejected_counts[sub.author_id] = rejected_counts.get(sub.author_id, 0) + 1

    # Batch: net challenge votes received by challenge author (medium weight)
    vote_rows = (
        ChallengeVote.query
        .join(Challenge, ChallengeVote.challenge_id == Challenge.id)
        .with_entities(Challenge.author_id,
                       func.sum(ChallengeVote.value).label('net'))
        .group_by(Challenge.author_id)
        .all()
    )
    vote_net: dict[int, int] = {uid: (net or 0) for uid, net in vote_rows}

    # Batch: upvotes per user (via post ownership)
    upvote_rows = (
        PostUpvote.query
        .join(CommunityPost, PostUpvote.post_id == CommunityPost.id)
        .with_entities(CommunityPost.author_id, func.count(PostUpvote.id))
        .group_by(CommunityPost.author_id)
        .all()
    )
    upvotes_received: dict[int, int] = {uid: cnt for uid, cnt in upvote_rows}

    # Batch: wrong flag attempts per user
    wrong_rows = (
        FlagAttempt.query
        .filter_by(correct=False)
        .with_entities(FlagAttempt.user_id, func.count(FlagAttempt.id))
        .group_by(FlagAttempt.user_id)
        .all()
    )
    wrong_attempts: dict[int, int] = {uid: cnt for uid, cnt in wrong_rows}

    BLOOD_BONUS = {1: 15.0, 2: 8.0, 3: 4.0}  # low consideration

    scores: dict[int, float] = {}
    for user in users:
        solve_score = 0.0
        blood_score = 0.0
        solved_cats: dict[str, int] = {}
        for solve in user.solves:
            c = challenges.get(solve.challenge_id)
            if not c:
                continue
            rarity = 1.0 / (solve_counts.get(c.id, 1) ** 0.5)
            diff_w = DIFFICULTY_WEIGHT.get(c.difficulty, 1.0)
            pts_w = (c.points / 100.0) ** 0.6
            solve_score += rarity * diff_w * pts_w * 40
            solved_cats[c.category] = solved_cats.get(c.category, 0) + 1
            # Blood bonus (low weight)
            blood_pos = blood_map.get(c.id, {}).get(user.id)
            if blood_pos:
                blood_score += BLOOD_BONUS[blood_pos]

        cat_score = sum(
            (cnt / cat_totals.get(cat, 1)) * 12
            for cat, cnt in solved_cats.items()
        )
        post_score       = len(user.posts) * 2.5
        submission_score = (accepted_counts.get(user.id, 0) * 8.0
                            - rejected_counts.get(user.id, 0) * 1.5)
        # Challenge vote score: medium weight (+3 per upvote, -2 per downvote)
        net_votes = vote_net.get(user.id, 0)
        vote_score = (max(net_votes, 0) * 3.0) + (min(net_votes, 0) * 2.0)
        reaction_score   = upvotes_received.get(user.id, 0) * 1.2
        comment_score    = len(user.comments) * 1.0
        attempt_penalty  = wrong_attempts.get(user.id, 0) * 0.05

        scores[user.id] = (solve_score + blood_score + cat_score + post_score
                           + submission_score + vote_score + reaction_score
                           + comment_score - attempt_penalty)

    g._rank_scores = scores
    return scores


def get_user_rank(user) -> tuple[float, str]:
    """Return (percentile, rank_title). Legendary rank takes priority."""
    if getattr(user, 'legendary_rank', None) and user.legendary_rank in LEGENDARY_TIERS:
        return 100.0, user.legendary_rank

    scores = compute_all_scores()
    if not scores:
        return 0.0, 'Neo Initiate'

    my_score = scores.get(user.id, 0.0)
    all_scores = sorted(scores.values())
    n = len(all_scores)
    beats = sum(1 for s in all_scores if s <= my_score)
    percentile = (beats / n) * 100.0

    for threshold, title in RANK_TIERS:
        if percentile >= threshold:
            return round(percentile, 2), title
    return 0.0, 'Neo Initiate'


def get_category_radar_data(users) -> tuple[list, list]:
    """
    Return (categories, datasets).
    Reuses the already-loaded challenge data where possible.
    """
    all_cats = sorted({c.category for c in Challenge.query.all()})
    datasets = []
    for user in users:
        cat_points: dict[str, int] = {cat: 0 for cat in all_cats}
        for solve in user.solves:
            cat = solve.challenge.category
            if cat in cat_points:
                cat_points[cat] += solve.challenge.points
        datasets.append({
            'user_id': user.id,
            'username': user.username,
            'data': [cat_points[cat] for cat in all_cats],
        })
    return all_cats, datasets
