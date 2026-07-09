from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required, role_required, log_audit
import secrets
import hashlib
from datetime import datetime, date

telemedicine_bp = Blueprint('telemedicine', __name__, url_prefix='/telemedicine')


# ─── Pages ───

@telemedicine_bp.route('/', strict_slashes=False)
@login_required
def dashboard_page():
    return render_template('telemedicine/dashboard.html')


@telemedicine_bp.route('/sessions', strict_slashes=False)
@login_required
def sessions_page():
    return render_template('telemedicine/sessions.html')


@telemedicine_bp.route('/sessions/new', strict_slashes=False)
@login_required
def session_new_page():
    return render_template('telemedicine/session_form.html')


@telemedicine_bp.route('/sessions/<int:id>', strict_slashes=False)
@login_required
def session_detail_page(id):
    db = get_db()
    session = db.execute(
        '''SELECT t.*, 
                  p.first_name as p_first, p.last_name as p_last, p.phone as p_phone, p.email as p_email,
                  p.patient_id as p_patient_id,
                  u.first_name as d_first, u.last_name as d_last, u.email as d_email
           FROM telemedicine_sessions t
           LEFT JOIN patients p ON t.patient_id = p.id
           LEFT JOIN users u ON t.doctor_id = u.id
           WHERE t.id = ?''', (id,)).fetchone()
    db.close()
    current_user = get_jwt()
    if not session:
        return render_template('telemedicine/session_detail.html', session={}, session_id=id, current_user=current_user)
    return render_template('telemedicine/session_detail.html', session=dict(session), session_id=id, current_user=current_user)


@telemedicine_bp.route('/sessions/<int:id>/room', strict_slashes=False)
@login_required
def video_room_page(id):
    db = get_db()
    session = db.execute(
        '''SELECT t.*, 
                  p.first_name as p_first, p.last_name as p_last,
                  u.first_name as d_first, u.last_name as d_last
           FROM telemedicine_sessions t
           LEFT JOIN patients p ON t.patient_id = p.id
           LEFT JOIN users u ON t.doctor_id = u.id
           WHERE t.id = ?''', (id,)).fetchone()
    db.close()
    current_user = get_jwt()
    if not session:
        return render_template('telemedicine/video_room.html', session={}, session_id=id, current_user=current_user)
    return render_template('telemedicine/video_room.html', session=dict(session), session_id=id, current_user=current_user)


@telemedicine_bp.route('/waiting-room', strict_slashes=False)
@login_required
def waiting_room_page():
    return render_template('telemedicine/waiting_room.html')


# ─── API: Dashboard Stats ───

@telemedicine_bp.route('/api/dashboard', methods=['GET'])
@login_required
def api_dashboard():
    db = get_db()
    today = date.today().isoformat()

    scheduled = db.execute(
        "SELECT COUNT(*) as c FROM telemedicine_sessions WHERE status = 'scheduled'"
    ).fetchone()['c']

    waiting = db.execute(
        "SELECT COUNT(*) as c FROM telemedicine_sessions WHERE status = 'waiting'"
    ).fetchone()['c']

    in_progress = db.execute(
        "SELECT COUNT(*) as c FROM telemedicine_sessions WHERE status = 'in_progress'"
    ).fetchone()['c']

    completed_today = db.execute(
        'SELECT COUNT(*) as c FROM telemedicine_sessions WHERE status = ? AND DATE(ended_at) = ?',
        ('completed', today)
    ).fetchone()['c']

    total_revenue = db.execute(
        'SELECT COALESCE(SUM(amount), 0) as total FROM telemedicine_payments WHERE status = ? AND DATE(paid_at) = ?',
        ('completed', today)
    ).fetchone()['total']

    recent = db.execute(
        '''SELECT t.*, p.first_name as p_first, p.last_name as p_last,
                  u.first_name as d_first, u.last_name as d_last
           FROM telemedicine_sessions t
           LEFT JOIN patients p ON t.patient_id = p.id
           LEFT JOIN users u ON t.doctor_id = u.id
           ORDER BY t.created_at DESC LIMIT 10'''
    ).fetchall()

    db.close()
    return jsonify({
        'scheduled': scheduled,
        'waiting': waiting,
        'in_progress': in_progress,
        'completed_today': completed_today,
        'total_revenue': total_revenue,
        'recent': [dict(r) for r in recent]
    })


