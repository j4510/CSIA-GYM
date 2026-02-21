"""
Challenges Routes Blueprint

Handles challenge listing, viewing, and flag submission.

TO EXTEND THIS SECTION:
- Add filtering by category/difficulty
- Add search functionality
- Add hints system
- Add challenge files download
- Add first blood/solve time tracking
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import Challenge, UserChallengeSolve

# Create blueprint
challenges_bp = Blueprint('challenges', __name__, template_folder='../templates')


@challenges_bp.route('/challenges')
@login_required  # Requires user to be logged in
def list():
    """
    Display all challenges.
    
    TO EXTEND:
    - Add pagination for many challenges
    - Add filtering: ?category=web or ?difficulty=easy
    - Add sorting: ?sort=newest, ?sort=points
    - Add search: ?q=sql
    """
    
    # Get all challenges ordered by creation date
    challenges = Challenge.query.order_by(Challenge.created_at.desc()).all()
    
    # TO ADD: Filtering example
    # category = request.args.get('category')
    # if category:
    #     challenges = challenges.filter_by(category=category).all()
    
    # TO ADD: Search example
    # search_query = request.args.get('q')
    # if search_query:
    #     challenges = Challenge.query.filter(
    #         Challenge.title.contains(search_query) | 
    #         Challenge.description.contains(search_query)
    #     ).all()
    
    return render_template('challenges/list.html', challenges=challenges)


@challenges_bp.route('/challenges/<int:challenge_id>')
@login_required
def detail(challenge_id):
    """
    Display single challenge details.
    
    Shows:
    - Challenge description
    - Flag submission form
    - Solve count
    - List of solvers (optional)
    
    TO EXTEND:
    - Add downloadable files
    - Add hints that cost points
    - Add attempt tracking
    """
    
    # Get challenge or return 404 if not found
    challenge = Challenge.query.get_or_404(challenge_id)
    
    # Check if current user already solved this
    already_solved = UserChallengeSolve.query.filter_by(
        user_id=current_user.id,
        challenge_id=challenge_id
    ).first() is not None
    
    # Get list of users who solved this (optional)
    # solvers = [solve.user for solve in challenge.solves]
    
    return render_template(
        'challenges/detail.html', 
        challenge=challenge, 
        already_solved=already_solved
    )


@challenges_bp.route('/challenges/<int:challenge_id>/submit', methods=['POST'])
@login_required
def submit_flag(challenge_id):
    """
    Handle flag submission for a challenge.
    
    Validates the submitted flag and awards points if correct.
    
    TO EXTEND:
    - Add rate limiting (max attempts per minute)
    - Add wrong attempt tracking
    - Add dynamic scoring (points decrease with more solves)
    - Add first blood bonus
    """
    
    challenge = Challenge.query.get_or_404(challenge_id)
    submitted_flag = request.form.get('flag', '').strip()
    
    # Check if already solved
    already_solved = UserChallengeSolve.query.filter_by(
        user_id=current_user.id,
        challenge_id=challenge_id
    ).first()
    
    if already_solved:
        flash('You have already solved this challenge!', 'info')
        return redirect(url_for('challenges.detail', challenge_id=challenge_id))
    
    # Validate flag
    if submitted_flag == challenge.flag:
        # Correct flag - record solve
        solve = UserChallengeSolve(user_id=current_user.id, challenge_id=challenge_id)
        db.session.add(solve)
        db.session.commit()
        
        flash(f'Correct! You earned {challenge.points} points!', 'success')
        
        # TO ADD: Check if this is first blood
        # if challenge.solve_count() == 1:
        #     flash('First Blood! 🩸', 'success')
    else:
        # Wrong flag
        flash('Incorrect flag. Try again!', 'danger')
        
        # TO ADD: Track wrong attempts
        # WrongAttempt.create(user_id=current_user.id, challenge_id=challenge_id)
    
    return redirect(url_for('challenges.detail', challenge_id=challenge_id))


@challenges_bp.route('/scoreboard')
@login_required
def scoreboard():
    """
    Display leaderboard of all users sorted by score.
    
    TO EXTEND:
    - Add team scores
    - Add filtering by time period
    - Add graphs/charts
    - Add solve timeline
    """
    
    from app.models import User
    
    # Get all users
    users = User.query.all()
    
    # Sort by score (calculated from solved challenges)
    leaderboard = sorted(users, key=lambda u: u.get_score(), reverse=True)
    
    # TO ADD: More efficient database query
    # This current approach loads all users into memory
    # For large scale, use SQL aggregation instead
    
    return render_template('challenges/scoreboard.html', leaderboard=leaderboard)


# ========================================
# TO ADD: Additional challenge features
# ========================================

# File download example:
# @challenges_bp.route('/challenges/<int:challenge_id>/files/<filename>')
# @login_required
# def download_file(challenge_id, filename):
#     from flask import send_from_directory
#     challenge = Challenge.query.get_or_404(challenge_id)
#     return send_from_directory('uploads/challenges', filename)

# Hint unlock example:
# @challenges_bp.route('/challenges/<int:challenge_id>/hints/<int:hint_id>')
# @login_required
# def unlock_hint(challenge_id, hint_id):
#     hint = Hint.query.get_or_404(hint_id)
#     # Deduct points from user
#     # Mark hint as unlocked for user
#     pass
