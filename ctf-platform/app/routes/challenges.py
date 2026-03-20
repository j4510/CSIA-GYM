import re
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, make_response, abort
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models import Challenge, UserChallengeSolve, User, ChallengeSubmission, FlagAttempt, WebChallenge, NcChallenge, DynamicFlag, ChallengeVote, BadgeRule, BadgeClaim, UserBadge, ChallengeBookmark, ChallengeSubscription, ChallengeOpen
from app.routes.admin import log_event
from app.ranking import check_auto_badges
from app.notifs import notify_challenge_solve, notify_challenge_subscribers, notify_first_blood

challenges_bp = Blueprint('challenges', __name__, template_folder='../templates')


def _challenge_host() -> str:
    from flask import current_app
    return current_app.config.get('CHALLENGE_HOST') or request.host.split(':')[0]


def _nc_host() -> str:
    from flask import current_app
    return current_app.config.get('NC_CHALLENGE_HOST') or _challenge_host()


def _web_host() -> str:
    from flask import current_app
    return current_app.config.get('WEB_CHALLENGE_HOST') or _challenge_host()


def _upsert_dynamic_flag(challenge_id: int, user_id: int, flag: str):
    row = DynamicFlag.query.filter_by(challenge_id=challenge_id, user_id=user_id).first()
    if row:
        row.flag = flag
        row.created_at = datetime.utcnow()
    else:
        db.session.add(DynamicFlag(challenge_id=challenge_id, user_id=user_id, flag=flag))
    db.session.commit()


