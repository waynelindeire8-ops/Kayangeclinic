import os
import sqlite3
from werkzeug.security import generate_password_hash
from config import Config


def get_db():
    conn = sqlite3.connect(Config.DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _migrate_appointments_type(conn):
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='appointments'"
    ).fetchone()
    if schema and 'walk_in' not in schema['sql']:
        conn.executescript('''
            DROP TABLE IF EXISTS appointments_new;
            CREATE TABLE appointments_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                doctor_id INTEGER,
                appointment_date DATE NOT NULL,
                appointment_time TIME NOT NULL,
                reason TEXT,
                status TEXT DEFAULT 'scheduled' CHECK(status IN ('scheduled','confirmed','in_progress','completed','cancelled','no_show')),
                type TEXT DEFAULT 'phone' CHECK(type IN ('phone','online','walk_in')),
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE,
                FOREIGN KEY(doctor_id) REFERENCES users(id),
                FOREIGN KEY(created_by) REFERENCES users(id)
            );
            INSERT INTO appointments_new SELECT * FROM appointments;
            DROP TABLE appointments;
            ALTER TABLE appointments_new RENAME TO appointments;
        ''')
        conn.commit()


def init_db():
    db_exists = os.path.exists(Config.DATABASE)
    conn = get_db()

    if db_exists:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if len(tables) > 5:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS patient_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    file_size INTEGER,
                    mime_type TEXT,
                    notes TEXT,
                    uploaded_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
                )''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS vaccines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vaccine_name TEXT NOT NULL,
                    manufacturer TEXT,
                    vaccine_type TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS vaccination_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL,
                    vaccine_id INTEGER NOT NULL,
                    dose_number INTEGER DEFAULT 1,
                    batch_number TEXT,
                    manufacturer TEXT,
                    date_administered DATE NOT NULL,
                    administered_by INTEGER REFERENCES users(id),
                    injection_site TEXT,
                    notes TEXT,
                    next_dose_due DATE,
                    certificate_id INTEGER REFERENCES medical_certificates(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE,
                    FOREIGN KEY(vaccine_id) REFERENCES vaccines(id)
                )''')
            _migrate_patients_yellow_book_fields(conn)
            _seed_vaccines(conn)
            _create_indexes(conn)
            conn.commit()
            conn.close()
            return

    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','doctor','locum_doctor','nurse','locum_nurse','lab_staff','lab_supervisor','lab_tech','lab_care','front_desk','file_manager')),
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT UNIQUE NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            dob DATE,
            gender TEXT CHECK(gender IN ('Male','Female','Other')),
            phone TEXT,
            email TEXT,
            address TEXT,
            emergency_contact_name TEXT,
            emergency_contact_phone TEXT,
            blood_group TEXT,
            scheme_provider TEXT,
            scheme_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS patient_allergies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            allergy TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS patient_medical_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            condition_name TEXT NOT NULL,
            diagnosis_date DATE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS patient_medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            medication_name TEXT NOT NULL,
            dosage TEXT,
            frequency TEXT,
            prescribed_by INTEGER,
            start_date DATE,
            end_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE,
            FOREIGN KEY(prescribed_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER,
            appointment_date DATE NOT NULL,
            appointment_time TIME NOT NULL,
            reason TEXT,
            status TEXT DEFAULT 'scheduled' CHECK(status IN ('scheduled','confirmed','in_progress','completed','cancelled','no_show')),
            type TEXT DEFAULT 'phone' CHECK(type IN ('phone','online','walk_in')),
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE,
            FOREIGN KEY(doctor_id) REFERENCES users(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            appointment_id INTEGER,
            consultation_type TEXT CHECK(consultation_type IN ('general','internal_medicine')),
            diagnosis TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(doctor_id) REFERENCES users(id),
            FOREIGN KEY(appointment_id) REFERENCES appointments(id)
        );

        CREATE TABLE IF NOT EXISTS lab_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER,
            test_name TEXT NOT NULL,
            test_category TEXT DEFAULT 'general',
            results TEXT,
            status TEXT DEFAULT 'ordered' CHECK(status IN ('ordered','collected','in_progress','completed')),
            ordered_date DATE,
            completed_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(doctor_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS procedures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            performed_by INTEGER,
            procedure_type TEXT CHECK(procedure_type IN ('short_stay','nebulisation','burn_wound','ecg','other')),
            notes TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(performed_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS medical_certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            certificate_type TEXT CHECK(certificate_type IN ('sick_note','tep','insurance','police','yellow_book','foreign_stamp')),
            issue_date DATE NOT NULL,
            valid_until DATE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(doctor_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS vaccines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vaccine_name TEXT NOT NULL,
            manufacturer TEXT,
            vaccine_type TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vaccination_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            vaccine_id INTEGER NOT NULL,
            dose_number INTEGER DEFAULT 1,
            batch_number TEXT,
            manufacturer TEXT,
            date_administered DATE NOT NULL,
            administered_by INTEGER REFERENCES users(id),
            injection_site TEXT,
            notes TEXT,
            next_dose_due DATE,
            certificate_id INTEGER REFERENCES medical_certificates(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE,
            FOREIGN KEY(vaccine_id) REFERENCES vaccines(id)
        );

        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package_name TEXT NOT NULL,
            description TEXT,
            total_amount REAL NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS package_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package_id INTEGER NOT NULL,
            service_name TEXT NOT NULL,
            service_type TEXT,
            FOREIGN KEY(package_id) REFERENCES packages(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS billing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            appointment_id INTEGER,
            package_id INTEGER,
            invoice_number TEXT UNIQUE NOT NULL,
            total_amount REAL NOT NULL,
            amount_paid REAL DEFAULT 0,
            balance REAL DEFAULT 0,
            payment_method TEXT CHECK(payment_method IN ('cash','card','insurance','mobile_money')),
            payment_status TEXT DEFAULT 'pending' CHECK(payment_status IN ('pending','partial','paid')),
            insurance_claim_id TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(appointment_id) REFERENCES appointments(id),
            FOREIGN KEY(package_id) REFERENCES packages(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS billing_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            billing_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_type TEXT CHECK(item_type IN ('consultation','lab','procedure','pharmacy','certificate','package')),
            quantity INTEGER DEFAULT 1,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            FOREIGN KEY(billing_id) REFERENCES billing(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS lab_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT UNIQUE NOT NULL,
            patient_id INTEGER NOT NULL,
            total_amount REAL NOT NULL DEFAULT 0,
            amount_paid REAL DEFAULT 0,
            balance REAL DEFAULT 0,
            payment_method TEXT CHECK(payment_method IN ('cash','card','insurance','mobile_money')),
            payment_status TEXT DEFAULT 'pending' CHECK(payment_status IN ('pending','partial','paid')),
            notes TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS lab_invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_invoice_id INTEGER NOT NULL,
            lab_test_id INTEGER,
            item_name TEXT NOT NULL,
            description TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            FOREIGN KEY(lab_invoice_id) REFERENCES lab_invoices(id) ON DELETE CASCADE,
            FOREIGN KEY(lab_test_id) REFERENCES lab_tests(id)
        );

        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_person TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            category TEXT DEFAULT 'general',
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pharmacy_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name TEXT NOT NULL,
            generic_name TEXT,
            category TEXT,
            stock_quantity INTEGER DEFAULT 0,
            unit_price REAL NOT NULL,
            expiry_date DATE,
            supplier TEXT,
            reorder_level INTEGER DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pharmacy_dispensing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            inventory_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            prescription_notes TEXT,
            dispensed_by INTEGER,
            dispensed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(inventory_id) REFERENCES pharmacy_inventory(id),
            FOREIGN KEY(dispensed_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS drug_scheme_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_id INTEGER NOT NULL,
            provider_id INTEGER NOT NULL,
            scheme_price REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(inventory_id) REFERENCES pharmacy_inventory(id) ON DELETE CASCADE,
            FOREIGN KEY(provider_id) REFERENCES insurance_providers(id) ON DELETE CASCADE,
            UNIQUE(inventory_id, provider_id)
        );

        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            from_doctor_id INTEGER,
            to_facility TEXT NOT NULL,
            reason TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(from_doctor_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS diet_support (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            dietitian_name TEXT,
            plan_details TEXT,
            start_date DATE,
            end_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        );

        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id INTEGER,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS vital_signs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            bp_systolic INTEGER,
            bp_diastolic INTEGER,
            heart_rate INTEGER,
            temperature REAL,
            respiratory_rate INTEGER,
            oxygen_saturation INTEGER,
            weight REAL,
            height REAL,
            bmi REAL,
            notes TEXT,
            recorded_by INTEGER,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(consultation_id) REFERENCES consultations(id) ON DELETE CASCADE,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(recorded_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS medical_examinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id INTEGER NOT NULL,
            system_name TEXT NOT NULL,
            findings TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(consultation_id) REFERENCES consultations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id INTEGER NOT NULL,
            diagnosis_name TEXT NOT NULL,
            diagnosis_type TEXT NOT NULL CHECK(diagnosis_type IN ('primary','secondary','complication')),
            icd_code TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(consultation_id) REFERENCES consultations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            inventory_id INTEGER,
            drug_name TEXT NOT NULL,
            dosage TEXT,
            frequency TEXT,
            duration TEXT,
            route TEXT,
            instructions TEXT,
            quantity INTEGER,
            status TEXT DEFAULT 'active' CHECK(status IN ('active','discontinued','completed')),
            prescribed_by INTEGER,
            prescribed_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(consultation_id) REFERENCES consultations(id) ON DELETE CASCADE,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(inventory_id) REFERENCES pharmacy_inventory(id),
            FOREIGN KEY(prescribed_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            read_at TIMESTAMP,
            sender_deleted INTEGER DEFAULT 0,
            receiver_deleted INTEGER DEFAULT 0,
            FOREIGN KEY(sender_id) REFERENCES users(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS lab_test_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_name TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            sample_type TEXT DEFAULT 'blood',
            classification TEXT DEFAULT 'standard',
            description TEXT,
            default_price REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS lab_test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_test_id INTEGER NOT NULL,
            parameter_name TEXT NOT NULL,
            value TEXT,
            reference_range TEXT,
            unit TEXT,
            flag TEXT CHECK(flag IN ('normal','high','low','critical_high','critical_low','pending')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(lab_test_id) REFERENCES lab_tests(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS prescription_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            notes TEXT,
            status TEXT DEFAULT 'active' CHECK(status IN ('active','completed','cancelled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(doctor_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS prescription_refills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            refill_date DATE NOT NULL,
            quantity INTEGER,
            refilled_by INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES prescription_orders(id),
            FOREIGN KEY(refilled_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS insurance_providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE,
            contact_person TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS patient_insurance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            provider_id INTEGER NOT NULL,
            policy_number TEXT NOT NULL,
            member_name TEXT,
            group_number TEXT,
            effective_date DATE,
            expiry_date DATE,
            is_primary INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE,
            FOREIGN KEY(provider_id) REFERENCES insurance_providers(id)
        );

        CREATE TABLE IF NOT EXISTS insurance_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_number TEXT UNIQUE,
            patient_id INTEGER NOT NULL,
            provider_id INTEGER NOT NULL,
            policy_id INTEGER,
            billing_id INTEGER,
            consultation_id INTEGER,
            claim_date DATE NOT NULL,
            service_date DATE,
            total_amount REAL NOT NULL,
            approved_amount REAL DEFAULT 0,
            paid_amount REAL DEFAULT 0,
            status TEXT DEFAULT 'draft' CHECK(status IN ('draft','submitted','in_review','additional_info','approved','partially_approved','denied','appealed','paid','cancelled')),
            submitted_date DATE,
            reviewed_date DATE,
            paid_date DATE,
            denial_reason TEXT,
            notes TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(provider_id) REFERENCES insurance_providers(id),
            FOREIGN KEY(policy_id) REFERENCES patient_insurance(id),
            FOREIGN KEY(billing_id) REFERENCES billing(id),
            FOREIGN KEY(consultation_id) REFERENCES consultations(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS claim_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            procedure_code TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            FOREIGN KEY(claim_id) REFERENCES insurance_claims(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS claim_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            notes TEXT,
            changed_by INTEGER,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(claim_id) REFERENCES insurance_claims(id) ON DELETE CASCADE,
            FOREIGN KEY(changed_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            type TEXT DEFAULT 'info',
            reference_url TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS radiology_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER,
            modality TEXT NOT NULL CHECK(modality IN ('xray','ultrasound','ct','mri','ecg','echo','mammogram','fluoroscopy','other')),
            body_part TEXT,
            clinical_history TEXT,
            status TEXT DEFAULT 'ordered' CHECK(status IN ('ordered','in_progress','completed','cancelled','referred')),
            ordered_date DATE,
            completed_date DATE,
            referred_to TEXT,
            priority TEXT DEFAULT 'routine' CHECK(priority IN ('routine','urgent','stat')),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(doctor_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS radiology_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            findings TEXT,
            impression TEXT,
            recommendation TEXT,
            result_image_path TEXT,
            reported_by INTEGER,
            reported_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES radiology_orders(id) ON DELETE CASCADE,
            FOREIGN KEY(reported_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS telemedicine_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            appointment_id INTEGER,
            consultation_id INTEGER,
            status TEXT DEFAULT 'scheduled' CHECK(status IN ('scheduled','waiting','in_progress','completed','cancelled','no_show')),
            session_type TEXT DEFAULT 'video' CHECK(session_type IN ('video','audio','chat')),
            reason TEXT,
            diagnosis TEXT,
            notes TEXT,
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
            duration_minutes INTEGER,
            token_patient TEXT,
            token_doctor TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(doctor_id) REFERENCES users(id),
            FOREIGN KEY(appointment_id) REFERENCES appointments(id),
            FOREIGN KEY(consultation_id) REFERENCES consultations(id)
        );

        CREATE TABLE IF NOT EXISTS telemedicine_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES telemedicine_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(sender_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS telemedicine_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'MWK',
            payment_method TEXT CHECK(payment_method IN ('mobile_money','card','cash','insurance','bank_transfer')),
            transaction_id TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending','completed','failed','refunded')),
            paid_at TIMESTAMP,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES telemedicine_sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS telemedicine_recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            recording_url TEXT,
            duration INTEGER,
            file_size INTEGER,
            recorded_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES telemedicine_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(recorded_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS insurance_authorization_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL,
            item_type TEXT NOT NULL CHECK(item_type IN ('pharmacy','procedure','lab','radiology','consultation')),
            item_name TEXT NOT NULL,
            requires_auth INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(provider_id) REFERENCES insurance_providers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS short_stay_beds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bed_number INTEGER NOT NULL,
            label TEXT NOT NULL,
            status TEXT DEFAULT 'available' CHECK(status IN ('available','occupied','reserved','cleaning')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS short_stay_drip_stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_number INTEGER NOT NULL,
            label TEXT NOT NULL,
            status TEXT DEFAULT 'available' CHECK(status IN ('available','occupied','reserved')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS short_stay_admissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            bed_id INTEGER,
            drip_station_id INTEGER,
            admitted_by INTEGER NOT NULL,
            admitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            discharge_type TEXT,
            discharged_at TIMESTAMP,
            diagnosis TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(bed_id) REFERENCES short_stay_beds(id),
            FOREIGN KEY(drip_station_id) REFERENCES short_stay_drip_stations(id),
            FOREIGN KEY(admitted_by) REFERENCES users(id)
        );
    ''')

    conn.commit()
    _migrate_appointments_type(conn)
    _migrate_lab_catalog_params(conn)
    _migrate_prescriptions(conn)
    _seed_system_config(conn)
    _seed_insurance_providers(conn)
    _seed_insurance_providers_missing(conn)
    _migrate_lab_barcode(conn)
    _seed_radiology_catalog(conn)
    _migrate_telemedicine(conn)
    _seed_auth_rules(conn)
    _seed_short_stay(conn)
    _migrate_procedures_ecg(conn)
    _migrate_radiology_refer(conn)
    _migrate_lab_roles(conn)
    _seed_inventory(conn)
    _migrate_catalog_classification(conn)
    _migrate_certificates_yellow_book(conn)
    _seed_lab_catalog(conn)
    _migrate_dispensing_unit_price(conn)
    _migrate_patients_nullable(conn)
    _migrate_patients_yellow_book_fields(conn)
    _seed_vaccines(conn)
    _migrate_patient_documents(conn)
    _seed_admin_user(conn)
    conn.close()