# ─── API: Sessions CRUD ───

@telemedicine_bp.route('/api/sessions', methods=['GET'])
@login_required
def api_sessions_list():
    db = get_db()
    status = request.args.get('status', '')
    patient_id = request.args.get('patient_id', '')
    doctor_id = request.args.get('doctor_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = '''SELECT t.*, p.first_name as p_first, p.last_name as p_last,
                      u.first_name as d_first, u.last_name as d_last
               FROM telemedicine_sessions t
               LEFT JOIN patients p ON t.patient_id = p.id
               LEFT JOIN users u ON t.doctor_id = u.id WHERE 1=1'''
    params = []

    if status:
        query += ' AND t.status = ?'
        params.append(status)
    if patient_id:
        query += ' AND t.patient_id = ?'
        params.append(patient_id)
    if doctor_id:
        query += ' AND t.doctor_id = ?'
        params.append(doctor_id)
    if date_from:
        query += ' AND DATE(t.created_at) >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND DATE(t.created_at) <= ?'
        params.append(date_to)

    query += ' ORDER BY t.created_at DESC'
    sessions = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(s) for s in sessions])


@telemedicine_bp.route('/api/sessions', methods=['POST'])
@login_required
def api_session_create():
    claims = get_jwt()
    data = request.json
    patient_id = data.get('patient_id')
    doctor_id = data.get('doctor_id')
    session_type = data.get('session_type', 'video')
    reason = data.get('reason', '')
    appointment_id = data.get('appointment_id')

    if not patient_id or not doctor_id:
        return jsonify({'error': 'Patient and doctor required'}), 400

    db = get_db()
    session_id = 'TM-' + datetime.now().strftime('%Y%m%d') + '-' + secrets.token_hex(3).upper()
    token_patient = secrets.token_urlsafe(32)
    token_doctor = secrets.token_urlsafe(32)

    cur = db.execute(
        '''INSERT INTO telemedicine_sessions 
           (session_id, patient_id, doctor_id, appointment_id, session_type, reason, status, token_patient, token_doctor)
           VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?, ?)''',
        (session_id, patient_id, doctor_id, appointment_id, session_type, reason, token_patient, token_doctor)
    )
    session_db_id = cur.lastrowid
    db.commit()
    db.close()

    log_audit(claims['id'], claims['username'], 'create', 'telemedicine_session', session_db_id,
              f'Created session {session_id}')

    return jsonify({'id': session_db_id, 'session_id': session_id, 'token_patient': token_patient, 'token_doctor': token_doctor}), 201


@telemedicine_bp.route('/api/sessions/<int:id>', methods=['GET'])
@login_required
def api_session_get(id):
    db = get_db()
    session = db.execute(
        '''SELECT t.*, p.first_name as p_first, p.last_name as p_last, p.phone as p_phone, p.email as p_email,
                  p.patient_id as p_patient_id,
                  u.first_name as d_first, u.last_name as d_last, u.email as d_email
           FROM telemedicine_sessions t
           LEFT JOIN patients p ON t.patient_id = p.id
           LEFT JOIN users u ON t.doctor_id = u.id
           WHERE t.id = ?''', (id,)).fetchone()
    db.close()
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    return jsonify(dict(session))


@telemedicine_bp.route('/api/sessions/<int:id>', methods=['PUT'])
@login_required
def api_session_update(id):
    claims = get_jwt()
    data = request.json
    db = get_db()

    session = db.execute('SELECT * FROM telemedicine_sessions WHERE id = ?', (id,)).fetchone()
    if not session:
        db.close()
        return jsonify({'error': 'Session not found'}), 404

    updates = []
    params = []
    for field in ['status', 'diagnosis', 'notes', 'reason', 'session_type']:
        if field in data:
            updates.append(f'{field} = ?')
            params.append(data[field])

    if 'status' in data:
        if data['status'] == 'in_progress' and not session['started_at']:
            updates.append('started_at = ?')
            params.append(datetime.now().isoformat())
        elif data['status'] in ('completed', 'cancelled'):
            updates.append('ended_at = ?')
            params.append(datetime.now().isoformat())
            if session['started_at']:
                started = datetime.fromisoformat(session['started_at'])
                duration = int((datetime.now() - started).total_seconds() / 60)
                updates.append('duration_minutes = ?')
                params.append(duration)

    if updates:
        params.append(id)
        db.execute(f'UPDATE telemedicine_sessions SET {", ".join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?', params)
        db.commit()

    db.close()
    log_audit(claims['id'], claims['username'], 'update', 'telemedicine_session', id, f'Updated session')
    return jsonify({'message': 'Session updated'})


@telemedicine_bp.route('/api/sessions/<int:id>', methods=['DELETE'])
@login_required
def api_session_delete(id):
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    db = get_db()
    db.execute('DELETE FROM telemedicine_sessions WHERE id = ?', (id,))
    db.commit()
    db.close()
    log_audit(claims['id'], claims['username'], 'delete', 'telemedicine_session', id, 'Deleted session')
    return jsonify({'message': 'Session deleted'})


# ─── API: Join Session (generate/validate tokens) ───

@telemedicine_bp.route('/api/sessions/<int:id>/join', methods=['POST'])
@login_required
def api_session_join(id):
    claims = get_jwt()
    db = get_db()
    session = db.execute('SELECT * FROM telemedicine_sessions WHERE id = ?', (id,)).fetchone()
    if not session:
        db.close()
        return jsonify({'error': 'Session not found'}), 404

    is_doctor = claims['id'] == session['doctor_id']
    token = session['token_doctor'] if is_doctor else session['token_patient']

    if session['status'] == 'scheduled':
        db.execute("UPDATE telemedicine_sessions SET status = 'waiting', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (id,))
        db.commit()
    elif session['status'] == 'waiting' and is_doctor:
        db.execute("UPDATE telemedicine_sessions SET status = 'in_progress', started_at = COALESCE(started_at, CURRENT_TIMESTAMP), updated_at = CURRENT_TIMESTAMP WHERE id = ?", (id,))
        db.commit()

    db.close()
    return jsonify({'token': token, 'is_doctor': is_doctor, 'session_id': session['session_id']})


@telemedicine_bp.route('/api/sessions/<int:id>/validate-token', methods=['POST'])
@login_required
def api_validate_token(id):
    data = request.json
    token = data.get('token', '')
    db = get_db()
    session = db.execute('SELECT * FROM telemedicine_sessions WHERE id = ?', (id,)).fetchone()
    db.close()
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    if token == session['token_patient'] or token == session['token_doctor']:
        return jsonify({'valid': True})
    return jsonify({'valid': False}), 403


# ─── API: Waiting Room ───

@telemedicine_bp.route('/api/waiting-room', methods=['GET'])
@login_required
def api_waiting_room():
    db = get_db()
    waiting = db.execute(
        '''SELECT t.*, p.first_name as p_first, p.last_name as p_last,
                  u.first_name as d_first, u.last_name as d_last
           FROM telemedicine_sessions t
           LEFT JOIN patients p ON t.patient_id = p.id
           LEFT JOIN users u ON t.doctor_id = u.id
           WHERE t.status IN ('scheduled', 'waiting')
           ORDER BY t.created_at ASC'''
    ).fetchall()
    db.close()
    return jsonify([dict(w) for w in waiting])


# ─── API: Messages (in-session chat) ───

@telemedicine_bp.route('/api/sessions/<int:id>/messages', methods=['GET'])
@login_required
def api_session_messages(id):
    db = get_db()
    messages = db.execute(
        '''SELECT m.*, u.first_name as sender_first, u.last_name as sender_last
           FROM telemedicine_messages m
           LEFT JOIN users u ON m.sender_id = u.id
           WHERE m.session_id = ?
           ORDER BY m.created_at ASC''', (id,)
    ).fetchall()
    db.close()
    return jsonify([dict(m) for m in messages])


@telemedicine_bp.route('/api/sessions/<int:id>/messages', methods=['POST'])
@login_required
def api_session_message_send(id):
    claims = get_jwt()
    data = request.json
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Message required'}), 400

    db = get_db()
    db.execute(
        'INSERT INTO telemedicine_messages (session_id, sender_id, message) VALUES (?, ?, ?)',
        (id, claims['id'], message)
    )
    db.commit()
    db.close()
    return jsonify({'message': 'Sent'}), 201


# ─── API: Payments ───

@telemedicine_bp.route('/api/sessions/<int:id>/payments', methods=['GET'])
@login_required
def api_session_payments(id):
    db = get_db()
    payments = db.execute(
        'SELECT * FROM telemedicine_payments WHERE session_id = ? ORDER BY created_at DESC', (id,)
    ).fetchall()
    db.close()
    return jsonify([dict(p) for p in payments])


@telemedicine_bp.route('/api/sessions/<int:id>/payments', methods=['POST'])
@login_required
def api_session_payment_add(id):
    claims = get_jwt()
    data = request.json
    amount = data.get('amount')
    payment_method = data.get('payment_method')
    transaction_id = data.get('transaction_id', '')
    notes = data.get('notes', '')

    if not amount or not payment_method:
        return jsonify({'error': 'Amount and payment method required'}), 400

    db = get_db()
    cur = db.execute(
        '''INSERT INTO telemedicine_payments (session_id, amount, payment_method, transaction_id, status, paid_at, notes)
           VALUES (?, ?, ?, ?, 'completed', CURRENT_TIMESTAMP, ?)''',
        (id, amount, payment_method, transaction_id, notes)
    )
    db.commit()
    db.close()

    log_audit(claims['id'], claims['username'], 'create', 'telemedicine_payment', cur.lastrowid,
              f'Payment MWK {amount} for session {id}')
    return jsonify({'message': 'Payment recorded', 'id': cur.lastrowid}), 201


@telemedicine_bp.route('/api/payments/<int:id>/refund', methods=['POST'])
@login_required
def api_payment_refund(id):
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Admin only'}), 403

    db = get_db()
    payment = db.execute('SELECT * FROM telemedicine_payments WHERE id = ?', (id,)).fetchone()
    if not payment:
        db.close()
        return jsonify({'error': 'Payment not found'}), 404

    db.execute("UPDATE telemedicine_payments SET status = 'refunded' WHERE id = ?", (id,))
    db.commit()
    db.close()

    log_audit(claims['id'], claims['username'], 'refund', 'telemedicine_payment', id,
              f'Refunded MWK {payment["amount"]}')
    return jsonify({'message': 'Payment refunded'})


# ─── API: E-Prescription from session ───

@telemedicine_bp.route('/api/sessions/<int:id>/prescriptions', methods=['GET'])
@login_required
def api_session_prescriptions(id):
    db = get_db()
    prescriptions = db.execute(
        '''SELECT pr.*, u.first_name as prescribed_first, u.last_name as prescribed_last
           FROM prescriptions pr
           LEFT JOIN users u ON pr.prescribed_by = u.id
           WHERE pr.session_id = ?
           ORDER BY pr.created_at DESC''', (id,)
    ).fetchall()
    db.close()
    return jsonify([dict(p) for p in prescriptions])


@telemedicine_bp.route('/api/sessions/<int:id>/prescriptions', methods=['POST'])
@login_required
def api_session_prescription_add(id):
    claims = get_jwt()
    data = request.json
    patient_id = data.get('patient_id')
    drug_name = data.get('drug_name', '').strip()
    dosage = data.get('dosage', '')
    frequency = data.get('frequency', '')
    duration = data.get('duration', '')
    route = data.get('route', 'oral')
    instructions = data.get('instructions', '')
    quantity = data.get('quantity')

    if not patient_id or not drug_name:
        return jsonify({'error': 'Patient and drug name required'}), 400

    db = get_db()
    cur = db.execute(
        '''INSERT INTO prescriptions (session_id, patient_id, drug_name, dosage, frequency, duration, route, instructions, quantity, prescribed_by, prescribed_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_DATE)''',
        (id, patient_id, drug_name, dosage, frequency, duration, route, instructions, quantity, claims['id'])
    )
    db.commit()
    db.close()

    log_audit(claims['id'], claims['username'], 'create', 'prescription', cur.lastrowid,
              f'E-prescription: {drug_name} for session {id}')
    return jsonify({'message': 'Prescription added', 'id': cur.lastrowid}), 201


# ─── API: Doctors list ───

@telemedicine_bp.route('/api/doctors', methods=['GET'])
@login_required
def api_doctors_list():
    db = get_db()
    doctors = db.execute(
        "SELECT id, first_name, last_name, email FROM users WHERE role IN ('doctor', 'locum_doctor') AND is_active = 1 ORDER BY first_name"
    ).fetchall()
    db.close()
    return jsonify([dict(d) for d in doctors])
