from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.database import get_db
from app.auth import login_required

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.route('')
@reports_bp.route('/', strict_slashes=False)
@login_required
def index_page():
    return render_template('reports/index.html')


@reports_bp.route('/api/dashboard', methods=['GET'])
@login_required
def api_dashboard():
    db = get_db()
    from datetime import date, timedelta
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    total_patients = db.execute('SELECT COUNT(*) as c FROM patients').fetchone()['c']
    today_appointments = db.execute(
        'SELECT COUNT(*) as c FROM appointments WHERE appointment_date = ?', (today,)).fetchone()['c']
    pending_appointments = db.execute(
        'SELECT COUNT(*) as c FROM appointments WHERE status = "scheduled"').fetchone()['c']
    today_revenue = db.execute(
        'SELECT COALESCE(SUM(amount_paid), 0) as c FROM billing WHERE DATE(created_at) = ?', (today,)).fetchone()['c']
    total_revenue = db.execute('SELECT COALESCE(SUM(amount_paid), 0) as c FROM billing').fetchone()['c']
    pending_billing = db.execute(
        'SELECT COALESCE(SUM(balance), 0) as c FROM billing WHERE payment_status != "paid"').fetchone()['c']
    low_stock = db.execute(
        'SELECT COUNT(*) as c FROM pharmacy_inventory WHERE stock_quantity <= reorder_level').fetchone()['c']
    total_staff = db.execute('SELECT COUNT(*) as c FROM users WHERE is_active = 1').fetchone()['c']
    doctors_available = db.execute(
        '''SELECT COUNT(*) as c FROM users
           WHERE role IN ('doctor','locum_doctor') AND is_active = 1''').fetchone()['c']

    revenue_7d = db.execute(
        '''SELECT DATE(created_at) as d, COALESCE(SUM(amount_paid), 0) as total
           FROM billing WHERE created_at >= ? GROUP BY DATE(created_at) ORDER BY d''', (week_ago,)).fetchall()

    appointments_today = db.execute(
        '''SELECT a.*, p.first_name as p_first, p.last_name as p_last, p.phone as p_phone,
                  u.first_name as d_first, u.last_name as d_last
           FROM appointments a
           LEFT JOIN patients p ON a.patient_id = p.id
           LEFT JOIN users u ON a.doctor_id = u.id
           WHERE a.appointment_date = ? AND a.type != 'walk_in'
           ORDER BY a.appointment_time ASC''', (today,)).fetchall()

    recent_patients = db.execute(
        'SELECT * FROM patients ORDER BY created_at DESC LIMIT 5').fetchall()

    db.close()
    return jsonify({
        'total_patients': total_patients,
        'today_appointments': today_appointments,
        'pending_appointments': pending_appointments,
        'today_revenue': float(today_revenue),
        'total_revenue': float(total_revenue),
        'pending_billing': float(pending_billing),
        'low_stock': low_stock,
        'total_staff': total_staff,
        'doctors_available': doctors_available,
        'revenue_7d': [{'date': r['d'], 'total': float(r['total'])} for r in revenue_7d],
        'appointments_today': [dict(a) for a in appointments_today],
        'recent_patients': [dict(p) for p in recent_patients]
    })


@reports_bp.route('/api/revenue', methods=['GET'])
@login_required
def api_revenue():
    db = get_db()
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    query = '''SELECT DATE(b.created_at) as d, COUNT(*) as invoice_count,
                      COALESCE(SUM(b.total_amount), 0) as total_billed,
                      COALESCE(SUM(b.amount_paid), 0) as total_paid,
                      COALESCE(SUM(b.balance), 0) as total_balance
               FROM billing b WHERE 1=1'''
    params = []
    if start:
        query += ' AND DATE(b.created_at) >= ?'
        params.append(start)
    if end:
        query += ' AND DATE(b.created_at) <= ?'
        params.append(end)
    query += ' GROUP BY DATE(b.created_at) ORDER BY d DESC'
    data = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(d) for d in data])


@reports_bp.route('/api/patients', methods=['GET'])
@login_required
def api_patient_stats():
    db = get_db()
    total = db.execute('SELECT COUNT(*) as c FROM patients').fetchone()['c']
    male = db.execute('SELECT COUNT(*) as c FROM patients WHERE gender = "Male"').fetchone()['c']
    female = db.execute('SELECT COUNT(*) as c FROM patients WHERE gender = "Female"').fetchone()['c']
    with_scheme = db.execute(
        'SELECT COUNT(*) as c FROM patients WHERE scheme_provider IS NOT NULL AND scheme_provider != ""').fetchone()['c']
    db.close()
    return jsonify({'total': total, 'male': male, 'female': female, 'with_scheme': with_scheme})


@reports_bp.route('/api/appointments', methods=['GET'])
@login_required
def api_appointment_stats():
    db = get_db()
    stats = db.execute(
        '''SELECT status, COUNT(*) as c FROM appointments GROUP BY status''').fetchall()
    by_type = db.execute(
        '''SELECT type, COUNT(*) as c FROM appointments GROUP BY type''').fetchall()
    db.close()
    return jsonify({
        'by_status': [dict(s) for s in stats],
        'by_type': [dict(t) for t in by_type]
    })


