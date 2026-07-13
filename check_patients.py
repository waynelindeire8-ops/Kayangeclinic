import sqlite3
conn = sqlite3.connect('kayange.db')
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for t in tables:
    if 'patient' in t.lower():
        cnt = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f'  {t}: {cnt} rows')
conn.close()
