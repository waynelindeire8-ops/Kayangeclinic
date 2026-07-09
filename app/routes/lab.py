from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required, role_required, log_audit

lab_bp = Blueprint('lab', __name__, url_prefix='/lab')


# ─── Pages ───

@lab_bp.route('/', strict_slashes=False)
@login_required
def dashboard_page():
    return render_template('lab/dashboard.html')


@lab_bp.route('/orders', strict_slashes=False)
@login_required
def orders_page():
    return render_template('lab/orders.html')


@lab_bp.route('/orders/new', strict_slashes=False)
@login_required
def order_new_page():
    return render_template('lab/order_form.html')


@lab_bp.route('/orders/<int:id>', strict_slashes=False)
@login_required
def order_detail_page(id):
    db = get_db()
    order = db.execute(
        '''SELECT l.*, p.first_name as p_first, p.last_name as p_last, p.dob, p.gender,
                  p.patient_id as p_patient_id, u.first_name as d_first, u.last_name as d_last
           FROM lab_tests l
           LEFT JOIN patients p ON l.patient_id = p.id
           LEFT JOIN users u ON l.doctor_id = u.id
           WHERE l.id = ?''', (id,)).fetchone()
    db.close()
    current_user = get_jwt()
    if not order:
        return render_template('lab/order_detail.html', order={}, order_id=id, current_user=current_user)
    return render_template('lab/order_detail.html', order=dict(order), order_id=id, current_user=current_user)


@lab_bp.route('/catalog', strict_slashes=False)
@login_required
def catalog_page():
    return render_template('lab/catalog.html')


# ─── API: Dashboard Stats ───

@lab_bp.route('/api/dashboard', methods=['GET'])
@login_required
def api_dashboard():
    db = get_db()
    from datetime import date, datetime, timedelta
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    pending = db.execute(
        "SELECT COUNT(*) as c FROM lab_tests WHERE status IN ('ordered','collected')"
    ).fetchone()['c']

    in_progress = db.execute(
        "SELECT COUNT(*) as c FROM lab_tests WHERE status = 'in_progress'"
    ).fetchone()['c']

    completed_today = db.execute(
        'SELECT COUNT(*) as c FROM lab_tests WHERE status = ? AND completed_date = ?',
        ('completed', today)
    ).fetchone()['c']

    ordered_today = db.execute(
        'SELECT COUNT(*) as c FROM lab_tests WHERE DATE(ordered_date) = ?', (today,)
    ).fetchone()['c']

    recent = db.execute(
        '''SELECT l.*, p.first_name as p_first, p.last_name as p_last,
                  u.first_name as d_first, u.last_name as d_last
           FROM lab_tests l
           LEFT JOIN patients p ON l.patient_id = p.id
           LEFT JOIN users u ON l.doctor_id = u.id
           ORDER BY l.created_at DESC LIMIT 10'''
    ).fetchall()

    results_today = db.execute(
        '''SELECT lr.*, lt.test_name, p.first_name as p_first, p.last_name as p_last
           FROM lab_test_results lr
           JOIN lab_tests lt ON lr.lab_test_id = lt.id
           JOIN patients p ON lt.patient_id = p.id
           WHERE DATE(lr.created_at) = ?
           ORDER BY lr.created_at DESC LIMIT 20''', (today,)
    ).fetchall()

    db.close()
    return jsonify({
        'pending': pending,
        'in_progress': in_progress,
        'completed_today': completed_today,
        'ordered_today': ordered_today,
        'recent': [dict(r) for r in recent],
        'results_today': [dict(r) for r in results_today]
    })


# ─── API: Orders ───

