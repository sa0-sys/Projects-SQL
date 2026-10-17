"""Runs every query in queries.sql against payments.db and prints the results. Run: python run_queries.py"""
import re, sqlite3
con = sqlite3.connect("payments.db")
sql = open("queries.sql").read()
blocks = re.split(r"(?m)^-- (Q\d+)\.", sql)
for i in range(1, len(blocks), 2):
    label, body = blocks[i], blocks[i + 1]
    title, _, query = body.partition("\n")
    cur = con.execute(query.strip().rstrip(";"))
    cols = [c[0] for c in cur.description]
    print(f"\n{label}.{title}\n" + " | ".join(cols))
    for row in cur.fetchall():
        print(" | ".join("" if v is None else str(v) for v in row))
