from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from app import db
from app.models import User, MailMessage, UserNotification

mail_bp = Blueprint('mail', __name__, url_prefix='/mail')


@mail_bp.route('/')
@login_required
def inbox():
    folder = request.args.get('folder', 'inbox')
    if folder == 'sent':
        messages = MailMessage.query.filter_by(
            sender_id=current_user.id, is_deleted_by_sender=False
        ).order_by(MailMessage.created_at.desc()).all()
    else:
        messages = MailMessage.query.filter_by(
            recipient_id=current_user.id, is_deleted_by_recipient=False
        ).order_by(MailMessage.created_at.desc()).all()
    return render_template('mail/inbox.html', messages=messages, folder=folder)


@mail_bp.route('/compose', methods=['GET', 'POST'])
@login_required
def compose():
    to_user = request.args.get('to', '')
    if request.method == 'POST':
        recipient_username = request.form.get('to', '').strip()
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()

        if not recipient_username or not subject or not body:
            flash('All fields are required.', 'danger')
            return redirect(url_for('mail.compose', to=recipient_username))

        recipient = User.query.filter_by(username=recipient_username).first()
        if not recipient:
            flash(f'User "{recipient_username}" not found.', 'danger')
            return redirect(url_for('mail.compose'))
        if recipient.id == current_user.id:
            flash('You cannot message yourself.', 'danger')
            return redirect(url_for('mail.compose'))

        msg = MailMessage(
            sender_id=current_user.id,
            recipient_id=recipient.id,
            subject=subject,
            body=body,
        )
        db.session.add(msg)
        # Notify recipient
        db.session.add(UserNotification(
            user_id=recipient.id,
            title=f'New message from {current_user.username}',
            body=f'Subject: {subject}',
            category='system',
            link='/mail/',
        ))
        db.session.commit()
        flash('Message sent.', 'success')
        return redirect(url_for('mail.inbox', folder='sent'))

    return render_template('mail/compose.html', to_user=to_user)


@mail_bp.route('/message/<int:msg_id>')
@login_required
def view_message(msg_id):
    msg = MailMessage.query.get_or_404(msg_id)
    if msg.recipient_id != current_user.id and msg.sender_id != current_user.id:
        abort(403)
    if msg.recipient_id == current_user.id and not msg.is_read:
        msg.is_read = True
        db.session.commit()
    return render_template('mail/view.html', msg=msg)


@mail_bp.route('/message/<int:msg_id>/delete', methods=['POST'])
@login_required
def delete_message(msg_id):
    msg = MailMessage.query.get_or_404(msg_id)
    if msg.recipient_id == current_user.id:
        msg.is_deleted_by_recipient = True
    elif msg.sender_id == current_user.id:
        msg.is_deleted_by_sender = True
    else:
        abort(403)
    db.session.commit()
    return redirect(url_for('mail.inbox'))


@mail_bp.route('/api/unread-count')
@login_required
def unread_count():
    count = MailMessage.query.filter_by(
        recipient_id=current_user.id, is_read=False, is_deleted_by_recipient=False
    ).count()
    return jsonify(count=count)
