import json
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, make_response, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from app.database import get_db

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

ROLE_HIERARCHY = {
    'admin': 100,
    'doctor': 80,
    'locum_doctor': 70,
    'nurse': 60,
    'locum_nurse': 50,
    'lab_supervisor': 55,
    'lab_staff': 50,
    'lab_tech': 50,
    'lab_care': 45,
    'front_desk': 40,
    'file_manager': 30,
}


def get_current_user():
    return get_jwt()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except Exception:
            if '/api/' in request.path:
                return jsonify({'error': 'Authentication required'}), 401
            return redirect('/auth/login')
        return f(*args, **kwargs)
    return wrapper


def role_required(min_role):
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            if ROLE_HIERARCHY.get(claims.get('role', ''), 0) < ROLE_HIERARCHY.get(min_role, 0):
                return jsonify({'error': 'Insufficient permissions'}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


def log_audit(user_id, username, action, resource_type, resource_id=None, details=None, ip_address=None):
    db = get_db()
    db.execute(
        '''INSERT INTO audit_logs (user_id, username, action, resource_type, resource_id, details, ip_address)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (user_id, username, action, resource_type, resource_id, details, ip_address)
    )
    db.commit()
    db.close()


@auth_bp.route('/login', methods=['GET'], strict_slashes=False)
def login_page():
    return render_template('login.html')


@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE username = ? AND is_active = 1', (username,)).fetchone()
    db.close()

    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401

    access_token = create_access_token(
        identity=str(user['id']),
        additional_claims={
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'first_name': user['first_name'],
            'last_name': user['last_name']
        }
    )

    resp = make_response(jsonify({
        'token': access_token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'first_name': user['first_name'],
            'last_name': user['last_name']
        }
    }))
    resp.set_cookie(
        'access_token',
        access_token,
        httponly=True,
        samesite='Lax',
        secure=False,
        max_age=36000
    )
    return resp


@auth_bp.route('/api/me', methods=['GET'])
@login_required
def api_me():
    return jsonify({'user': get_jwt()})


@auth_bp.route('/api/change-password', methods=['POST'])
@login_required
def api_change_password():
    claims = get_jwt()
    data = request.json
    old_password = data.get('old_password')
    new_password = data.get('new_password')

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (claims['id'],)).fetchone()

    if not check_password_hash(user['password_hash'], old_password):
        db.close()
        return jsonify({'error': 'Current password is incorrect'}), 400

    db.execute('UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
               (generate_password_hash(new_password), claims['id']))
    db.commit()
    log_audit(claims['id'], claims['username'], 'password_change', 'user', claims['id'])
    db.close()

    return jsonify({'message': 'Password changed successfully'})