def _migrate_lab_catalog_params(conn):
    try:
        conn.execute("ALTER TABLE lab_test_catalog ADD COLUMN default_params TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_prescriptions(conn):
    try:
        conn.execute("ALTER TABLE prescriptions ADD COLUMN order_id INTEGER REFERENCES prescription_orders(id)")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE prescriptions ADD COLUMN refill_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='prescriptions'"
    ).fetchone()
    if schema and 'NOT NULL' in schema['sql'].split('consultation_id')[-1].split(',')[0]:
        conn.executescript('''
            DROP TABLE IF EXISTS prescriptions_new;
            CREATE TABLE prescriptions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                consultation_id INTEGER,
                order_id INTEGER,
                patient_id INTEGER NOT NULL,
                inventory_id INTEGER,
                drug_name TEXT NOT NULL,
                dosage TEXT,
                frequency TEXT,
                duration TEXT,
                route TEXT,
                instructions TEXT,
                quantity INTEGER,
                refill_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active' CHECK(status IN ('active','discontinued','completed')),
                prescribed_by INTEGER,
                prescribed_date DATE DEFAULT CURRENT_DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(consultation_id) REFERENCES consultations(id) ON DELETE CASCADE,
                FOREIGN KEY(order_id) REFERENCES prescription_orders(id),
                FOREIGN KEY(patient_id) REFERENCES patients(id),
                FOREIGN KEY(inventory_id) REFERENCES pharmacy_inventory(id),
                FOREIGN KEY(prescribed_by) REFERENCES users(id)
            );
            INSERT INTO prescriptions_new SELECT id, consultation_id, NULL, patient_id, inventory_id, drug_name, dosage, frequency, duration, route, instructions, quantity, 0, status, prescribed_by, prescribed_date, created_at FROM prescriptions;
            DROP TABLE prescriptions;
            ALTER TABLE prescriptions_new RENAME TO prescriptions;
        ''')
        conn.commit()


