from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from datetime import date
from app.database import get_db
from app.auth import login_required, log_audit

lab_invoices_bp = Blueprint('lab_invoices', __name__, url_prefix='/lab/invoices')


# ─── Pages ───

@lab_invoices_bp.route('/', strict_slashes=False)
@login_required
def list_page():
    return render_template('lab/invoices.html')


@lab_invoices_bp.route('/new', strict_slashes=False)
@login_required
def create_page():
    return render_template('lab/invoice_form.html')


@lab_invoices_bp.route('/<int:id>', strict_slashes=False)
@login_required
def detail_page(id):
    return render_template('lab/invoice_detail.html', invoice_id=id)


# ─── API: List ───

@lab_invoices_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    db = get_db()
    status = request.args.get('status', '')
    patient_id = request.args.get('patient_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = '''SELECT li.*, p.first_name as p_first, p.last_name as p_last,
                      p.patient_id as p_patient_id, u.first_name as u_first, u.last_name as u_last
               FROM lab_invoices li
               LEFT JOIN patients p ON li.patient_id = p.id
               LEFT JOIN users u ON li.created_by = u.id
               WHERE 1=1'''
    params = []
    if status:
        query += ' AND li.payment_status = ?'
        params.append(status)
    if patient_id:
        query += ' AND li.patient_id = ?'
        params.append(patient_id)
    if date_from:
        query += ' AND DATE(li.created_at) >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND DATE(li.created_at) <= ?'
        params.append(date_to)
    query += ' ORDER BY li.created_at DESC'
    invoices = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(i) for i in invoices])


# ─── API: Get ───

@lab_invoices_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    db = get_db()
    invoice = db.execute(
        '''SELECT li.*, p.first_name as p_first, p.last_name as p_last,
                  p.patient_id as p_patient_id, p.phone as p_phone,
                  u.first_name as u_first, u.last_name as u_last
           FROM lab_invoices li
           LEFT JOIN patients p ON li.patient_id = p.id
           LEFT JOIN users u ON li.created_by = u.id
           WHERE li.id = ?''', (id,)).fetchone()
    if not invoice:
        db.close()
        return jsonify({'error': 'Invoice not found'}), 404
    items = db.execute(
        '''SELECT lii.*, lt.test_name, lt.test_category
           FROM lab_invoice_items lii
           LEFT JOIN lab_tests lt ON lii.lab_test_id = lt.id
           WHERE lii.lab_invoice_id = ?''', (id,)).fetchall()
    db.close()
    result = dict(invoice)
    result['items'] = [dict(i) for i in items]
    return jsonify(result)


# ─── API: Create ───

@lab_invoices_bp.route('/api', methods=['POST'])
@login_required
def api_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()

    last_inv = db.execute('SELECT invoice_number FROM lab_invoices ORDER BY id DESC LIMIT 1').fetchone()
    if last_inv:
        num = int(last_inv['invoice_number'].replace('LAB-', '')) + 1
    else:
        num = 1001
    invoice_number = f'LAB-{num}'

    total = sum(item.get('total_price', 0) for item in data.get('items', []))
    amount_paid = data.get('amount_paid', 0)
    balance = total - amount_paid
    payment_status = 'paid' if balance <= 0 else ('partial' if amount_paid > 0 else 'pending')

    cursor = db.execute(
        '''INSERT INTO lab_invoices (invoice_number, patient_id, total_amount, amount_paid, balance,
           payment_method, payment_status, notes, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (invoice_number, data['patient_id'], total, amount_paid, balance,
         data.get('payment_method', 'cash'), payment_status, data.get('notes'), current_user['id']))
    invoice_id = cursor.lastrowid

    for item in data.get('items', []):
        db.execute(
            '''INSERT INTO lab_invoice_items (lab_invoice_id, lab_test_id, item_name, description,
               quantity, unit_price, total_price)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (invoice_id, item.get('lab_test_id'), item['item_name'], item.get('description'),
             item.get('quantity', 1), item['unit_price'], item['total_price']))

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'lab_invoice', invoice_id,
              f'Created lab invoice {invoice_number}', request.remote_addr)
    db.close()
    return jsonify({'id': invoice_id, 'invoice_number': invoice_number}), 201


# ─── API: Update ───

@lab_invoices_bp.route('/api/<int:id>', methods=['PUT'])
@login_required
def api_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()

    total = sum(item.get('total_price', 0) for item in data.get('items', []))
    amount_paid = data.get('amount_paid', 0)
    balance = total - amount_paid
    payment_status = 'paid' if balance <= 0 else ('partial' if amount_paid > 0 else 'pending')

    db.execute(
        '''UPDATE lab_invoices SET total_amount=?, amount_paid=?, balance=?,
           payment_method=?, payment_status=?, notes=?, updated_at=CURRENT_TIMESTAMP
           WHERE id=?''',
        (total, amount_paid, balance, data.get('payment_method', 'cash'),
         payment_status, data.get('notes'), id))

    db.execute('DELETE FROM lab_invoice_items WHERE lab_invoice_id = ?', (id,))
    for item in data.get('items', []):
        db.execute(
            '''INSERT INTO lab_invoice_items (lab_invoice_id, lab_test_id, item_name, description,
               quantity, unit_price, total_price)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (id, item.get('lab_test_id'), item['item_name'], item.get('description'),
             item.get('quantity', 1), item['unit_price'], item['total_price']))

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'lab_invoice', id,
              'Updated lab invoice', request.remote_addr)
    db.close()
    return jsonify({'message': 'Invoice updated'})


