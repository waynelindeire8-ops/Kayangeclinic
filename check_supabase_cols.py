import psycopg2
from config import Config

conn = psycopg2.connect(Config.SUPABASE_DB_URL, connect_timeout=10)
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'patients' AND table_schema = 'public'")
cols = [r[0] for r in cur.fetchall()]
print('Supabase patients columns:', cols)
print('is_active in Supabase:', 'is_active' in cols)
cur.close()
conn.close()