def _migrate_telemedicine(conn):
    try:
        conn.execute("ALTER TABLE telemedicine_sessions ADD COLUMN session_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE telemedicine_sessions ADD COLUMN token_patient TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE telemedicine_sessions ADD COLUMN token_doctor TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE prescriptions ADD COLUMN session_id INTEGER REFERENCES telemedicine_sessions(id)")
    except sqlite3.OperationalError:
        pass
    _migrate_patient_scheme(conn)
    conn.commit()


def _migrate_patient_scheme(conn):
    try:
        conn.execute("ALTER TABLE patients ADD COLUMN scheme_id INTEGER REFERENCES insurance_providers(id)")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE patients ADD COLUMN scheme_number TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def _seed_system_config(conn):
    defaults = {
        'clinic_name': 'Kayange Clinic',
        'clinic_address': 'Blantyre, Malawi',
        'clinic_phone': '+265 1 XXX XXXX',
        'clinic_email': '',
        'timezone': 'Africa/Blantyre',
        'date_format': 'DD/MM/YYYY',
        'currency': 'MWK',
        'low_stock_threshold': '10',
        'appointment_slot_minutes': '30',
        'auto_sync_interval': '1',
    }
    existing = {r[0] for r in conn.execute('SELECT key FROM system_config').fetchall()}
    for k, v in defaults.items():
        if k not in existing:
            conn.execute('INSERT INTO system_config (key, value) VALUES (?, ?)', (k, v))
    conn.commit()


