from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from datetime import date
import hashlib
from app.database import get_db
from app.auth import login_required, role_required, log_audit

radiology_bp = Blueprint('radiology', __name__, url_prefix='/radiology')

MODALITIES = {
    'xray': 'X-Ray',
    'ultrasound': 'Ultrasound',
    'ct': 'CT Scan',
    'mri': 'MRI',
    'ecg': 'ECG',
    'echo': 'Echocardiogram',
    'mammogram': 'Mammogram',
    'fluoroscopy': 'Fluoroscopy',
    'other': 'Other'
}


# ─── Pages ───

@radiology_bp.route('/', strict_slashes=False)
@login_required
def dashboard_page():
    return render_template('radiology/dashboard.html')


@radiology_bp.route('/orders', strict_slashes=False)
@login_required
def orders_page():
    return render_template('radiology/orders.html')


@radiology_bp.route('/orders/new', strict_slashes=False)
@login_required
def order_new_page():
    return render_template('radiology/order_form.html')


@radiology_bp.route('/orders/<int:id>', strict_slashes=False)
@login_required
def order_detail_page(id):
    db = get_db()
    order = db.execute(
        '''SELECT r.*, p.first_name as p_first, p.last_name as p_last, p.dob, p.gender,
                  p.patient_id as p_patient_id, u.first_name as d_first, u.last_name as d_last
           FROM radiology_orders r
           LEFT JOIN patients p ON r.patient_id = p.id
           LEFT JOIN users u ON r.doctor_id = u.id
           WHERE r.id = ?''', (id,)).fetchone()
    db.close()
    if not order:
        return render_template('radiology/order_detail.html', order={}, order_id=id)
    return render_template('radiology/order_detail.html', order=dict(order), order_id=id)


# ─── API: Dashboard Stats ───

@radiology_bp.route('/api/dashboard', methods=['GET'])
@login_required
def api_dashboard():
    db = get_db()
    today = date.today().isoformat()
    pending = db.execute(
        "SELECT COUNT(*) as c FROM radiology_orders WHERE status IN ('ordered','in_progress')"
    ).fetchone()['c']
    completed_today = db.execute(
        'SELECT COUNT(*) as c FROM radiology_orders WHERE status = ? AND completed_date = ?',
        ('completed', today)).fetchone()['c']
    ordered_today = db.execute(
        'SELECT COUNT(*) as c FROM radiology_orders WHERE DATE(ordered_date) = ?', (today,)
    ).fetchone()['c']
    referred = db.execute(
        "SELECT COUNT(*) as c FROM radiology_orders WHERE status = 'referred'"
    ).fetchone()['c']
    recent = db.execute(
        '''SELECT r.*, p.first_name as p_first, p.last_name as p_last,
                  u.first_name as d_first, u.last_name as d_last
           FROM radiology_orders r
           LEFT JOIN patients p ON r.patient_id = p.id
           LEFT JOIN users u ON r.doctor_id = u.id
           ORDER BY r.created_at DESC LIMIT 10'''
    ).fetchall()
    db.close()
    return jsonify({
        'pending': pending, 'completed_today': completed_today,
        'ordered_today': ordered_today, 'referred': referred,
        'recent': [dict(r) for r in recent]
    })


# ─── API: Orders ───

