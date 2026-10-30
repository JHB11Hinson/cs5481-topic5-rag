import sqlite3
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "data/cache/prefixes.sqlite"
conn = sqlite3.connect(path)
total = conn.execute("SELECT COUNT(*) FROM prefixes").fetchone()[0]
empty = conn.execute("SELECT COUNT(*) FROM prefixes WHERE TRIM(prefix) = ''").fetchone()[0]
print("cached:", total, "empty:", empty)
for row in conn.execute("SELECT substr(prefix, 1, 100) FROM prefixes LIMIT 2"):
    print("-", row[0])
