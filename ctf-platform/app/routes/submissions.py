"""
Submissions Routes Blueprint

Allows users to submit their own challenges for admin approval.
Description uses Quill in Markdown mode.
File attachments are stored per-submission; each user has a 250 MB
pending-file quota that frees up when submissions are approved.
"""

import os
import uuid
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, send_from_directory, abort)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError
from app import db, csrf
from app.models import ChallengeSubmission, SubmissionFile
from app.routes.admin import log_event

submissions_bp = Blueprint('submissions', __name__, template_folder='../templates')

SUBMISSION_FILES_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'instance', 'submission_files'
)
WEB_CHALLENGES_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'instance', 'web_challenges'
)
NC_CHALLENGES_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'instance', 'nc_challenges'
)
USER_QUOTA_BYTES = 250 * 1024 * 1024   # 250 MB
MAX_FILE_BYTES   = 250 * 1024 * 1024   # single file hard cap
MAX_WEB_ARCHIVE_BYTES = 100 * 1024 * 1024  # 100 MB cap for web archives
MAX_NC_BINARY_BYTES   = 100 * 1024 * 1024  # 100 MB cap for RE archives/binaries


def _pending_usage(user_id: int) -> int:
    """Total bytes of files belonging to pending submissions for this user."""
    rows = (
        db.session.query(db.func.sum(SubmissionFile.file_size))
        .join(ChallengeSubmission, SubmissionFile.submission_id == ChallengeSubmission.id)
        .filter(
            SubmissionFile.user_id == user_id,
            ChallengeSubmission.status == 'pending',
        )
        .scalar()
    )
    return rows or 0


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


