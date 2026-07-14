import sqlite3
conn = sqlite3.connect('kayange.db')
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT * FROM system_config WHERE key='last_sync_time'").fetchone()
if row:
    print('last_sync_time:', row['value'])
else:
    print('last_sync_time not set')

row = conn.execute("SELECT * FROM system_config WHERE key='auto_sync_interval'").fetchone()
if row:
    print('auto_sync_interval:', row['value'])
else:
    print('auto_sync_interval not set')
conn.close()