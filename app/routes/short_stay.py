from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required, log_audit
from datetime import datetime

short_stay_bp = Blueprint('short_stay', __name__, url_prefix='/short-stay')


# ─── Pages ───

@short_stay_bp.route('/', strict_slashes=False)
@login_required
def dashboard_page():
    return render_template('short_stay/dashboard.html')


@short_stay_bp.route('/admissions', strict_slashes=False)
@login_required
def admissions_page():
    return render_template('short_stay/admissions.html')


# ─── API: Occupancy ───

@short_stay_bp.route('/api/occupancy', methods=['GET'])
@login_required
def api_occupancy():
    db = get_db()
    beds = db.execute('SELECT * FROM short_stay_beds ORDER BY bed_number').fetchall()
    stations = db.execute('SELECT * FROM short_stay_drip_stations ORDER BY station_number').fetchall()

    occupied_beds = db.execute(
        '''SELECT ssa.*, p.first_name as p_first, p.last_name as p_last, p.patient_id as p_patient_id,
                  u.first_name as u_first, u.last_name as u_last
           FROM short_stay_admissions ssa
           LEFT JOIN patients p ON ssa.patient_id = p.id
           LEFT JOIN users u ON ssa.admitted_by = u.id
           WHERE ssa.bed_id IS NOT NULL AND ssa.discharged_at IS NULL
           ORDER BY ssa.admitted_at DESC''').fetchall()

    occupied_stations = db.execute(
        '''SELECT ssa.*, p.first_name as p_first, p.last_name as p_last, p.patient_id as p_patient_id,
                  u.first_name as u_first, u.last_name as u_last
           FROM short_stay_admissions ssa
           LEFT JOIN patients p ON ssa.patient_id = p.id
           LEFT JOIN users u ON ssa.admitted_by = u.id
           WHERE ssa.drip_station_id IS NOT NULL AND ssa.discharged_at IS NULL
           ORDER BY ssa.admitted_at DESC''').fetchall()

    recent = db.execute(
        '''SELECT ssa.*, p.first_name as p_first, p.last_name as p_last, p.patient_id as p_patient_id,
                  u.first_name as u_first, u.last_name as u_last
           FROM short_stay_admissions ssa
           LEFT JOIN patients p ON ssa.patient_id = p.id
           LEFT JOIN users u ON ssa.admitted_by = u.id
           ORDER BY ssa.created_at DESC LIMIT 10''').fetchall()

    db.close()
    return jsonify({
        'beds': [dict(b) for b in beds],
        'stations': [dict(s) for s in stations],
        'occupied_beds': [dict(o) for o in occupied_beds],
        'occupied_stations': [dict(o) for o in occupied_stations],
        'recent': [dict(r) for r in recent]
    })


# ─── API: Admit ───

@short_stay_bp.route('/api/admit', methods=['POST'])
@login_required
def api_admit():
    claims = get_jwt()
    data = request.json
    patient_id = data.get('patient_id')
    resource_type = data.get('resource_type')  # 'bed' or 'drip'
    resource_id = data.get('resource_id')
    diagnosis = data.get('diagnosis', '')
    notes = data.get('notes', '')

    if not patient_id or not resource_type or not resource_id:
        return jsonify({'error': 'Patient and resource required'}), 400

    db = get_db()
    if resource_type == 'bed':
        resource = db.execute('SELECT * FROM short_stay_beds WHERE id = ? AND status = ?',
                              (resource_id, 'available')).fetchone()
    else:
        resource = db.execute('SELECT * FROM short_stay_drip_stations WHERE id = ? AND status = ?',
                              (resource_id, 'available')).fetchone()

    if not resource:
        db.close()
        return jsonify({'error': 'Resource not available'}), 409

    if resource_type == 'bed':
        cur = db.execute(
            '''INSERT INTO short_stay_admissions (patient_id, bed_id, admitted_by, diagnosis, notes)
               VALUES (?, ?, ?, ?, ?)''',
            (patient_id, resource_id, claims['id'], diagnosis, notes))
        db.execute('UPDATE short_stay_beds SET status = ? WHERE id = ?', ('occupied', resource_id))
    else:
        cur = db.execute(
            '''INSERT INTO short_stay_admissions (patient_id, drip_station_id, admitted_by, diagnosis, notes)
               VALUES (?, ?, ?, ?, ?)''',
            (patient_id, resource_id, claims['id'], diagnosis, notes))
        db.execute('UPDATE short_stay_drip_stations SET status = ? WHERE id = ?', ('occupied', resource_id))

    db.commit()
    log_audit(claims['id'], claims['username'], 'admit', 'short_stay', cur.lastrowid,
              f'Admitted to {"bed" if resource_type == "bed" else "drip station"} #{resource_id}')
    db.close()
    return jsonify({'message': 'Patient admitted', 'id': cur.lastrowid}), 201