@reports_bp.route('/api/inventory', methods=['GET'])
@login_required
def api_inventory_report():
    db = get_db()
    total_items = db.execute('SELECT COUNT(*) as c FROM pharmacy_inventory').fetchone()['c']
    total_value = db.execute(
        'SELECT COALESCE(SUM(stock_quantity * unit_price), 0) as c FROM pharmacy_inventory').fetchone()['c']
    low_stock = db.execute(
        'SELECT COUNT(*) as c FROM pharmacy_inventory WHERE stock_quantity <= reorder_level').fetchone()['c']
    expired = db.execute(
        'SELECT COUNT(*) as c FROM pharmacy_inventory WHERE expiry_date < DATE("now")').fetchone()['c']
    db.close()
    return jsonify({
        'total_items': total_items,
        'total_value': float(total_value),
        'low_stock': low_stock,
        'expired': expired
    })


@reports_bp.route('/api/audit-logs', methods=['GET'])
@login_required
def api_audit_logs():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 50
    offset = (page - 1) * per_page
    logs = db.execute(
        'SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ? OFFSET ?',
        (per_page, offset)).fetchall()
    total = db.execute('SELECT COUNT(*) as c FROM audit_logs').fetchone()['c']
    db.close()
    return jsonify({
        'logs': [dict(l) for l in logs],
        'total': total,
        'page': page,
        'pages': (total + per_page - 1) // per_page
    })


@reports_bp.route('/api/queue', methods=['GET'])
@login_required
def api_queue():
    db = get_db()
    from datetime import date, datetime
    today = date.today().isoformat()
    now = datetime.now()

    queue = db.execute(
        '''SELECT a.id, a.appointment_time, a.reason, a.status, a.type,
                  p.id as patient_id, p.first_name as p_first, p.last_name as p_last, p.phone as p_phone,
                  u.id as doctor_id, u.first_name as d_first, u.last_name as d_last
           FROM appointments a
           JOIN patients p ON a.patient_id = p.id
           LEFT JOIN users u ON a.doctor_id = u.id
           WHERE a.appointment_date = ? AND a.status IN ('scheduled', 'confirmed', 'in_progress') AND a.type = 'walk_in'
           ORDER BY a.appointment_time ASC, a.id ASC''', (today,)).fetchall()

    completed = db.execute(
        '''SELECT a.appointment_time, a.reason,
                  p.first_name as p_first, p.last_name as p_last,
                  u.first_name as d_first, u.last_name as d_last
           FROM appointments a
           JOIN patients p ON a.patient_id = p.id
           LEFT JOIN users u ON a.doctor_id = u.id
           WHERE a.appointment_date = ? AND a.status = 'completed'
           ORDER BY a.updated_at DESC LIMIT 10''', (today,)).fetchall()

    result = []
    for i, apt in enumerate(queue):
        entry = dict(apt)
        entry['position'] = i + 1
        try:
            apt_time = datetime.strptime(apt['appointment_time'], '%H:%M')
            wait_minutes = int((now - apt_time).total_seconds() / 60)
            entry['wait_minutes'] = max(0, wait_minutes)
        except:
            entry['wait_minutes'] = 0
        result.append(entry)

    db.close()
    return jsonify({
        'queue': result,
        'waiting_count': sum(1 for a in queue if a['status'] != 'in_progress'),
        'in_progress_count': sum(1 for a in queue if a['status'] == 'in_progress'),
        'completed_today': len(completed),
        'completed': [dict(c) for c in completed]
    })


@reports_bp.route('/api/consultations', methods=['GET'])
@login_required
def api_consultation_stats():
    db = get_db()
    stats = db.execute(
        'SELECT consultation_type, COUNT(*) as c FROM consultations GROUP BY consultation_type').fetchall()
    db.close()
    return jsonify([dict(s) for s in stats])


@reports_bp.route('/api/procedures', methods=['GET'])
@login_required
def api_procedure_stats():
    db = get_db()
    from datetime import date, datetime
    today = date.today().isoformat()

    total = db.execute('SELECT COUNT(*) as c FROM procedures').fetchone()['c']
    today_count = db.execute(
        'SELECT COUNT(*) as c FROM procedures WHERE DATE(created_at) = ?', (today,)).fetchone()['c']

    by_type = db.execute(
        '''SELECT COALESCE(procedure_type, 'other') as type, COUNT(*) as c
           FROM procedures GROUP BY procedure_type ORDER BY c DESC''').fetchall()

    by_month = db.execute(
        '''SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as c
           FROM procedures GROUP BY month ORDER BY month DESC LIMIT 12''').fetchall()

    recent = db.execute(
        '''SELECT p.*, pt.first_name as p_first, pt.last_name as p_last,
                  u.first_name as u_first, u.last_name as u_last
           FROM procedures p
           LEFT JOIN patients pt ON p.patient_id = pt.id
           LEFT JOIN users u ON p.performed_by = u.id
           ORDER BY p.created_at DESC LIMIT 10''').fetchall()

    db.close()
    return jsonify({
        'total': total,
        'today': today_count,
        'by_type': [dict(t) for t in by_type],
        'by_month': [dict(m) for m in by_month],
        'recent': [dict(r) for r in recent]
    })
