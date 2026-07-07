from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt
from app.database import get_db
from app.auth import login_required, role_required, log_audit

departments_bp = Blueprint('departments', __name__, url_prefix='/departments')


@departments_bp.route('/', strict_slashes=False)
@login_required
def list_page():
    return render_template('departments/list.html')


@departments_bp.route('/new', strict_slashes=False)
@login_required
def new_page():
    return render_template('departments/form.html')


@departments_bp.route('/<int:id>/edit', strict_slashes=False)
@login_required
def edit_page(id):
    return render_template('departments/form.html', department_id=id)


@departments_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    db = get_db()
    depts = db.execute('SELECT * FROM departments ORDER BY name').fetchall()
    db.close()
    return jsonify([dict(d) for d in depts])


@departments_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    db = get_db()
    dept = db.execute('SELECT * FROM departments WHERE id = ?', (id,)).fetchone()
    db.close()
    if not dept:
        return jsonify({'error': 'Department not found'}), 404
    return jsonify(dict(dept))


@departments_bp.route('/api', methods=['POST'])
@role_required('admin')
def api_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()

    existing = db.execute('SELECT id FROM departments WHERE name = ?', (data['name'],)).fetchone()
    if existing:
        db.close()
        return jsonify({'error': 'Department name already exists'}), 400

    cursor = db.execute(
        'INSERT INTO departments (name, description) VALUES (?, ?)',
        (data['name'], data.get('description'))
    )
    new_id = cursor.lastrowid
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'department', new_id,
              f'Created department {data["name"]}', request.remote_addr)
    db.close()
    return jsonify({'id': new_id}), 201


@departments_bp.route('/api/<int:id>', methods=['PUT'])
@role_required('admin')
def api_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()

    existing = db.execute('SELECT id FROM departments WHERE name = ? AND id != ?', (data['name'], id)).fetchone()
    if existing:
        db.close()
        return jsonify({'error': 'Department name already exists'}), 400

    db.execute(
        'UPDATE departments SET name=?, description=?, is_active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
        (data['name'], data.get('description'), data.get('is_active', 1), id)
    )
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'department', id,
              f'Updated department {data["name"]}', request.remote_addr)
    db.close()
    return jsonify({'message': 'Department updated successfully'})


@departments_bp.route('/api/<int:id>', methods=['DELETE'])
@role_required('admin')
def api_delete(id):
    current_user = get_jwt()
    db = get_db()
    dept = db.execute('SELECT * FROM departments WHERE id = ?', (id,)).fetchone()
    if not dept:
        db.close()
        return jsonify({'error': 'Department not found'}), 404
    db.execute('DELETE FROM departments WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'delete', 'department', id,
              f'Deleted department {dept["name"]}', request.remote_addr)
    db.close()
    return jsonify({'message': 'Department deleted successfully'})
