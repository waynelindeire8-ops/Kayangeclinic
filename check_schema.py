import sqlite3
conn = sqlite3.connect('kayange.db')
cursor = conn.cursor()
schema = cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='prescriptions'").fetchone()
if schema:
    print(schema[0])
conn.close()