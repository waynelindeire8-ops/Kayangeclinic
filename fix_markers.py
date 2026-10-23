p = "app/backup.py"
raw = open(p, encoding="utf-8", newline="").read()
nl = "\r\n" if "\r\n" in raw else "\n"
L = raw.split(nl)
start = next(i for i, l in enumerate(L) if l.startswith("<<<<<<<"))
end = next(i for i, l in enumerate(L) if i > start and l.startswith(">>>>>>>"))
assert end - start <= 10, "block too big, stop"
L[start:end + 1] = [" " * 20 + "_relax_not_null(cur, sqlite_db, table_name)"]
open(p, "w", encoding="utf-8", newline="").write(nl.join(L))
print("fixed lines", start + 1, "to", end + 1)