@challenges_bp.route('/challenges')
@login_required
def list():
    query = Challenge.query.filter_by(is_hidden=False)

    category = request.args.get('category')
    if category:
        query = query.filter_by(category=category)

    difficulty = request.args.get('difficulty')
    if difficulty:
        query = query.filter_by(difficulty=difficulty)

    source = request.args.get('source')
    if source in ('official', 'community'):
        admin_ids = db.session.query(User.id).filter_by(is_admin=True).scalar_subquery()
        if source == 'official':
            query = query.filter(Challenge.author_id.in_(admin_ids))
        else:
            query = query.filter(Challenge.author_id.notin_(admin_ids))

    search = request.args.get('search')
    if search:
        query = query.filter(
            Challenge.title.contains(search) | Challenge.description.contains(search)
        )

    solved_challenge_ids = {
        s.challenge_id for s in
        UserChallengeSolve.query.filter_by(user_id=current_user.id)
        .with_entities(UserChallengeSolve.challenge_id).all()
    }

    hide_solved = request.args.get('hide_solved') == '1'
    if hide_solved and solved_challenge_ids:
        query = query.filter(Challenge.id.notin_(solved_challenge_ids))

    bookmarked_ids = {
        b.challenge_id for b in
        ChallengeBookmark.query.filter_by(user_id=current_user.id)
        .with_entities(ChallengeBookmark.challenge_id).all()
    }

    hide_saved = request.args.get('hide_saved') == '1'
    if hide_saved:
        if bookmarked_ids:
            query = query.filter(Challenge.id.in_(bookmarked_ids))
        else:
            query = query.filter(Challenge.id.in_([-1]))  # no bookmarks → show nothing

    subscribed_ids = {
        s.challenge_id for s in
        ChallengeSubscription.query.filter_by(user_id=current_user.id)
        .with_entities(ChallengeSubscription.challenge_id).all()
    }

    # Blood positions: {challenge_id: position (1/2/3)}
    blood_rows = (
        db.session.query(
            UserChallengeSolve.challenge_id,
            UserChallengeSolve.user_id,
            func.rank().over(
                partition_by=UserChallengeSolve.challenge_id,
                order_by=UserChallengeSolve.solved_at
            ).label('pos')
        ).subquery()
    )
    blood_positions = {
        r.challenge_id: r.pos
        for r in db.session.query(blood_rows).filter(
            blood_rows.c.user_id == current_user.id,
            blood_rows.c.pos <= 3
        ).all()
    }

    challenges = query.order_by(Challenge.created_at.desc()).all()
    categories = [r[0] for r in db.session.query(Challenge.category).distinct().all()]

    resp = make_response(render_template(
        'challenges/list.html',
        challenges=challenges,
        categories=categories,
        current_category=category,
        current_difficulty=difficulty,
        current_source=source,
        current_search=search,
        hide_solved=hide_solved,
        hide_saved=hide_saved,
        solved_challenge_ids=solved_challenge_ids,
        bookmarked_ids=bookmarked_ids,
        subscribed_ids=subscribed_ids,
        blood_positions=blood_positions,
        show_tour=not current_user.has_seen_tour,
    ))
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@challenges_bp.route('/challenges/<int:challenge_id>')
@login_required
def detail(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    if challenge.is_hidden and not current_user.is_admin:
        abort(404)
    already_solved = UserChallengeSolve.query.filter_by(
        user_id=current_user.id, challenge_id=challenge_id
    ).first() is not None

    db.session.add(ChallengeOpen(user_id=current_user.id, challenge_id=challenge_id))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    is_bookmarked = ChallengeBookmark.query.filter_by(
        user_id=current_user.id, challenge_id=challenge_id
    ).first() is not None

    is_subscribed = ChallengeSubscription.query.filter_by(
        user_id=current_user.id, challenge_id=challenge_id
    ).first() is not None

    submission = ChallengeSubmission.query.filter_by(
        title=challenge.title, author_id=challenge.author_id, status='approved'
    ).first()
    submission_files = submission.files if submission else []

    vote_row = db.session.query(func.sum(ChallengeVote.value)).filter_by(challenge_id=challenge_id).scalar() or 0
    upvotes = db.session.query(func.count(ChallengeVote.id)).filter_by(challenge_id=challenge_id, value=1).scalar() or 0
    downvotes = db.session.query(func.count(ChallengeVote.id)).filter_by(challenge_id=challenge_id, value=-1).scalar() or 0
    user_vote = None
    if already_solved:
        v = ChallengeVote.query.filter_by(
            challenge_id=challenge_id, user_id=current_user.id).first()
        user_vote = v.value if v else None

    solvers = (
        UserChallengeSolve.query
        .filter_by(challenge_id=challenge_id)
        .order_by(UserChallengeSolve.solved_at)
        .all()
    )

    return render_template(
        'challenges/detail.html',
        challenge=challenge,
        already_solved=already_solved,
        submission_files=submission_files,
        upvotes=upvotes,
        downvotes=downvotes,
        net_votes=vote_row,
        user_vote=user_vote,
        solvers=solvers,
        is_bookmarked=is_bookmarked,
        is_subscribed=is_subscribed,
    )


@challenges_bp.route('/challenges/<int:challenge_id>/submit', methods=['POST'])
@login_required
def submit_flag(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    submitted_flag = request.form.get('flag', '').strip()

    if UserChallengeSolve.query.filter_by(
            user_id=current_user.id, challenge_id=challenge_id).first():
        flash('You have already solved this challenge!', 'info')
        return redirect(url_for('challenges.detail', challenge_id=challenge_id))

    if not submitted_flag.startswith('CSIA{') or not submitted_flag.endswith('}'):
        flash('Invalid flag format. Flags must be in the format CSIA{...}', 'danger')
        return redirect(url_for('challenges.detail', challenge_id=challenge_id))

    dyn = DynamicFlag.query.filter_by(challenge_id=challenge_id, user_id=current_user.id).first()
    if dyn:
        correct = submitted_flag == dyn.flag
    elif challenge.is_regex:
        try:
            correct = bool(re.fullmatch(challenge.flag, submitted_flag))
        except re.error:
            correct = submitted_flag == challenge.flag
    else:
        correct = submitted_flag == challenge.flag

    if correct:
        is_first_blood = not UserChallengeSolve.query.filter_by(challenge_id=challenge_id).first()
        db.session.add(UserChallengeSolve(user_id=current_user.id, challenge_id=challenge_id))
        db.session.add(FlagAttempt(user_id=current_user.id, challenge_id=challenge_id, correct=True, submitted_flag=submitted_flag))
        db.session.commit()
        DynamicFlag.query.filter_by(challenge_id=challenge_id, user_id=current_user.id).delete()
        db.session.commit()
        check_auto_badges(current_user.id)
        log_event(actor=current_user.username, action='flag_correct', target=challenge.title, category='challenge')
        notify_challenge_solve(current_user.id, challenge)
        notify_challenge_subscribers(current_user.id, challenge)
        if is_first_blood:
            notify_first_blood(current_user.id, challenge)
        flash(f'Correct! You earned {challenge.points} points!', 'success')
    else:
        db.session.add(FlagAttempt(user_id=current_user.id, challenge_id=challenge_id, correct=False, submitted_flag=submitted_flag))
        db.session.commit()
        log_event(actor=current_user.username, action='flag_wrong', target=challenge.title, category='challenge')
        flash('Incorrect flag. Try again!', 'danger')

    return redirect(url_for('challenges.detail', challenge_id=challenge_id))


@challenges_bp.route('/challenges/<int:challenge_id>/vote', methods=['POST'])
@login_required
def vote_challenge(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    if not UserChallengeSolve.query.filter_by(
            user_id=current_user.id, challenge_id=challenge_id).first():
        return jsonify(ok=False, error='Must solve first'), 403
    value = request.json.get('value') if request.is_json else int(request.form.get('value', 0))
    if value not in (1, -1):
        return jsonify(ok=False, error='Invalid'), 400
    existing = ChallengeVote.query.filter_by(challenge_id=challenge_id, user_id=current_user.id).first()
    if existing:
        if existing.value == value:
            db.session.delete(existing)
            new_value = None
        else:
            existing.value = value
            new_value = value
    else:
        db.session.add(ChallengeVote(
            challenge_id=challenge_id, user_id=current_user.id, value=value))
        new_value = value
    db.session.commit()
    log_event(actor=current_user.username, action='vote_challenge',
              target=f'{challenge.title} value:{new_value}', category='challenge')
    upvotes = db.session.query(func.count(ChallengeVote.id)).filter_by(challenge_id=challenge_id, value=1).scalar() or 0
    downvotes = db.session.query(func.count(ChallengeVote.id)).filter_by(challenge_id=challenge_id, value=-1).scalar() or 0
    return jsonify(ok=True, upvotes=upvotes, downvotes=downvotes, user_vote=new_value)


@challenges_bp.route('/claim/<token>')
@login_required
def claim_badge(token):
    rule = BadgeRule.query.filter_by(claim_token=token, is_active=True).first_or_404()
    badge = rule.badge
    if BadgeClaim.query.filter_by(rule_id=rule.id, user_id=current_user.id).first():
        flash(f'You have already claimed the "{badge.title}" badge.', 'info')
        return redirect(url_for('settings.badges'))
    if badge.is_limited and badge.limited_count:
        if len(badge.recipients) >= badge.limited_count:
            flash(f'Sorry — the "{badge.title}" badge is sold out (limited edition).', 'danger')
            return redirect(url_for('settings.badges'))
    db.session.add(BadgeClaim(rule_id=rule.id, user_id=current_user.id))
    if not UserBadge.query.filter_by(user_id=current_user.id, badge_id=badge.id).first():
        db.session.add(UserBadge(user_id=current_user.id, badge_id=badge.id))
    db.session.commit()
    log_event(actor=current_user.username, action='claim_badge', target=badge.title, category='challenge')
    flash(f'🎉 You claimed the "{badge.title}" badge!', 'success')
    return redirect(url_for('settings.badges'))


@challenges_bp.route('/scoreboard')
def scoreboard():
    from sqlalchemy import func
    score_sq = (
        db.session.query(
            UserChallengeSolve.user_id,
            func.sum(Challenge.points).label('score'),
            func.count(UserChallengeSolve.id).label('solves')
        )
        .join(Challenge, UserChallengeSolve.challenge_id == Challenge.id)
        .group_by(UserChallengeSolve.user_id)
        .subquery()
    )
    rows = (
        db.session.query(User, score_sq.c.score, score_sq.c.solves)
        .outerjoin(score_sq, User.id == score_sq.c.user_id)
        .filter(User.is_hidden_from_scoreboard == False)
        .order_by((score_sq.c.score).desc().nullslast())
        .all()
    )
    leaderboard = [
        {'user': u, 'score': score or 0, 'solves': solves or 0}
        for u, score, solves in rows
    ]
    return render_template('challenges/scoreboard.html', leaderboard=leaderboard)


@challenges_bp.route('/challenges/<int:challenge_id>/launch-nc', methods=['POST'])
@login_required
def launch_nc(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    if challenge.category != 'Reverse Engineering':
        return jsonify(ok=False, error='Not a reverse engineering challenge'), 400
    nc = NcChallenge.query.filter_by(challenge_id=challenge_id).first()
    if not nc:
        return jsonify(ok=False, error='No binary attached to this challenge.'), 404
    from app.nc_runner import start_nc_server
    try:
        port, expires_at, dynamic_flag = start_nc_server(challenge_id, current_user.id, nc.binary_path)
        if dynamic_flag:
            _upsert_dynamic_flag(challenge_id, current_user.id, dynamic_flag)
        host = _nc_host()
        log_event(actor=current_user.username, action='instance_launch_nc', target=challenge.title, category='challenge')
        return jsonify(ok=True, port=port, host=host, expires_at=expires_at, has_dynamic_flag=bool(dynamic_flag))
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@challenges_bp.route('/challenges/<int:challenge_id>/stop-nc', methods=['POST'])
@login_required
def stop_nc(challenge_id):
    from app.nc_runner import stop_nc_server
    stop_nc_server(challenge_id, current_user.id)
    return jsonify(ok=True)


@challenges_bp.route('/challenges/<int:challenge_id>/extend-nc', methods=['POST'])
@login_required
def extend_nc(challenge_id):
    from app.nc_runner import extend_nc_server
    ok, err, new_expires = extend_nc_server(challenge_id, current_user.id)
    if ok:
        return jsonify(ok=True, expires_at=new_expires)
    return jsonify(ok=False, error=err, expires_at=new_expires)


@challenges_bp.route('/challenges/<int:challenge_id>/nc-status')
@login_required
def nc_status(challenge_id):
    Challenge.query.get_or_404(challenge_id)
    from app.nc_runner import nc_server_status
    status = nc_server_status(challenge_id, current_user.id)
    if status['running']:
        status['host'] = _nc_host()
        dyn = DynamicFlag.query.filter_by(challenge_id=challenge_id, user_id=current_user.id).first()
        status['has_dynamic_flag'] = bool(dyn)
        status.pop('dynamic_flag', None)
    return jsonify(status)


@challenges_bp.route('/challenges/<int:challenge_id>/launch', methods=['POST'])
@login_required
def launch_web(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    if challenge.category != 'Web':
        return jsonify(ok=False, error='Not a web challenge'), 400
    wc = WebChallenge.query.filter_by(challenge_id=challenge_id).first()
    if not wc:
        return jsonify(ok=False, error='No web archive attached to this challenge.'), 404
    from app.web_runner import start_server
    try:
        port, expires_at, dynamic_flag = start_server(challenge_id, current_user.id, wc.archive_path)
        if dynamic_flag:
            _upsert_dynamic_flag(challenge_id, current_user.id, dynamic_flag)
        host = _web_host()
        log_event(actor=current_user.username, action='instance_launch_web', target=challenge.title, category='challenge')
        return jsonify(ok=True, port=port, url=f'http://{host}:{port}/', expires_at=expires_at, has_dynamic_flag=bool(dynamic_flag))
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@challenges_bp.route('/challenges/<int:challenge_id>/stop-web', methods=['POST'])
@login_required
def stop_web(challenge_id):
    from app.web_runner import stop_server
    stop_server(challenge_id, current_user.id)
    return jsonify(ok=True)


@challenges_bp.route('/challenges/<int:challenge_id>/extend-web', methods=['POST'])
@login_required
def extend_web(challenge_id):
    from app.web_runner import extend_server
    ok, err, new_expires = extend_server(challenge_id, current_user.id)
    if ok:
        return jsonify(ok=True, expires_at=new_expires)
    return jsonify(ok=False, error=err, expires_at=new_expires)


@challenges_bp.route('/challenges/<int:challenge_id>/web-status')
@login_required
def web_status(challenge_id):
    Challenge.query.get_or_404(challenge_id)
    from app.web_runner import server_status
    status = server_status(challenge_id, current_user.id)
    if status['running']:
        host = _web_host()
        status['url'] = f"http://{host}:{status['port']}/"
        dyn = DynamicFlag.query.filter_by(challenge_id=challenge_id, user_id=current_user.id).first()
        status['has_dynamic_flag'] = bool(dyn)
        status.pop('dynamic_flag', None)
    return jsonify(status)


@challenges_bp.route('/challenges/<int:challenge_id>/bookmark', methods=['POST'])
@login_required
def toggle_bookmark(challenge_id):
    Challenge.query.get_or_404(challenge_id)
    existing = ChallengeBookmark.query.filter_by(
        user_id=current_user.id, challenge_id=challenge_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify(ok=True, bookmarked=False)
    db.session.add(ChallengeBookmark(user_id=current_user.id, challenge_id=challenge_id))
    db.session.commit()
    return jsonify(ok=True, bookmarked=True)


@challenges_bp.route('/challenges/<int:challenge_id>/subscribe', methods=['POST'])
@login_required
def toggle_subscribe(challenge_id):
    Challenge.query.get_or_404(challenge_id)
    existing = ChallengeSubscription.query.filter_by(
        user_id=current_user.id, challenge_id=challenge_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify(ok=True, subscribed=False)
    db.session.add(ChallengeSubscription(user_id=current_user.id, challenge_id=challenge_id))
    db.session.commit()
    return jsonify(ok=True, subscribed=True)


@challenges_bp.route('/bookmarks')
@login_required
def bookmarks():
    saved = ChallengeBookmark.query.filter_by(user_id=current_user.id)\
        .order_by(ChallengeBookmark.created_at.desc()).all()
    solved_ids = {s.challenge_id for s in
                  UserChallengeSolve.query.filter_by(user_id=current_user.id).all()}
    return render_template('challenges/bookmarks.html', saved=saved, solved_ids=solved_ids)
