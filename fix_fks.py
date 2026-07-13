import sqlite3
conn = sqlite3.connect('kayange.db')
conn.row_factory = sqlite3.Row

# Get all tables with FKs pointing to patients_old
tables_to_fix = []
for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
    table = row[0]
    for fk in conn.execute(f'PRAGMA foreign_key_list({table})').fetchall():
        if fk['table'] == 'patients_old' and fk['to'] == 'id':
            tables_to_fix.append((table, fk['from']))

print(f"Found {len(tables_to_fix)} tables with broken FK refs\n")

for table, col in tables_to_fix:
    create_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()[0]
    
    # Replace with quoted variant
    fixed_sql = create_sql.replace('"patients_old"', '"patients"')
    
    if fixed_sql == create_sql:
        fixed_sql = create_sql.replace("'patients_old'", "'patients'")
    if fixed_sql == create_sql:
        fixed_sql = create_sql.replace('patients_old', 'patients')
    
    temp_table = f'{table}_fix_temp'
    conn.execute(f'ALTER TABLE {table} RENAME TO {temp_table}')
    conn.execute(fixed_sql)
    
    cols = conn.execute(f'PRAGMA table_info({table})').fetchall()
    col_names = ', '.join([c[1] for c in cols])
    conn.execute(f'INSERT INTO {table} SELECT {col_names} FROM {temp_table}')
    conn.execute(f'DROP TABLE {temp_table}')
    conn.commit()
    print(f"Fixed {table}")

print("\n=== Verification ===")
for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
    table = row[0]
    for fk in conn.execute(f'PRAGMA foreign_key_list({table})').fetchall():
        if 'patients' in fk['table']:
            print(f"  {table}.{fk['from']} -> {fk['table']}.{fk['to']}")

conn.close()
