#!/usr/bin/env bash
# runner.sh — Ejecuta scraping de ChileCompra y sube a GitHub
# Cron: 0 10 * * * /bin/bash /home/alwyzon/chilecompra-iso-scanner/scripts/runner.sh
set -e

REPO_DIR="/home/alwyzon/chilecompra-iso-scanner"

cd "$REPO_DIR"

# 1. Pull latest
git pull origin main 2>/dev/null || true

# 2. Ejecutar scraper
python3 "$REPO_DIR/scripts/scraper_completo.py"

# 3. Git add, commit, push
git add -A
git commit -m "auto: actualización $(date +'%d/%m/%Y %H:%M')" || true
git push origin main 2>&1

echo "✅ Ejecutado: $(date)"
