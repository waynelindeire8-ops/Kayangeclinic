from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt
from app.database import get_db
from app.auth import login_required, log_audit

pharmacy_bp = Blueprint('pharmacy', __name__, url_prefix='/pharmacy')


@pharmacy_bp.route('/')
@login_required
def inventory_page():
    return render_template('pharmacy/inventory.html')


@pharmacy_bp.route('/dispensing')
@login_required
def dispensing_page():
    return render_template('pharmacy/dispensing.html')


@pharmacy_bp.route('/api/inventory', methods=['GET'])
@login_required
def api_inventory():
    db = get_db()
    search = request.args.get('search', '')
    low_stock = request.args.get('low_stock', '')
    if search:
        items = db.execute(
            '''SELECT * FROM pharmacy_inventory
               WHERE drug_name LIKE ? OR generic_name LIKE ? OR category LIKE ?
               ORDER BY drug_name''',
            (f'%{search}%', f'%{search}%', f'%{search}%')).fetchall()
    elif low_stock:
        items = db.execute(
            'SELECT * FROM pharmacy_inventory WHERE stock_quantity <= reorder_level ORDER BY drug_name').fetchall()
    else:
        items = db.execute('SELECT * FROM pharmacy_inventory ORDER BY drug_name').fetchall()
    db.close()
    return jsonify([dict(i) for i in items])


@pharmacy_bp.route('/api/inventory', methods=['POST'])
@login_required
def api_inventory_add():
    current_user = get_jwt()
    data = request.json
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO pharmacy_inventory (drug_name, generic_name, category, stock_quantity, unit_price,
           expiry_date, supplier, reorder_level)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (data['drug_name'], data.get('generic_name'), data.get('category'),
         data.get('stock_quantity', 0), data['unit_price'], data.get('expiry_date'),
         data.get('supplier'), data.get('reorder_level', 10))
    )
    new_id = cursor.lastrowid
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'pharmacy_inventory', new_id,
              f'Added drug {data["drug_name"]}', request.remote_addr)
    db.close()
    return jsonify({'id': new_id}), 201


@pharmacy_bp.route('/api/inventory/<int:id>', methods=['PUT'])
@login_required
def api_inventory_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    db.execute(
        '''UPDATE pharmacy_inventory SET drug_name=?, generic_name=?, category=?, stock_quantity=?,
           unit_price=?, expiry_date=?, supplier=?, reorder_level=?, updated_at=CURRENT_TIMESTAMP
           WHERE id=?''',
        (data['drug_name'], data.get('generic_name'), data.get('category'),
         data.get('stock_quantity', 0), data['unit_price'], data.get('expiry_date'),
         data.get('supplier'), data.get('reorder_level', 10), id)
    )
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'pharmacy_inventory', id,
              f'Updated drug inventory {data["drug_name"]}', request.remote_addr)
    db.close()
    return jsonify({'message': 'Inventory updated'})


@pharmacy_bp.route('/api/inventory/<int:id>', methods=['DELETE'])
@login_required
def api_inventory_delete(id):
    current_user = get_jwt()
    db = get_db()
    db.execute('DELETE FROM pharmacy_inventory WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'delete', 'pharmacy_inventory', id,
              'Deleted inventory item', request.remote_addr)
    db.close()
    return jsonify({'message': 'Deleted'})


@pharmacy_bp.route('/api/inventory/<int:id>/stock', methods=['PATCH'])
@login_required
def api_adjust_stock(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    item = db.execute('SELECT * FROM pharmacy_inventory WHERE id = ?', (id,)).fetchone()
    if not item:
        db.close()
        return jsonify({'error': 'Item not found'}), 404
    qty = data.get('quantity', 0)
    operation = data.get('operation', 'add')
    new_qty = item['stock_quantity'] + qty if operation == 'add' else item['stock_quantity'] - qty
    if new_qty < 0:
        db.close()
        return jsonify({'error': 'Insufficient stock'}), 400
    db.execute('UPDATE pharmacy_inventory SET stock_quantity=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
               (new_qty, id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'stock_adjust', 'pharmacy_inventory', id,
              f'Adjusted stock from {item["stock_quantity"]} to {new_qty}', request.remote_addr)
    db.close()
    return jsonify({'message': 'Stock adjusted', 'new_quantity': new_qty})


@pharmacy_bp.route('/api/dispensing', methods=['GET'])
@login_required
def api_dispensing_list():
    db = get_db()
    items = db.execute(
        '''SELECT d.*, p.first_name as p_first, p.last_name as p_last,
                  i.drug_name, u.first_name as disp_first, u.last_name as disp_last
           FROM pharmacy_dispensing d
           LEFT JOIN patients p ON d.patient_id = p.id
           LEFT JOIN pharmacy_inventory i ON d.inventory_id = i.id
           LEFT JOIN users u ON d.dispensed_by = u.id
           ORDER BY d.dispensed_date DESC''').fetchall()
    db.close()
    return jsonify([dict(i) for i in items])


@pharmacy_bp.route('/api/dispensing', methods=['POST'])
@login_required
def api_dispense():
    current_user = get_jwt()
    data = request.json
    db = get_db()

    inventory = db.execute('SELECT * FROM pharmacy_inventory WHERE id = ?',
                           (data['inventory_id'],)).fetchone()
    if not inventory or inventory['stock_quantity'] < data['quantity']:
        db.close()
        return jsonify({'error': 'Insufficient stock'}), 400

    cursor = db.execute(
        '''INSERT INTO pharmacy_dispensing (patient_id, inventory_id, quantity, prescription_notes, dispensed_by)
           VALUES (?, ?, ?, ?, ?)''',
        (data['patient_id'], data['inventory_id'], data['quantity'],
         data.get('prescription_notes'), current_user['id'])
    )
    new_qty = inventory['stock_quantity'] - data['quantity']
    db.execute('UPDATE pharmacy_inventory SET stock_quantity=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
               (new_qty, data['inventory_id']))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'dispense', 'pharmacy_dispensing', cursor.lastrowid,
              f'Dispensed {data["quantity"]} of {inventory["drug_name"]} to patient {data["patient_id"]}',
              request.remote_addr)
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201