@lab_bp.route('/api/orders', methods=['GET'])
@login_required
def api_orders():
    db = get_db()
    status = request.args.get('status', '')
    patient_id = request.args.get('patient_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = '''SELECT l.*, p.first_name as p_first, p.last_name as p_last,
                      p.patient_id as p_patient_id, u.first_name as d_first, u.last_name as d_last
               FROM lab_tests l
               LEFT JOIN patients p ON l.patient_id = p.id
               LEFT JOIN users u ON l.doctor_id = u.id
               WHERE 1=1'''
    params = []
    if status:
        query += ' AND l.status = ?'
        params.append(status)
    if patient_id:
        query += ' AND l.patient_id = ?'
        params.append(patient_id)
    if date_from:
        query += ' AND l.ordered_date >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND l.ordered_date <= ?'
        params.append(date_to)
    query += ' ORDER BY l.created_at DESC'

    orders = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(o) for o in orders])


@lab_bp.route('/api/orders', methods=['POST'])
@login_required
def api_order_create():
    current_user = get_jwt()
    data = request.json

    if not data.get('patient_id') or not data.get('test_name'):
        return jsonify({'error': 'Patient and test name are required'}), 400

    db = get_db()
    catalog_id = data.get('catalog_id')
    if not catalog_id:
        cat = db.execute(
            'SELECT id FROM lab_test_catalog WHERE test_name = ? AND is_active = 1',
            (data['test_name'],)
        ).fetchone()
        if cat:
            catalog_id = cat['id']

    cursor = db.execute(
        '''INSERT INTO lab_tests (patient_id, doctor_id, test_name, test_category, status, ordered_date)
           VALUES (?, ?, ?, ?, 'ordered', DATE('now'))''',
        (data['patient_id'], current_user['id'], data['test_name'],
         data.get('test_category', 'general'))
    )
    new_id = cursor.lastrowid

    if catalog_id:
        cat_params = db.execute(
            'SELECT * FROM lab_test_catalog WHERE id = ?', (catalog_id,)
        ).fetchone()
        if cat_params and cat_params.get('default_params'):
            import json
            try:
                params = json.loads(cat_params['default_params'])
                for p in params:
                    db.execute(
                        '''INSERT INTO lab_test_results (lab_test_id, parameter_name, reference_range, unit, flag)
                           VALUES (?, ?, ?, ?, 'pending')''',
                        (new_id, p.get('parameter_name') or p.get('name'), p.get('ref_range'), p.get('unit'))
                    )
            except: pass

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'order_lab', 'lab_test', new_id,
              f'Ordered lab: {data["test_name"]}', request.remote_addr)
    db.close()
    return jsonify({'id': new_id}), 201


@lab_bp.route('/api/orders/<int:id>', methods=['GET'])
@login_required
def api_order_get(id):
    db = get_db()
    order = db.execute(
        '''SELECT l.*, p.first_name as p_first, p.last_name as p_last, p.dob, p.gender,
                  p.patient_id as p_patient_id, u.first_name as d_first, u.last_name as d_last
           FROM lab_tests l
           LEFT JOIN patients p ON l.patient_id = p.id
           LEFT JOIN users u ON l.doctor_id = u.id
           WHERE l.id = ?''', (id,)).fetchone()
    if not order:
        db.close()
        return jsonify({'error': 'Lab order not found'}), 404

    results = db.execute(
        'SELECT * FROM lab_test_results WHERE lab_test_id = ? ORDER BY id', (id,)).fetchall()

    catalog = db.execute(
        'SELECT * FROM lab_test_catalog WHERE test_name = ? AND is_active = 1',
        (order['test_name'],)).fetchone()

    db.close()
    result = dict(order)
    result['results'] = [dict(r) for r in results]
    result['catalog'] = dict(catalog) if catalog else None
    return jsonify(result)


@lab_bp.route('/api/orders/<int:id>/status', methods=['PUT'])
@login_required
def api_order_status(id):
    current_user = get_jwt()
    data = request.json
    new_status = data.get('status')
    if new_status not in ('ordered', 'collected', 'in_progress', 'completed'):
        return jsonify({'error': 'Invalid status'}), 400

    db = get_db()
    order = db.execute('SELECT * FROM lab_tests WHERE id = ?', (id,)).fetchone()
    if not order:
        db.close()
        return jsonify({'error': 'Lab order not found'}), 404

    if new_status == 'completed':
        db.execute(
            'UPDATE lab_tests SET status = ?, completed_date = DATE("now") WHERE id = ?',
            (new_status, id))
    else:
        db.execute('UPDATE lab_tests SET status = ? WHERE id = ?', (new_status, id))

    log_audit(current_user['id'], current_user['username'], 'update_status', 'lab_test', id,
              f'Lab status changed to {new_status}', request.remote_addr)
    db.commit()
    db.close()
    return jsonify({'message': 'Status updated'})


# ─── API: Results ───

@lab_bp.route('/api/orders/<int:id>/results', methods=['GET'])
@login_required
def api_results_get(id):
    db = get_db()
    results = db.execute(
        'SELECT * FROM lab_test_results WHERE lab_test_id = ? ORDER BY id', (id,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in results])


@lab_bp.route('/api/orders/<int:id>/results', methods=['POST'])
@login_required
def api_results_save(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()

    order = db.execute('SELECT * FROM lab_tests WHERE id = ?', (id,)).fetchone()
    if not order:
        db.close()
        return jsonify({'error': 'Lab order not found'}), 404

    results = data.get('results', [])
    for r in results:
        rid = r.get('id')
        flag = 'normal'
        if r.get('value') and r.get('reference_range'):
            try:
                val = float(r['value'])
                parts = r['reference_range'].replace(' ', '').split('-')
                if len(parts) == 2:
                    lo, hi = float(parts[0]), float(parts[1])
                    if val < lo: flag = 'low'
                    elif val > hi: flag = 'high'
                    else: flag = 'normal'
            except: pass

        if rid:
            db.execute(
                '''UPDATE lab_test_results SET value=?, reference_range=?, unit=?, flag=?
                   WHERE id=? AND lab_test_id=?''',
                (r.get('value'), r.get('reference_range'), r.get('unit'), flag, rid, id)
            )
        else:
            db.execute(
                '''INSERT INTO lab_test_results (lab_test_id, parameter_name, value, reference_range, unit, flag)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (id, r.get('parameter_name'), r.get('value'), r.get('reference_range'),
                 r.get('unit'), flag)
            )

    if data.get('complete') and order['status'] != 'completed':
        db.execute('UPDATE lab_tests SET status = ?, completed_date = DATE("now") WHERE id = ?',
                   ('completed', id))

    log_audit(current_user['id'], current_user['username'], 'save_results', 'lab_test', id,
              'Saved lab results', request.remote_addr)
    db.commit()
    db.close()
    return jsonify({'message': 'Results saved'})


