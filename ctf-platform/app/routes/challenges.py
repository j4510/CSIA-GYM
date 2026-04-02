import re
import os
import uuid
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, make_response, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import func
from app import db, csrf
from app.models import Challenge, UserChallengeSolve, User, ChallengeSubmission, FlagAttempt, WebChallenge, NcChallenge, DynamicFlag, ChallengeVote, BadgeRule, BadgeClaim, UserBadge, ChallengeBookmark, ChallengeSubscription, ChallengeOpen
from app.routes.admin import log_event
from app.ranking import check_auto_badges
from app.notifs import notify_challenge_solve, notify_challenge_subscribers, notify_first_blood

challenges_bp = Blueprint('challenges', __name__, template_folder='../templates')

# Directory for storing player solution submissions (web exploitation tar.gz files)
SOLUTIONS_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'instance', 'player_solutions'
)
MAX_SOLUTION_FILE_BYTES = 100 * 1024 * 1024  # 100 MB cap for solution files


def _safe_join(base: str, filename: str) -> str:
    """Resolve filename inside base and assert containment. Raises ValueError on escape."""
    real_base = os.path.realpath(base)
    safe_name = os.path.basename(filename)
    if not safe_name:
        raise ValueError(f'Empty filename after basename: {filename!r}')
    real_path = os.path.realpath(real_base + os.sep + safe_name)
    if not real_path.startswith(real_base + os.sep) and real_path != real_base:
        raise ValueError(f'Path traversal detected: {filename!r}')
    return real_path


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
        row.created_at = datetime.now(timezone.utc)
    else:
        db.session.add(DynamicFlag(challenge_id=challenge_id, user_id=user_id, flag=flag))
    db.session.commit()


def _apply_challenge_filters(query, category, difficulty, source, search):
    """Apply filter parameters to a Challenge query and return it."""
    if category:
        query = query.filter_by(category=category)
    if difficulty:
        query = query.filter_by(difficulty=difficulty)
    if source in ('official', 'community'):
        admin_ids = db.session.query(User.id).filter_by(is_admin=True).scalar_subquery()
        if source == 'official':
            query = query.filter(Challenge.author_id.in_(admin_ids))
        else:
            query = query.filter(Challenge.author_id.notin_(admin_ids))
    if search:
        query = query.filter(
            Challenge.title.contains(search) | Challenge.description.contains(search)
        )
    return query


def _get_user_challenge_sets(user_id):
    """Return (solved_ids, bookmarked_ids, subscribed_ids) sets for a user."""
    solved_ids = {
        s.challenge_id for s in
        UserChallengeSolve.query.filter_by(user_id=user_id)
        .with_entities(UserChallengeSolve.challenge_id).all()
    }
    bookmarked_ids = {
        b.challenge_id for b in
        ChallengeBookmark.query.filter_by(user_id=user_id)
        .with_entities(ChallengeBookmark.challenge_id).all()
    }
    subscribed_ids = {
        s.challenge_id for s in
        ChallengeSubscription.query.filter_by(user_id=user_id)
        .with_entities(ChallengeSubscription.challenge_id).all()
    }
    return solved_ids, bookmarked_ids, subscribed_ids


def _get_blood_positions(user_id):
    """Return {challenge_id: position} for top-3 blood positions for a user."""
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
    return {
        r.challenge_id: r.pos
        for r in db.session.query(blood_rows).filter(
            blood_rows.c.user_id == user_id,
            blood_rows.c.pos <= 3
        ).all()
    }


