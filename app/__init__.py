from flask import Flask, render_template, redirect, request
from flask_jwt_extended import JWTManager
from config import Config
import os, logging

jwt = JWTManager()
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    jwt.init_app(app)

    from app.database import init_db
    init_db()

    # On Vercel: sync any local changes to Supabase first, then restore on cold start
    if os.environ.get('VERCEL'):
        try:
            from app.backup import sync_all, restore_all, HAS_PG
            if HAS_PG:
                logger.info("Vercel: Pushing local changes to Supabase...")
                sync_results = sync_all()
                pushed = sum(v for v in sync_results.values() if v > 0)
                logger.info(f"Vercel: Synced {pushed} rows to Supabase")

                logger.info("Vercel: Restoring data from Supabase...")
                results = restore_all()
                total = sum(v for v in results.values() if v > 0)
                logger.info(f"Vercel: Restored {total} rows from Supabase")
        except Exception as e:
            logger.error(f"Vercel restore failed: {e}")

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

    # Start background auto-sync (pushes SQLite to Supabase periodically)
    try:
        from app.backup import start_auto_sync
        start_auto_sync(app)
    except Exception as e:
        logger.warning(f"Auto-sync failed to start: {e}")

    # On Vercel, sync to Supabase immediately after any write request
    if os.environ.get('VERCEL'):
        @app.after_request
        def sync_after_write(response):
            if response.status_code in (200, 201, 204) and request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                try:
                    from app.backup import sync_all, HAS_PG
                    if HAS_PG:
                        import threading
                        threading.Thread(target=sync_all, daemon=True).start()
                except Exception:
                    pass
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