# ─── API: Catalog ───

@lab_bp.route('/api/catalog', methods=['GET'])
@login_required
def api_catalog_list():
    db = get_db()
    items = db.execute(
        'SELECT * FROM lab_test_catalog ORDER BY category, test_name').fetchall()
    db.close()
    return jsonify([dict(i) for i in items])


@lab_bp.route('/api/catalog', methods=['POST'])
@role_required('admin')
def api_catalog_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()
    default_params = data.get('parameters')
    cursor = db.execute(
        '''INSERT INTO lab_test_catalog (test_name, category, sample_type, description, default_price, default_params, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (data['test_name'], data.get('category', 'general'),
         data.get('sample_type', 'blood'), data.get('description'),
         data.get('default_price', 0), default_params, 1)
    )
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'lab_catalog', cursor.lastrowid,
              f'Added lab test: {data["test_name"]}', request.remote_addr)
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201


@lab_bp.route('/api/catalog/<int:id>', methods=['GET'])
@login_required
def api_catalog_get(id):
    db = get_db()
    item = db.execute('SELECT * FROM lab_test_catalog WHERE id = ?', (id,)).fetchone()
    db.close()
    if not item:
        return jsonify({'error': 'Catalog item not found'}), 404
    return jsonify(dict(item))


@lab_bp.route('/api/catalog/<int:id>', methods=['PUT'])
@role_required('admin')
def api_catalog_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    default_params = data.get('parameters')
    db.execute(
        '''UPDATE lab_test_catalog SET test_name=?, category=?, sample_type=?, description=?,
           default_price=?, default_params=?, is_active=? WHERE id=?''',
        (data['test_name'], data.get('category'), data.get('sample_type'),
         data.get('description'), data.get('default_price', 0),
         default_params, data.get('is_active', 1), id)
    )
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'lab_catalog', id,
              f'Updated lab test catalog item', request.remote_addr)
    db.close()
    return jsonify({'message': 'Catalog item updated'})


@lab_bp.route('/api/catalog/<int:id>', methods=['DELETE'])
@role_required('admin')
def api_catalog_delete(id):
    current_user = get_jwt()
    db = get_db()
    db.execute('UPDATE lab_test_catalog SET is_active = 0 WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'deactivate', 'lab_catalog', id,
              'Deactivated lab test catalog item', request.remote_addr)
    db.close()
    return jsonify({'message': 'Catalog item deactivated'})
