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

    from app.routes.staff import staff_bp
    app.register_blueprint(staff_bp)

    from app.routes.billing import billing_bp
    app.register_blueprint(billing_bp)

    from app.routes.pharmacy import pharmacy_bp
    app.register_blueprint(pharmacy_bp)

    from app.routes.reports import reports_bp
    app.register_blueprint(reports_bp)

    @app.route('/')
    def index():
        return redirect('/dashboard')

    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')

    return app
