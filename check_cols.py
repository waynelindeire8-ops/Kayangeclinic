import sqlite3
conn = sqlite3.connect('kayange.db')
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(patients)")
columns = cursor.fetchall()
for col in columns:
    print(col[1])
conn.close()