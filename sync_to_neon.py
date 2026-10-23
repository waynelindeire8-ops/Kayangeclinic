"""One-time push of the local kayange.db into Neon, with live progress.

Run from the project folder, in the SAME terminal where NEON_DATABASE_URL is set:
    python sync_to_neon.py
Safe to stop (Ctrl+C) and re-run: rows that already synced are just updated.
"""
import sqlite3
import sys
import time

from config import Config

if not Config.NEON_DATABASE_URL:
    sys.exit('NEON_DATABASE_URL is not set in this terminal.')

from app import backup  # noqa: E402

# 1) How slow is the link to Neon?
t = time.time()
conn = backup._get_pg_conn()
print(f'connect: {time.time() - t:.1f}s', flush=True)
cur = conn.cursor()
times = []
for _ in range(5):
    t = time.time()
    cur.execute('SELECT 1')
    cur.fetchone()
    times.append(time.time() - t)
print(f'round trip to Neon: avg {sum(times) / len(times) * 1000:.0f} ms', flush=True)
conn.close()

# 2) Make sure tables exist
print('init tables:', backup.init_neon_tables(), flush=True)

# 3) Sync table by table, with timings
db = sqlite3.connect(Config.DATABASE)
total_start = time.time()
current = None
try:
    for table in backup.SYNC_TABLES:
        try:
            n = db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        except Exception:
            continue
        if not n:
            continue
        current = table
        t = time.time()
        print(f'{table}: {n} rows ...', end=' ', flush=True)
        result = backup.sync_table(table)
        status = 'FAILED' if result < 0 else f'{result} synced'
        print(f'{status} ({time.time() - t:.1f}s)', flush=True)
    print(f'All done in {time.time() - total_start:.0f}s', flush=True)
except KeyboardInterrupt:
    print(f'\nStopped by you while syncing: {current}', flush=True)
