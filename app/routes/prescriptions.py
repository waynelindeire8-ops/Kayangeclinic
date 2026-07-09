from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required, log_audit

prescriptions_bp = Blueprint('prescriptions', __name__, url_prefix='/prescriptions')


# ─── Pages ───

@prescriptions_bp.route('/', strict_slashes=False)
@login_required
def list_page():
    return render_template('prescriptions/list.html')


@prescriptions_bp.route('/new', strict_slashes=False)
@login_required
def new_page():
    return render_template('prescriptions/form.html')


@prescriptions_bp.route('/<int:id>', strict_slashes=False)
@login_required
def detail_page(id):
    return render_template('prescriptions/detail.html', order_id=id)


@prescriptions_bp.route('/<int:id>/edit', strict_slashes=False)
@login_required
def edit_page(id):
    return render_template('prescriptions/form.html', order_id=id)


@prescriptions_bp.route('/<int:id>/print', strict_slashes=False)
@login_required
def print_page(id):
    return render_template('prescriptions/print.html', order_id=id)


# ─── API: Orders ───

@prescriptions_bp.route('/api/orders', methods=['GET'])
@login_required
def api_orders_list():
    db = get_db()
    status = request.args.get('status', '')
    patient_id = request.args.get('patient_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = '''SELECT o.*, p.first_name as p_first, p.last_name as p_last,
                      p.patient_id as p_patient_id,
                      u.first_name as d_first, u.last_name as d_last
               FROM prescription_orders o
               LEFT JOIN patients p ON o.patient_id = p.id
               LEFT JOIN users u ON o.doctor_id = u.id
               WHERE 1=1'''
    params = []
    if status:
        query += ' AND o.status = ?'
        params.append(status)
    if patient_id:
        query += ' AND o.patient_id = ?'
        params.append(patient_id)
    if date_from:
        query += ' AND o.created_at >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND o.created_at <= ?'
        params.append(date_to + ' 23:59:59')
    query += ' ORDER BY o.created_at DESC'

    orders = db.execute(query, params).fetchall()
    result = []
    for o in orders:
        item_count = db.execute(
            'SELECT COUNT(*) as c FROM prescriptions WHERE order_id = ?', (o['id'],)).fetchone()['c']
        r = dict(o)
        r['item_count'] = item_count
        result.append(r)
    db.close()
    return jsonify(result)


@prescriptions_bp.route('/api/orders', methods=['POST'])
@login_required
def api_orders_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()

    cursor = db.execute(
        '''INSERT INTO prescription_orders (patient_id, doctor_id, notes, status)
           VALUES (?, ?, ?, 'active')''',
        (data['patient_id'], current_user['id'], data.get('notes'))
    )
    order_id = cursor.lastrowid

    items = data.get('items', [])
    for item in items:
        drug_name = item.get('drug_name')
        if item.get('inventory_id'):
            inv = db.execute('SELECT drug_name FROM pharmacy_inventory WHERE id=?',
                             (item['inventory_id'],)).fetchone()
            if inv:
                drug_name = inv['drug_name']
        db.execute(
            '''INSERT INTO prescriptions (order_id, patient_id, inventory_id, drug_name, dosage,
               frequency, duration, route, instructions, quantity, status, prescribed_by, prescribed_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, DATE('now'))''',
            (order_id, data['patient_id'], item.get('inventory_id'), drug_name,
             item.get('dosage'), item.get('frequency'), item.get('duration'),
             item.get('route'), item.get('instructions'), item.get('quantity'), current_user['id'])
        )

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'prescription_order', order_id,
              f'Created prescription order for patient {data["patient_id"]}', request.remote_addr)
    db.close()
    return jsonify({'id': order_id}), 201


@prescriptions_bp.route('/api/orders/<int:id>', methods=['GET'])
@login_required
def api_orders_get(id):
    db = get_db()
    order = db.execute(
        '''SELECT o.*, p.first_name as p_first, p.last_name as p_last,
                  p.dob, p.gender, p.blood_group, p.patient_id as p_patient_id,
                  u.first_name as d_first, u.last_name as d_last
           FROM prescription_orders o
           LEFT JOIN patients p ON o.patient_id = p.id
           LEFT JOIN users u ON o.doctor_id = u.id
           WHERE o.id = ?''', (id,)).fetchone()
    if not order:
        db.close()
        return jsonify({'error': 'Prescription order not found'}), 404

    items = db.execute(
        '''SELECT p.*, i.drug_name as inventory_drug, i.unit_price, i.stock_quantity
           FROM prescriptions p
           LEFT JOIN pharmacy_inventory i ON p.inventory_id = i.id
           WHERE p.order_id = ?
           ORDER BY p.created_at''', (id,)).fetchall()

    refills = db.execute(
        '''SELECT r.*, u.first_name as r_first, u.last_name as r_last
           FROM prescription_refills r
           LEFT JOIN users u ON r.refilled_by = u.id
           WHERE r.order_id = ?
           ORDER BY r.refill_date DESC''', (id,)).fetchall()

    db.close()
    result = dict(order)
    result['items'] = [dict(i) for i in items]
    result['refills'] = [dict(r) for r in refills]
    return jsonify(result)


@prescriptions_bp.route('/api/orders/<int:id>', methods=['PUT'])
@login_required
def api_orders_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()

    order = db.execute('SELECT * FROM prescription_orders WHERE id = ?', (id,)).fetchone()
    if not order:
        db.close()
        return jsonify({'error': 'Prescription order not found'}), 404

    db.execute(
        'UPDATE prescription_orders SET notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (data.get('notes'), id)
    )

    existing = {r['id'] for r in db.execute(
        'SELECT id FROM prescriptions WHERE order_id = ?', (id,)).fetchall()}
    submitted_ids = set()

    for item in data.get('items', []):
        drug_name = item.get('drug_name')
        if item.get('inventory_id'):
            inv = db.execute('SELECT drug_name FROM pharmacy_inventory WHERE id=?',
                             (item['inventory_id'],)).fetchone()
            if inv:
                drug_name = inv['drug_name']

        item_id = item.get('id')
        if item_id and item_id in existing:
            submitted_ids.add(item_id)
            db.execute(
                '''UPDATE prescriptions SET inventory_id=?, drug_name=?, dosage=?, frequency=?,
                   duration=?, route=?, instructions=?, quantity=?, status=?
                   WHERE id=? AND order_id=?''',
                (item.get('inventory_id'), drug_name, item.get('dosage'), item.get('frequency'),
                 item.get('duration'), item.get('route'), item.get('instructions'),
                 item.get('quantity'), item.get('status', 'active'), item_id, id)
            )
        else:
            cursor = db.execute(
                '''INSERT INTO prescriptions (order_id, patient_id, inventory_id, drug_name, dosage,
                   frequency, duration, route, instructions, quantity, status, prescribed_by, prescribed_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, DATE('now'))''',
                (id, order['patient_id'], item.get('inventory_id'), drug_name,
                 item.get('dosage'), item.get('frequency'), item.get('duration'),
                 item.get('route'), item.get('instructions'), item.get('quantity'), current_user['id'])
            )
            submitted_ids.add(cursor.lastrowid)

    to_delete = existing - submitted_ids
    for did in to_delete:
        db.execute('DELETE FROM prescriptions WHERE id = ? AND order_id = ?', (did, id))

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'prescription_order', id,
              'Updated prescription order', request.remote_addr)
    db.close()
    return jsonify({'message': 'Prescription order updated'})


@prescriptions_bp.route('/api/orders/<int:id>', methods=['DELETE'])
@login_required
def api_orders_delete(id):
    current_user = get_jwt()
    db = get_db()
    db.execute('DELETE FROM prescriptions WHERE order_id = ?', (id,))
    db.execute('DELETE FROM prescription_refills WHERE order_id = ?', (id,))
    db.execute('DELETE FROM prescription_orders WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'delete', 'prescription_order', id,
              'Deleted prescription order', request.remote_addr)
    db.close()
    return jsonify({'message': 'Deleted'})


@prescriptions_bp.route('/api/orders/<int:id>/status', methods=['PUT'])
@login_required
def api_orders_status(id):
    current_user = get_jwt()
    data = request.json
    new_status = data.get('status')
    if new_status not in ('active', 'completed', 'cancelled'):
        return jsonify({'error': 'Invalid status'}), 400

    db = get_db()
    db.execute('UPDATE prescription_orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
               (new_status, id))
    db.execute(
        'UPDATE prescriptions SET status = ? WHERE order_id = ?',
        ('discontinued' if new_status == 'cancelled' else new_status, id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'change_status', 'prescription_order', id,
              f'Order status changed to {new_status}', request.remote_addr)
    db.close()
    return jsonify({'message': 'Status updated'})


# ─── API: Items ───

@prescriptions_bp.route('/api/orders/<int:oid>/items', methods=['POST'])
@login_required
def api_items_create(oid):
    current_user = get_jwt()
    data = request.json
    db = get_db()

    order = db.execute('SELECT * FROM prescription_orders WHERE id = ?', (oid,)).fetchone()
    if not order:
        db.close()
        return jsonify({'error': 'Order not found'}), 404

    drug_name = data.get('drug_name')
    if data.get('inventory_id'):
        inv = db.execute('SELECT drug_name FROM pharmacy_inventory WHERE id=?',
                         (data['inventory_id'],)).fetchone()
        if inv:
            drug_name = inv['drug_name']

    cursor = db.execute(
        '''INSERT INTO prescriptions (order_id, patient_id, inventory_id, drug_name, dosage,
           frequency, duration, route, instructions, quantity, status, prescribed_by, prescribed_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, DATE('now'))''',
        (oid, order['patient_id'], data.get('inventory_id'), drug_name,
         data.get('dosage'), data.get('frequency'), data.get('duration'),
         data.get('route'), data.get('instructions'), data.get('quantity'), current_user['id'])
    )
    db.commit()
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201


@prescriptions_bp.route('/api/items/<int:id>', methods=['PUT'])
@login_required
def api_items_update(id):
    data = request.json
    db = get_db()
    drug_name = data.get('drug_name')
    if data.get('inventory_id'):
        inv = db.execute('SELECT drug_name FROM pharmacy_inventory WHERE id=?',
                         (data['inventory_id'],)).fetchone()
        if inv:
            drug_name = inv['drug_name']
    db.execute(
        '''UPDATE prescriptions SET inventory_id=?, drug_name=?, dosage=?, frequency=?, duration=?,
           route=?, instructions=?, quantity=?, status=? WHERE id=?''',
        (data.get('inventory_id'), drug_name, data.get('dosage'), data.get('frequency'),
         data.get('duration'), data.get('route'), data.get('instructions'),
         data.get('quantity'), data.get('status', 'active'), id)
    )
    db.commit()
    db.close()
    return jsonify({'message': 'Item updated'})


@prescriptions_bp.route('/api/items/<int:id>', methods=['DELETE'])
@login_required
def api_items_delete(id):
    db = get_db()
    db.execute('DELETE FROM prescriptions WHERE id = ?', (id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Deleted'})


# ─── API: Refills ───

@prescriptions_bp.route('/api/orders/<int:oid>/refills', methods=['GET'])
@login_required
def api_refills_list(oid):
    db = get_db()
    refills = db.execute(
        '''SELECT r.*, u.first_name as r_first, u.last_name as r_last
           FROM prescription_refills r
           LEFT JOIN users u ON r.refilled_by = u.id
           WHERE r.order_id = ?
           ORDER BY r.refill_date DESC''', (oid,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in refills])


@prescriptions_bp.route('/api/orders/<int:oid>/refills', methods=['POST'])
@login_required
def api_refills_create(oid):
    current_user = get_jwt()
    data = request.json
    db = get_db()

    order = db.execute('SELECT * FROM prescription_orders WHERE id = ?', (oid,)).fetchone()
    if not order:
        db.close()
        return jsonify({'error': 'Order not found'}), 404

    cursor = db.execute(
        '''INSERT INTO prescription_refills (order_id, refill_date, quantity, refilled_by, notes)
           VALUES (?, DATE('now'), ?, ?, ?)''',
        (oid, data.get('quantity'), current_user['id'], data.get('notes'))
    )
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'refill', 'prescription_order', oid,
              f'Added refill for prescription order {oid}', request.remote_addr)
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201