def _seed_insurance_providers(conn):
    existing = conn.execute('SELECT COUNT(*) as c FROM insurance_providers').fetchone()['c']
    if existing > 0:
        return
    providers = [
        ('NHIMA', 'NHIMA', 'National Health Insurance Management Authority', '+265 1 750 777', 'info@nhima.mw', 'Lilongwe, Malawi'),
        ('First Capital Health Insurance', 'FCHI', 'First Capital Insurance', '+265 1 822 822', 'health@firstcapital.mw', 'Blantyre, Malawi'),
        ('Axa Insurance Malawi', 'AXA', 'Axa Insurance', '+265 1 824 200', 'info@axa.mw', 'Blantyre, Malawi'),
        ('Old Mutual Insurance', 'OMI', 'Old Mutual Malawi', '+265 1 820 522', 'insurance@oldmutual.mw', 'Blantyre, Malawi'),
        ('Jubilee Insurance Malawi', 'JUB', 'Jubilee Insurance', '+265 1 828 500', 'info@jubilee.mw', 'Blantyre, Malawi'),
        ('NICO Insurance', 'NICO', 'NICO Insurance', '+265 1 824 444', 'insurance@nico.mw', 'Blantyre, Malawi'),
        ('RESMAID', 'RESMAID', 'RESMAID Insurance', '', '', ''),
        ('MedHealth', 'MEDHEALTH', 'MedHealth Insurance', '', '', ''),
        ('COMAID', 'COMAID', 'COMAID Insurance', '', '', ''),
        ('ESCOM', 'ESCOM', 'ESCOM Staff Scheme', '', '', ''),
        ('MRA', 'MRA', 'Malawi Revenue Authority Staff Scheme', '', '', ''),
        ('NABMAS', 'NABMAS', 'NABMAS Insurance', '', '', ''),
        ('MASM Exe', 'MASM_EXE', 'MASM Executive', '', '', ''),
        ('MASM VIP', 'MASM_VIP', 'MASM Very Important Person', '', '', ''),
        ('MASM VVIP', 'MASM_VVIP', 'MASM Very Very Important Person', '', '', ''),
        ('Companies', 'COMPANIES', 'Corporate Companies', '', '', ''),
        ('PVT', 'PVT', 'Private Patients', '', '', ''),
    ]
    for name, code, contact, phone, email, address in providers:
        conn.execute(
            'INSERT INTO insurance_providers (name, code, contact_person, phone, email, address) VALUES (?,?,?,?,?,?)',
            (name, code, contact, phone, email, address))
    conn.commit()


