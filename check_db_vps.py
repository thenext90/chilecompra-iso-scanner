#!/usr/bin/env python3
"""Check ChileCompra DB status on VPS"""
import sqlite3, os, sys

db_path = "/home/alwyzon/chilecompra-iso-scanner/data/chilecompra.db"

if not os.path.exists(db_path):
    print(f"ERROR: DB not found at {db_path}")
    sys.exit(1)

conn = sqlite3.connect(db_path)
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur]
print(f"Tablas: {tables}")

for t in tables:
    cur = conn.execute(f"SELECT COUNT(*) FROM {t}")
    cnt = cur.fetchone()[0]
    print(f"\n  {t}: {cnt} registros")
    
    cur = conn.execute(f"PRAGMA table_info({t})")
    cols = [(r[1], r[2]) for r in cur]
    print(f"  Columnas: {[c[0] for c in cols]}")
    
    if cnt > 0:
        cur = conn.execute(f"SELECT * FROM {t} LIMIT 5")
        for i, row in enumerate(cur):
            print(f"  [{i+1}] {row}")

conn.close()
