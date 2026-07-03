from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt
from werkzeug.security import generate_password_hash
from app.database import get_db
from app.auth import login_required, role_required, log_audit

staff_bp = Blueprint('staff', __name__, url_prefix='/staff')


@staff_bp.route('/')
@login_required
def list_page():
    return render_template('staff/list.html')


@staff_bp.route('/new')
@login_required
def new_page():
    return render_template('staff/form.html')


@staff_bp.route('/<int:id>/edit')
@login_required
def edit_page(id):
    return render_template('staff/form.html', staff_id=id)


@staff_bp.route('/schedule')
@login_required
def schedule_page():
    return render_template('staff/schedule.html')


@staff_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    db = get_db()
    staff = db.execute('SELECT id, username, role, first_name, last_name, email, phone, is_active, created_at FROM users ORDER BY role, first_name').fetchall()
    db.close()
    return jsonify([dict(s) for s in staff])


@staff_bp.route('/api/doctors', methods=['GET'])
@login_required
def api_doctors():
    db = get_db()
    doctors = db.execute(
        'SELECT id, first_name, last_name, role FROM users WHERE role IN ("doctor","locum_doctor") AND is_active = 1'
    ).fetchall()
    db.close()
    return jsonify([dict(d) for d in doctors])


@staff_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    db = get_db()
    staff = db.execute('SELECT id, username, role, first_name, last_name, email, phone, is_active FROM users WHERE id = ?',
                       (id,)).fetchone()
    db.close()
    if not staff:
        return jsonify({'error': 'Staff not found'}), 404
    return jsonify(dict(staff))


@staff_bp.route('/api', methods=['POST'])
@role_required('admin')
def api_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()

    existing = db.execute('SELECT id FROM users WHERE username = ?', (data['username'],)).fetchone()
    if existing:
        db.close()
        return jsonify({'error': 'Username already exists'}), 400

    password_hash = generate_password_hash(data.get('password', 'changeme123'))
    cursor = db.execute(
        '''INSERT INTO users (username, password_hash, role, first_name, last_name, email, phone)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (data['username'], password_hash, data['role'], data['first_name'],
         data['last_name'], data.get('email'), data.get('phone'))
    )
    new_id = cursor.lastrowid
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'user', new_id,
              f'Created staff account {data["username"]}', request.remote_addr)
    db.close()
    return jsonify({'id': new_id}), 201


@staff_bp.route('/api/<int:id>', methods=['PUT'])
@role_required('admin')
def api_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    db.execute(
        '''UPDATE users SET first_name=?, last_name=?, email=?, phone=?, role=?, is_active=?, updated_at=CURRENT_TIMESTAMP
           WHERE id=?''',
        (data['first_name'], data['last_name'], data.get('email'), data.get('phone'),
         data.get('role'), data.get('is_active', 1), id)
    )
    if data.get('password'):
        db.execute('UPDATE users SET password_hash=? WHERE id=?',
                   (generate_password_hash(data['password']), id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'user', id,
              f'Updated staff account', request.remote_addr)
    db.close()
    return jsonify({'message': 'Staff updated successfully'})


@staff_bp.route('/api/role-hierarchy', methods=['GET'])
@login_required
def api_role_hierarchy():
    from app.auth import ROLE_HIERARCHY
    return jsonify(ROLE_HIERARCHY)
