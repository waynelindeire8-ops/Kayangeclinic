import sqlite3

conn = sqlite3.connect('kayange.db')
conn.execute("PRAGMA foreign_keys = OFF")

fixes = [
    # (table_name, new_create_sql, column_mapping_func)
    ('billing_items', '''
        CREATE TABLE billing_items_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            billing_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_type TEXT CHECK(item_type IN ('consultation','lab','procedure','pharmacy','certificate','package')),
            quantity INTEGER DEFAULT 1,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            FOREIGN KEY(billing_id) REFERENCES billing(id) ON DELETE CASCADE
        );
    ''', lambda r: r),
    
    ('lab_invoice_items', '''
        CREATE TABLE lab_invoice_items_new (
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
    ''', lambda r: r),
    
    ('medical_examinations', '''
        CREATE TABLE medical_examinations_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id INTEGER NOT NULL,
            system_name TEXT NOT NULL,
            findings TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(consultation_id) REFERENCES consultations(id) ON DELETE CASCADE
        );
    ''', lambda r: r),
    
    ('diagnoses', '''
        CREATE TABLE diagnoses_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id INTEGER NOT NULL,
            diagnosis_name TEXT NOT NULL,
            diagnosis_type TEXT NOT NULL CHECK(diagnosis_type IN ('primary','secondary','complication')),
            icd_code TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(consultation_id) REFERENCES consultations(id) ON DELETE CASCADE
        );
    ''', lambda r: r),
    
    ('lab_test_results', '''
        CREATE TABLE lab_test_results_new (
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
    ''', lambda r: r),
    
    ('prescription_refills', '''
        CREATE TABLE prescription_refills_new (
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
    ''', lambda r: r),
    
    ('claim_items', '''
        CREATE TABLE claim_items_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            procedure_code TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            FOREIGN KEY(claim_id) REFERENCES insurance_claims(id) ON DELETE CASCADE
        );
    ''', lambda r: r),
    
    ('claim_status_history', '''
        CREATE TABLE claim_status_history_new (
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
    ''', lambda r: r),
    
    ('radiology_results', '''
        CREATE TABLE radiology_results_new (
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
    ''', lambda r: r),
    
    ('telemedicine_messages', '''
        CREATE TABLE telemedicine_messages_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES telemedicine_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(sender_id) REFERENCES users(id)
        );
    ''', lambda r: r),
    
    ('telemedicine_payments', '''
        CREATE TABLE telemedicine_payments_new (
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
    ''', lambda r: r),
    
    ('telemedicine_recordings', '''
        CREATE TABLE telemedicine_recordings_new (
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
    ''', lambda r: r),
    
    ('billing', '''
        CREATE TABLE billing_new (
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
    ''', lambda r: r),
    
    ('vital_signs', '''
        CREATE TABLE vital_signs_new (
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
    ''', lambda r: r),
    
    ('insurance_claims', '''
        CREATE TABLE insurance_claims_new (
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
    ''', lambda r: r),
    
    ('vaccination_records', '''
        CREATE TABLE vaccination_records_new (
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
    ''', lambda r: r),
]

for table_name, create_sql, map_func in fixes:
    print(f"Fixing {table_name}...")
    try:
        rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
        columns = [desc[0] for desc in conn.execute(f"SELECT * FROM {table_name} LIMIT 1").description] if rows else []
        print(f"  Rows: {len(rows)}, Columns: {columns}")
        
        conn.execute(f"DROP TABLE IF EXISTS {table_name}_new")
        conn.execute(create_sql)
        
        if rows:
            placeholders = ', '.join(['?'] * len(columns))
            cols_str = ', '.join(columns)
            for row in rows:
                conn.execute(f"INSERT INTO {table_name}_new ({cols_str}) VALUES ({placeholders})", row)
        
        conn.execute(f"DROP TABLE {table_name}")
        conn.execute(f"ALTER TABLE {table_name}_new RENAME TO {table_name}")
        print(f"  Fixed!")
    except Exception as e:
        print(f"  ERROR: {e}")
        conn.rollback()

conn.execute("PRAGMA foreign_keys = ON")
conn.commit()
print("\nAll tables fixed!")

# Verify no more temp references
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for (table,) in tables:
    schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if schema and ('fix_temp' in schema[0] or 'FIX_TEMP' in schema[0]):
        print(f"STILL HAS TEMP REF: {table}")

conn.close()