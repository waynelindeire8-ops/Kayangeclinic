import sqlite3
conn = sqlite3.connect('kayange.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for (table,) in tables:
    schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if schema and ('fix_temp' in schema[0] or 'FIX_TEMP' in schema[0]):
        print('STILL HAS TEMP REF:', table)
conn.close()
print('Check complete')