from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')


@notifications_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    claims = get_jwt()
    db = get_db()
    limit = request.args.get('limit', '20', type=int)
    unread_only = request.args.get('unread', '0') == '1'
    query = 'SELECT * FROM notifications WHERE user_id = ?'
    params = [claims['id']]
    if unread_only:
        query += ' AND is_read = 0'
    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    notifs = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(n) for n in notifs])


@notifications_bp.route('/api/unread-count', methods=['GET'])
@login_required
def api_unread_count():
    claims = get_jwt()
    db = get_db()
    count = db.execute(
        'SELECT COUNT(*) as c FROM notifications WHERE user_id = ? AND is_read = 0',
        (claims['id'],)).fetchone()['c']
    db.close()
    return jsonify({'count': count})


@notifications_bp.route('/api/<int:id>/read', methods=['PUT'])
@login_required
def api_mark_read(id):
    claims = get_jwt()
    db = get_db()
    db.execute('UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?',
               (id, claims['id']))
    db.commit()
    db.close()
    return jsonify({'message': 'Marked as read'})


@notifications_bp.route('/api/read-all', methods=['PUT'])
@login_required
def api_mark_all_read():
    claims = get_jwt()
    db = get_db()
    db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0',
               (claims['id'],))
    db.commit()
    db.close()
    return jsonify({'message': 'All marked as read'})


@notifications_bp.route('/api/<int:id>', methods=['DELETE'])
@login_required
def api_delete(id):
    claims = get_jwt()
    db = get_db()
    db.execute('DELETE FROM notifications WHERE id = ? AND user_id = ?', (id, claims['id']))
    db.commit()
    db.close()
    return jsonify({'message': 'Deleted'})


def notify(db, user_id, title, message, ntype='info', reference_url=None):
    db.execute(
        'INSERT INTO notifications (user_id, title, message, type, reference_url) VALUES (?,?,?,?,?)',
        (user_id, title, message, ntype, reference_url))
    db.commit()


def notify_all(db, title, message, ntype='info', reference_url=None, exclude_id=None):
    query = 'SELECT id FROM users WHERE is_active = 1'
    params = []
    if exclude_id:
        query += ' AND id != ?'
        params.append(exclude_id)
    users = db.execute(query, params).fetchall()
    for u in users:
        db.execute(
            'INSERT INTO notifications (user_id, title, message, type, reference_url) VALUES (?,?,?,?,?)',
            (u['id'], title, message, ntype, reference_url))
    db.commit()


def notify_role(db, role, title, message, ntype='info', reference_url=None):
    users = db.execute(
        'SELECT id FROM users WHERE role = ? AND is_active = 1', (role,)).fetchall()
    for u in users:
        db.execute(
            'INSERT INTO notifications (user_id, title, message, type, reference_url) VALUES (?,?,?,?,?)',
            (u['id'], title, message, ntype, reference_url))
    db.commit()
