from flask import Blueprint, jsonify, render_template
from app.database import get_db
from app.auth import login_required
from datetime import date, timedelta, datetime

reminders_bp = Blueprint('reminders', __name__, url_prefix='/reminders')


@reminders_bp.route('')
@reminders_bp.route('/', strict_slashes=False)
@login_required
def index_page():
    return render_template('reminders.html')


@reminders_bp.route('/api', methods=['GET'])
@login_required
def api_reminders():
    db = get_db()
    today = date.today()
    today_str = today.isoformat()
    tomorrow_str = (today + timedelta(days=1)).isoformat()

    birthdays_today = db.execute(
        "SELECT id, first_name, last_name, dob, phone FROM patients WHERE dob IS NOT NULL AND strftime('%m-%d', dob) = ?",
        (today.strftime('%m-%d'),)
    ).fetchall()

    birthdays_upcoming = db.execute(
        "SELECT id, first_name, last_name, dob, phone FROM patients WHERE dob IS NOT NULL AND (strftime('%m-%d', dob) > ? AND strftime('%m-%d', dob) <= ?)",
        (today.strftime('%m-%d'), (today + timedelta(days=7)).strftime('%m-%d'))
    ).fetchall()

    # handle year boundary
    if len(birthdays_upcoming) == 0 and today.month < 6:
        birthdays_upcoming = db.execute(
            "SELECT id, first_name, last_name, dob, phone FROM patients WHERE dob IS NOT NULL AND (strftime('%m-%d', dob) >= ?)",
            (today.strftime('%m-%d'),)
        ).fetchall()

    apts_tomorrow = db.execute(
        '''SELECT a.id, a.appointment_time, a.reason, a.status,
                  p.id as patient_id, p.first_name as p_first, p.last_name as p_last, p.phone
           FROM appointments a JOIN patients p ON a.patient_id = p.id
           WHERE a.appointment_date = ?''',
        (tomorrow_str,)
    ).fetchall()

    def calc_age(dob_str):
        if not dob_str:
            return None
        dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    def patient_json(row):
        d = dict(row)
        d['age'] = calc_age(d['dob'])
        return d

    db.close()

    return jsonify({
        'birthdays_today': [patient_json(r) for r in birthdays_today],
        'birthdays_upcoming': [patient_json(r) for r in birthdays_upcoming],
        'appointments_tomorrow': [dict(r) for r in apts_tomorrow]
    })
