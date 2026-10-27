import os
os.environ['VERCEL'] = '1'
from app.database import get_db

db = get_db()
print('Connection type:', type(db).__name__)

# Test multiple queries
cursor = db.execute('SELECT COUNT(*) as c FROM patients')
row = cursor.fetchone()
print('Patients count:', row)

cursor = db.execute('SELECT * FROM patients LIMIT 3')
rows = cursor.fetchall()
print('Sample patients:', len(rows))
for r in rows:
    print('  ', dict(r))

db.close()