from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from datetime import date, datetime
from app.database import get_db
from app.auth import login_required, role_required, log_audit

insurance_bp = Blueprint('insurance', __name__, url_prefix='/insurance')


# ─── Pages ───

@insurance_bp.route('/providers', strict_slashes=False)
@login_required
def providers_page():
    return render_template('insurance/providers.html')


@insurance_bp.route('/eligibility', strict_slashes=False)
@login_required
def eligibility_page():
    return render_template('insurance/eligibility.html')


@insurance_bp.route('/claims', strict_slashes=False)
@login_required
def claims_page():
    return render_template('insurance/claims.html')


@insurance_bp.route('/claims/new', strict_slashes=False)
@login_required
def claim_new_page():
    return render_template('insurance/claim_form.html')


@insurance_bp.route('/claims/<int:id>', strict_slashes=False)
@login_required
def claim_detail_page(id):
    return render_template('insurance/claim_detail.html', claim_id=id)


@insurance_bp.route('/claims/<int:id>/edit', strict_slashes=False)
@login_required
def claim_edit_page(id):
    return render_template('insurance/claim_form.html', claim_id=id)


# ─── API: Providers ───

@insurance_bp.route('/api/providers', methods=['GET'])
@login_required
def api_providers_list():
    db = get_db()
    providers = db.execute('SELECT * FROM insurance_providers ORDER BY name').fetchall()
    db.close()
    return jsonify([dict(p) for p in providers])


@insurance_bp.route('/api/providers', methods=['POST'])
@login_required
@role_required('admin')
def api_providers_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO insurance_providers (name, code, contact_person, phone, email, address)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (data['name'], data.get('code'), data.get('contact_person'),
         data.get('phone'), data.get('email'), data.get('address')))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'insurance_provider', cursor.lastrowid,
              f'Created provider: {data["name"]}', request.remote_addr)
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201


