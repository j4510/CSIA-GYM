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
from app import db
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


@submissions_bp.route('/submit-challenge', methods=['GET', 'POST'])
@login_required
def new():
    used_bytes = _pending_usage(current_user.id)

    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category    = request.form.get('category')
        difficulty  = request.form.get('difficulty')
        flag        = request.form.get('flag', '').strip()
        points      = request.form.get('points', type=int)

        if not all([title, description, category, difficulty, flag, points]):
            flash('All fields are required', 'danger')
            return redirect(url_for('submissions.new'))

        if points < 0:
            flash('Points must be positive', 'danger')
            return redirect(url_for('submissions.new'))

        is_regex = 'is_regex' in request.form

        if not flag.startswith('CSIA{') or not flag.endswith('}'):
            flash('Flag must be in the format CSIA{...}', 'danger')
            return redirect(url_for('submissions.new'))

        # ── Web archive validation ────────────────────────────────────────
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

        # ── RE binary/archive validation ──────────────────────────────────
        nc_binary = request.files.get('nc_binary')
        nc_binary_data = None
        if category == 'Reverse Engineering' and nc_binary and nc_binary.filename:
            nc_binary_data = nc_binary.read()
            if len(nc_binary_data) > MAX_NC_BINARY_BYTES:
                flash('RE challenge file exceeds the 100 MB limit.', 'danger')
                return redirect(url_for('submissions.new'))
            nc_binary.seek(0)
        elif category == 'Reverse Engineering':
            flash('Reverse Engineering challenges require an executable or .tar.gz archive.', 'danger')
            return redirect(url_for('submissions.new'))

        uploaded_files = request.files.getlist('attachments')
        valid_files = [f for f in uploaded_files if f and f.filename]

        new_bytes = sum(len(f.read()) for f in valid_files)
        for f in valid_files:
            f.seek(0)  # reset after reading for size

        if new_bytes > MAX_FILE_BYTES:
            flash(
                f'Total upload size exceeds 250 MB. Consider using Google Drive, '
                f'OneDrive, Dropbox, or another file-sharing service and linking it '
                f'in your description.',
                'warning'
            )
            return redirect(url_for('submissions.new'))

        if used_bytes + new_bytes > USER_QUOTA_BYTES:
            remaining_mb = (USER_QUOTA_BYTES - used_bytes) / (1024 * 1024)
            flash(
                f'You only have {remaining_mb:.1f} MB of pending quota left. '
                f'Wait for your existing submissions to be reviewed, or use '
                f'Google Drive / OneDrive / Dropbox for larger files.',
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
        db.session.flush()  # get submission.id before commit

        os.makedirs(SUBMISSION_FILES_DIR, exist_ok=True)
        for f in valid_files:
            original_name = secure_filename(f.filename)
            stored_name   = f'{uuid.uuid4().hex}_{original_name}'
            dest          = os.path.join(SUBMISSION_FILES_DIR, stored_name)
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

        # Save web archive if this is a Web challenge
        if web_archive_data is not None:
            os.makedirs(WEB_CHALLENGES_DIR, exist_ok=True)
            archive_name = f'web_{submission.id}_{uuid.uuid4().hex}.tar.gz'
            archive_path = os.path.join(WEB_CHALLENGES_DIR, archive_name)
            with open(archive_path, 'wb') as out:
                out.write(web_archive_data)
            # Store path on submission for admin to pick up on approval
            submission.web_archive_path = archive_path

        # Save RE binary if this is a Reverse Engineering challenge
        if nc_binary_data is not None:
            os.makedirs(NC_CHALLENGES_DIR, exist_ok=True)
            binary_name = f'nc_{submission.id}_{uuid.uuid4().hex}_{secure_filename(nc_binary.filename)}'
            binary_path = os.path.join(NC_CHALLENGES_DIR, binary_name)
            with open(binary_path, 'wb') as out:
                out.write(nc_binary_data)
            submission.nc_binary_path = binary_path

        db.session.commit()
        log_event(actor=current_user.username, action='challenge_submit', target=f'{title} [{category}]', category='submission')
        flash('Challenge submitted for review! Admins will review it soon.', 'success')
        return redirect(url_for('submissions.my_submissions'))

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
    """Download a file attached to a submission (author or admin only)."""
    sf = SubmissionFile.query.get_or_404(file_id)
    submission = ChallengeSubmission.query.get_or_404(sf.submission_id)

    if sf.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    return send_from_directory(
        os.path.abspath(SUBMISSION_FILES_DIR),
        sf.stored_name,
        as_attachment=True,
        download_name=sf.original_name,
    )
