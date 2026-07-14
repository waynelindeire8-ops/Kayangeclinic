import os
os.environ['VERCEL'] = '1'
from app.database import get_db

for i in range(5):
    db = get_db()
    cursor = db.execute('SELECT COUNT(*) as c FROM patients')
    row = cursor.fetchone()
    print(f'Attempt {i+1}: {row["c"]} patients')
    db.close()