@insurance_bp.route('/api/providers/<int:id>', methods=['PUT'])
@login_required
@role_required('admin')
def api_providers_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    db.execute(
        '''UPDATE insurance_providers SET name=?, code=?, contact_person=?, phone=?, email=?,
           address=?, is_active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (data['name'], data.get('code'), data.get('contact_person'),
         data.get('phone'), data.get('email'), data.get('address'),
         data.get('is_active', 1), id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'insurance_provider', id,
              'Updated provider', request.remote_addr)
    db.close()
    return jsonify({'message': 'Provider updated'})


@insurance_bp.route('/api/providers/<int:id>', methods=['DELETE'])
@login_required
@role_required('admin')
def api_providers_delete(id):
    current_user = get_jwt()
    db = get_db()
    db.execute('UPDATE insurance_providers SET is_active = 0 WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'deactivate', 'insurance_provider', id,
              'Deactivated provider', request.remote_addr)
    db.close()
    return jsonify({'message': 'Provider deactivated'})


# ─── API: Patient Insurance ───

@insurance_bp.route('/api/policies', methods=['GET'])
@login_required
def api_policies_list():
    db = get_db()
    patient_id = request.args.get('patient_id', '')
    if patient_id:
        policies = db.execute(
            '''SELECT pi.*, ip.name as provider_name, ip.code as provider_code,
                      p.first_name as p_first, p.last_name as p_last, p.patient_id as p_patient_id
               FROM patient_insurance pi
               LEFT JOIN insurance_providers ip ON pi.provider_id = ip.id
               LEFT JOIN patients p ON pi.patient_id = p.id
               WHERE pi.patient_id = ? ORDER BY pi.is_primary DESC, pi.created_at DESC''',
            (patient_id,)).fetchall()
    else:
        policies = db.execute(
            '''SELECT pi.*, ip.name as provider_name, ip.code as provider_code,
                      p.first_name as p_first, p.last_name as p_last, p.patient_id as p_patient_id
               FROM patient_insurance pi
               LEFT JOIN insurance_providers ip ON pi.provider_id = ip.id
               LEFT JOIN patients p ON pi.patient_id = p.id
               ORDER BY pi.created_at DESC LIMIT 200''').fetchall()
    db.close()
    return jsonify([dict(p) for p in policies])


@insurance_bp.route('/api/policies', methods=['POST'])
@login_required
def api_policies_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO patient_insurance (patient_id, provider_id, policy_number, member_name,
           group_number, effective_date, expiry_date, is_primary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (data['patient_id'], data['provider_id'], data['policy_number'],
         data.get('member_name'), data.get('group_number'),
         data.get('effective_date'), data.get('expiry_date'),
         data.get('is_primary', 1)))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'patient_insurance', cursor.lastrowid,
              f'Added policy {data["policy_number"]} for patient {data["patient_id"]}', request.remote_addr)
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201


@insurance_bp.route('/api/policies/<int:id>', methods=['PUT'])
@login_required
def api_policies_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    db.execute(
        '''UPDATE patient_insurance SET provider_id=?, policy_number=?, member_name=?,
           group_number=?, effective_date=?, expiry_date=?, is_primary=?, is_active=?
           WHERE id=?''',
        (data['provider_id'], data['policy_number'], data.get('member_name'),
         data.get('group_number'), data.get('effective_date'), data.get('expiry_date'),
         data.get('is_primary', 1), data.get('is_active', 1), id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'patient_insurance', id,
              'Updated policy', request.remote_addr)
    db.close()
    return jsonify({'message': 'Policy updated'})


@insurance_bp.route('/api/policies/<int:id>', methods=['DELETE'])
@login_required
def api_policies_delete(id):
    current_user = get_jwt()
    db = get_db()
    db.execute('DELETE FROM patient_insurance WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'delete', 'patient_insurance', id,
              'Deleted policy', request.remote_addr)
    db.close()
    return jsonify({'message': 'Deleted'})


# ─── API: Eligibility ───

@insurance_bp.route('/api/eligibility', methods=['GET'])
@login_required
def api_eligibility_check():
    patient_id = request.args.get('patient_id', '')
    provider_id = request.args.get('provider_id', '')
    if not patient_id:
        return jsonify({'error': 'Patient ID required'}), 400

    db = get_db()
    query = '''SELECT pi.*, ip.name as provider_name, ip.code as provider_code,
                      p.first_name as p_first, p.last_name as p_last, p.dob, p.gender
               FROM patient_insurance pi
               LEFT JOIN insurance_providers ip ON pi.provider_id = ip.id
               LEFT JOIN patients p ON pi.patient_id = p.id
               WHERE pi.patient_id = ? AND pi.is_active = 1'''
    params = [patient_id]
    if provider_id:
        query += ' AND pi.provider_id = ?'
        params.append(provider_id)
    query += ' ORDER BY pi.is_primary DESC'

    policies = db.execute(query, params).fetchall()
    db.close()

    results = []
    today = date.today().isoformat()
    for pol in policies:
        p = dict(pol)
        effective = p.get('effective_date')
        expiry = p.get('expiry_date')
        if effective and effective > today:
            p['eligibility'] = 'not_effective'
            p['eligibility_message'] = 'Policy not yet effective'
        elif expiry and expiry < today:
            p['eligibility'] = 'expired'
            p['eligibility_message'] = 'Policy expired on ' + expiry
        else:
            p['eligibility'] = 'active'
            p['eligibility_message'] = 'Coverage active - ' + (p.get('provider_name') or '') + ' (' + (p.get('policy_number') or '') + ')'
        results.append(p)

    return jsonify(results)


# ─── API: Claims ───

@insurance_bp.route('/api/claims', methods=['GET'])
@login_required
def api_claims_list():
    db = get_db()
    status = request.args.get('status', '')
    patient_id = request.args.get('patient_id', '')
    provider_id = request.args.get('provider_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = '''SELECT ic.*, p.first_name as p_first, p.last_name as p_last,
                      p.patient_id as p_patient_id,
                      ip.name as provider_name, ip.code as provider_code
               FROM insurance_claims ic
               LEFT JOIN patients p ON ic.patient_id = p.id
               LEFT JOIN insurance_providers ip ON ic.provider_id = ip.id
               WHERE 1=1'''
    params = []
    if status:
        query += ' AND ic.status = ?'
        params.append(status)
    if patient_id:
        query += ' AND ic.patient_id = ?'
        params.append(patient_id)
    if provider_id:
        query += ' AND ic.provider_id = ?'
        params.append(provider_id)
    if date_from:
        query += ' AND ic.claim_date >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND ic.claim_date <= ?'
        params.append(date_to)
    query += ' ORDER BY ic.created_at DESC'

    claims = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(c) for c in claims])


@insurance_bp.route('/api/claims', methods=['POST'])
@login_required
def api_claims_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()

    claim_count = db.execute('SELECT COUNT(*) as c FROM insurance_claims').fetchone()['c']
    claim_number = f"CLM-{date.today().strftime('%Y%m')}-{claim_count + 1:04d}"

    cursor = db.execute(
        '''INSERT INTO insurance_claims (claim_number, patient_id, provider_id, policy_id,
           billing_id, consultation_id, claim_date, service_date, total_amount, notes, created_by)
           VALUES (?, ?, ?, ?, ?, ?, DATE('now'), ?, ?, ?, ?)''',
        (claim_number, data['patient_id'], data['provider_id'], data.get('policy_id'),
         data.get('billing_id'), data.get('consultation_id'),
         data.get('service_date'), data['total_amount'],
         data.get('notes'), current_user['id']))
    claim_id = cursor.lastrowid

    for item in data.get('items', []):
        db.execute(
            '''INSERT INTO claim_items (claim_id, description, procedure_code, quantity, unit_price, total_price)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (claim_id, item['description'], item.get('procedure_code'),
             item.get('quantity', 1), item['unit_price'], item['total_price']))

    db.execute(
        '''INSERT INTO claim_status_history (claim_id, new_status, notes, changed_by)
           VALUES (?, 'draft', 'Claim created', ?)''',
        (claim_id, current_user['id']))

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'insurance_claim', claim_id,
              f'Created claim {claim_number}', request.remote_addr)
    db.close()
    return jsonify({'id': claim_id, 'claim_number': claim_number}), 201


