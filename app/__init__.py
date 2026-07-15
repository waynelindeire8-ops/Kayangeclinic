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

    # Vercel: restore from Supabase on cold start (ephemeral storage)
    if os.environ.get('VERCEL'):
        try:
            from app.backup import init_supabase_tables, restore_all, HAS_PG
            if HAS_PG:
                logger.info("Vercel: Initializing Supabase tables...")
                init_supabase_tables()
                logger.info("Vercel: Restoring data from Supabase...")
                results = restore_all()
                total = sum(v for v in results.values() if v > 0)
                logger.info(f"Vercel: Restored {total} rows from Supabase")
        except Exception as e:
            logger.error(f"Vercel restore failed: {e}")

    # Local: initial sync to Supabase on startup (backup local data) - run in background
    elif not os.environ.get('VERCEL'):
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
    # until it re-pulls. Full restore on cold start, then only high-velocity
    # tables (appointments, patients, billing) every 90s to keep it lightweight.
    if os.environ.get('VERCEL'):
        _vercel_state = {'last_pull': 0.0, 'initial_pull_done': False}
        _VERCEL_PULL_TABLES = ('appointments', 'patients', 'billing', 'prescriptions', 'lab_tests')

        @app.before_request
        def vercel_cold_start_pull():
            now = time.time()
            elapsed = now - _vercel_state['last_pull']
            # First GET: full restore (cold start). Subsequent: light pull every 90s.
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
                            logger.info(f"Vercel: periodic re-pull from Supabase ({int(elapsed)}s since last)")
                        _vercel_state['last_pull'] = now
                        _vercel_state['initial_pull_done'] = True
                except Exception as e:
                    logger.error(f"Vercel pull failed: {e}")
                    _vercel_state['initial_pull_done'] = True

    # Vercel: sync only the affected table to Supabase after writes.
    #
    # Previously synced ALL 5 tables on every write — now we only sync the
    # tables that map to the request path, cutting write latency ~5x.
    if os.environ.get('VERCEL'):
        _TABLE_ROUTE_MAP = {
            '/patients': 'patients',
            '/appointments': 'appointments',
            '/consultations': 'consultations',
            '/billing': 'billing',
            '/prescriptions': 'prescriptions',
            '/lab': 'lab_tests',
        }

        @app.after_request
        def vercel_fast_sync(response):
            if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and response.status_code < 400:
                try:
                    from app.backup import sync_table_fast, HAS_PG
                    if HAS_PG:
                        path = request.path.rstrip('/')
                        for prefix, table in _TABLE_ROUTE_MAP.items():
                            if path.startswith(prefix):
                                sync_table_fast(table)
                                break
                except Exception as e:
                    logger.error(f"Vercel inline sync failed: {e}")
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