# ─── API: Discharge ───

@short_stay_bp.route('/api/discharge/<int:id>', methods=['POST'])
@login_required
def api_discharge(id):
    claims = get_jwt()
    data = request.json
    discharge_type = data.get('discharge_type', 'discharged')

    db = get_db()
    admission = db.execute('SELECT * FROM short_stay_admissions WHERE id = ? AND discharged_at IS NULL',
                           (id,)).fetchone()
    if not admission:
        db.close()
        return jsonify({'error': 'Admission not found or already discharged'}), 404

    db.execute(
        '''UPDATE short_stay_admissions SET discharged_at = CURRENT_TIMESTAMP, discharge_type = ?
           WHERE id = ?''', (discharge_type, id))

    if admission['bed_id']:
        db.execute('UPDATE short_stay_beds SET status = ? WHERE id = ?', ('available', admission['bed_id']))
    if admission['drip_station_id']:
        db.execute('UPDATE short_stay_drip_stations SET status = ? WHERE id = ?',
                   ('available', admission['drip_station_id']))

    db.commit()
    log_audit(claims['id'], claims['username'], 'discharge', 'short_stay', id,
              f'Discharged from {"bed" if admission["bed_id"] else "drip station"}')
    db.close()
    return jsonify({'message': 'Patient discharged'})


# ─── API: Update resource status ───

@short_stay_bp.route('/api/resources/<string:rtype>/<int:id>/status', methods=['PUT'])
@login_required
def api_resource_status(rtype, id):
    data = request.json
    status = data.get('status')
    if not status:
        return jsonify({'error': 'Status required'}), 400

    db = get_db()
    if rtype == 'bed':
        db.execute('UPDATE short_stay_beds SET status = ? WHERE id = ?', (status, id))
    else:
        db.execute('UPDATE short_stay_drip_stations SET status = ? WHERE id = ?', (status, id))
    db.commit()
    db.close()
    return jsonify({'message': 'Status updated'})


# ─── API: History ───

@short_stay_bp.route('/api/admissions', methods=['GET'])
@login_required
def api_admissions():
    db = get_db()
    status = request.args.get('status', 'active')
    if status == 'active':
        query = '''SELECT ssa.*, p.first_name as p_first, p.last_name as p_last, p.patient_id as p_patient_id,
                          u.first_name as u_first, u.last_name as u_last
                   FROM short_stay_admissions ssa
                   LEFT JOIN patients p ON ssa.patient_id = p.id
                   LEFT JOIN users u ON ssa.admitted_by = u.id
                   WHERE ssa.discharged_at IS NULL
                   ORDER BY ssa.admitted_at DESC'''
    else:
        query = '''SELECT ssa.*, p.first_name as p_first, p.last_name as p_last, p.patient_id as p_patient_id,
                          u.first_name as u_first, u.last_name as u_last
                   FROM short_stay_admissions ssa
                   LEFT JOIN patients p ON ssa.patient_id = p.id
                   LEFT JOIN users u ON ssa.admitted_by = u.id
                   ORDER BY ssa.created_at DESC'''
    admissions = db.execute(query).fetchall()
    db.close()
    return jsonify([dict(a) for a in admissions])


# ─── API: ECG ───

@short_stay_bp.route('/api/ecg', methods=['POST'])
@login_required
def api_record_ecg():
    claims = get_jwt()
    data = request.json
    admission_id = data.get('admission_id')
    patient_id = data.get('patient_id')
    notes = data.get('notes', '')

    if not admission_id or not patient_id:
        return jsonify({'error': 'Admission and patient required'}), 400

    db = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        '''INSERT INTO procedures (patient_id, performed_by, procedure_type, notes, start_time, end_time)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (patient_id, claims['id'], 'ecg', notes, now, now))

    log_audit(claims['id'], claims['username'], 'record_ecg', 'short_stay', admission_id, 'ECG recorded')
    db.commit()
    db.close()
    return jsonify({'message': 'ECG recorded'}), 201


@short_stay_bp.route('/api/ecg/<int:admission_id>', methods=['GET'])
@login_required
def api_list_ecg(admission_id):
    db = get_db()
    admission = db.execute('SELECT patient_id FROM short_stay_admissions WHERE id = ?',
                           (admission_id,)).fetchone()
    if not admission:
        db.close()
        return jsonify({'error': 'Admission not found'}), 404

    ecgs = db.execute(
        '''SELECT p.*, u.first_name as u_first, u.last_name as u_last
           FROM procedures p
           LEFT JOIN users u ON p.performed_by = u.id
           WHERE p.patient_id = ? AND p.procedure_type = 'ecg'
           ORDER BY p.created_at DESC''',
        (admission['patient_id'],)).fetchall()
    db.close()
    return jsonify([dict(e) for e in ecgs])