@insurance_bp.route('/api/claims/<int:id>', methods=['GET'])
@login_required
def api_claims_get(id):
    db = get_db()
    claim = db.execute(
        '''SELECT ic.*, p.first_name as p_first, p.last_name as p_last, p.dob, p.gender,
                  p.patient_id as p_patient_id, p.phone as p_phone,
                  ip.name as provider_name, ip.code as provider_code,
                  pi.policy_number, pi.member_name
           FROM insurance_claims ic
           LEFT JOIN patients p ON ic.patient_id = p.id
           LEFT JOIN insurance_providers ip ON ic.provider_id = ip.id
           LEFT JOIN patient_insurance pi ON ic.policy_id = pi.id
           WHERE ic.id = ?''', (id,)).fetchone()
    if not claim:
        db.close()
        return jsonify({'error': 'Claim not found'}), 404

    items = db.execute('SELECT * FROM claim_items WHERE claim_id = ?', (id,)).fetchall()
    history = db.execute(
        '''SELECT csh.*, u.first_name as u_first, u.last_name as u_last
           FROM claim_status_history csh
           LEFT JOIN users u ON csh.changed_by = u.id
           WHERE csh.claim_id = ? ORDER BY csh.changed_at''', (id,)).fetchall()

    db.close()
    result = dict(claim)
    result['items'] = [dict(i) for i in items]
    result['history'] = [dict(h) for h in history]
    return jsonify(result)


