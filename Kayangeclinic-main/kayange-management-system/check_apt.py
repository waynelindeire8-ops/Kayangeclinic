import sqlite3
conn = sqlite3.connect('kayange.db')
schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='appointments'").fetchone()
print(schema[0])
conn.close()