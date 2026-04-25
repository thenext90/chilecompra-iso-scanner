#!/usr/bin/env python3
"""Fix 'stats' undefined error in app.py - replace individual vars with stats dict"""
import re

with open('/home/alwyzon/chilecompra-iso-scanner/app.py') as f:
    content = f.read()

old = '''    # Stats (defaults in case of error)
    total, abiertas, iso_opts, this_week, ultimo_scrape = 0, 0, 0, 0, ""
    try:
        total = conn.execute("SELECT COUNT(*) FROM licitaciones").fetchone()[0]
        abiertas = conn.execute("SELECT COUNT(*) FROM licitaciones WHERE estado='abierta'").fetchone()[0]
        iso_opts = conn.execute("SELECT COUNT(*) FROM licitaciones WHERE norma IN ('9001','14001','45001')").fetchone()[0]
        this_week = conn.execute(
            "SELECT COUNT(*) FROM licitaciones WHERE FechaPublicacion >= date('now','-7 days','-3 hours')"
        ).fetchone()[0]
        last_log = conn.execute("SELECT fecha FROM scraping_log ORDER BY id DESC LIMIT 1").fetchone()
        ultimo_scrape = last_log["fecha"] if last_log else "Nunca"
    except Exception:
        pass'''

new = '''    # Stats (defaults in case of error)
    stats = {"total": 0, "abiertas": 0, "iso_opts": 0, "this_week": 0, "ultimo_scrape": ""}
    try:
        stats["total"] = conn.execute("SELECT COUNT(*) FROM licitaciones").fetchone()[0]
        stats["abiertas"] = conn.execute("SELECT COUNT(*) FROM licitaciones WHERE estado='abierta'").fetchone()[0]
        stats["iso_opts"] = conn.execute("SELECT COUNT(*) FROM licitaciones WHERE norma IN ('9001','14001','45001')").fetchone()[0]
        stats["this_week"] = conn.execute(
            "SELECT COUNT(*) FROM licitaciones WHERE FechaPublicacion >= date('now','-7 days','-3 hours')"
        ).fetchone()[0]
        last_log = conn.execute("SELECT fecha FROM scraping_log ORDER BY id DESC LIMIT 1").fetchone()
        stats["ultimo_scrape"] = last_log["fecha"] if last_log else "Nunca"
    except Exception:
        pass'''

if old in content:
    content = content.replace(old, new)
    with open('/home/alwyzon/chilecompra-iso-scanner/app.py', 'w') as f:
        f.write(content)
    print("OK - stats dict fix applied")
else:
    print("ERROR: old text not found in file")
    # Debug: show what's around that area
    idx = content.find("# Stats")
    if idx >= 0:
        print("Found '# Stats' at", idx)
        print(repr(content[idx:idx+600]))
    else:
        print("'# Stats' not found either")
