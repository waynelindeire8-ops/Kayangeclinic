from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt
from app.database import get_db
from app.auth import login_required, role_required, log_audit

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')


@billing_bp.route('/')
@login_required
def list_page():
    return render_template('billing/list.html')


@billing_bp.route('/new')
@login_required
def new_page():
    return render_template('billing/form.html')


@billing_bp.route('/<int:id>')
@login_required
def invoice_page(id):
    return render_template('billing/invoice.html', billing_id=id)


@billing_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    db = get_db()
    status = request.args.get('status', '')
    query = '''SELECT b.*, p.first_name as p_first, p.last_name as p_last
               FROM billing b
               LEFT JOIN patients p ON b.patient_id = p.id
               WHERE 1=1'''
    params = []
    if status:
        query += ' AND b.payment_status = ?'
        params.append(status)
    query += ' ORDER BY b.created_at DESC'
    billing = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(b) for b in billing])


@billing_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    db = get_db()
    bill = db.execute(
        '''SELECT b.*, p.first_name as p_first, p.last_name as p_last, p.phone as p_phone
           FROM billing b
           LEFT JOIN patients p ON b.patient_id = p.id
           WHERE b.id = ?''', (id,)).fetchone()
    if not bill:
        db.close()
        return jsonify({'error': 'Billing record not found'}), 404
    items = db.execute('SELECT * FROM billing_items WHERE billing_id = ?', (id,)).fetchall()
    db.close()
    result = dict(bill)
    result['items'] = [dict(i) for i in items]
    return jsonify(result)


@billing_bp.route('/api', methods=['POST'])
@login_required
def api_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()

    last_inv = db.execute('SELECT invoice_number FROM billing ORDER BY id DESC LIMIT 1').fetchone()
    if last_inv:
        num = int(last_inv['invoice_number'].replace('INV-', '')) + 1
    else:
        num = 1001
    invoice_number = f'INV-{num}'

    total = sum(item.get('total_price', 0) for item in data.get('items', []))
    amount_paid = data.get('amount_paid', 0)
    balance = total - amount_paid
    payment_status = 'paid' if balance <= 0 else ('partial' if amount_paid > 0 else 'pending')

    cursor = db.execute(
        '''INSERT INTO billing (patient_id, appointment_id, package_id, invoice_number, total_amount,
           amount_paid, balance, payment_method, payment_status, insurance_claim_id, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data['patient_id'], data.get('appointment_id'), data.get('package_id'),
         invoice_number, total, amount_paid, balance, data.get('payment_method', 'cash'),
         payment_status, data.get('insurance_claim_id'), current_user['id'])
    )
    billing_id = cursor.lastrowid

    for item in data.get('items', []):
        db.execute(
            '''INSERT INTO billing_items (billing_id, item_name, item_type, quantity, unit_price, total_price)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (billing_id, item['item_name'], item.get('item_type', 'consultation'),
             item.get('quantity', 1), item['unit_price'], item['total_price'])
        )

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'billing', billing_id,
              f'Created invoice {invoice_number} for patient {data["patient_id"]}', request.remote_addr)
    db.close()
    return jsonify({'id': billing_id, 'invoice_number': invoice_number}), 201


@billing_bp.route('/api/<int:id>/payment', methods=['PATCH'])
@login_required
def api_add_payment(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    bill = db.execute('SELECT * FROM billing WHERE id = ?', (id,)).fetchone()
    if not bill:
        db.close()
        return jsonify({'error': 'Billing record not found'}), 404

    new_paid = bill['amount_paid'] + data.get('amount', 0)
    new_balance = bill['total_amount'] - new_paid
    new_status = 'paid' if new_balance <= 0 else 'partial'

    db.execute(
        '''UPDATE billing SET amount_paid=?, balance=?, payment_status=?, payment_method=?,
           insurance_claim_id=COALESCE(?, insurance_claim_id), updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (new_paid, new_balance, new_status, data.get('payment_method', bill['payment_method']),
         data.get('insurance_claim_id'), id)
    )
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'payment', 'billing', id,
              f'Payment of {data.get("amount", 0)} added to invoice {bill["invoice_number"]}',
              request.remote_addr)
    db.close()
    return jsonify({'message': 'Payment recorded', 'balance': new_balance, 'status': new_status})


@billing_bp.route('/api/packages', methods=['GET'])
@login_required
def api_packages():
    db = get_db()
    packages = db.execute('SELECT * FROM packages WHERE is_active = 1').fetchall()
    result = []
    for pkg in packages:
        p = dict(pkg)
        services = db.execute('SELECT * FROM package_services WHERE package_id = ?', (p['id'],)).fetchall()
        p['services'] = [dict(s) for s in services]
        result.append(p)
    db.close()
    return jsonify(result)


@billing_bp.route('/api/packages', methods=['POST'])
@role_required('admin')
def api_create_package():
    current_user = get_jwt()
    data = request.json
    db = get_db()
    cursor = db.execute(
        'INSERT INTO packages (package_name, description, total_amount) VALUES (?, ?, ?)',
        (data['package_name'], data.get('description'), data['total_amount'])
    )
    pkg_id = cursor.lastrowid
    for service in data.get('services', []):
        db.execute('INSERT INTO package_services (package_id, service_name, service_type) VALUES (?, ?, ?)',
                   (pkg_id, service['service_name'], service.get('service_type')))
    db.commit()
    db.close()
    return jsonify({'id': pkg_id}), 201


@billing_bp.route('/api/unbilled-services', methods=['GET'])
@login_required
def api_unbilled():
    patient_id = request.args.get('patient_id')
    db = get_db()
    data = {}
    consultations = db.execute(
        '''SELECT c.id, c.consultation_type, c.created_at
           FROM consultations c
           WHERE c.patient_id = ? AND c.id NOT IN (
               SELECT bi.resource_id FROM billing_items bi WHERE bi.item_type = 'consultation'
           )''', (patient_id,)).fetchall()
    data['consultations'] = [dict(c) for c in consultations]

    lab_tests = db.execute(
        'SELECT * FROM lab_tests WHERE patient_id = ? AND status = ?', (patient_id, 'completed')).fetchall()
    data['lab_tests'] = [dict(l) for l in lab_tests]

    procedures = db.execute(
        'SELECT * FROM procedures WHERE patient_id = ?', (patient_id,)).fetchall()
    data['procedures'] = [dict(p) for p in procedures]
    db.close()
    return jsonify(data)