@challenges_bp.route('/challenges')
@login_required
def list():
    category = request.args.get('category')
    difficulty = request.args.get('difficulty')
    source = request.args.get('source')
    hide_solved = request.args.get('hide_solved') == '1'
    hide_saved = request.args.get('hide_saved') == '1'

    # amazonq-ignore-next-line
    raw_search = request.args.get('search', '').strip()[:200]
    import re as _re
    search = _re.sub(r'[^\w\s\-_.,!?@#]', '', raw_search, flags=_re.UNICODE)[:200]
    safe_search = search

    solved_ids, bookmarked_ids, subscribed_ids = _get_user_challenge_sets(current_user.id)

    query = Challenge.query.filter_by(is_hidden=False)
    query = _apply_challenge_filters(query, category, difficulty, source, search)

    if hide_solved and solved_ids:
        query = query.filter(Challenge.id.notin_(solved_ids))
    if hide_saved:
        query = query.filter(
            Challenge.id.in_(bookmarked_ids) if bookmarked_ids else Challenge.id.in_([-1])
        )

    challenges = query.order_by(Challenge.created_at.desc()).all()
    categories = [r[0] for r in db.session.query(Challenge.category).distinct().all()]
    blood_positions = _get_blood_positions(current_user.id)

    resp = make_response(render_template(
        'challenges/list.html',
        challenges=challenges,
        categories=categories,
        current_category=category,
        current_difficulty=difficulty,
        current_source=source,
        current_search=safe_search,
        hide_solved=hide_solved,
        hide_saved=hide_saved,
        solved_challenge_ids=solved_ids,
        bookmarked_ids=bookmarked_ids,
        subscribed_ids=subscribed_ids,
        blood_positions=blood_positions,
        show_tour=not current_user.has_seen_tour,
    ))
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def _get_challenge_vote_data(challenge_id, user_id, already_solved):
    """Return (upvotes, downvotes, net_votes, user_vote) for a challenge."""
    net_votes = db.session.query(func.sum(ChallengeVote.value)).filter_by(challenge_id=challenge_id).scalar() or 0
    upvotes = db.session.query(func.count(ChallengeVote.id)).filter_by(challenge_id=challenge_id, value=1).scalar() or 0
    downvotes = db.session.query(func.count(ChallengeVote.id)).filter_by(challenge_id=challenge_id, value=-1).scalar() or 0
    user_vote = None
    if already_solved:
        v = ChallengeVote.query.filter_by(challenge_id=challenge_id, user_id=user_id).first()
        user_vote = v.value if v else None
    return upvotes, downvotes, net_votes, user_vote


def _get_submission_files(challenge):
    """Return submission files for a challenge."""
    submission = ChallengeSubmission.query.filter_by(
        title=challenge.title, author_id=challenge.author_id, status='approved'
    ).first()
    return submission.files if submission else []


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

    submission_files = _get_submission_files(challenge)
    upvotes, downvotes, net_votes, user_vote = _get_challenge_vote_data(
        challenge_id, current_user.id, already_solved
    )
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
        net_votes=net_votes,
        user_vote=user_vote,
        solvers=solvers,
        is_bookmarked=is_bookmarked,
        is_subscribed=is_subscribed,
    )


def _check_flag_correct(challenge, submitted_flag, user_id):
    """Return True if submitted_flag is correct for the challenge."""
    dyn = DynamicFlag.query.filter_by(challenge_id=challenge.id, user_id=user_id).first()
    if dyn:
        return submitted_flag == dyn.flag
    if challenge.is_regex:
        try:
            return bool(re.fullmatch(challenge.flag, submitted_flag))
        except re.error:
            return submitted_flag == challenge.flag
    return submitted_flag == challenge.flag


def _record_correct_solve(challenge, user_id):
    """Persist a correct solve, fire notifications and badge checks."""
    is_first_blood = not UserChallengeSolve.query.filter_by(challenge_id=challenge.id).first()
    db.session.add(UserChallengeSolve(user_id=user_id, challenge_id=challenge.id))
    db.session.add(FlagAttempt(user_id=user_id, challenge_id=challenge.id, correct=True,
                               submitted_flag=None))
    db.session.commit()
    DynamicFlag.query.filter_by(challenge_id=challenge.id, user_id=user_id).delete()
    db.session.commit()
    # Immediately kill the player's running instance on solve
    if challenge.category in ('Web', 'Binary Exploitation'):
        try:
            from app.challenge_runner import stop_server, stop_nc_server
            if challenge.category == 'Web':
                stop_server(challenge.id, user_id)
            else:
                stop_nc_server(challenge.id, user_id)
        except Exception:
            pass
    check_auto_badges(user_id)
    from app.routes.admin import check_milestones_for_user
    check_milestones_for_user(user_id)
    notify_challenge_solve(user_id, challenge)
    notify_challenge_subscribers(user_id, challenge)
    if is_first_blood:
        notify_first_blood(user_id, challenge)