@insurance_bp.route('/api/claims/<int:id>', methods=['PUT'])
@login_required
def api_claims_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()

    db.execute(
        '''UPDATE insurance_claims SET provider_id=?, policy_id=?, service_date=?,
           total_amount=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (data['provider_id'], data.get('policy_id'), data.get('service_date'),
         data['total_amount'], data.get('notes'), id))

    existing_items = {r['id'] for r in db.execute(
        'SELECT id FROM claim_items WHERE claim_id = ?', (id,)).fetchall()}
    submitted_ids = set()

    for item in data.get('items', []):
        item_id = item.get('id')
        if item_id and item_id in existing_items:
            submitted_ids.add(item_id)
            db.execute(
                '''UPDATE claim_items SET description=?, procedure_code=?, quantity=?,
                   unit_price=?, total_price=? WHERE id=?''',
                (item['description'], item.get('procedure_code'),
                 item.get('quantity', 1), item['unit_price'], item['total_price'], item_id))
        else:
            cursor = db.execute(
                '''INSERT INTO claim_items (claim_id, description, procedure_code, quantity, unit_price, total_price)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (id, item['description'], item.get('procedure_code'),
                 item.get('quantity', 1), item['unit_price'], item['total_price']))
            submitted_ids.add(cursor.lastrowid)

    for did in existing_items - submitted_ids:
        db.execute('DELETE FROM claim_items WHERE id = ?', (did,))

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'insurance_claim', id,
              'Updated claim', request.remote_addr)
    db.close()
    return jsonify({'message': 'Claim updated'})


@insurance_bp.route('/api/claims/<int:id>', methods=['DELETE'])
@login_required
def api_claims_delete(id):
    current_user = get_jwt()
    db = get_db()
    db.execute('DELETE FROM claim_items WHERE claim_id = ?', (id,))
    db.execute('DELETE FROM claim_status_history WHERE claim_id = ?', (id,))
    db.execute('DELETE FROM insurance_claims WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'delete', 'insurance_claim', id,
              'Deleted claim', request.remote_addr)
    db.close()
    return jsonify({'message': 'Deleted'})


@insurance_bp.route('/api/claims/<int:id>/status', methods=['PUT'])
@login_required
def api_claims_status(id):
    current_user = get_jwt()
    data = request.json
    new_status = data.get('status')
    valid = ('draft', 'submitted', 'in_review', 'additional_info', 'approved',
             'partially_approved', 'denied', 'appealed', 'paid', 'cancelled')
    if new_status not in valid:
        return jsonify({'error': 'Invalid status'}), 400

    db = get_db()
    claim = db.execute('SELECT status FROM insurance_claims WHERE id = ?', (id,)).fetchone()
    if not claim:
        db.close()
        return jsonify({'error': 'Claim not found'}), 404

    old_status = claim['status']
    db.execute('UPDATE insurance_claims SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
               (new_status, id))

    if new_status == 'submitted':
        db.execute('UPDATE insurance_claims SET submitted_date = DATE("now") WHERE id = ?', (id,))
    elif new_status in ('approved', 'partially_approved', 'paid'):
        db.execute('UPDATE insurance_claims SET reviewed_date = DATE("now") WHERE id = ?', (id,))
        if new_status == 'paid':
            db.execute('UPDATE insurance_claims SET paid_date = DATE("now") WHERE id = ?', (id,))
    elif new_status == 'denied':
        db.execute('UPDATE insurance_claims SET denial_reason = ? WHERE id = ?',
                   (data.get('notes', ''), id))

    if data.get('approved_amount') is not None:
        db.execute('UPDATE insurance_claims SET approved_amount = ? WHERE id = ?',
                   (data['approved_amount'], id))
    if data.get('paid_amount') is not None:
        db.execute('UPDATE insurance_claims SET paid_amount = ? WHERE id = ?',
                   (data['paid_amount'], id))

    db.execute(
        '''INSERT INTO claim_status_history (claim_id, old_status, new_status, notes, changed_by)
           VALUES (?, ?, ?, ?, ?)''',
        (id, old_status, new_status, data.get('notes'), current_user['id']))

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'status_change', 'insurance_claim', id,
              f'Claim status: {old_status} -> {new_status}', request.remote_addr)
    db.close()
    return jsonify({'message': 'Status updated'})


