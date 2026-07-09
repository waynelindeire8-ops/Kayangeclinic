from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required, log_audit

consultations_bp = Blueprint('consultations', __name__, url_prefix='/consultations')


@consultations_bp.route('/', strict_slashes=False)
@login_required
def list_page():
    return render_template('consultations/list.html')


@consultations_bp.route('/new', strict_slashes=False)
@login_required
def new_page():
    return render_template('consultations/form.html')


@consultations_bp.route('/<int:id>/edit', strict_slashes=False)
@login_required
def edit_page(id):
    return render_template('consultations/form.html', consultation_id=id)


@consultations_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    db = get_db()
    patient_id = request.args.get('patient_id', '')
    query = '''SELECT c.*, p.first_name as p_first, p.last_name as p_last,
                      u.first_name as d_first, u.last_name as d_last
               FROM consultations c
               LEFT JOIN patients p ON c.patient_id = p.id
               LEFT JOIN users u ON c.doctor_id = u.id
               WHERE 1=1'''
    params = []
    if patient_id:
        query += ' AND c.patient_id = ?'
        params.append(patient_id)
    query += ' ORDER BY c.created_at DESC'
    consultations = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(c) for c in consultations])


@consultations_bp.route('/api', methods=['POST'])
@login_required
def api_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO consultations (patient_id, doctor_id, appointment_id, consultation_type, diagnosis, notes)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (data['patient_id'], data.get('doctor_id', current_user['id']),
         data.get('appointment_id'), data.get('consultation_type', 'general'),
         data.get('diagnosis'), data.get('notes'))
    )
    new_id = cursor.lastrowid
    if data.get('appointment_id'):
        db.execute('UPDATE appointments SET status = ? WHERE id = ?',
                   ('completed', data['appointment_id']))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'consultation', new_id,
              f'Created consultation for patient {data["patient_id"]}', request.remote_addr)
    db.close()
    return jsonify({'id': new_id}), 201


@consultations_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    db = get_db()
    c = db.execute(
        '''SELECT c.*, p.first_name as p_first, p.last_name as p_last,
                  p.dob, p.gender, p.blood_group,
                  u.first_name as d_first, u.last_name as d_last
           FROM consultations c
           LEFT JOIN patients p ON c.patient_id = p.id
           LEFT JOIN users u ON c.doctor_id = u.id
           WHERE c.id = ?''', (id,)).fetchone()
    vitals = db.execute(
        'SELECT * FROM vital_signs WHERE consultation_id = ? ORDER BY recorded_at DESC', (id,)).fetchall()
    examinations = db.execute(
        'SELECT * FROM medical_examinations WHERE consultation_id = ?', (id,)).fetchall()
    diagnoses = db.execute(
        'SELECT * FROM diagnoses WHERE consultation_id = ?', (id,)).fetchall()
    prescriptions = db.execute(
        'SELECT * FROM prescriptions WHERE consultation_id = ? ORDER BY created_at DESC', (id,)).fetchall()
    db.close()
    if not c:
        return jsonify({'error': 'Consultation not found'}), 404
    result = dict(c)
    result['vitals'] = [dict(v) for v in vitals]
    result['examinations'] = [dict(e) for e in examinations]
    result['diagnoses'] = [dict(d) for d in diagnoses]
    result['prescriptions'] = [dict(p) for p in prescriptions]
    return jsonify(result)


@consultations_bp.route('/api/<int:id>', methods=['PUT'])
@login_required
def api_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    db.execute(
        '''UPDATE consultations SET consultation_type=?, diagnosis=?, notes=? WHERE id=?''',
        (data.get('consultation_type'), data.get('diagnosis'), data.get('notes'), id)
    )
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'consultation', id,
              'Updated consultation', request.remote_addr)
    db.close()
    return jsonify({'message': 'Consultation updated'})


@consultations_bp.route('/api/<int:id>', methods=['DELETE'])
@login_required
def api_delete(id):
    current_user = get_jwt()
    db = get_db()
    db.execute('DELETE FROM consultations WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'delete', 'consultation', id,
              'Deleted consultation', request.remote_addr)
    db.close()
    return jsonify({'message': 'Deleted'})


# ─── Vital Signs ───

@consultations_bp.route('/api/<int:id>/vitals', methods=['GET'])
@login_required
def api_vitals_list(id):
    db = get_db()
    vitals = db.execute(
        'SELECT * FROM vital_signs WHERE consultation_id = ? ORDER BY recorded_at DESC', (id,)).fetchall()
    db.close()
    return jsonify([dict(v) for v in vitals])


