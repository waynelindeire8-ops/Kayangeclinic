from app.database import get_db
db = get_db()
tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for t in tables:
    fks = db.execute(f'PRAGMA foreign_key_list({t})').fetchall()
    if fks:
        print(f'=== {t} ===')
        for fk in fks:
            print(dict(fk))
db.close()
