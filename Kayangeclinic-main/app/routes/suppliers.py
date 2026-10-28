from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required, log_audit

suppliers_bp = Blueprint('suppliers', __name__, url_prefix='/suppliers')


# ─── Pages ───

@suppliers_bp.route('/', strict_slashes=False)
@login_required
def list_page():
    return render_template('suppliers/list.html')


# ─── API: List ───

@suppliers_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    db = get_db()
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    active_only = request.args.get('active', '')

    query = 'SELECT * FROM suppliers WHERE 1=1'
    params = []
    if search:
        query += ' AND (name LIKE ? OR contact_person LIKE ? OR phone LIKE ? OR email LIKE ?)'
        params.extend([f'%{search}%'] * 4)
    if category:
        query += ' AND category = ?'
        params.append(category)
    if active_only:
        query += ' AND is_active = 1'
    query += ' ORDER BY name'
    suppliers = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(s) for s in suppliers])


# ─── API: Get ───

@suppliers_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    db = get_db()
    supplier = db.execute('SELECT * FROM suppliers WHERE id = ?', (id,)).fetchone()
    db.close()
    if not supplier:
        return jsonify({'error': 'Supplier not found'}), 404
    return jsonify(dict(supplier))


# ─── API: Create ───

@suppliers_bp.route('/api', methods=['POST'])
@login_required
def api_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO suppliers (name, contact_person, phone, email, address, category, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (data['name'], data.get('contact_person'), data.get('phone'), data.get('email'),
         data.get('address'), data.get('category', 'general'), data.get('notes')))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'supplier', cursor.lastrowid,
              f'Added supplier: {data["name"]}', request.remote_addr)
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201


# ─── API: Update ───

@suppliers_bp.route('/api/<int:id>', methods=['PUT'])
@login_required
def api_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    db.execute(
        '''UPDATE suppliers SET name=?, contact_person=?, phone=?, email=?, address=?,
           category=?, notes=?, is_active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (data['name'], data.get('contact_person'), data.get('phone'), data.get('email'),
         data.get('address'), data.get('category', 'general'), data.get('notes'),
         data.get('is_active', 1), id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'supplier', id,
              f'Updated supplier: {data["name"]}', request.remote_addr)
    db.close()
    return jsonify({'message': 'Supplier updated'})


# ─── API: Delete ───

@suppliers_bp.route('/api/<int:id>', methods=['DELETE'])
@login_required
def api_delete(id):
    current_user = get_jwt()
    db = get_db()
    db.execute('DELETE FROM suppliers WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'delete', 'supplier', id,
              'Deleted supplier', request.remote_addr)
    db.close()
    return jsonify({'message': 'Deleted'})


# ─── API: Stats ───

@suppliers_bp.route('/api/stats', methods=['GET'])
@login_required
def api_stats():
    db = get_db()
    total = db.execute('SELECT COUNT(*) as c FROM suppliers').fetchone()['c']
    active = db.execute('SELECT COUNT(*) as c FROM suppliers WHERE is_active = 1').fetchone()['c']
    categories = db.execute(
        'SELECT category, COUNT(*) as c FROM suppliers GROUP BY category ORDER BY c DESC'
    ).fetchall()
    db.close()
    return jsonify({
        'total': total, 'active': active,
        'categories': [dict(c) for c in categories]
    })
