from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required, log_audit

certificates_bp = Blueprint('certificates', __name__, url_prefix='/certificates')


@certificates_bp.route('/', strict_slashes=False)
@login_required
def list_page():
    return render_template('certificates/list.html')


@certificates_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    db = get_db()
    cert_type = request.args.get('type', '')
    patient_id = request.args.get('patient_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = '''SELECT mc.*, p.first_name as p_first, p.last_name as p_last,
                      p.patient_id as p_patient_id, u.first_name as d_first, u.last_name as d_last
               FROM medical_certificates mc
               LEFT JOIN patients p ON mc.patient_id = p.id
               LEFT JOIN users u ON mc.doctor_id = u.id
               WHERE 1=1'''
    params = []
    if cert_type:
        query += ' AND mc.certificate_type = ?'
        params.append(cert_type)
    if patient_id:
        query += ' AND mc.patient_id = ?'
        params.append(patient_id)
    if date_from:
        query += ' AND mc.issue_date >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND mc.issue_date <= ?'
        params.append(date_to)
    query += ' ORDER BY mc.created_at DESC'
    certs = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(c) for c in certs])


@certificates_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_get(id):
    db = get_db()
    cert = db.execute(
        '''SELECT mc.*, p.first_name as p_first, p.last_name as p_last,
                  p.patient_id as p_patient_id, p.phone as p_phone, p.passport_number,
                  u.first_name as d_first, u.last_name as d_last
           FROM medical_certificates mc
           LEFT JOIN patients p ON mc.patient_id = p.id
           LEFT JOIN users u ON mc.doctor_id = u.id
           WHERE mc.id = ?''', (id,)).fetchone()
    db.close()
    if not cert:
        return jsonify({'error': 'Certificate not found'}), 404
    return jsonify(dict(cert))


@certificates_bp.route('/api/stats', methods=['GET'])
@login_required
def api_stats():
    db = get_db()
    total = db.execute('SELECT COUNT(*) as c FROM medical_certificates').fetchone()['c']
    yellow_book = db.execute(
        "SELECT COUNT(*) as c FROM medical_certificates WHERE certificate_type = 'yellow_book'"
    ).fetchone()['c']
    foreign_stamp = db.execute(
        "SELECT COUNT(*) as c FROM medical_certificates WHERE certificate_type = 'foreign_stamp'"
    ).fetchone()['c']
    sick_notes = db.execute(
        "SELECT COUNT(*) as c FROM medical_certificates WHERE certificate_type = 'sick_note'"
    ).fetchone()['c']
    this_month = db.execute(
        "SELECT COUNT(*) as c FROM medical_certificates WHERE issue_date >= DATE('now', 'start of month')"
    ).fetchone()['c']
    db.close()
    return jsonify({
        'total': total, 'yellow_book': yellow_book, 'foreign_stamp': foreign_stamp,
        'sick_notes': sick_notes, 'this_month': this_month
    })
