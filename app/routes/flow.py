from flask import Blueprint, jsonify, render_template, request
from app.database import get_db
from app.auth import login_required, get_jwt
from app.routes.notifications import notify
from datetime import datetime

flow_bp = Blueprint('flow', __name__, url_prefix='/flow')


def transfer_patient(db, patient_id, to_department_id, moved_by, notes=''):
    """Transfer a patient to a new department. Creates flow entry + log + notifications."""
    current = db.execute('SELECT * FROM patient_flow WHERE patient_id=?', (patient_id,)).fetchone()
    from_dept = current['department_id'] if current else None

    if current:
        db.execute(
            'UPDATE patient_flow SET department_id=?, status=?, notes=?, assigned_to=?, updated_at=CURRENT_TIMESTAMP WHERE patient_id=?',
            (to_department_id, 'waiting', notes, moved_by, patient_id))
    else:
        db.execute(
            'INSERT INTO patient_flow (patient_id, department_id, status, notes, assigned_to) VALUES (?,?,?,?,?)',
            (patient_id, to_department_id, 'waiting', notes, moved_by))

    db.execute(
        'INSERT INTO patient_flow_log (patient_id, from_department_id, to_department_id, moved_by, notes) VALUES (?,?,?,?,?)',
        (patient_id, from_dept, to_department_id, moved_by, notes))

    dept = db.execute('SELECT name FROM departments WHERE id=?', (to_department_id,)).fetchone()
    patient = db.execute('SELECT first_name, last_name, patient_id FROM patients WHERE id=?', (patient_id,)).fetchone()
    if dept and patient:
        dept_users = db.execute(
            'SELECT id FROM users WHERE department_id=? AND is_active=1', (to_department_id,)).fetchall()
        for u in dept_users:
            notify(db, u['id'], 'Patient Arrived',
                   f'{patient["first_name"]} {patient["last_name"]} ({patient["patient_id"]}) has arrived in {dept["name"]}',
                   'info', f'/patients/{patient_id}')


def complete_patient_flow(db, patient_id, moved_by):
    """Mark a patient's flow as completed (discharge)."""
    current = db.execute('SELECT * FROM patient_flow WHERE patient_id=?', (patient_id,)).fetchone()
    if current:
        db.execute(
            'UPDATE patient_flow SET status=?, updated_at=CURRENT_TIMESTAMP WHERE patient_id=?',
            ('completed', patient_id))
        db.execute(
            'INSERT INTO patient_flow_log (patient_id, from_department_id, to_department_id, moved_by, notes) VALUES (?,?,?,?,?)',
            (patient_id, current['department_id'], current['department_id'], moved_by, 'Discharged'))


@flow_bp.route('')
@flow_bp.route('/', strict_slashes=False)
@login_required
def index_page():
    return render_template('flow/overview.html')


@flow_bp.route('/api/overview', methods=['GET'])
@login_required
def api_overview():
    db = get_db()
    departments = db.execute(
        'SELECT id, name, description FROM departments WHERE is_active=1 ORDER BY name').fetchall()
    result = []
    for dept in departments:
        patients = db.execute(
            '''SELECT pf.id, pf.status, pf.notes, pf.created_at, pf.updated_at,
                      p.id as patient_id, p.patient_id as patient_code,
                      p.first_name, p.last_name, p.phone,
                      u.first_name as assigned_first, u.last_name as assigned_last
               FROM patient_flow pf
               JOIN patients p ON pf.patient_id = p.id
               LEFT JOIN users u ON pf.assigned_to = u.id
               WHERE pf.department_id=? AND pf.status != 'completed'
               ORDER BY pf.updated_at DESC''',
            (dept['id'],)).fetchall()
        result.append({
            'id': dept['id'],
            'name': dept['name'],
            'description': dept['description'],
            'patient_count': len(patients),
            'patients': [dict(p) for p in patients]
        })
    db.close()
    return jsonify({'departments': result})


