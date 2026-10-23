import psycopg2
from config import Config

conn = psycopg2.connect(Config.SUPABASE_DB_URL)
cur = conn.cursor()

# Get all table names
cur.execute("""
    SELECT tablename FROM pg_tables 
    WHERE schemaname = 'public'
""")
tables = [row[0] for row in cur.fetchall()]

# Drop all tables
for table in tables:
    try:
        cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        print(f'Dropped: {table}')
    except Exception as e:
        print(f'Error dropping {table}: {e}')

conn.commit()
cur.close()
conn.close()
print('All tables cleaned up')