def _seed_insurance_providers_missing(conn):
    additional = [
        ('RESMAID', 'RESMAID', 'RESMAID Insurance', '', '', ''),
        ('MedHealth', 'MEDHEALTH', 'MedHealth Insurance', '', '', ''),
        ('COMAID', 'COMAID', 'COMAID Insurance', '', '', ''),
        ('ESCOM', 'ESCOM', 'ESCOM Staff Scheme', '', '', ''),
        ('MRA', 'MRA', 'Malawi Revenue Authority Staff Scheme', '', '', ''),
        ('NABMAS', 'NABMAS', 'NABMAS Insurance', '', '', ''),
        ('MASM Exe', 'MASM_EXE', 'MASM Executive', '', '', ''),
        ('MASM VIP', 'MASM_VIP', 'MASM Very Important Person', '', '', ''),
        ('MASM VVIP', 'MASM_VVIP', 'MASM Very Very Important Person', '', '', ''),
        ('Companies', 'COMPANIES', 'Corporate Companies', '', '', ''),
        ('PVT', 'PVT', 'Private Patients', '', '', ''),
    ]
    existing_codes = {r['code'] for r in conn.execute('SELECT code FROM insurance_providers').fetchall()}
    for name, code, contact, phone, email, address in additional:
        if code not in existing_codes:
            conn.execute(
                'INSERT INTO insurance_providers (name, code, contact_person, phone, email, address) VALUES (?,?,?,?,?,?)',
                (name, code, contact, phone, email, address))
    conn.commit()


def _migrate_lab_barcode(conn):
    try:
        conn.execute("ALTER TABLE lab_tests ADD COLUMN barcode TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE lab_tests ADD COLUMN sample_collected_date DATE")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE lab_tests ADD COLUMN sample_collected_by INTEGER REFERENCES users(id)")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def _seed_radiology_catalog(conn):
    existing = conn.execute('SELECT COUNT(*) as c FROM lab_test_catalog WHERE category = "radiology"').fetchone()['c']
    if existing > 0:
        return
    radiology_tests = [
        ('Chest X-Ray (PA)', 'radiology', 'radiology', 'PA chest radiograph', None),
        ('Chest X-Ray (Lateral)', 'radiology', 'radiology', 'Lateral chest radiograph', None),
        ('Abdominal X-Ray', 'radiology', 'radiology', 'Plain abdominal radiograph', None),
        ('Pelvic X-Ray', 'radiology', 'radiology', 'Pelvic radiograph', None),
        ('Spine X-Ray (Cervical)', 'radiology', 'radiology', 'Cervical spine radiograph', None),
        ('Spine X-Ray (Thoracic)', 'radiology', 'radiology', 'Thoracic spine radiograph', None),
        ('Spine X-Ray (Lumbar)', 'radiology', 'radiology', 'Lumbar spine radiograph', None),
        ('Limbs X-Ray', 'radiology', 'radiology', 'Extremity radiograph', None),
        ('Skull X-Ray', 'radiology', 'radiology', 'Skull radiograph', None),
        ('Abdominal Ultrasound', 'radiology', 'ultrasound', 'Abdominal/pelvic ultrasound', None),
        ('Obstetric Ultrasound', 'radiology', 'ultrasound', 'Obstetric ultrasound scan', None),
        ('Thyroid Ultrasound', 'radiology', 'ultrasound', 'Thyroid gland ultrasound', None),
        ('Breast Ultrasound', 'radiology', 'ultrasound', 'Breast ultrasound', None),
        ('Echocardiogram', 'radiology', 'cardiac', 'Transthoracic echocardiogram', None),
        ('ECG (12-Lead)', 'radiology', 'cardiac', '12-lead electrocardiogram', None),
    ]
    for name, cat, subcat, desc, params in radiology_tests:
        conn.execute(
            'INSERT INTO lab_test_catalog (test_name, category, sample_type, description, default_params, is_active) VALUES (?,?,?,?,?,1)',
            (name, cat, subcat, desc, params))
    conn.commit()


def _seed_auth_rules(conn):
    medhealth = conn.execute(
        'SELECT id FROM insurance_providers WHERE code = "MEDHEALTH"').fetchone()
    if not medhealth:
        return
    existing = conn.execute(
        'SELECT COUNT(*) as c FROM insurance_authorization_rules WHERE provider_id = ?', (medhealth['id'],)).fetchone()['c']
    if existing > 0:
        return
    rules = [
        (medhealth['id'], 'pharmacy', 'Drip', 1),
        (medhealth['id'], 'pharmacy', 'IV Fluid', 1),
        (medhealth['id'], 'pharmacy', 'Normal Saline', 1),
        (medhealth['id'], 'pharmacy', 'Hartmanns', 1),
        (medhealth['id'], 'pharmacy', 'Ringer Lactate', 1),
        (medhealth['id'], 'pharmacy', 'Dextrose', 1),
    ]
    for provider_id, item_type, item_name, requires_auth in rules:
        conn.execute(
            'INSERT INTO insurance_authorization_rules (provider_id, item_type, item_name, requires_auth) VALUES (?, ?, ?, ?)',
            (provider_id, item_type, item_name, requires_auth))
    conn.commit()