# amazonq-ignore-next-line
@submissions_bp.route('/submit-challenge', methods=['GET', 'POST'])
@login_required
@csrf.exempt
def new():
    # Validate CSRF token on every POST unconditionally
    if request.method == 'POST':
        try:
            validate_csrf(request.form.get('csrf_token'))
        except ValidationError:
            abort(403)
        used_bytes = _pending_usage(current_user.id)
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category    = request.form.get('category')
        difficulty  = request.form.get('difficulty')
        flag        = request.form.get('flag', '').strip()
        points      = request.form.get('points', type=int)

        if not all([title, description, category, difficulty, flag, points]):
            flash('All fields are required', 'danger')
            return redirect(url_for('submissions.new'))

        if points is None or points < 0:
            flash('Points must be positive', 'danger')
            return redirect(url_for('submissions.new'))

        is_regex = 'is_regex' in request.form

        if not flag.startswith('CSIA{') or not flag.endswith('}'):
            flash('Flag must be in the format CSIA{...}', 'danger')
            return redirect(url_for('submissions.new'))

        web_archive = request.files.get('web_archive')
        web_archive_data = None
        if category == 'Web' and web_archive and web_archive.filename:
            if not web_archive.filename.endswith('.tar.gz'):
                flash('Web challenge archive must be a .tar.gz file.', 'danger')
                return redirect(url_for('submissions.new'))
            web_archive_data = web_archive.read()
            if len(web_archive_data) > MAX_WEB_ARCHIVE_BYTES:
                flash('Web archive exceeds the 100 MB limit.', 'danger')
                return redirect(url_for('submissions.new'))
            web_archive.seek(0)
        elif category == 'Web':
            flash('Web Exploitation challenges require a .tar.gz archive.', 'danger')
            return redirect(url_for('submissions.new'))

        nc_binary = request.files.get('nc_binary')
        nc_binary_data = None
        if category == 'Binary Exploitation' and nc_binary and nc_binary.filename:
            nc_binary_data = nc_binary.read()
            if len(nc_binary_data) > MAX_NC_BINARY_BYTES:
                flash('Binary Exploitation challenge file exceeds the 100 MB limit.', 'danger')
                return redirect(url_for('submissions.new'))
            nc_binary.seek(0)
        elif category == 'Binary Exploitation':
            flash('Binary Exploitation challenges require an executable or .tar.gz archive.', 'danger')
            return redirect(url_for('submissions.new'))

        uploaded_files = request.files.getlist('attachments')
        valid_files = [f for f in uploaded_files if f and f.filename]

        new_bytes = sum(len(f.read()) for f in valid_files)
        for f in valid_files:
            f.seek(0)

        if new_bytes > MAX_FILE_BYTES:
            flash(
                'Total upload size exceeds 250 MB. Consider using Google Drive, '
                'OneDrive, Dropbox, or another file-sharing service and linking it '
                'in your description.',
                'warning'
            )
            return redirect(url_for('submissions.new'))

        if used_bytes + new_bytes > USER_QUOTA_BYTES:
            remaining_mb = (USER_QUOTA_BYTES - used_bytes) / (1024 * 1024)
            flash(
                f'You only have {remaining_mb:.1f} MB of pending quota left. '
                'Wait for your existing submissions to be reviewed, or use '
                'Google Drive / OneDrive / Dropbox for larger files.',
                'warning'
            )
            return redirect(url_for('submissions.new'))

        submission = ChallengeSubmission(
            title=title,
            description=description,
            category=category,
            difficulty=difficulty,
            flag=flag,
            is_regex=is_regex,
            points=points,
            author_id=current_user.id,
        )
        db.session.add(submission)
        db.session.flush()

        os.makedirs(SUBMISSION_FILES_DIR, exist_ok=True)
        for f in valid_files:
            original_name = secure_filename(f.filename)
            stored_name   = f'{uuid.uuid4().hex}_{original_name}'
            dest          = _safe_join(SUBMISSION_FILES_DIR, stored_name)
            data          = f.read()
            with open(dest, 'wb') as out:
                out.write(data)
            db.session.add(SubmissionFile(
                submission_id=submission.id,
                user_id=current_user.id,
                original_name=original_name,
                stored_name=stored_name,
                file_size=len(data),
            ))

        if web_archive_data is not None:
            os.makedirs(WEB_CHALLENGES_DIR, exist_ok=True)
            real_web_dir = os.path.realpath(WEB_CHALLENGES_DIR)
            archive_name = uuid.uuid4().hex + '.tar.gz'
            archive_path = os.path.realpath(real_web_dir + os.sep + archive_name)
            if not archive_path.startswith(real_web_dir + os.sep):
                abort(400)
            with open(archive_path, 'wb') as out:
                out.write(web_archive_data)
            submission.web_archive_path = archive_path

        if nc_binary_data is not None:
            os.makedirs(NC_CHALLENGES_DIR, exist_ok=True)
            real_nc_dir = os.path.realpath(NC_CHALLENGES_DIR)
            binary_name = uuid.uuid4().hex + '.bin'
            binary_path = os.path.realpath(real_nc_dir + os.sep + binary_name)
            if not binary_path.startswith(real_nc_dir + os.sep):
                abort(400)
            with open(binary_path, 'wb') as out:
                out.write(nc_binary_data)
            submission.nc_binary_path = binary_path

        db.session.commit()
        log_event(actor=current_user.username, action='challenge_submit', target=f'{title} [{category}]', category='submission')
        flash('Challenge submitted for review! Admins will review it soon.', 'success')
        return redirect(url_for('submissions.my_submissions'))

    used_bytes = _pending_usage(current_user.id)
    return render_template(
        'submissions/new.html',
        used_bytes=used_bytes,
        quota_bytes=USER_QUOTA_BYTES,
    )


@submissions_bp.route('/my-submissions')
@login_required
def my_submissions():
    submissions = ChallengeSubmission.query.filter_by(
        author_id=current_user.id
    ).order_by(ChallengeSubmission.created_at.desc()).all()
    return render_template('submissions/list.html', submissions=submissions)


@submissions_bp.route('/submission-file/<int:file_id>')
@login_required
def download_file(file_id):
    """Download a file attached to a submission.
    Access: the file's author, any admin, or any authenticated user
    if the submission has been approved (file is public on the challenge).
    """
    sf = SubmissionFile.query.get_or_404(file_id)
    submission = ChallengeSubmission.query.get_or_404(sf.submission_id)

    is_owner = sf.user_id == current_user.id
    is_approved = submission.status == 'approved'
    if not is_owner and not current_user.is_admin and not is_approved:
        abort(403)

    try:
        safe_path = _safe_join(os.path.abspath(SUBMISSION_FILES_DIR), sf.stored_name)
    except ValueError:
        abort(400)

    return send_from_directory(
        os.path.abspath(SUBMISSION_FILES_DIR),
        os.path.basename(safe_path),
        as_attachment=True,
        download_name=sf.original_name,
    )
