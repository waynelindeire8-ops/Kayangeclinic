from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required, log_audit

messages_bp = Blueprint('messages', __name__, url_prefix='/messages')


@messages_bp.route('/', strict_slashes=False)
@login_required
def inbox_page():
    return render_template('messages/inbox.html')


@messages_bp.route('/sent', strict_slashes=False)
@login_required
def sent_page():
    return render_template('messages/sent.html')


@messages_bp.route('/compose', strict_slashes=False)
@login_required
def compose_page():
    return render_template('messages/compose.html')


@messages_bp.route('/api/inbox', methods=['GET'])
@login_required
def api_inbox():
    current_user = get_jwt()
    db = get_db()
    msgs = db.execute(
        '''SELECT m.*, u.first_name as s_first, u.last_name as s_last, u.role as s_role
           FROM messages m LEFT JOIN users u ON m.sender_id = u.id
           WHERE m.receiver_id = ? AND m.receiver_deleted = 0
           ORDER BY m.sent_at DESC''', (current_user['id'],)).fetchall()
    db.close()
    return jsonify([dict(m) for m in msgs])


@messages_bp.route('/api/sent', methods=['GET'])
@login_required
def api_sent():
    current_user = get_jwt()
    db = get_db()
    msgs = db.execute(
        '''SELECT m.*, u.first_name as r_first, u.last_name as r_last, u.role as r_role
           FROM messages m LEFT JOIN users u ON m.receiver_id = u.id
           WHERE m.sender_id = ? AND m.sender_deleted = 0
           ORDER BY m.sent_at DESC''', (current_user['id'],)).fetchall()
    db.close()
    return jsonify([dict(m) for m in msgs])


@messages_bp.route('/api/unread-count', methods=['GET'])
@login_required
def api_unread_count():
    current_user = get_jwt()
    db = get_db()
    count = db.execute(
        'SELECT COUNT(*) as c FROM messages WHERE receiver_id = ? AND is_read = 0 AND receiver_deleted = 0',
        (current_user['id'],)).fetchone()
    db.close()
    return jsonify({'count': count['c']})


@messages_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    current_user = get_jwt()
    db = get_db()
    msg = db.execute(
        '''SELECT m.*, s.first_name as s_first, s.last_name as s_last, s.role as s_role,
                  r.first_name as r_first, r.last_name as r_last, r.role as r_role
           FROM messages m
           LEFT JOIN users s ON m.sender_id = s.id
           LEFT JOIN users r ON m.receiver_id = r.id
           WHERE m.id = ? AND (m.sender_id = ? OR m.receiver_id = ?)''',
        (id, current_user['id'], current_user['id'])).fetchone()
    if not msg:
        db.close()
        return jsonify({'error': 'Message not found'}), 404
    msg = dict(msg)
    if msg['receiver_id'] == current_user['id'] and not msg['is_read']:
        db.execute('UPDATE messages SET is_read = 1, read_at = CURRENT_TIMESTAMP WHERE id = ?', (id,))
        db.commit()
        msg['is_read'] = 1
    db.close()
    return jsonify(msg)


@messages_bp.route('/api', methods=['POST'])
@login_required
def api_send():
    current_user = get_jwt()
    data = request.json
    receiver_id = data.get('receiver_id')
    subject = data.get('subject', '').strip()
    body = data.get('body', '').strip()

    if not receiver_id:
        return jsonify({'error': 'Recipient is required'}), 400
    if not subject:
        return jsonify({'error': 'Subject is required'}), 400
    if not body:
        return jsonify({'error': 'Message body is required'}), 400

    db = get_db()
    receiver = db.execute('SELECT id FROM users WHERE id = ? AND is_active = 1', (receiver_id,)).fetchone()
    if not receiver:
        db.close()
        return jsonify({'error': 'Recipient not found or inactive'}), 404

    cursor = db.execute(
        'INSERT INTO messages (sender_id, receiver_id, subject, body) VALUES (?, ?, ?, ?)',
        (current_user['id'], receiver_id, subject, body)
    )
    db.commit()
    from app.routes.notifications import notify
    sender_name = current_user['first_name'] + ' ' + current_user['last_name']
    notify(db, receiver_id, 'New Message', f'{sender_name}: {subject}', 'message',
           f'/messages')
    log_audit(current_user['id'], current_user['username'], 'send_message', 'message', cursor.lastrowid,
              f'Sent message to user {receiver_id}', request.remote_addr)
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201


@messages_bp.route('/api/<int:id>/delete', methods=['PUT'])
@login_required
def api_delete(id):
    current_user = get_jwt()
    db = get_db()
    msg = db.execute('SELECT * FROM messages WHERE id = ?', (id,)).fetchone()
    if not msg:
        db.close()
        return jsonify({'error': 'Message not found'}), 404

    if msg['sender_id'] == current_user['id']:
        db.execute('UPDATE messages SET sender_deleted = 1 WHERE id = ?', (id,))
    elif msg['receiver_id'] == current_user['id']:
        db.execute('UPDATE messages SET receiver_deleted = 1 WHERE id = ?', (id,))
    else:
        db.close()
        return jsonify({'error': 'Unauthorized'}), 403

    if msg['sender_deleted'] or msg['receiver_deleted']:
        db.execute('DELETE FROM messages WHERE sender_deleted = 1 AND receiver_deleted = 1 AND id = ?', (id,))

    db.commit()
    db.close()
    return jsonify({'message': 'Message deleted'})