def _seed_short_stay(conn):
    bed_count = conn.execute('SELECT COUNT(*) as c FROM short_stay_beds').fetchone()['c']
    if bed_count == 0:
        for i in range(1, 5):
            conn.execute('INSERT INTO short_stay_beds (bed_number, label) VALUES (?, ?)',
                         (i, f'Bed {i}'))
    station_count = conn.execute('SELECT COUNT(*) as c FROM short_stay_drip_stations').fetchone()['c']
    if station_count == 0:
        for i in range(1, 4):
            conn.execute('INSERT INTO short_stay_drip_stations (station_number, label) VALUES (?, ?)',
                         (i, f'Drip Station {i}'))
    conn.commit()


def _migrate_procedures_ecg(conn):
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='procedures'"
    ).fetchone()
    if schema and 'ecg' not in schema['sql']:
        conn.executescript('''
            DROP TABLE IF EXISTS procedures_new;
            CREATE TABLE procedures_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                performed_by INTEGER,
                procedure_type TEXT CHECK(procedure_type IN ('short_stay','nebulisation','burn_wound','ecg','other')),
                notes TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(patient_id) REFERENCES patients(id),
                FOREIGN KEY(performed_by) REFERENCES users(id)
            );
            INSERT INTO procedures_new SELECT * FROM procedures;
            DROP TABLE procedures;
            ALTER TABLE procedures_new RENAME TO procedures;
        ''')
        conn.commit()


def _migrate_radiology_refer(conn):
    try:
        conn.execute("ALTER TABLE radiology_orders ADD COLUMN referred_to TEXT")
    except sqlite3.OperationalError:
        pass
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='radiology_orders'"
    ).fetchone()
    if schema and 'referred' not in schema['sql']:
        conn.executescript('''
            DROP TABLE IF EXISTS radiology_orders_new;
            CREATE TABLE radiology_orders_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT UNIQUE,
                patient_id INTEGER NOT NULL,
                doctor_id INTEGER,
                modality TEXT NOT NULL CHECK(modality IN ('xray','ultrasound','ct','mri','ecg','echo','mammogram','fluoroscopy','other')),
                body_part TEXT,
                clinical_history TEXT,
                status TEXT DEFAULT 'ordered' CHECK(status IN ('ordered','in_progress','completed','cancelled','referred')),
                ordered_date DATE,
                completed_date DATE,
                referred_to TEXT,
                priority TEXT DEFAULT 'routine' CHECK(priority IN ('routine','urgent','stat')),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(patient_id) REFERENCES patients(id),
                FOREIGN KEY(doctor_id) REFERENCES users(id)
            );
            INSERT INTO radiology_orders_new SELECT * FROM radiology_orders;
            DROP TABLE radiology_orders;
            ALTER TABLE radiology_orders_new RENAME TO radiology_orders;
        ''')
        conn.commit()


def _migrate_lab_roles(conn):
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if schema and 'lab_supervisor' not in schema['sql']:
        conn.execute('PRAGMA foreign_keys = OFF')
        conn.executescript('''
            DROP TABLE IF EXISTS users_new;
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','doctor','locum_doctor','nurse','locum_nurse','lab_staff','lab_supervisor','lab_tech','lab_care','front_desk','file_manager')),
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO users_new SELECT * FROM users;
            DROP TABLE users;
            ALTER TABLE users_new RENAME TO users;
        ''')
        conn.execute('PRAGMA foreign_keys = ON')
        conn.commit()


def _seed_inventory(conn):
    existing = conn.execute("SELECT COUNT(*) as c FROM pharmacy_inventory WHERE drug_name LIKE '%Tube%'").fetchone()['c']
    if existing > 0:
        return
    tubes = [
        ('Red Top Tube (Serum)', 'Vacutainer Red', 'Lab Supplies', 500, 12.00, '2028-06-30', 'BD Medical', 100),
        ('Purple Top Tube (EDTA)', 'Vacutainer EDTA', 'Lab Supplies', 500, 14.00, '2028-06-30', 'BD Medical', 100),
    ]
    for item in tubes:
        conn.execute(
            'INSERT INTO pharmacy_inventory (drug_name, generic_name, category, stock_quantity, unit_price, expiry_date, supplier, reorder_level) VALUES (?,?,?,?,?,?,?,?)',
            item)
    conn.commit()


def _migrate_catalog_classification(conn):
    try:
        conn.execute("ALTER TABLE lab_test_catalog ADD COLUMN classification TEXT DEFAULT 'standard'")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def _migrate_certificates_yellow_book(conn):
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='medical_certificates'"
    ).fetchone()
    if schema and 'yellow_book' not in schema['sql']:
        conn.executescript('''
            DROP TABLE IF EXISTS medical_certificates_new;
            CREATE TABLE medical_certificates_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                doctor_id INTEGER NOT NULL,
                certificate_type TEXT CHECK(certificate_type IN ('sick_note','tep','insurance','police','yellow_book','foreign_stamp')),
                issue_date DATE NOT NULL,
                valid_until DATE,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(patient_id) REFERENCES patients(id),
                FOREIGN KEY(doctor_id) REFERENCES users(id)
            );
            INSERT INTO medical_certificates_new SELECT * FROM medical_certificates;
            DROP TABLE medical_certificates;
            ALTER TABLE medical_certificates_new RENAME TO medical_certificates;
        ''')
        conn.commit()