@flow_bp.route('/api/department/<int:dept_id>', methods=['GET'])
@login_required
def api_department(dept_id):
    db = get_db()
    dept = db.execute('SELECT * FROM departments WHERE id=?', (dept_id,)).fetchone()
    if not dept:
        db.close()
        return jsonify({'error': 'Department not found'}), 404
    patients = db.execute(
        '''SELECT pf.id, pf.status, pf.notes, pf.created_at, pf.updated_at,
                  p.id as patient_id, p.patient_id as patient_code,
                  p.first_name, p.last_name, p.phone, p.gender,
                  u.first_name as assigned_first, u.last_name as assigned_last
           FROM patient_flow pf
           JOIN patients p ON pf.patient_id = p.id
           LEFT JOIN users u ON pf.assigned_to = u.id
           WHERE pf.department_id=? AND pf.status != 'completed'
           ORDER BY pf.updated_at DESC''',
        (dept_id,)).fetchall()
    db.close()
    return jsonify({
        'department': dict(dept),
        'patients': [dict(p) for p in patients]
    })


@flow_bp.route('/api/transfer', methods=['POST'])
@login_required
def api_transfer():
    data = request.json
    patient_id = data.get('patient_id')
    to_dept_id = data.get('to_department_id')
    notes = data.get('notes', '')
    if not patient_id or not to_dept_id:
        return jsonify({'error': 'patient_id and to_department_id required'}), 400
    db = get_db()
    current_user = get_jwt()
    transfer_patient(db, patient_id, to_dept_id, current_user['id'], notes)
    db.commit()
    db.close()
    return jsonify({'message': 'Patient transferred'}), 201


@flow_bp.route('/api/patient/<int:patient_id>', methods=['GET'])
@login_required
def api_patient_flow(patient_id):
    db = get_db()
    flow = db.execute(
        '''SELECT pf.*, d.name as department_name
           FROM patient_flow pf
           JOIN departments d ON pf.department_id = d.id
           WHERE pf.patient_id=?''',
        (patient_id,)).fetchone()
    log = db.execute(
        '''SELECT pfl.*, fd.name as from_dept_name, td.name as to_dept_name,
                  u.first_name as moved_first, u.last_name as moved_last
           FROM patient_flow_log pfl
           LEFT JOIN departments fd ON pfl.from_department_id = fd.id
           JOIN departments td ON pfl.to_department_id = td.id
           LEFT JOIN users u ON pfl.moved_by = u.id
           WHERE pfl.patient_id=?
           ORDER BY pfl.created_at DESC''',
        (patient_id,)).fetchall()
    db.close()
    return jsonify({
        'current': dict(flow) if flow else None,
        'history': [dict(l) for l in log]
    })


@flow_bp.route('/api/log', methods=['GET'])
@login_required
def api_flow_log():
    db = get_db()
    limit = request.args.get('limit', 50, type=int)
    log = db.execute(
        '''SELECT pfl.*, p.first_name as p_first, p.last_name as p_last, p.patient_id as patient_code,
                  fd.name as from_dept_name, td.name as to_dept_name,
                  u.first_name as moved_first, u.last_name as moved_last
           FROM patient_flow_log pfl
           JOIN patients p ON pfl.patient_id = p.id
           LEFT JOIN departments fd ON pfl.from_department_id = fd.id
           JOIN departments td ON pfl.to_department_id = td.id
           LEFT JOIN users u ON pfl.moved_by = u.id
           ORDER BY pfl.created_at DESC
           LIMIT ?''',
        (limit,)).fetchall()
    db.close()
    return jsonify({'log': [dict(l) for l in log]})


@flow_bp.route('/api/discharge', methods=['POST'])
@login_required
def api_discharge():
    data = request.json
    patient_id = data.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'patient_id required'}), 400
    db = get_db()
    current_user = get_jwt()
    complete_patient_flow(db, patient_id, current_user['id'])
    db.commit()
    db.close()
    return jsonify({'message': 'Patient discharged'})
