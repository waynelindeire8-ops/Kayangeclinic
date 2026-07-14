import os
os.environ['VERCEL'] = '1'
from app.database import get_db
from config import Config

# Check the connection string
print('DB URL:', Config.SUPABASE_DB_URL[:60] + '...')

db = get_db()
cursor = db.conn.cursor()
cursor.execute('SELECT current_database(), current_schema()')
print('Database/Schema:', cursor.fetchone())

cursor.execute('SELECT COUNT(*) FROM patients')
print('Count:', cursor.fetchone())

cursor.execute('SELECT * FROM patients LIMIT 3')
print('Sample:', cursor.fetchall())

db.close()