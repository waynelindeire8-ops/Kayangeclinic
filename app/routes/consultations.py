from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt
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
                  u.first_name as d_first, u.last_name as d_last
           FROM consultations c
           LEFT JOIN patients p ON c.patient_id = p.id
           LEFT JOIN users u ON c.doctor_id = u.id
           WHERE c.id = ?''', (id,)).fetchone()
    db.close()
    if not c:
        return jsonify({'error': 'Consultation not found'}), 404
    return jsonify(dict(c))


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
            log_audit(current_user['id'], current_user['username'], 'create', 'referral', cursor.lastrowid,
                      f'Created referral for patient {data["patient_id"]}', request.remote_addr)

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
