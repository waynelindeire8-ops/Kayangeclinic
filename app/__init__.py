from flask import Flask, render_template, redirect
from flask_jwt_extended import JWTManager
from config import Config

jwt = JWTManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    jwt.init_app(app)

    from app.database import init_db
    init_db()

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

    from app.routes.backup import backup_bp
    app.register_blueprint(backup_bp)

    @app.route('/')
    def index():
        return redirect('/dashboard')

    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')

    return app
