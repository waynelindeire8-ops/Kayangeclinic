from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from werkzeug.security import check_password_hash, generate_password_hash
from app.database import get_db
from app.auth import login_required, role_required, log_audit

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


# ─── Pages ───

@settings_bp.route('/profile', strict_slashes=False)
@login_required
def profile_page():
    return render_template('settings/profile.html')


@settings_bp.route('/system', strict_slashes=False)
@login_required
@role_required('admin')
def system_page():
    return render_template('settings/system.html')


# ─── API: Profile ───

@settings_bp.route('/api/profile', methods=['GET'])
@login_required
def api_profile_get():
    claims = get_jwt()
    db = get_db()
    user = db.execute(
        'SELECT id, username, role, first_name, last_name, email, phone, is_active, created_at FROM users WHERE id = ?',
        (claims['id'],)).fetchone()
    db.close()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(dict(user))


@settings_bp.route('/api/profile', methods=['PUT'])
@login_required
def api_profile_update():
    claims = get_jwt()
    data = request.json
    db = get_db()
    db.execute(
        '''UPDATE users SET first_name=?, last_name=?, email=?, phone=?, updated_at=CURRENT_TIMESTAMP
           WHERE id=?''',
        (data.get('first_name'), data.get('last_name'), data.get('email'),
         data.get('phone'), claims['id']))
    db.commit()
    log_audit(claims['id'], claims['username'], 'update_profile', 'user', claims['id'],
              'Updated profile', request.remote_addr)
    db.close()
    return jsonify({'message': 'Profile updated'})


@settings_bp.route('/api/change-password', methods=['POST'])
@login_required
def api_change_password():
    claims = get_jwt()
    data = request.json
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (claims['id'],)).fetchone()

    if not user or not check_password_hash(user['password_hash'], data.get('old_password', '')):
        db.close()
        return jsonify({'error': 'Current password is incorrect'}), 400

    db.execute(
        'UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (generate_password_hash(data['new_password']), claims['id']))
    db.commit()
    log_audit(claims['id'], claims['username'], 'password_change', 'user', claims['id'],
              'Changed password', request.remote_addr)
    db.close()
    return jsonify({'message': 'Password changed successfully'})


# ─── API: System Config ───

@settings_bp.route('/api/system', methods=['GET'])
@login_required
@role_required('admin')
def api_system_get():
    db = get_db()
    rows = db.execute('SELECT key, value FROM system_config').fetchall()
    db.close()
    return jsonify({r['key']: r['value'] for r in rows})


@settings_bp.route('/api/system', methods=['PUT'])
@login_required
@role_required('admin')
def api_system_update():
    claims = get_jwt()
    data = request.json
    db = get_db()
    for k, v in data.items():
        db.execute(
            '''INSERT INTO system_config (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP''',
            (k, str(v)))
    db.commit()
    log_audit(claims['id'], claims['username'], 'update_system_config', 'system_config', None,
              'Updated system settings', request.remote_addr)
    db.close()
    return jsonify({'message': 'Settings saved'})
