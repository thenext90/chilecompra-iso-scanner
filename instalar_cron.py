#!/usr/bin/env python3
"""Instala el crontab para el scraper de ChileCompra."""
import os

cron_line = "0 6 * * * /usr/bin/python3 /home/alwyzon/chilecompra-iso-scanner/magochic_scraper.py --source api --days 1 >> /home/alwyzon/chilecompra-iso-scanner/data/scraper.log 2>&1\n"

# Obtener crontab actual
import subprocess
try:
    current = subprocess.check_output(["crontab", "-l"]).decode()
except:
    current = ""

if cron_line not in current:
    new_cron = current + cron_line
    p = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE)
    p.communicate(new_cron.encode())
    print(f"✓ Crontab instalado: {cron_line.strip()}")
else:
    print("✓ Crontab ya existe")

print("\nCrontab actual:")
os.system("crontab -l")
