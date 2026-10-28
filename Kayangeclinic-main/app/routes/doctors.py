from sqlite3 import IntegrityError
from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from werkzeug.security import generate_password_hash
from app.database import get_db
from app.auth import login_required, role_required, log_audit

doctors_bp = Blueprint('doctors', __name__, url_prefix='/doctors')

DOCTOR_ROLES = ('doctor', 'locum_doctor')


@doctors_bp.route('/', strict_slashes=False)
@login_required
def list_page():
    return render_template('doctors/list.html')


@doctors_bp.route('/new', strict_slashes=False)
@login_required
def new_page():
    return render_template('doctors/form.html')


@doctors_bp.route('/<int:id>/edit', strict_slashes=False)
@login_required
def edit_page(id):
    return render_template('doctors/form.html', doctor_id=id)


@doctors_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    db = get_db()
    doctors = db.execute(
        'SELECT id, username, role, first_name, last_name, email, phone, is_active, created_at FROM users WHERE role IN (?, ?) ORDER BY role, first_name',
        DOCTOR_ROLES
    ).fetchall()
    db.close()
    return jsonify([dict(d) for d in doctors])


@doctors_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    db = get_db()
    doctor = db.execute(
        'SELECT id, username, role, first_name, last_name, email, phone, is_active FROM users WHERE id = ? AND role IN (?, ?)',
        (id, *DOCTOR_ROLES)
    ).fetchone()
    db.close()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    return jsonify(dict(doctor))


@doctors_bp.route('/api', methods=['POST'])
@role_required('admin')
def api_create():
    current_user = get_jwt()
    data = request.json
    role = data.get('role', 'doctor')
    if role not in DOCTOR_ROLES:
        return jsonify({'error': 'Role must be doctor or locum_doctor'}), 400

    db = get_db()
    existing = db.execute('SELECT id FROM users WHERE username = ?', (data['username'],)).fetchone()
    if existing:
        db.close()
        return jsonify({'error': 'Username already exists'}), 400

    password_hash = generate_password_hash(data.get('password', 'changeme123'))
    cursor = db.execute(
        '''INSERT INTO users (username, password_hash, role, first_name, last_name, email, phone)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (data['username'], password_hash, role, data['first_name'],
         data['last_name'], data.get('email'), data.get('phone'))
    )
    new_id = cursor.lastrowid
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'user', new_id,
              f'Created doctor account {data["username"]}', request.remote_addr)
    db.close()
    return jsonify({'id': new_id}), 201


@doctors_bp.route('/api/<int:id>', methods=['PUT'])
@role_required('admin')
def api_update(id):
    current_user = get_jwt()
    data = request.json
    role = data.get('role', 'doctor')
    if role not in DOCTOR_ROLES:
        return jsonify({'error': 'Role must be doctor or locum_doctor'}), 400

    db = get_db()
    db.execute(
        '''UPDATE users SET first_name=?, last_name=?, email=?, phone=?, role=?, is_active=?, updated_at=CURRENT_TIMESTAMP
           WHERE id=? AND role IN (?, ?)''',
        (data['first_name'], data['last_name'], data.get('email'), data.get('phone'),
         role, data.get('is_active', 1), id, *DOCTOR_ROLES)
    )
    if data.get('password'):
        db.execute('UPDATE users SET password_hash=? WHERE id=?',
                   (generate_password_hash(data['password']), id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'user', id,
              f'Updated doctor account', request.remote_addr)
    db.close()
    return jsonify({'message': 'Doctor updated successfully'})


@doctors_bp.route('/api/<int:id>', methods=['DELETE'])
@role_required('admin')
def api_delete(id):
    current_user = get_jwt()
    db = get_db()
    doctor = db.execute(
        'SELECT * FROM users WHERE id = ? AND role IN (?, ?)', (id, *DOCTOR_ROLES)
    ).fetchone()
    if not doctor:
        db.close()
        return jsonify({'error': 'Doctor not found'}), 404
    try:
        db.execute('DELETE FROM users WHERE id = ?', (id,))
        db.commit()
    except IntegrityError:
        db.close()
        return jsonify({'error': 'Cannot delete doctor with existing appointments, consultations, or other related data. Deactivate the account instead.'}), 409
    log_audit(current_user['id'], current_user['username'], 'delete', 'user', id,
              f'Deleted doctor {doctor["first_name"]} {doctor["last_name"]}', request.remote_addr)
    db.close()
    return jsonify({'message': 'Doctor deleted successfully'})
