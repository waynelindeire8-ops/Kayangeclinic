import app.backup as backup
import psycopg2
from config import Config

# Check if tables exist in Supabase
conn = psycopg2.connect(Config.SUPABASE_DB_URL)
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
tables = [row[0] for row in cur.fetchall()]
print('Tables in Supabase:', tables)
cur.close()
conn.close()

# Try syncing just users table
print('Syncing users...')
result = backup.sync_table('users')
print(f'Result: {result}')