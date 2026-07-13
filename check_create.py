import sqlite3
conn = sqlite3.connect('kayange.db')
sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='patient_allergies'").fetchone()
print(repr(sql[0]))
conn.close()
