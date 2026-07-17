from flask import Flask, render_template, redirect, request
from flask_jwt_extended import JWTManager
from config import Config
import os, logging, queue, threading, time

jwt = JWTManager()
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    jwt.init_app(app)

    from app.database import init_db
    init_db()

    # Vercel: data restore handled by vercel_cold_start_pull in before_request
    # (restoring in create_app() blocks the process for 24s+ and causes 30s timeout)

    # Local: initial sync to Supabase on startup (backup local data) - run in background
    if not os.environ.get('VERCEL'):
        try:
            from app.backup import sync_all, HAS_PG
            if HAS_PG:
                logger.info("Starting initial backup sync to Supabase in background...")
                import threading
                def _initial_sync():
                    try:
                        results = sync_all()
                        synced = sum(v for v in results.values() if v > 0)
                        logger.info(f"Initial backup sync complete: {synced} rows")
                    except Exception as e:
                        logger.warning(f"Initial backup sync failed: {e}")
                threading.Thread(target=_initial_sync, daemon=True).start()
        except Exception as e:
            logger.warning(f"Failed to start initial backup sync: {e}")

    # Start background auto-sync (pushes SQLite to Supabase periodically)
    # Start background auto-sync (pushes SQLite to Supabase periodically) — skip on Vercel
    if not os.environ.get('VERCEL'):
        try:
            from app.backup import start_auto_sync
            start_auto_sync(app)
        except Exception as e:
            logger.warning(f"Auto-sync failed to start: {e}")

    # Register blueprints
    from app.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.routes.patients import patients_bp
    app.register_blueprint(patients_bp)

    from app.routes.appointments import appointments_bp
    app.register_blueprint(appointments_bp)

    from app.routes.consultations import consultations_bp
    app.register_blueprint(consultations_bp)

    from app.routes.doctors import doctors_bp
    app.register_blueprint(doctors_bp)

    from app.routes.departments import departments_bp
    app.register_blueprint(departments_bp)

    from app.routes.staff import staff_bp
    app.register_blueprint(staff_bp)

    from app.routes.billing import billing_bp
    app.register_blueprint(billing_bp)

    from app.routes.pharmacy import pharmacy_bp
    app.register_blueprint(pharmacy_bp)

    from app.routes.reports import reports_bp
    app.register_blueprint(reports_bp)

    from app.routes.messages import messages_bp
    app.register_blueprint(messages_bp)

    from app.routes.lab import lab_bp
    app.register_blueprint(lab_bp)

    from app.routes.prescriptions import prescriptions_bp
    app.register_blueprint(prescriptions_bp)

    from app.routes.settings import settings_bp
    app.register_blueprint(settings_bp)

    from app.routes.insurance import insurance_bp
    app.register_blueprint(insurance_bp)

    from app.routes.notifications import notifications_bp
    app.register_blueprint(notifications_bp)

    from app.routes.radiology import radiology_bp
    app.register_blueprint(radiology_bp)

    from app.routes.telemedicine import telemedicine_bp
    app.register_blueprint(telemedicine_bp)

    from app.routes.short_stay import short_stay_bp
    app.register_blueprint(short_stay_bp)

    from app.routes.lab_invoices import lab_invoices_bp
    app.register_blueprint(lab_invoices_bp)

    from app.routes.suppliers import suppliers_bp
    app.register_blueprint(suppliers_bp)

    from app.routes.certificates import certificates_bp
    app.register_blueprint(certificates_bp)

    from app.routes.yellow_book import yellow_book_bp
    app.register_blueprint(yellow_book_bp)

    from app.routes.backup import backup_bp
    app.register_blueprint(backup_bp)

    from app.routes.users import users_bp
    app.register_blueprint(users_bp)

    from app.routes.reminders import reminders_bp
    app.register_blueprint(reminders_bp)

    # Vercel: periodic pull from Supabase so warm containers stay fresh.
    #
    # On Vercel, each warm container has its own ephemeral SQLite at /tmp.
    # Writes on Container A sync to Supabase, but Container B's SQLite is stale
    # until it re-pulls. Full restore on cold start, then periodic re-pull of
    # high-velocity tables.
    if os.environ.get('VERCEL'):
        _vercel_state = {'last_pull': 0.0, 'initial_pull_done': False}
        _VERCEL_PULL_TABLES = (
            'appointments', 'patients', 'billing', 'prescriptions',
            'lab_tests', 'consultations',
        )

        @app.before_request
        def vercel_cold_start_pull():
            now = time.time()
            elapsed = now - _vercel_state['last_pull']
            if _vercel_state['initial_pull_done'] and elapsed < 90:
                return
            if request.method == 'GET' or not _vercel_state['initial_pull_done']:
                try:
                    from app.backup import restore_all, restore_table, HAS_PG
                    if HAS_PG:
                        if not _vercel_state['initial_pull_done']:
                            restore_all()
                            logger.info("Vercel: full restore from Supabase (cold start)")
                        else:
                            for t in _VERCEL_PULL_TABLES:
                                restore_table(t)
                            logger.info(f"Vercel: periodic re-pull ({int(elapsed)}s)")
                        _vercel_state['last_pull'] = now
                        _vercel_state['initial_pull_done'] = True
                except Exception as e:
                    logger.error(f"Vercel pull failed: {e}")
                    _vercel_state['initial_pull_done'] = True

    # Vercel: after a write, push just the affected row to Supabase.
    # Uses sync_single_row / sync_delete_row (instant) instead of full-table dump.
    if os.environ.get('VERCEL'):
        _TABLE_ROUTE_MAP = {
            '/lab/invoices': 'lab_invoices',
            '/lab': 'lab_tests',
            '/patients': 'patients',
            '/appointments': 'appointments',
            '/consultations': 'consultations',
            '/billing': 'billing',
            '/prescriptions': 'prescription_orders',
            '/pharmacy': 'pharmacy_inventory',
            '/radiology': 'radiology_orders',
            '/suppliers': 'suppliers',
            '/departments': 'departments',
            '/yellow-book': 'vaccination_records',
            '/insurance': 'insurance_claims',
            '/telemedicine': 'telemedicine_sessions',
            '/short-stay': 'short_stay_admissions',
            '/users': 'users',
            '/staff': 'users',
            '/messages': 'messages',
            '/notifications': 'notifications',
        }
        _TABLE_ROUTE_KEYS = sorted(_TABLE_ROUTE_MAP.keys(), key=len, reverse=True)
        _ANCILLARY_TYPE_TABLE = {
            'lab': 'lab_tests', 'procedure': 'procedures',
            'certificate': 'medical_certificates', 'referral': 'referrals',
            'diet': 'diet_support',
        }

        @app.after_request
        def vercel_fast_sync(response):
            if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE') or response.status_code >= 400:
                return response
            try:
                from app.backup import sync_single_row, sync_delete_row, HAS_PG
                if not HAS_PG:
                    return response
                path = request.path.rstrip('/')
                table = None
                for prefix in _TABLE_ROUTE_KEYS:
                    if path.startswith(prefix):
                        table = _TABLE_ROUTE_MAP[prefix]
                        break
                if table == 'consultations' and '/api/ancillaries' in path:
                    try:
                        body = request.get_json(silent=True) or {}
                        table = _ANCILLARY_TYPE_TABLE.get(body.get('type'), 'consultations')
                    except Exception:
                        pass
                if request.method == 'DELETE' and table:
                    row_id = path.rsplit('/', 1)[-1]
                    if row_id.isdigit():
                        sync_delete_row(table, int(row_id))
                    return response
                if table and request.method in ('POST', 'PUT', 'PATCH'):
                    resp_json = response.get_json(silent=True) or {}
                    row_id = resp_json.get('id')
                    if row_id:
                        sync_single_row(table, row_id)
            except Exception as e:
                logger.error(f"Vercel row sync failed: {e}")
            return response

    @app.route('/help')
    def help_page():
        return render_template('help.html')

    @app.route('/')
    def index():
        return redirect('/dashboard')

    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')

    return app