@radiology_bp.route('/api/orders', methods=['GET'])
@login_required
def api_orders_list():
    db = get_db()
    status = request.args.get('status', '')
    modality = request.args.get('modality', '')
    patient_id = request.args.get('patient_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = '''SELECT r.*, p.first_name as p_first, p.last_name as p_last,
                      p.patient_id as p_patient_id, u.first_name as d_first, u.last_name as d_last
               FROM radiology_orders r
               LEFT JOIN patients p ON r.patient_id = p.id
               LEFT JOIN users u ON r.doctor_id = u.id
               WHERE 1=1'''
    params = []
    if status:
        query += ' AND r.status = ?'
        params.append(status)
    if modality:
        query += ' AND r.modality = ?'
        params.append(modality)
    if patient_id:
        query += ' AND r.patient_id = ?'
        params.append(patient_id)
    if date_from:
        query += ' AND r.ordered_date >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND r.ordered_date <= ?'
        params.append(date_to)
    query += ' ORDER BY r.created_at DESC'
    orders = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(o) for o in orders])


@radiology_bp.route('/api/orders', methods=['POST'])
@login_required
def api_orders_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()

    order_count = db.execute('SELECT COUNT(*) as c FROM radiology_orders').fetchone()['c']
    order_number = f"RAD-{date.today().strftime('%Y%m')}-{order_count + 1:04d}"

    cursor = db.execute(
        '''INSERT INTO radiology_orders (order_number, patient_id, doctor_id, modality, body_part,
           clinical_history, status, ordered_date, priority, notes)
           VALUES (?, ?, ?, ?, ?, ?, 'ordered', DATE('now'), ?, ?)''',
        (order_number, data['patient_id'], current_user['id'], data['modality'],
         data.get('body_part'), data.get('clinical_history'),
         data.get('priority', 'routine'), data.get('notes')))
    order_id = cursor.lastrowid
    db.commit()

    from app.routes.notifications import notify_role
    pat = db.execute('SELECT first_name, last_name FROM patients WHERE id = ?', (data['patient_id'],)).fetchone()
    pat_name = (pat['first_name'] + ' ' + pat['last_name']) if pat else 'Patient'
    mod_name = MODALITIES.get(data['modality'], data['modality'])
    for r in ('lab_staff', 'lab_supervisor', 'lab_tech', 'lab_care'):
        notify_role(db, r, 'New Radiology Order',
                    f'{pat_name} - {mod_name} ({data.get("body_part", "N/A")}) - {order_number}',
                    'info', '/radiology/orders')

    log_audit(current_user['id'], current_user['username'], 'create', 'radiology_order', order_id,
              f'Created radiology order {order_number}', request.remote_addr)
    db.close()
    return jsonify({'id': order_id, 'order_number': order_number}), 201


@radiology_bp.route('/api/orders/<int:id>', methods=['GET'])
@login_required
def api_orders_get(id):
    db = get_db()
    order = db.execute(
        '''SELECT r.*, p.first_name as p_first, p.last_name as p_last, p.dob, p.gender,
                  p.patient_id as p_patient_id, p.phone as p_phone,
                  u.first_name as d_first, u.last_name as d_last
           FROM radiology_orders r
           LEFT JOIN patients p ON r.patient_id = p.id
           LEFT JOIN users u ON r.doctor_id = u.id
           WHERE r.id = ?''', (id,)).fetchone()
    if not order:
        db.close()
        return jsonify({'error': 'Order not found'}), 404
    results = db.execute(
        '''SELECT rr.*, u.first_name as r_first, u.last_name as r_last
           FROM radiology_results rr
           LEFT JOIN users u ON rr.reported_by = u.id
           WHERE rr.order_id = ? ORDER BY rr.created_at DESC''', (id,)).fetchall()
    db.close()
    result = dict(order)
    result['results'] = [dict(r) for r in results]
    return jsonify(result)


@radiology_bp.route('/api/orders/<int:id>', methods=['PUT'])
@login_required
def api_orders_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    db.execute(
        '''UPDATE radiology_orders SET modality=?, body_part=?, clinical_history=?,
           priority=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (data.get('modality'), data.get('body_part'), data.get('clinical_history'),
         data.get('priority', 'routine'), data.get('notes'), id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'radiology_order', id,
              'Updated radiology order', request.remote_addr)
    db.close()
    return jsonify({'message': 'Order updated'})


@radiology_bp.route('/api/orders/<int:id>', methods=['DELETE'])
@login_required
def api_orders_delete(id):
    current_user = get_jwt()
    db = get_db()
    db.execute('DELETE FROM radiology_results WHERE order_id = ?', (id,))
    db.execute('DELETE FROM radiology_orders WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'delete', 'radiology_order', id,
              'Deleted radiology order', request.remote_addr)
    db.close()
    return jsonify({'message': 'Deleted'})


@radiology_bp.route('/api/orders/<int:id>/status', methods=['PUT'])
@login_required
def api_orders_status(id):
    current_user = get_jwt()
    data = request.json
    new_status = data.get('status')
    if new_status not in ('ordered', 'in_progress', 'completed', 'cancelled', 'referred'):
        return jsonify({'error': 'Invalid status'}), 400
    db = get_db()
    if new_status == 'completed':
        db.execute('UPDATE radiology_orders SET status=?, completed_date=DATE("now") WHERE id=?',
                   (new_status, id))
    else:
        db.execute('UPDATE radiology_orders SET status=? WHERE id=?', (new_status, id))
    log_audit(current_user['id'], current_user['username'], 'status_change', 'radiology_order', id,
              f'Status changed to {new_status}', request.remote_addr)
    db.commit()
    db.close()
    return jsonify({'message': 'Status updated'})


# ─── API: Refer Out ───

@radiology_bp.route('/api/orders/<int:id>/refer', methods=['POST'])
@login_required
def api_orders_refer(id):
    current_user = get_jwt()
    data = request.json
    facility = data.get('facility', 'DR Sam Kampondeni Clinic')
    notes = data.get('notes', '')

    db = get_db()
    db.execute(
        'UPDATE radiology_orders SET status = ?, referred_to = ?, notes = COALESCE(notes || ?, ?) WHERE id = ?',
        ('referred', facility, notes, f'\nReferred to: {facility} - {notes}', id))
    db.commit()

    from app.routes.notifications import notify_role
    pat = db.execute(
        '''SELECT p.first_name, p.last_name FROM radiology_orders r
           JOIN patients p ON r.patient_id = p.id WHERE r.id = ?''', (id,)).fetchone()
    pat_name = (pat['first_name'] + ' ' + pat['last_name']) if pat else 'Patient'
    for r in ('lab_staff', 'lab_supervisor', 'lab_tech', 'lab_care'):
        notify_role(db, r, 'Radiology Referred Out',
                    f'{pat_name} sent to {facility} for imaging', 'info', '/radiology/orders')

    log_audit(current_user['id'], current_user['username'], 'refer_out', 'radiology_order', id,
              f'Referred to {facility}', request.remote_addr)
    db.close()
    return jsonify({'message': f'Referred to {facility}'})


# ─── API: Results ───

@radiology_bp.route('/api/orders/<int:id>/results', methods=['POST'])
@login_required
def api_results_create(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO radiology_results (order_id, findings, impression, recommendation, reported_by, reported_date)
           VALUES (?, ?, ?, ?, ?, DATE('now'))''',
        (id, data.get('findings'), data.get('impression'), data.get('recommendation'), current_user['id']))
    db.execute('UPDATE radiology_orders SET status = ? WHERE id = ?', ('completed', id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'radiology_result', cursor.lastrowid,
              f'Added radiology result for order {id}', request.remote_addr)
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201


@radiology_bp.route('/api/orders/<int:id>/results', methods=['PUT'])
@login_required
def api_results_update(id):
    data = request.json
    db = get_db()
    db.execute(
        '''UPDATE radiology_results SET findings=?, impression=?, recommendation=?
           WHERE id=? AND order_id=?''',
        (data.get('findings'), data.get('impression'), data.get('recommendation'),
         data['result_id'], id))
    db.commit()
    db.close()
    return jsonify({'message': 'Result updated'})


# ─── API: Barcode ───

@radiology_bp.route('/api/barcode/<int:id>', methods=['GET'])
@login_required
def api_barcode_get(id):
    db = get_db()
    order = db.execute('SELECT id, order_number, patient_id, body_part FROM radiology_orders WHERE id = ?', (id,)).fetchone()
    db.close()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    return jsonify({
        'id': order['id'],
        'order_number': order['order_number'],
        'patient_id': order['patient_id'],
        'body_part': order['body_part'],
        'barcode_data': order['order_number']
    })
