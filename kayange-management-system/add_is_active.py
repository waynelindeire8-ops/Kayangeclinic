import sqlite3
conn = sqlite3.connect('kayange.db')
conn.execute('ALTER TABLE patients ADD COLUMN is_active INTEGER DEFAULT 1')
conn.commit()
print('Column added')
schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='patients'").fetchone()
print(schema[0])
conn.close()