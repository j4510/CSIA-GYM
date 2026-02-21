"""
Submissions Routes Blueprint

Allows users to submit their own challenges for admin approval.

TO EXTEND THIS SECTION:
- Add file uploads for challenge files
- Add admin approval interface
- Add email notifications on approval/rejection
- Add edit functionality for pending submissions
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import ChallengeSubmission

# Create blueprint
submissions_bp = Blueprint('submissions', __name__, template_folder='../templates')


@submissions_bp.route('/submit-challenge', methods=['GET', 'POST'])
@login_required
def new():
    """
    Create a new challenge submission.
    
    GET: Show submission form
    POST: Process submission and save to database
    
    TO EXTEND:
    - Add file upload for challenge files
    - Add rich text editor for description
    - Add preview before submission
    - Add draft save functionality
    """
    
    if request.method == 'POST':
        # Get form data
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category')
        difficulty = request.form.get('difficulty')
        flag = request.form.get('flag', '').strip()
        points = request.form.get('points', type=int)
        
        # Validation
        if not all([title, description, category, difficulty, flag, points]):
            flash('All fields are required', 'danger')
            return redirect(url_for('submissions.new'))
        
        if points < 0:
            flash('Points must be positive', 'danger')
            return redirect(url_for('submissions.new'))
        
        # TO ADD: Additional validation
        # - Check flag format (e.g., must start with FLAG{})
        # - Validate points range (e.g., 50-500)
        # - Check description length
        
        # Create submission
        submission = ChallengeSubmission(
            title=title,
            description=description,
            category=category,
            difficulty=difficulty,
            flag=flag,
            points=points,
            author_id=current_user.id
        )
        
        db.session.add(submission)
        db.session.commit()
        
        flash('Challenge submitted for review! Admins will review it soon.', 'success')
        return redirect(url_for('submissions.my_submissions'))
    
    # GET - show form
    return render_template('submissions/new.html')


@submissions_bp.route('/my-submissions')
@login_required
def my_submissions():
    """
    View all submissions by current user.
    
    Shows submission status: pending, approved, or rejected.
    
    TO EXTEND:
    - Add edit functionality for pending submissions
    - Add delete functionality
    - Show admin feedback/notes
    """
    
    # Get user's submissions
    submissions = ChallengeSubmission.query.filter_by(
        author_id=current_user.id
    ).order_by(
        ChallengeSubmission.created_at.desc()
    ).all()
    
    return render_template('submissions/list.html', submissions=submissions)


# ========================================
# TO ADD: Admin approval routes
# These should be protected with admin-only decorator
# ========================================

# View all pending submissions (admin only):
# @submissions_bp.route('/admin/submissions')
# @login_required
# @admin_required  # Create this decorator
# def admin_list():
#     pending = ChallengeSubmission.query.filter_by(status='pending').all()
#     return render_template('submissions/admin_list.html', submissions=pending)

# Approve submission (admin only):
# @submissions_bp.route('/admin/submissions/<int:id>/approve', methods=['POST'])
# @login_required
# @admin_required
# def approve(id):
#     submission = ChallengeSubmission.query.get_or_404(id)
#     submission.status = 'approved'
#     
#     # Optionally create Challenge from submission
#     challenge = Challenge(
#         title=submission.title,
#         description=submission.description,
#         category=submission.category,
#         difficulty=submission.difficulty,
#         flag=submission.flag,
#         points=submission.points,
#         author_id=submission.author_id
#     )
#     db.session.add(challenge)
#     db.session.commit()
#     
#     flash('Submission approved and challenge created!', 'success')
#     return redirect(url_for('submissions.admin_list'))

# Reject submission (admin only):
# @submissions_bp.route('/admin/submissions/<int:id>/reject', methods=['POST'])
# @login_required
# @admin_required
# def reject(id):
#     submission = ChallengeSubmission.query.get_or_404(id)
#     submission.status = 'rejected'
#     submission.admin_notes = request.form.get('notes')
#     db.session.commit()
#     flash('Submission rejected', 'info')
#     return redirect(url_for('submissions.admin_list'))
