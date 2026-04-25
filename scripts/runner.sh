#!/usr/bin/env bash
# ==============================================================
# runner.sh — Ejecuta scraping de ChileCompra y sube a GitHub
# Para ejecutar vía cron en la VPS
# ==============================================================
set -e

REPO_DIR="/home/alwyzon/chilecompra-iso-scanner"
API_KEY="CD89C6AC-C570-4BE6-BF0F-B25C35393FAB"
SCRIPTS_DIR="$REPO_DIR/scripts"
DATA_DIR="$REPO_DIR/data"

cd "$REPO_DIR"

# 1. Pull latest
git pull origin main 2>/dev/null || true

# 2. Ejecutar scraping (últimos 7 días)
python3 "$SCRIPTS_DIR/procesar_aseo.py"

# 3. Git add, commit, push
git add -A
git commit -m "auto: actualización $(date +'%d/%m/%Y %H:%M')" || true
git push origin main 2>&1

echo "✅ Ejecutado: $(date)"