@consultations_bp.route('/api/<int:id>/vitals', methods=['POST'])
@login_required
def api_vitals_create(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    bp_s = data.get('bp_systolic')
    bp_d = data.get('bp_diastolic')
    weight = data.get('weight')
    height = data.get('height')
    bmi = None
    if weight and height and float(height) > 0:
        bmi = round(float(weight) / ((float(height) / 100) ** 2), 1)
    cursor = db.execute(
        '''INSERT INTO vital_signs (consultation_id, patient_id, bp_systolic, bp_diastolic, heart_rate,
           temperature, respiratory_rate, oxygen_saturation, weight, height, bmi, notes, recorded_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (id, data['patient_id'], bp_s, bp_d, data.get('heart_rate'),
         data.get('temperature'), data.get('respiratory_rate'), data.get('oxygen_saturation'),
         weight, height, bmi, data.get('notes'), current_user['id'])
    )
    db.commit()
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201


@consultations_bp.route('/api/<int:id>/vitals/<int:vid>', methods=['PUT'])
@login_required
def api_vitals_update(id, vid):
    data = request.json
    db = get_db()
    weight = data.get('weight')
    height = data.get('height')
    bmi = None
    if weight and height and float(height) > 0:
        bmi = round(float(weight) / ((float(height) / 100) ** 2), 1)
    db.execute(
        '''UPDATE vital_signs SET bp_systolic=?, bp_diastolic=?, heart_rate=?, temperature=?,
           respiratory_rate=?, oxygen_saturation=?, weight=?, height=?, bmi=?, notes=?
           WHERE id=? AND consultation_id=?''',
        (data.get('bp_systolic'), data.get('bp_diastolic'), data.get('heart_rate'),
         data.get('temperature'), data.get('respiratory_rate'), data.get('oxygen_saturation'),
         weight, height, bmi, data.get('notes'), vid, id)
    )
    db.commit()
    db.close()
    return jsonify({'message': 'Vitals updated'})


# ─── Medical Examinations ───

@consultations_bp.route('/api/<int:id>/examinations', methods=['GET'])
@login_required
def api_exam_list(id):
    db = get_db()
    exams = db.execute(
        'SELECT * FROM medical_examinations WHERE consultation_id = ?', (id,)).fetchall()
    db.close()
    return jsonify([dict(e) for e in exams])


@consultations_bp.route('/api/<int:id>/examinations', methods=['POST'])
@login_required
def api_exam_create(id):
    data = request.json
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO medical_examinations (consultation_id, system_name, findings, notes)
           VALUES (?, ?, ?, ?)''',
        (id, data['system_name'], data.get('findings'), data.get('notes'))
    )
    db.commit()
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201


@consultations_bp.route('/api/<int:id>/examinations/<int:eid>', methods=['PUT'])
@login_required
def api_exam_update(id, eid):
    data = request.json
    db = get_db()
    db.execute(
        'UPDATE medical_examinations SET system_name=?, findings=?, notes=? WHERE id=? AND consultation_id=?',
        (data.get('system_name'), data.get('findings'), data.get('notes'), eid, id)
    )
    db.commit()
    db.close()
    return jsonify({'message': 'Examination updated'})


@consultations_bp.route('/api/<int:id>/examinations/<int:eid>', methods=['DELETE'])
@login_required
def api_exam_delete(id, eid):
    db = get_db()
    db.execute('DELETE FROM medical_examinations WHERE id=? AND consultation_id=?', (eid, id))
    db.commit()
    db.close()
    return jsonify({'message': 'Examination deleted'})


# ─── Diagnoses ───

@consultations_bp.route('/api/<int:id>/diagnoses', methods=['GET'])
@login_required
def api_diagnosis_list(id):
    db = get_db()
    diags = db.execute(
        'SELECT * FROM diagnoses WHERE consultation_id = ?', (id,)).fetchall()
    db.close()
    return jsonify([dict(d) for d in diags])


@consultations_bp.route('/api/<int:id>/diagnoses', methods=['POST'])
@login_required
def api_diagnosis_create(id):
    data = request.json
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO diagnoses (consultation_id, diagnosis_name, diagnosis_type, icd_code, notes)
           VALUES (?, ?, ?, ?, ?)''',
        (id, data['diagnosis_name'], data.get('diagnosis_type', 'primary'),
         data.get('icd_code'), data.get('notes'))
    )
    db.commit()
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201


@consultations_bp.route('/api/<int:id>/diagnoses/<int:did>', methods=['PUT'])
@login_required
def api_diagnosis_update(id, did):
    data = request.json
    db = get_db()
    db.execute(
        '''UPDATE diagnoses SET diagnosis_name=?, diagnosis_type=?, icd_code=?, notes=?
           WHERE id=? AND consultation_id=?''',
        (data.get('diagnosis_name'), data.get('diagnosis_type'),
         data.get('icd_code'), data.get('notes'), did, id)
    )
    db.commit()
    db.close()
    return jsonify({'message': 'Diagnosis updated'})


@consultations_bp.route('/api/<int:id>/diagnoses/<int:did>', methods=['DELETE'])
@login_required
def api_diagnosis_delete(id, did):
    db = get_db()
    db.execute('DELETE FROM diagnoses WHERE id=? AND consultation_id=?', (did, id))
    db.commit()
    db.close()
    return jsonify({'message': 'Diagnosis deleted'})


# ─── Prescriptions ───

@consultations_bp.route('/api/<int:id>/prescriptions', methods=['GET'])
@login_required
def api_rx_list(id):
    db = get_db()
    rxs = db.execute(
        '''SELECT p.*, i.drug_name as inventory_drug, i.unit_price
           FROM prescriptions p
           LEFT JOIN pharmacy_inventory i ON p.inventory_id = i.id
           WHERE p.consultation_id = ?
           ORDER BY p.created_at DESC''', (id,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rxs])


@consultations_bp.route('/api/<int:id>/prescriptions', methods=['POST'])
@login_required
def api_rx_create(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    drug_name = data.get('drug_name')
    if data.get('inventory_id'):
        inv = db.execute('SELECT drug_name FROM pharmacy_inventory WHERE id=?',
                         (data['inventory_id'],)).fetchone()
        if inv:
            drug_name = inv['drug_name']
    cursor = db.execute(
        '''INSERT INTO prescriptions (consultation_id, patient_id, inventory_id, drug_name, dosage,
           frequency, duration, route, instructions, quantity, status, prescribed_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)''',
        (id, data['patient_id'], data.get('inventory_id'), drug_name,
         data.get('dosage'), data.get('frequency'), data.get('duration'),
         data.get('route'), data.get('instructions'), data.get('quantity'), current_user['id'])
    )
    db.commit()
    db.close()
    return jsonify({'id': cursor.lastrowid}), 201


@consultations_bp.route('/api/<int:id>/prescriptions/<int:rid>', methods=['PUT'])
@login_required
def api_rx_update(id, rid):
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
           route=?, instructions=?, quantity=?, status=? WHERE id=? AND consultation_id=?''',
        (data.get('inventory_id'), drug_name, data.get('dosage'), data.get('frequency'),
         data.get('duration'), data.get('route'), data.get('instructions'),
         data.get('quantity'), data.get('status', 'active'), rid, id)
    )
    db.commit()
    db.close()
    return jsonify({'message': 'Prescription updated'})