@insurance_bp.route('/api/claims/<int:id>/submit', methods=['POST'])
@login_required
def api_claims_submit(id):
    return api_claims_status(id) if request.json else (jsonify({'error': 'No data'}), 400)


# ─── API: Stats ───

@insurance_bp.route('/api/stats', methods=['GET'])
@login_required
def api_stats():
    db = get_db()
    total = db.execute('SELECT COUNT(*) as c FROM insurance_claims').fetchone()['c']
    pending = db.execute(
        "SELECT COUNT(*) as c FROM insurance_claims WHERE status IN ('draft','submitted','in_review','additional_info')"
    ).fetchone()['c']
    approved = db.execute(
        "SELECT COUNT(*) as c FROM insurance_claims WHERE status IN ('approved','partially_approved')"
    ).fetchone()['c']
    paid = db.execute("SELECT COUNT(*) as c FROM insurance_claims WHERE status = 'paid'").fetchone()['c']
    denied = db.execute("SELECT COUNT(*) as c FROM insurance_claims WHERE status = 'denied'").fetchone()['c']
    total_claimed = db.execute('SELECT COALESCE(SUM(total_amount),0) as s FROM insurance_claims').fetchone()['s']
    total_paid = db.execute('SELECT COALESCE(SUM(paid_amount),0) as s FROM insurance_claims').fetchone()['s']
    total_approved = db.execute('SELECT COALESCE(SUM(approved_amount),0) as s FROM insurance_claims').fetchone()['s']
    db.close()
    return jsonify({
        'total': total, 'pending': pending, 'approved': approved,
        'paid': paid, 'denied': denied,
        'total_claimed': total_claimed, 'total_paid': total_paid, 'total_approved': total_approved
    })


@insurance_bp.route('/api/authorization-rules', methods=['GET'])
@login_required
def api_authorization_rules():
    provider_id = request.args.get('provider_id', type=int)
    item_name = request.args.get('item', '')
    db = get_db()
    query = 'SELECT * FROM insurance_authorization_rules WHERE 1=1'
    params = []
    if provider_id:
        query += ' AND provider_id = ?'
        params.append(provider_id)
    if item_name:
        query += ' AND LOWER(item_name) LIKE ?'
        params.append(f'%{item_name.lower()}%')
    rules = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(r) for r in rules])


@insurance_bp.route('/api/authorization-rules/check', methods=['POST'])
@login_required
def api_authorization_check():
    data = request.json
    patient_id = data.get('patient_id')
    item_name = data.get('item', '').strip()
    item_type = data.get('item_type', 'pharmacy')

    if not patient_id or not item_name:
        return jsonify({'error': 'Patient ID and item required'}), 400

    db = get_db()
    patient = db.execute(
        'SELECT scheme_id FROM patients WHERE id = ?', (patient_id,)).fetchone()
    if not patient or not patient['scheme_id']:
        db.close()
        return jsonify({'requires_auth': False, 'reason': 'No insurance scheme'})

    rule = db.execute(
        '''SELECT r.*, p.name as provider_name
           FROM insurance_authorization_rules r
           JOIN insurance_providers p ON r.provider_id = p.id
           WHERE r.provider_id = ? AND r.item_type = ? AND LOWER(r.item_name) = ? AND r.requires_auth = 1''',
        (patient['scheme_id'], item_type, item_name.lower())).fetchone()
    db.close()

    if rule:
        return jsonify({'requires_auth': True, 'provider': rule['provider_name'], 'item': rule['item_name']})
    return jsonify({'requires_auth': False, 'reason': 'No restriction'})
