import os
os.environ['VERCEL'] = '1'
from app.database import get_db

db = get_db()
print('Connection type:', type(db).__name__)

# Test with raw cursor
cursor = db.conn.cursor()
cursor.execute('SELECT COUNT(*) FROM patients')
row = cursor.fetchone()
print('Raw cursor count:', row)

cursor.execute('SELECT * FROM patients LIMIT 3')
rows = cursor.fetchall()
print('Raw sample:', len(rows))
for r in rows:
    print('  ', r)

db.close()