def _seed_lab_catalog(conn):
    existing = conn.execute("SELECT COUNT(*) as c FROM lab_test_catalog WHERE category != 'radiology'").fetchone()['c']
    if existing > 10:
        return
    tests = [
        # Haematology
        ('CBC/FBC', 'haematology', 'blood', 'standard', 'Complete Blood Count / Full Blood Count'),
        ('MPS', 'haematology', 'blood', 'standard', 'Malaria Parasite Stain'),
        ('Malaria Antigens', 'haematology', 'blood', 'rapid', 'Malaria Rapid Diagnostic Test'),
        ('ESR', 'haematology', 'blood', 'standard', 'Erythrocyte Sedimentation Rate'),
        # Parasitology
        ('Stool Analysis', 'parasitology', 'stool', 'standard', 'Macroscopic and microscopic stool examination'),
        ('Occult Blood', 'parasitology', 'stool', 'rapid', 'Faecal Occult Blood Test'),
        ('Urine Analysis', 'parasitology', 'urine', 'standard', 'Urinalysis - physical, chemical and microscopic'),
        ('Pregnancy Test', 'parasitology', 'urine', 'rapid', 'Urine Pregnancy Test (hCG)'),
        # Microbiology
        ('Gram Stain', 'microbiology', 'specimen', 'standard', 'Gram staining for bacterial identification'),
        ('ZN Stain', 'microbiology', 'specimen', 'standard', 'Ziehl-Neelsen staining for AFB'),
        ('Viral Load', 'microbiology', 'blood', 'standard', 'HIV Viral Load'),
        # Chemistry
        ('FBS', 'chemistry', 'blood', 'standard', 'Fasting Blood Sugar'),
        ('RBS', 'chemistry', 'blood', 'rapid', 'Random Blood Sugar'),
        ('Glycosylated Haemoglobin (HbA1c)', 'chemistry', 'blood', 'standard', 'Haemoglobin A1c'),
        ('LFT', 'chemistry', 'blood', 'standard', 'Liver Function Test'),
        ('SGOT (AST)', 'chemistry', 'blood', 'standard', 'Aspartate Aminotransferase'),
        ('SGPT (ALT)', 'chemistry', 'blood', 'standard', 'Alanine Aminotransferase'),
        ('GGT', 'chemistry', 'blood', 'standard', 'Gamma Glutamyl Transferase'),
        ('LDH', 'chemistry', 'blood', 'standard', 'Lactate Dehydrogenase'),
        ('ALP', 'chemistry', 'blood', 'standard', 'Alkaline Phosphatase'),
        ('Bilirubin - Total and Direct', 'chemistry', 'blood', 'standard', 'Total and Direct Bilirubin'),
        ('Protein - Total and Albumin', 'chemistry', 'blood', 'standard', 'Total Protein and Albumin'),
        # Lipogram
        ('Total Cholesterol', 'lipogram', 'blood', 'standard', 'Total Cholesterol'),
        ('HDL Cholesterol', 'lipogram', 'blood', 'standard', 'High Density Lipoprotein Cholesterol'),
        ('LDL Cholesterol', 'lipogram', 'blood', 'standard', 'Low Density Lipoprotein Cholesterol'),
        ('Triglycerides', 'lipogram', 'blood', 'standard', 'Triglycerides'),
        # U&E
        ('BUN', 'u_and_e', 'blood', 'standard', 'Blood Urea Nitrogen'),
        ('Creatinine', 'u_and_e', 'blood', 'standard', 'Serum Creatinine'),
        ('Sodium', 'u_and_e', 'blood', 'standard', 'Serum Sodium'),
        ('Potassium', 'u_and_e', 'blood', 'standard', 'Serum Potassium'),
        ('Ammonia', 'u_and_e', 'blood', 'standard', 'Blood Ammonia'),
        ('Calcium', 'u_and_e', 'blood', 'standard', 'Serum Calcium'),
        ('Phosphorus', 'u_and_e', 'blood', 'standard', 'Serum Phosphorus'),
        ('Chloride', 'u_and_e', 'blood', 'standard', 'Serum Chloride'),
        # Cardiac Enzymes
        ('CK', 'cardiac', 'blood', 'standard', 'Creatine Kinase'),
        ('CK BB', 'cardiac', 'blood', 'standard', 'CK Brain Band'),
        ('CK MB', 'cardiac', 'blood', 'standard', 'CK Myocardial Band'),
        ('CK MM', 'cardiac', 'blood', 'standard', 'CK Muscle Band'),
        # Other Chemistries
        ('Amylase', 'chemistry', 'blood', 'standard', 'Serum Amylase'),
        ('Lactate', 'chemistry', 'blood', 'standard', 'Blood Lactate'),
        ('Uric Acid', 'chemistry', 'blood', 'standard', 'Serum Uric Acid'),
        # Serology
        ('CRP', 'serology', 'blood', 'rapid', 'C-Reactive Protein'),
        ('HIV', 'serology', 'blood', 'rapid', 'HIV Test'),
        ('RF', 'serology', 'blood', 'standard', 'Rheumatoid Factor'),
        ('VDRL', 'serology', 'blood', 'standard', 'Venereal Disease Research Laboratory'),
        ('HCV', 'serology', 'blood', 'standard', 'Hepatitis C Virus Antibody'),
        ('ASOT', 'serology', 'blood', 'standard', 'Anti-Streptolysin O Titre'),
        ('Brucella IgG and IgM', 'serology', 'blood', 'standard', 'Brucella IgG and IgM Antibodies'),
        ('Hepatitis B Surface Antigen', 'serology', 'blood', 'rapid', 'HBsAg'),
        # Tumour Markers
        ('CEA', 'tumour_markers', 'blood', 'standard', 'Carcinoembryonic Antigen'),
        ('PSA', 'tumour_markers', 'blood', 'standard', 'Prostate Specific Antigen'),
        ('AFP', 'tumour_markers', 'blood', 'standard', 'Alpha Fetoprotein'),
        # Endocrinology
        ('Thyroid Hormone T3', 'endocrinology', 'blood', 'standard', 'Triiodothyronine'),
        ('Thyroid Hormone T4', 'endocrinology', 'blood', 'standard', 'Thyroxine'),
        ('TSH', 'endocrinology', 'blood', 'standard', 'Thyroid Stimulating Hormone'),
        # Fertility and Steroids
        ('Sperm Count', 'fertility', 'semen', 'standard', 'Semen Analysis - Sperm Count'),
        ('Prolactin', 'fertility', 'blood', 'standard', 'Serum Prolactin'),
        ('HCG', 'fertility', 'blood', 'standard', 'Human Chorionic Gonadotropin'),
        ('LH', 'fertility', 'blood', 'standard', 'Luteinizing Hormone'),
        ('FSH', 'fertility', 'blood', 'standard', 'Follicle Stimulating Hormone'),
        ('Testosterone', 'fertility', 'blood', 'standard', 'Serum Testosterone'),
        ('Estradiol', 'fertility', 'blood', 'standard', 'Serum Estradiol'),
        ('Cortisol', 'fertility', 'blood', 'standard', 'Serum Cortisol'),
        ('Progesterone', 'fertility', 'blood', 'standard', 'Serum Progesterone'),
    ]
    for name, cat, sample, classification, desc in tests:
        conn.execute(
            'INSERT INTO lab_test_catalog (test_name, category, sample_type, classification, description, is_active) VALUES (?,?,?,?,?,1)',
            (name, cat, sample, classification, desc))
    conn.commit()


