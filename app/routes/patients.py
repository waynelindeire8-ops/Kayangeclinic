from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt
from app.database import get_db
from app.auth import login_required, log_audit

patients_bp = Blueprint('patients', __name__, url_prefix='/patients')


@patients_bp.route('/')
@login_required
def list_page():
    return render_template('patients/list.html')


@patients_bp.route('/new')
@login_required
def new_page():
    return render_template('patients/form.html')


@patients_bp.route('/<int:id>')
@login_required
def detail_page(id):
    return render_template('patients/detail.html', patient_id=id)


@patients_bp.route('/<int:id>/edit')
@login_required
def edit_page(id):
    return render_template('patients/form.html', patient_id=id)


@patients_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    db = get_db()
    search = request.args.get('search', '')
    if search:
        patients = db.execute(
            '''SELECT * FROM patients
               WHERE first_name LIKE ? OR last_name LIKE ? OR patient_id LIKE ? OR phone LIKE ?
               ORDER BY created_at DESC''',
            (f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%')
        ).fetchall()
    else:
        patients = db.execute('SELECT * FROM patients ORDER BY created_at DESC').fetchall()
    db.close()
    return jsonify([dict(p) for p in patients])


@patients_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    db = get_db()
    patient = db.execute('SELECT * FROM patients WHERE id = ?', (id,)).fetchone()
    if not patient:
        db.close()
        return jsonify({'error': 'Patient not found'}), 404

    allergies = db.execute('SELECT * FROM patient_allergies WHERE patient_id = ?', (id,)).fetchall()
    medical_history = db.execute('SELECT * FROM patient_medical_history WHERE patient_id = ?', (id,)).fetchall()
    medications = db.execute('SELECT * FROM patient_medications WHERE patient_id = ?', (id,)).fetchall()
    db.close()

    result = dict(patient)
    result['allergies'] = [dict(a) for a in allergies]
    result['medical_history'] = [dict(m) for m in medical_history]
    result['medications'] = [dict(m) for m in medications]
    return jsonify(result)


@patients_bp.route('/api', methods=['POST'])
@login_required
def api_create():
    current_user = get_jwt()
    data = request.json

    db = get_db()
    last = db.execute('SELECT patient_id FROM patients ORDER BY id DESC LIMIT 1').fetchone()
    if last:
        num = int(last['patient_id'].replace('KMC-', '')) + 1
    else:
        num = 1001
    patient_id = f'KMC-{num}'

    cursor = db.execute(
        '''INSERT INTO patients (patient_id, first_name, last_name, dob, gender, phone, email, address,
           emergency_contact_name, emergency_contact_phone, blood_group, scheme_provider, scheme_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (patient_id, data['first_name'], data['last_name'], data['dob'], data.get('gender'),
         data['phone'], data.get('email'), data.get('address'), data.get('emergency_contact_name'),
         data.get('emergency_contact_phone'), data.get('blood_group'), data.get('scheme_provider'),
         data.get('scheme_type'))
    )
    new_id = cursor.lastrowid

    for allergy in data.get('allergies', []):
        db.execute('INSERT INTO patient_allergies (patient_id, allergy) VALUES (?, ?)', (new_id, allergy))

    for condition in data.get('medical_history', []):
        db.execute('INSERT INTO patient_medical_history (patient_id, condition_name, diagnosis_date, notes) VALUES (?, ?, ?, ?)',
                   (new_id, condition.get('condition_name'), condition.get('diagnosis_date'), condition.get('notes')))

    for med in data.get('medications', []):
        db.execute('INSERT INTO patient_medications (patient_id, medication_name, dosage, frequency, prescribed_by, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (new_id, med.get('medication_name'), med.get('dosage'), med.get('frequency'),
                    med.get('prescribed_by'), med.get('start_date'), med.get('end_date')))

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'create', 'patient', new_id,
              f'Created patient {data["first_name"]} {data["last_name"]}', request.remote_addr)
    db.close()

    return jsonify({'id': new_id, 'patient_id': patient_id}), 201


@patients_bp.route('/api/<int:id>', methods=['PUT'])
@login_required
def api_update(id):
    current_user = get_jwt()
    data = request.json

    db = get_db()
    db.execute(
        '''UPDATE patients SET first_name=?, last_name=?, dob=?, gender=?, phone=?, email=?, address=?,
           emergency_contact_name=?, emergency_contact_phone=?, blood_group=?, scheme_provider=?, scheme_type=?,
           updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (data['first_name'], data['last_name'], data['dob'], data.get('gender'),
         data['phone'], data.get('email'), data.get('address'), data.get('emergency_contact_name'),
         data.get('emergency_contact_phone'), data.get('blood_group'), data.get('scheme_provider'),
         data.get('scheme_type'), id)
    )

    db.execute('DELETE FROM patient_allergies WHERE patient_id = ?', (id,))
    for allergy in data.get('allergies', []):
        db.execute('INSERT INTO patient_allergies (patient_id, allergy) VALUES (?, ?)', (id, allergy))

    db.execute('DELETE FROM patient_medical_history WHERE patient_id = ?', (id,))
    for condition in data.get('medical_history', []):
        db.execute('INSERT INTO patient_medical_history (patient_id, condition_name, diagnosis_date, notes) VALUES (?, ?, ?, ?)',
                   (id, condition.get('condition_name'), condition.get('diagnosis_date'), condition.get('notes')))

    db.execute('DELETE FROM patient_medications WHERE patient_id = ?', (id,))
    for med in data.get('medications', []):
        db.execute('INSERT INTO patient_medications (patient_id, medication_name, dosage, frequency, prescribed_by, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (id, med.get('medication_name'), med.get('dosage'), med.get('frequency'),
                    med.get('prescribed_by'), med.get('start_date'), med.get('end_date')))

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'patient', id,
              f'Updated patient {data["first_name"]} {data["last_name"]}', request.remote_addr)
    db.close()

    return jsonify({'message': 'Patient updated successfully'})