@consultations_bp.route('/api/<int:id>/prescriptions/<int:rid>', methods=['DELETE'])
@login_required
def api_rx_delete(id, rid):
    db = get_db()
    db.execute('DELETE FROM prescriptions WHERE id=? AND consultation_id=?', (rid, id))
    db.commit()
    db.close()
    return jsonify({'message': 'Prescription deleted'})


@consultations_bp.route('/api/ancillaries', methods=['GET', 'POST'])
@login_required
def api_ancillaries():
    current_user = get_jwt()
    db = get_db()

    if request.method == 'POST':
        data = request.json
        anc_type = data.get('type')

        if anc_type == 'lab':
            cursor = db.execute(
                '''INSERT INTO lab_tests (patient_id, doctor_id, test_name, test_category, status, ordered_date)
                   VALUES (?, ?, ?, ?, 'ordered', DATE('now'))''',
                (data['patient_id'], current_user['id'], data['test_name'], data.get('test_category', 'general')))
            log_audit(current_user['id'], current_user['username'], 'create', 'lab_test', cursor.lastrowid,
                      f'Ordered lab test for patient {data["patient_id"]}', request.remote_addr)

        elif anc_type == 'procedure':
            cursor = db.execute(
                '''INSERT INTO procedures (patient_id, performed_by, procedure_type, notes)
                   VALUES (?, ?, ?, ?)''',
                (data['patient_id'], current_user['id'], data.get('procedure_type'), data.get('notes')))
            log_audit(current_user['id'], current_user['username'], 'create', 'procedure', cursor.lastrowid,
                      f'Created procedure for patient {data["patient_id"]}', request.remote_addr)

        elif anc_type == 'certificate':
            cursor = db.execute(
                '''INSERT INTO medical_certificates (patient_id, doctor_id, certificate_type, issue_date, valid_until, notes)
                   VALUES (?, ?, ?, DATE('now'), ?, ?)''',
                (data['patient_id'], current_user['id'], data.get('certificate_type'),
                 data.get('valid_until'), data.get('notes')))
            log_audit(current_user['id'], current_user['username'], 'create', 'medical_certificate', cursor.lastrowid,
                      f'Issued certificate for patient {data["patient_id"]}', request.remote_addr)

        elif anc_type == 'referral':
            cursor = db.execute(
                '''INSERT INTO referrals (patient_id, from_doctor_id, to_facility, reason, notes)
                   VALUES (?, ?, ?, ?, ?)''',
                (data['patient_id'], current_user['id'], data['to_facility'], data.get('reason'), data.get('notes')))

            from flask import current_app
            call_out_fee = current_app.config.get('CALL_OUT_FEE', 20000)
            last_inv = db.execute('SELECT invoice_number FROM billing ORDER BY id DESC LIMIT 1').fetchone()
            if last_inv:
                num = int(last_inv['invoice_number'].replace('INV-', '')) + 1
            else:
                num = 1001
            invoice_number = f'INV-{num}'
            db.execute(
                '''INSERT INTO billing (patient_id, invoice_number, total_amount, amount_paid, balance,
                   payment_method, payment_status, created_by)
                   VALUES (?, ?, ?, 0, ?, 'cash', 'pending', ?)''',
                (data['patient_id'], invoice_number, call_out_fee, call_out_fee, current_user['id']))
            billing_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            db.execute(
                '''INSERT INTO billing_items (billing_id, item_name, item_type, quantity, unit_price, total_price)
                   VALUES (?, 'Call Out Fee', 'consultation', 1, ?, ?)''',
                (billing_id, call_out_fee, call_out_fee))

            log_audit(current_user['id'], current_user['username'], 'create', 'referral', cursor.lastrowid,
                      f'Created referral for patient {data["patient_id"]} - Call Out Fee MWK {call_out_fee}',
                      request.remote_addr)

        elif anc_type == 'diet':
            cursor = db.execute(
                '''INSERT INTO diet_support (patient_id, dietitian_name, plan_details, start_date, end_date)
                   VALUES (?, ?, ?, ?, ?)''',
                (data['patient_id'], data.get('dietitian_name'), data.get('plan_details'),
                 data.get('start_date'), data.get('end_date')))
            log_audit(current_user['id'], current_user['username'], 'create', 'diet_support', cursor.lastrowid,
                      f'Created diet plan for patient {data["patient_id"]}', request.remote_addr)

        else:
            db.close()
            return jsonify({'error': 'Invalid ancillary type'}), 400

        db.commit()
        db.close()
        return jsonify({'id': cursor.lastrowid}), 201

    patient_id = request.args.get('patient_id', '')
    lab_tests = db.execute(
        'SELECT * FROM lab_tests WHERE patient_id = ? ORDER BY created_at DESC',
        (patient_id,)).fetchall() if patient_id else []
    procedures = db.execute(
        'SELECT * FROM procedures WHERE patient_id = ? ORDER BY created_at DESC',
        (patient_id,)).fetchall() if patient_id else []
    certificates = db.execute(
        'SELECT * FROM medical_certificates WHERE patient_id = ? ORDER BY created_at DESC',
        (patient_id,)).fetchall() if patient_id else []
    referrals = db.execute(
        'SELECT * FROM referrals WHERE patient_id = ? ORDER BY created_at DESC',
        (patient_id,)).fetchall() if patient_id else []
    diet = db.execute(
        'SELECT * FROM diet_support WHERE patient_id = ? ORDER BY created_at DESC',
        (patient_id,)).fetchall() if patient_id else []
    db.close()
    return jsonify({
        'lab_tests': [dict(l) for l in lab_tests],
        'procedures': [dict(p) for p in procedures],
        'certificates': [dict(c) for c in certificates],
        'referrals': [dict(r) for r in referrals],
        'diet_support': [dict(d) for d in diet]
    })
