import sqlite3
conn = sqlite3.connect('kayange.db')
for table in ['telemedicine_sessions', 'consultations', 'prescription_orders']:
    schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if schema:
        print('=== ' + table + ' ===')
        print(schema[0])
        print()
conn.close()