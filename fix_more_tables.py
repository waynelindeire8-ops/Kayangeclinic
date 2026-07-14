import sqlite3

conn = sqlite3.connect('kayange.db')
conn.execute("PRAGMA foreign_keys = OFF")

# Fix telemedicine_sessions
print("Fixing telemedicine_sessions...")
rows = conn.execute("SELECT * FROM telemedicine_sessions").fetchall()
conn.executescript('''
    DROP TABLE IF EXISTS telemedicine_sessions_new;
    CREATE TABLE telemedicine_sessions_new (
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
''')
for row in rows:
    conn.execute('''
        INSERT INTO telemedicine_sessions_new (id, session_id, patient_id, doctor_id, appointment_id, consultation_id, status, session_type, reason, diagnosis, notes, started_at, ended_at, duration_minutes, token_patient, token_doctor, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', row)
conn.execute('DROP TABLE telemedicine_sessions')
conn.execute('ALTER TABLE telemedicine_sessions_new RENAME TO telemedicine_sessions')
print(f"  Fixed {len(rows)} rows")

# Fix consultations
print("Fixing consultations...")
rows = conn.execute("SELECT * FROM consultations").fetchall()
conn.executescript('''
    DROP TABLE IF EXISTS consultations_new;
    CREATE TABLE consultations_new (
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
''')
for row in rows:
    conn.execute('''
        INSERT INTO consultations_new (id, patient_id, doctor_id, appointment_id, consultation_type, diagnosis, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', row)
conn.execute('DROP TABLE consultations')
conn.execute('ALTER TABLE consultations_new RENAME TO consultations')
print(f"  Fixed {len(rows)} rows")

conn.execute("PRAGMA foreign_keys = ON")
conn.commit()
print("All tables fixed!")

# Verify
for table in ['telemedicine_sessions', 'consultations']:
    schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    print(f"\n=== {table} ===")
    print(schema[0])

conn.close()