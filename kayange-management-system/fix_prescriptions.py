import sqlite3

conn = sqlite3.connect('kayange.db')
conn.execute("PRAGMA foreign_keys = OFF")

# Get current data from prescriptions
rows = conn.execute("SELECT * FROM prescriptions").fetchall()
columns = [desc[0] for desc in conn.execute("SELECT * FROM prescriptions LIMIT 1").description]
print(f"Current prescriptions columns: {columns}")
print(f"Number of rows: {len(rows)}")

# Create new table without the temp table references
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
''')

# Copy data (adjusting for new schema - consultation_id may be NULL now)
for row in rows:
    # Map old row to new columns
    # Old schema has: id, consultation_id, patient_id, inventory_id, drug_name, dosage, frequency, duration, route, instructions, quantity, status, prescribed_by, prescribed_date, created_at, order_id, refill_count, session_id
    # New schema has: id, consultation_id, order_id, patient_id, inventory_id, drug_name, dosage, frequency, duration, route, instructions, quantity, refill_count, status, prescribed_by, prescribed_date, created_at
    vals = list(row)
    # Insert with new column order
    conn.execute('''
        INSERT INTO prescriptions_new (id, consultation_id, order_id, patient_id, inventory_id, drug_name, dosage, frequency, duration, route, instructions, quantity, refill_count, status, prescribed_by, prescribed_date, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (vals[0], vals[1], vals[15], vals[2], vals[3], vals[4], vals[5], vals[6], vals[7], vals[8], vals[9], vals[10], vals[16], vals[11], vals[12], vals[13], vals[14]))

conn.execute('DROP TABLE prescriptions')
conn.execute('ALTER TABLE prescriptions_new RENAME TO prescriptions')
conn.execute("PRAGMA foreign_keys = ON")
conn.commit()
print("Prescriptions table fixed!")

# Verify
schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='prescriptions'").fetchone()
print(schema[0])
conn.close()