@patients_bp.route('/api/<int:id>', methods=['DELETE'])
@login_required
def api_delete(id):
    current_user = get_jwt()
    db = get_db()
    patient = db.execute('SELECT * FROM patients WHERE id = ?', (id,)).fetchone()
    if not patient:
        db.close()
        return jsonify({'error': 'Patient not found'}), 404
    db.execute('DELETE FROM patients WHERE id = ?', (id,))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'delete', 'patient', id,
              f'Deleted patient {patient["first_name"]} {patient["last_name"]}', request.remote_addr)
    db.close()
    return jsonify({'message': 'Patient deleted successfully'})


@patients_bp.route('/api/<int:id>/history', methods=['GET'])
@login_required
def api_history(id):
    db = get_db()
    consultations = db.execute(
        '''SELECT c.*, u.first_name as doctor_first, u.last_name as doctor_last
           FROM consultations c LEFT JOIN users u ON c.doctor_id = u.id
           WHERE c.patient_id = ? ORDER BY c.created_at DESC''', (id,)).fetchall()
    lab_tests = db.execute(
        '''SELECT l.*, u.first_name as doctor_first, u.last_name as doctor_last
           FROM lab_tests l LEFT JOIN users u ON l.doctor_id = u.id
           WHERE l.patient_id = ? ORDER BY l.created_at DESC''', (id,)).fetchall()
    procedures = db.execute(
        '''SELECT p.*, u.first_name as doctor_first, u.last_name as doctor_last
           FROM procedures p LEFT JOIN users u ON p.performed_by = u.id
           WHERE p.patient_id = ? ORDER BY p.created_at DESC''', (id,)).fetchall()
    billing = db.execute(
        'SELECT * FROM billing WHERE patient_id = ? ORDER BY created_at DESC', (id,)).fetchall()
    db.close()
    return jsonify({
        'consultations': [dict(c) for c in consultations],
        'lab_tests': [dict(l) for l in lab_tests],
        'procedures': [dict(p) for p in procedures],
        'billing': [dict(b) for b in billing]
    })