def _migrate_dispensing_unit_price(conn):
    try:
        conn.execute("ALTER TABLE pharmacy_dispensing ADD COLUMN unit_price REAL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def _seed_admin_user(conn):
    count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if count == 0:
        conn.execute(
            'INSERT INTO users (username, password_hash, role, first_name, last_name, email, phone) VALUES (?,?,?,?,?,?,?)',
            ('admin', generate_password_hash('admin123'), 'admin', 'System', 'Admin', 'admin@kayange.com', '0700000000')
        )
        conn.commit()
        print('Default admin user created: admin / admin123')


def _migrate_patients_nullable(conn):
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(patients)").fetchall()]
        if 'dob' in cols:
            dob_info = conn.execute("PRAGMA table_info(patients)").fetchone()
            for r in conn.execute("PRAGMA table_info(patients)").fetchall():
                if r[1] == 'dob' and r[3] == 1:
                    _recreate_patients_table(conn)
                    return
    except sqlite3.OperationalError:
        pass


def _recreate_patients_table(conn):
    conn.execute("ALTER TABLE patients RENAME TO patients_old")
    conn.execute('''CREATE TABLE patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT UNIQUE NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        dob DATE,
        gender TEXT CHECK(gender IN ('Male','Female','Other')),
        phone TEXT,
        email TEXT,
        address TEXT,
        emergency_contact_name TEXT,
        emergency_contact_phone TEXT,
        blood_group TEXT,
        scheme_provider TEXT,
        scheme_type TEXT,
        scheme_id INTEGER,
        scheme_number TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''INSERT INTO patients
        SELECT id, patient_id, first_name, last_name, dob, gender, phone, email, address,
               emergency_contact_name, emergency_contact_phone, blood_group, scheme_provider,
               scheme_type, scheme_id, scheme_number, created_at, updated_at
        FROM patients_old''')
    conn.execute("DROP TABLE patients_old")
    conn.commit()
    print('Migrated patients table: dob and phone now nullable')


def _migrate_patients_yellow_book_fields(conn):
    try:
        conn.execute("ALTER TABLE patients ADD COLUMN passport_number TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE patients ADD COLUMN nationality TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def _seed_vaccines(conn):
    existing = conn.execute("SELECT COUNT(*) as c FROM vaccines").fetchone()['c']
    if existing > 0:
        return
    vaccines = [
        ('Yellow Fever', 'Sanofi Pasteur', 'viral'),
        ('Cholera', 'Valneva', 'bacterial'),
        ('Typhoid', 'Sanofi Pasteur', 'bacterial'),
        ('Hepatitis A', 'GSK', 'viral'),
        ('Hepatitis B', 'Merck', 'viral'),
        ('Meningococcal (ACWY)', 'Sanofi Pasteur', 'bacterial'),
        ('Polio IPV', 'Sanofi Pasteur', 'viral'),
        ('Rabies', 'Sanofi Pasteur', 'viral'),
        ('Tetanus/Diphtheria', 'GSK', 'toxoid'),
        ('COVID-19', 'Various', 'viral'),
        ('MMR', 'Merck', 'viral'),
        ('Influenza', 'Sanofi Pasteur', 'viral'),
    ]
    for name, manufacturer, vtype in vaccines:
        conn.execute(
            'INSERT INTO vaccines (vaccine_name, manufacturer, vaccine_type) VALUES (?, ?, ?)',
            (name, manufacturer, vtype))
    conn.commit()


def _migrate_patient_documents(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS patient_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            file_size INTEGER,
            mime_type TEXT,
            notes TEXT,
            uploaded_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
        )''')
    conn.commit()