@challenges_bp.route('/challenges/<int:challenge_id>/submit', methods=['POST'])
@login_required
def submit_flag(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    submitted_flag = request.form.get('flag', '').strip()
    solution_file = request.files.get('solution_file') if challenge.category == 'Web Exploitation' else None

    if UserChallengeSolve.query.filter_by(
            user_id=current_user.id, challenge_id=challenge_id).first():
        flash('You have already solved this challenge!', 'info')
        return redirect(url_for('challenges.detail', challenge_id=challenge_id))

    # For Web Exploitation challenges, require solution file
    if challenge.category == 'Web Exploitation':
        if not solution_file or not solution_file.filename:
            flash('Web Exploitation challenges require a solution file (.tar.gz)', 'danger')
            return redirect(url_for('challenges.detail', challenge_id=challenge_id))
        
        if not solution_file.filename.endswith('.tar.gz'):
            flash('Solution file must be a .tar.gz archive.', 'danger')
            return redirect(url_for('challenges.detail', challenge_id=challenge_id))
        
        # Check file size
        solution_data = solution_file.read()
        if len(solution_data) > MAX_SOLUTION_FILE_BYTES:
            flash('Solution file exceeds the 100 MB limit.', 'danger')
            return redirect(url_for('challenges.detail', challenge_id=challenge_id))
        solution_file.seek(0)
    else:
        solution_data = None

    if not submitted_flag.startswith('CSIA{') or not submitted_flag.endswith('}'):
        flash('Invalid flag format. Flags must be in the format CSIA{...}', 'danger')
        return redirect(url_for('challenges.detail', challenge_id=challenge_id))

    if _check_flag_correct(challenge, submitted_flag, current_user.id):
        _record_correct_solve(challenge, current_user.id)
        log_event(actor=current_user.username, action='flag_correct',
                  target=challenge.title, category='challenge')
        flash(f'Correct! You earned {challenge.points} points!', 'success')
    else:
        # Create FlagAttempt record with optional solution file
        flag_attempt = FlagAttempt(
            user_id=current_user.id,
            challenge_id=challenge_id,
            correct=False,
            submitted_flag=submitted_flag
        )
        
        # If solution file was provided, save it
        if solution_data is not None:
            os.makedirs(SOLUTIONS_DIR, exist_ok=True)
            original_name = secure_filename(solution_file.filename)
            stored_name = f'{uuid.uuid4().hex}_{original_name}'
            dest = _safe_join(SOLUTIONS_DIR, stored_name)
            with open(dest, 'wb') as out:
                out.write(solution_data)
            flag_attempt.solution_file_path = dest
            flag_attempt.solution_file_name = original_name
        
        db.session.add(flag_attempt)
        db.session.commit()
        log_event(actor=current_user.username, action='flag_wrong',
                  target=challenge.title, category='challenge')
        flash('Incorrect flag. Try again!', 'danger')

    return redirect(url_for('challenges.detail', challenge_id=challenge_id))


def _parse_vote_value(request_obj):
    """Extract and validate vote value from JSON or form data. Returns int or None."""
    data = request_obj.get_json(silent=True, force=True) or {}
    value = data.get('value') if isinstance(data, dict) else None
    if value is None:
        value = request_obj.form.get('value', type=int, default=0)
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value in (1, -1) else None


def _apply_vote(challenge_id, user_id, value):
    """Upsert or remove a vote. Returns the new vote value (or None if removed)."""
    existing = ChallengeVote.query.filter_by(
        challenge_id=challenge_id, user_id=user_id).first()
    if existing:
        if existing.value == value:
            db.session.delete(existing)
            new_value = None
        else:
            existing.value = value
            new_value = value
    else:
        db.session.add(ChallengeVote(
            challenge_id=challenge_id, user_id=user_id, value=value))
        new_value = value
    db.session.commit()
    return new_value


@challenges_bp.route('/challenges/<int:challenge_id>/vote', methods=['POST'])
@login_required
@csrf.exempt
def vote_challenge(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    if not UserChallengeSolve.query.filter_by(
            user_id=current_user.id, challenge_id=challenge_id).first():
        return jsonify(ok=False, error='Must solve first'), 403

    value = _parse_vote_value(request)
    if value is None:
        return jsonify(ok=False, error='Invalid'), 400

    new_value = _apply_vote(challenge_id, current_user.id, value)
    log_event(actor=current_user.username, action='vote_challenge',
              target=f'{challenge.title} value:{new_value}', category='challenge')
    upvotes = db.session.query(func.count(ChallengeVote.id)).filter_by(
        challenge_id=challenge_id, value=1).scalar() or 0
    downvotes = db.session.query(func.count(ChallengeVote.id)).filter_by(
        challenge_id=challenge_id, value=-1).scalar() or 0
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
@login_required
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
@csrf.exempt
def launch_nc(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    if challenge.category != 'Binary Exploitation':
        return jsonify(ok=False, error='Not a binary exploitation challenge'), 400
    nc = NcChallenge.query.filter_by(challenge_id=challenge_id).first()
    if not nc:
        return jsonify(ok=False, error='No binary attached to this challenge.'), 404
    from app.challenge_runner import start_nc_server
    try:
        port, subdomain, expires_at, dynamic_flag = start_nc_server(challenge_id, current_user.id, nc.binary_path)
        if dynamic_flag:
            _upsert_dynamic_flag(challenge_id, current_user.id, dynamic_flag)
        log_event(actor=current_user.username, action='instance_launch_nc', target=challenge.title, category='challenge')
        return jsonify(ok=True, port=port, host=subdomain, expires_at=expires_at, has_dynamic_flag=bool(dynamic_flag))
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@challenges_bp.route('/challenges/<int:challenge_id>/stop-nc', methods=['POST'])
@login_required
@csrf.exempt
def stop_nc(challenge_id):
    from app.challenge_runner import stop_nc_server
    stop_nc_server(challenge_id, current_user.id)
    return jsonify(ok=True)


@challenges_bp.route('/challenges/<int:challenge_id>/extend-nc', methods=['POST'])
@login_required
@csrf.exempt
def extend_nc(challenge_id):
    from app.challenge_runner import extend_nc_server
    ok, err, new_expires = extend_nc_server(challenge_id, current_user.id)
    if ok:
        return jsonify(ok=True, expires_at=new_expires)
    return jsonify(ok=False, error=err, expires_at=new_expires)


@challenges_bp.route('/challenges/<int:challenge_id>/nc-status')
@login_required
def nc_status(challenge_id):
    Challenge.query.get_or_404(challenge_id)
    from app.challenge_runner import nc_server_status
    st = nc_server_status(challenge_id, current_user.id)
    if st['running']:
        dyn = DynamicFlag.query.filter_by(challenge_id=challenge_id, user_id=current_user.id).first()
        st['has_dynamic_flag'] = bool(dyn)
        st.pop('dynamic_flag', None)
    return jsonify(st)


@challenges_bp.route('/challenges/<int:challenge_id>/launch', methods=['POST'])
@login_required
@csrf.exempt
def launch_web(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    if challenge.category != 'Web':
        return jsonify(ok=False, error='Not a web challenge'), 400
    wc = WebChallenge.query.filter_by(challenge_id=challenge_id).first()
    if not wc:
        return jsonify(ok=False, error='No web archive attached to this challenge.'), 404
    from app.challenge_runner import start_server
    try:
        port, subdomain, expires_at, dynamic_flag = start_server(challenge_id, current_user.id, wc.archive_path)
        if dynamic_flag:
            _upsert_dynamic_flag(challenge_id, current_user.id, dynamic_flag)
        log_event(actor=current_user.username, action='instance_launch_web', target=challenge.title, category='challenge')
        return jsonify(ok=True, port=port, url=f'http://{subdomain}:{port}/', expires_at=expires_at,
                       has_dynamic_flag=bool(dynamic_flag))
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@challenges_bp.route('/challenges/<int:challenge_id>/stop-web', methods=['POST'])
@login_required
@csrf.exempt
def stop_web(challenge_id):
    from app.challenge_runner import stop_server
    stop_server(challenge_id, current_user.id)
    return jsonify(ok=True)


@challenges_bp.route('/challenges/<int:challenge_id>/extend-web', methods=['POST'])
@login_required
@csrf.exempt
def extend_web(challenge_id):
    from app.challenge_runner import extend_server
    ok, err, new_expires = extend_server(challenge_id, current_user.id)
    if ok:
        return jsonify(ok=True, expires_at=new_expires)
    return jsonify(ok=False, error=err, expires_at=new_expires)


@challenges_bp.route('/challenges/<int:challenge_id>/web-status')
@login_required
def web_status(challenge_id):
    Challenge.query.get_or_404(challenge_id)
    from app.challenge_runner import server_status
    st = server_status(challenge_id, current_user.id)
    if st['running']:
        st['url'] = f"http://{st['subdomain']}:{st['port']}/"
        dyn = DynamicFlag.query.filter_by(challenge_id=challenge_id, user_id=current_user.id).first()
        st['has_dynamic_flag'] = bool(dyn)
        st.pop('dynamic_flag', None)
    return jsonify(st)


@challenges_bp.route('/challenges/<int:challenge_id>/bookmark', methods=['POST'])
@login_required
@csrf.exempt
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
@csrf.exempt
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


@challenges_bp.route('/challenges/<int:attempt_id>/solution', methods=['GET'])
@login_required
def download_solution(attempt_id):
    """Download a solution file from a challenge attempt (admin or uploader only)."""
    from flask import send_file
    
    attempt = FlagAttempt.query.get_or_404(attempt_id)
    
    # Only allow admin or the user who submitted it
    if not current_user.is_admin and attempt.user_id != current_user.id:
        abort(403)
    
    # Check if solution file exists
    if not attempt.solution_file_path:
        abort(404)
    
    try:
        real_path = _safe_join(os.path.abspath(SOLUTIONS_DIR), os.path.basename(attempt.solution_file_path))
    except ValueError:
        abort(400)
    
    if not os.path.exists(real_path):
        abort(404)
    
    return send_file(
        real_path,
        as_attachment=True,
        download_name=attempt.solution_file_name or f'solution_{attempt_id}.tar.gz'
    )
