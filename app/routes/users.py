from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from werkzeug.security import generate_password_hash
from app.database import get_db
from app.auth import login_required, role_required, log_audit, ROLE_HIERARCHY

users_bp = Blueprint('users', __name__, url_prefix='/users')


@users_bp.route('/', strict_slashes=False)
@login_required
@role_required('admin')
def users_page():
    return render_template('users/list.html')


@users_bp.route('/api', methods=['GET'])
@login_required
@role_required('admin')
def api_list():
    db = get_db()
    users = db.execute(
        '''SELECT id, username, role, first_name, last_name, email, phone, is_active, created_at, updated_at
           FROM users ORDER BY role, first_name'''
    ).fetchall()
    db.close()
    return jsonify([dict(u) for u in users])


@users_bp.route('/api/<int:id>', methods=['GET'])
@login_required
@role_required('admin')
def api_get(id):
    db = get_db()
    user = db.execute(
        'SELECT id, username, role, first_name, last_name, email, phone, is_active, created_at FROM users WHERE id = ?',
        (id,)
    ).fetchone()
    db.close()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(dict(user))


@users_bp.route('/api', methods=['POST'])
@login_required
@role_required('admin')
def api_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()

    existing = db.execute('SELECT id FROM users WHERE username = ?', (data['username'],)).fetchone()
    if existing:
        db.close()
        return jsonify({'error': 'Username already exists'}), 400

    password = data.get('password', 'changeme123')
    cursor = db.execute(
        '''INSERT INTO users (username, password_hash, role, first_name, last_name, email, phone, department_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (data['username'], generate_password_hash(password), data['role'],
         data['first_name'], data['last_name'], data.get('email'), data.get('phone'), data.get('department_id'))
    )
    new_id = cursor.lastrowid
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'user', new_id,
              f'Created user {data["username"]} with role {data["role"]}', request.remote_addr)
    db.close()

    # On Vercel: sync in background so created user survives cold starts
    import os, threading
    if os.environ.get('VERCEL'):
        try:
            from app.backup import sync_table, HAS_PG
            if HAS_PG:
                threading.Thread(target=sync_table, args=('users',), daemon=True).start()
        except Exception:
            pass

    return jsonify({'id': new_id}), 201


@users_bp.route('/api/<int:id>', methods=['PUT'])
@login_required
@role_required('admin')
def api_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()

    user = db.execute('SELECT id FROM users WHERE id = ?', (id,)).fetchone()
    if not user:
        db.close()
        return jsonify({'error': 'User not found'}), 404

    db.execute(
        '''UPDATE users SET first_name=?, last_name=?, email=?, phone=?, role=?, is_active=?,
           department_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (data['first_name'], data['last_name'], data.get('email'), data.get('phone'),
         data['role'], data.get('is_active', 1), data.get('department_id'), id)
    )
    if data.get('password'):
        db.execute('UPDATE users SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                   (generate_password_hash(data['password']), id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'user', id,
              f'Updated user {data.get("username", id)}', request.remote_addr)
    db.close()
    return jsonify({'message': 'User updated successfully'})


@users_bp.route('/api/<int:id>/toggle', methods=['POST'])
@login_required
@role_required('admin')
def api_toggle_active(id):
    current_user = get_jwt()
    db = get_db()
    user = db.execute('SELECT id, username, is_active FROM users WHERE id = ?', (id,)).fetchone()
    if not user:
        db.close()
        return jsonify({'error': 'User not found'}), 404

    new_status = 0 if user['is_active'] else 1
    db.execute('UPDATE users SET is_active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (new_status, id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'user', id,
              f'{"Activated" if new_status else "Deactivated"} user {user["username"]}', request.remote_addr)
    db.close()
    return jsonify({'is_active': new_status, 'message': f'User {"activated" if new_status else "deactivated"}'})


@users_bp.route('/api/<int:id>/reset-password', methods=['POST'])
@login_required
@role_required('admin')
def api_reset_password(id):
    current_user = get_jwt()
    data = request.json
    new_password = data.get('password', 'changeme123')
    db = get_db()
    user = db.execute('SELECT id, username FROM users WHERE id = ?', (id,)).fetchone()
    if not user:
        db.close()
        return jsonify({'error': 'User not found'}), 404

    db.execute('UPDATE users SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
               (generate_password_hash(new_password), id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'password_reset', 'user', id,
              f'Reset password for {user["username"]}', request.remote_addr)
    db.close()
    return jsonify({'message': f'Password reset for {user["username"]}'})


@users_bp.route('/api/<int:id>', methods=['DELETE'])
@login_required
@role_required('admin')
def api_delete(id):
    current_user = get_jwt()
    db = get_db()
    user = db.execute('SELECT id, username FROM users WHERE id = ?', (id,)).fetchone()
    if not user:
        db.close()
        return jsonify({'error': 'User not found'}), 404

    if user['username'] == 'admin':
        db.close()
        return jsonify({'error': 'Cannot delete the main admin user'}), 400

    db.execute('DELETE FROM users WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'delete', 'user', id,
              f'Deleted user {user["username"]}', request.remote_addr)
    db.close()
    return jsonify({'message': f'User {user["username"]} deleted'})


@users_bp.route('/api/roles', methods=['GET'])
@login_required
def api_roles():
    return jsonify(ROLE_HIERARCHY)
