from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required, role_required, log_audit

yellow_book_bp = Blueprint('yellow_book', __name__, url_prefix='/yellow-book')


@yellow_book_bp.route('/', strict_slashes=False)
@login_required
def patients_page():
    return render_template('yellow_book/patients.html')


@yellow_book_bp.route('/patient/<int:patient_id>')
@login_required
def patient_detail(patient_id):
    return render_template('yellow_book/patient_detail.html', patient_id=patient_id)


@yellow_book_bp.route('/api/records/<int:patient_id>', methods=['GET'])
@login_required
def api_records_list(patient_id):
    db = get_db()
    records = db.execute(
        '''SELECT vr.*, v.vaccine_name, v.vaccine_type,
                  u.first_name as u_first, u.last_name as u_last
           FROM vaccination_records vr
           LEFT JOIN vaccines v ON vr.vaccine_id = v.id
           LEFT JOIN users u ON vr.administered_by = u.id
           WHERE vr.patient_id = ?
           ORDER BY vr.date_administered DESC''',
        (patient_id,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in records])


@yellow_book_bp.route('/api/records', methods=['POST'])
@login_required
def api_record_create():
    claims = get_jwt()
    data = request.get_json()
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO vaccination_records
           (patient_id, vaccine_id, dose_number, batch_number, manufacturer,
            date_administered, administered_by, injection_site, notes, next_dose_due, certificate_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data['patient_id'], data['vaccine_id'], data.get('dose_number', 1),
         data.get('batch_number', ''), data.get('manufacturer', ''),
         data['date_administered'], claims['id'],
         data.get('injection_site', ''), data.get('notes', ''),
         data.get('next_dose_due'), data.get('certificate_id')))
    record_id = cursor.lastrowid
    db.commit()
    db.close()
    log_audit(claims['id'], claims['username'], 'create', 'vaccination_records', record_id,
              f'Added vaccination record for patient {data["patient_id"]}')
    return jsonify({'id': record_id, 'message': 'Vaccination record added'}), 201


@yellow_book_bp.route('/api/records/<int:id>', methods=['PUT'])
@login_required
def api_record_update(id):
    claims = get_jwt()
    data = request.get_json()
    db = get_db()
    db.execute(
        '''UPDATE vaccination_records SET vaccine_id=?, dose_number=?, batch_number=?, manufacturer=?,
            date_administered=?, injection_site=?, notes=?, next_dose_due=?, certificate_id=?
           WHERE id=?''',
        (data['vaccine_id'], data.get('dose_number', 1),
         data.get('batch_number', ''), data.get('manufacturer', ''),
         data['date_administered'], data.get('injection_site', ''),
         data.get('notes', ''), data.get('next_dose_due'),
         data.get('certificate_id'), id))
    db.commit()
    db.close()
    log_audit(claims['id'], claims['username'], 'update', 'vaccination_records', id, 'Updated vaccination record')
    return jsonify({'message': 'Vaccination record updated'})


@yellow_book_bp.route('/api/records/<int:id>', methods=['DELETE'])
@login_required
@role_required('admin')
def api_record_delete(id):
    claims = get_jwt()
    db = get_db()
    record = db.execute('SELECT patient_id FROM vaccination_records WHERE id=?', (id,)).fetchone()
    if not record:
        db.close()
        return jsonify({'error': 'Record not found'}), 404
    db.execute('DELETE FROM vaccination_records WHERE id=?', (id,))
    db.commit()
    db.close()
    log_audit(claims['id'], claims['username'], 'delete', 'vaccination_records', id, 'Deleted vaccination record')
    return jsonify({'message': 'Vaccination record deleted'})


@yellow_book_bp.route('/api/vaccines', methods=['GET'])
@login_required
def api_vaccines_list():
    db = get_db()
    vaccines = db.execute(
        'SELECT * FROM vaccines WHERE is_active=1 ORDER BY vaccine_name').fetchall()
    db.close()
    return jsonify([dict(v) for v in vaccines])


@yellow_book_bp.route('/api/vaccines', methods=['POST'])
@login_required
@role_required('admin')
def api_vaccine_create():
    claims = get_jwt()
    data = request.get_json()
    db = get_db()
    cursor = db.execute(
        'INSERT INTO vaccines (vaccine_name, manufacturer, vaccine_type) VALUES (?, ?, ?)',
        (data['vaccine_name'], data.get('manufacturer', ''), data.get('vaccine_type', '')))
    vaccine_id = cursor.lastrowid
    db.commit()
    db.close()
    log_audit(claims['id'], claims['username'], 'create', 'vaccines', vaccine_id,
              f'Added vaccine {data["vaccine_name"]}')
    return jsonify({'id': vaccine_id, 'message': 'Vaccine added'}), 201


@yellow_book_bp.route('/api/vaccines/<int:id>', methods=['PUT'])
@login_required
@role_required('admin')
def api_vaccine_update(id):
    claims = get_jwt()
    data = request.get_json()
    db = get_db()
    db.execute(
        'UPDATE vaccines SET vaccine_name=?, manufacturer=?, vaccine_type=?, is_active=? WHERE id=?',
        (data['vaccine_name'], data.get('manufacturer', ''),
         data.get('vaccine_type', ''), data.get('is_active', 1), id))
    db.commit()
    db.close()
    log_audit(claims['id'], claims['username'], 'update', 'vaccines', id,
              f'Updated vaccine {data["vaccine_name"]}')
    return jsonify({'message': 'Vaccine updated'})


@yellow_book_bp.route('/api/stats', methods=['GET'])
@login_required
def api_stats():
    db = get_db()
    total_records = db.execute('SELECT COUNT(*) as c FROM vaccination_records').fetchone()['c']
    total_patients = db.execute(
        'SELECT COUNT(DISTINCT patient_id) as c FROM vaccination_records').fetchone()['c']
    total_vaccines = db.execute(
        'SELECT COUNT(*) as c FROM vaccines WHERE is_active=1').fetchone()['c']
    this_month = db.execute(
        "SELECT COUNT(*) as c FROM vaccination_records WHERE date_administered >= DATE('now', 'start of month')"
    ).fetchone()['c']
    db.close()
    return jsonify({
        'total_records': total_records,
        'total_patients': total_patients,
        'total_vaccines': total_vaccines,
        'this_month': this_month
    })


@yellow_book_bp.route('/api/certificate/<int:patient_id>', methods=['GET'])
@login_required
def api_certificate_data(patient_id):
    db = get_db()
    patient = db.execute('SELECT * FROM patients WHERE id=?', (patient_id,)).fetchone()
    if not patient:
        db.close()
        return jsonify({'error': 'Patient not found'}), 404
    records = db.execute(
        '''SELECT vr.*, v.vaccine_name, v.vaccine_type,
                  u.first_name as u_first, u.last_name as u_last
           FROM vaccination_records vr
           LEFT JOIN vaccines v ON vr.vaccine_id = v.id
           LEFT JOIN users u ON vr.administered_by = u.id
           WHERE vr.patient_id = ?
           ORDER BY vr.date_administered ASC''',
        (patient_id,)).fetchall()
    db.close()
    return jsonify({
        'patient': dict(patient),
        'records': [dict(r) for r in records]
    })