# ─── API: Delete ───

@lab_invoices_bp.route('/api/<int:id>', methods=['DELETE'])
@login_required
def api_delete(id):
    current_user = get_jwt()
    db = get_db()
    db.execute('DELETE FROM lab_invoice_items WHERE lab_invoice_id = ?', (id,))
    db.execute('DELETE FROM lab_invoices WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'delete', 'lab_invoice', id,
              'Deleted lab invoice', request.remote_addr)
    db.close()
    return jsonify({'message': 'Deleted'})


# ─── API: Record Payment ───

@lab_invoices_bp.route('/api/<int:id>/payment', methods=['PATCH'])
@login_required
def api_payment(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    invoice = db.execute('SELECT * FROM lab_invoices WHERE id = ?', (id,)).fetchone()
    if not invoice:
        db.close()
        return jsonify({'error': 'Invoice not found'}), 404

    new_paid = invoice['amount_paid'] + data.get('amount', 0)
    new_balance = invoice['total_amount'] - new_paid
    new_status = 'paid' if new_balance <= 0 else 'partial'

    db.execute(
        '''UPDATE lab_invoices SET amount_paid=?, balance=?, payment_status=?,
           payment_method=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (new_paid, new_balance, new_status, data.get('payment_method', invoice['payment_method']), id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'payment', 'lab_invoice', id,
              f'Payment of {data.get("amount", 0)} recorded', request.remote_addr)
    db.close()
    return jsonify({'message': 'Payment recorded', 'amount_paid': new_paid, 'balance': new_balance, 'payment_status': new_status})


# ─── API: Dashboard Stats ───

@lab_invoices_bp.route('/api/dashboard', methods=['GET'])
@login_required
def api_dashboard():
    db = get_db()
    today = date.today().isoformat()
    today_revenue = db.execute(
        'SELECT COALESCE(SUM(amount_paid), 0) as c FROM lab_invoices WHERE DATE(created_at) = ?',
        (today,)).fetchone()['c']
    total_revenue = db.execute(
        'SELECT COALESCE(SUM(amount_paid), 0) as c FROM lab_invoices').fetchone()['c']
    pending = db.execute(
        'SELECT COALESCE(SUM(balance), 0) as c FROM lab_invoices WHERE payment_status != "paid"'
    ).fetchone()['c']
    today_count = db.execute(
        'SELECT COUNT(*) as c FROM lab_invoices WHERE DATE(created_at) = ?', (today,)
    ).fetchone()['c']
    recent = db.execute(
        '''SELECT li.*, p.first_name as p_first, p.last_name as p_last
           FROM lab_invoices li
           LEFT JOIN patients p ON li.patient_id = p.id
           ORDER BY li.created_at DESC LIMIT 10'''
    ).fetchall()
    db.close()
    return jsonify({
        'today_revenue': today_revenue, 'total_revenue': total_revenue,
        'pending': pending, 'today_count': today_count,
        'recent': [dict(r) for r in recent]
    })


# ─── API: From Lab Order ───

@lab_invoices_bp.route('/api/from-order/<int:order_id>', methods=['POST'])
@login_required
def api_from_order(order_id):
    current_user = get_jwt()
    data = request.json
    db = get_db()

    order = db.execute('SELECT * FROM lab_tests WHERE id = ?', (order_id,)).fetchone()
    if not order:
        db.close()
        return jsonify({'error': 'Lab order not found'}), 404

    catalog = db.execute('SELECT * FROM lab_test_catalog WHERE test_name = ?',
                         (order['test_name'],)).fetchone()
    price = data.get('price', catalog['default_price'] if catalog else 0)

    last_inv = db.execute('SELECT invoice_number FROM lab_invoices ORDER BY id DESC LIMIT 1').fetchone()
    if last_inv:
        num = int(last_inv['invoice_number'].replace('LAB-', '')) + 1
    else:
        num = 1001
    invoice_number = f'LAB-{num}'

    amount_paid = data.get('amount_paid', 0)
    balance = price - amount_paid
    payment_status = 'paid' if balance <= 0 else ('partial' if amount_paid > 0 else 'pending')

    cursor = db.execute(
        '''INSERT INTO lab_invoices (invoice_number, patient_id, total_amount, amount_paid, balance,
           payment_method, payment_status, notes, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (invoice_number, order['patient_id'], price, amount_paid, balance,
         data.get('payment_method', 'cash'), payment_status,
         f'Auto-created from lab order #{order_id}', current_user['id']))
    invoice_id = cursor.lastrowid

    db.execute(
        '''INSERT INTO lab_invoice_items (lab_invoice_id, lab_test_id, item_name, description,
           quantity, unit_price, total_price)
           VALUES (?, ?, ?, ?, 1, ?, ?)''',
        (invoice_id, order_id, order['test_name'], order.get('test_category'), price, price))

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'lab_invoice', invoice_id,
              f'Created lab invoice {invoice_number} from order #{order_id}', request.remote_addr)
    db.close()
    return jsonify({'id': invoice_id, 'invoice_number': invoice_number}), 201
