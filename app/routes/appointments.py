from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required, log_audit

appointments_bp = Blueprint('appointments', __name__, url_prefix='/appointments')


@appointments_bp.route('/', strict_slashes=False)
@login_required
def list_page():
    return render_template('appointments/list.html')


@appointments_bp.route('/new', strict_slashes=False)
@login_required
def new_page():
    return render_template('appointments/form.html')


@appointments_bp.route('/calendar', strict_slashes=False)
@login_required
def calendar_page():
    return render_template('appointments/calendar.html')


@appointments_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    db = get_db()
    status = request.args.get('status', '')
    date = request.args.get('date', '')
    query = '''SELECT a.*, p.first_name as p_first, p.last_name as p_last, p.phone as p_phone,
                      u.first_name as d_first, u.last_name as d_last
               FROM appointments a
               LEFT JOIN patients p ON a.patient_id = p.id
               LEFT JOIN users u ON a.doctor_id = u.id
               WHERE 1=1'''
    params = []
    if status:
        query += ' AND a.status = ?'
        params.append(status)
    if date:
        query += ' AND a.appointment_date = ?'
        params.append(date)
    query += ' ORDER BY a.appointment_date DESC, a.appointment_time ASC'
    appointments = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(a) for a in appointments])


@appointments_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    db = get_db()
    apt = db.execute(
        '''SELECT a.*, p.first_name as p_first, p.last_name as p_last, p.phone as p_phone,
                  u.first_name as d_first, u.last_name as d_last
           FROM appointments a
           LEFT JOIN patients p ON a.patient_id = p.id
           LEFT JOIN users u ON a.doctor_id = u.id
           WHERE a.id = ?''', (id,)).fetchone()
    db.close()
    if not apt:
        return jsonify({'error': 'Appointment not found'}), 404
    return jsonify(dict(apt))


@appointments_bp.route('/api', methods=['POST'])
@login_required
def api_create():
    current_user = get_jwt()
    data = request.json
    db = get_db()
    cursor = db.execute(
        '''INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, type, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (data['patient_id'], data.get('doctor_id'), data['appointment_date'],
         data['appointment_time'], data.get('reason'), data.get('type', 'phone'), current_user['id'])
    )
    new_id = cursor.lastrowid
    db.commit()
    if data.get('doctor_id'):
        from app.routes.notifications import notify
        from app.database import get_db as _gdb
        _db = _gdb()
        pat = _db.execute('SELECT first_name, last_name FROM patients WHERE id = ?', (data['patient_id'],)).fetchone()
        pat_name = (pat['first_name'] + ' ' + pat['last_name']) if pat else 'Patient #' + str(data['patient_id'])
        notify(_db, data['doctor_id'], 'New Appointment', f'Appointment with {pat_name} on {data["appointment_date"]} at {data["appointment_time"]}', 'appointment', '/appointments')
        _db.close()
    log_audit(current_user['id'], current_user['username'], 'create', 'appointment', new_id,
              f'Created appointment for patient {data["patient_id"]}', request.remote_addr)
    db.close()
    return jsonify({'id': new_id}), 201


@appointments_bp.route('/api/<int:id>', methods=['PUT'])
@login_required
def api_update(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    db.execute(
        '''UPDATE appointments SET patient_id=?, doctor_id=?, appointment_date=?, appointment_time=?,
           reason=?, status=?, type=?, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (data['patient_id'], data.get('doctor_id'), data['appointment_date'],
         data['appointment_time'], data.get('reason'), data.get('status', 'scheduled'),
         data.get('type', 'phone'), id)
    )
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update', 'appointment', id,
              f'Updated appointment {id}', request.remote_addr)
    db.close()
    return jsonify({'message': 'Appointment updated successfully'})


@appointments_bp.route('/api/<int:id>/status', methods=['PATCH'])
@login_required
def api_update_status(id):
    current_user = get_jwt()
    data = request.json
    db = get_db()
    db.execute('UPDATE appointments SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
               (data['status'], id))
    db.commit()
    log_audit(current_user['id'], current_user['username'], 'update_status', 'appointment', id,
              f'Changed appointment {id} status to {data["status"]}', request.remote_addr)
    db.close()
    return jsonify({'message': 'Status updated'})


@appointments_bp.route('/api/quick-add', methods=['POST'])
@login_required
def api_quick_add():
    current_user = get_jwt()
    data = request.json
    from datetime import date, datetime
    today = date.today().isoformat()
    now = datetime.now().strftime('%H:%M')

    db = get_db()
    cursor = db.execute(
        '''INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, type, status, created_by)
           VALUES (?, ?, ?, ?, ?, 'walk_in', 'scheduled', ?)''',
        (data['patient_id'], data.get('doctor_id'), today, now,
         data.get('reason', 'Walk-in'), current_user['id'])
    )
    new_id = cursor.lastrowid

    apt = db.execute(
        '''SELECT a.*, p.first_name as p_first, p.last_name as p_last, p.phone as p_phone,
                  u.first_name as d_first, u.last_name as d_last
           FROM appointments a
           LEFT JOIN patients p ON a.patient_id = p.id
           LEFT JOIN users u ON a.doctor_id = u.id
           WHERE a.id = ?''', (new_id,)).fetchone()

    db.commit()
    log_audit(current_user['id'], current_user['username'], 'walk_in', 'appointment', new_id,
              f'Walk-in added for patient ID {data["patient_id"]}', request.remote_addr)
    db.close()
    return jsonify(dict(apt)), 201


@appointments_bp.route('/api/today', methods=['GET'])
@login_required
def api_today():
    db = get_db()
    from datetime import date
    today = date.today().isoformat()
    appointments = db.execute(
        '''SELECT a.*, p.first_name as p_first, p.last_name as p_last, p.phone as p_phone,
                  u.first_name as d_first, u.last_name as d_last
           FROM appointments a
           LEFT JOIN patients p ON a.patient_id = p.id
           LEFT JOIN users u ON a.doctor_id = u.id
           WHERE a.appointment_date = ?
           ORDER BY a.appointment_time ASC''', (today,)).fetchall()
    db.close()
    return jsonify([dict(a) for a in appointments])
