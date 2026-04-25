#!/usr/bin/env python3
"""
ChileCompra ISO Scanner — Dashboard Web
Busca oportunidades ISO 9001/14001/45001 en Mercado Público
Login protegido, filtros Magochic, scraping automático

Desplegar en VPS: 203.98.67.84
"""

import os
import json
import csv
import io
import time
import re
import sqlite3
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import quote_plus

from flask import (
    Flask, render_template_string, request, redirect,
    url_for, session, flash, jsonify, send_file
)
import requests
from bs4 import BeautifulSoup

# ─── Config ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "chilecompra.db")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ─── Usuarios ───────────────────────────────────────────────────────────
USERS = {
    "admin": hashlib.sha256("magochic2026".encode()).hexdigest(),
    "jp": hashlib.sha256("cms2026".encode()).hexdigest(),
}

# ─── DB Init ────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS licitaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE,
            nombre TEXT,
            organismo TEXT,
            FechaPublicacion TEXT,
            FechaCierre TEXT,
            estado TEXT,
            monto INTEGER,
            categoria TEXT,
            region TEXT,
            norma TEXT,
            keywords TEXT,
            url TEXT,
            created_at TEXT DEFAULT (datetime('now','-3 hours'))
        );
        CREATE TABLE IF NOT EXISTS scraping_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            encontradas INTEGER,
            nuevas INTEGER,
            duracion INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_norma ON licitaciones(norma);
        CREATE INDEX IF NOT EXISTS idx_estado ON licitaciones(estado);
        CREATE INDEX IF NOT EXISTS idx_fecha ON licitaciones(FechaCierre);
    """)
    conn.commit()
    conn.close()

# ─── Login Decorator ────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ─── Routes ─────────────────────────────────────────────────────────────

# ─── HTML Templates ─────────────────────────────────────────────────────
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ChileCompra ISO Scanner</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
               background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
               min-height:100vh; display:flex; align-items:center; justify-content:center; }
        .card { background:white; border-radius:16px; padding:40px; width:380px;
                box-shadow:0 20px 60px rgba(0,0,0,0.3); }
        h1 { font-size:24px; margin-bottom:8px; color:#333; }
        p { color:#666; margin-bottom:24px; font-size:14px; }
        input { width:100%; padding:12px 16px; margin-bottom:16px; border:2px solid #e0e0e0;
                border-radius:8px; font-size:14px; transition:border-color .2s; }
        input:focus { border-color:#667eea; outline:none; }
        button { width:100%; padding:12px; background:linear-gradient(135deg,#667eea,#764ba2);
                 color:white; border:none; border-radius:8px; font-size:15px; font-weight:600;
                 cursor:pointer; transition:opacity .2s; }
        button:hover { opacity:.9; }
        .error { background:#ffe0e0; color:#c00; padding:10px; border-radius:8px;
                 margin-bottom:16px; font-size:13px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>🔍 ISO Scanner</h1>
        <p>Oportunidades ISO en ChileCompra</p>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <input type="text" name="username" placeholder="Usuario" required>
            <input type="password" name="password" placeholder="Contraseña" required>
            <button type="submit">Ingresar</button>
        </form>
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ISO Scanner — Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
               background:#f5f7fb; color:#333; }
        .header { background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
                  color:white; padding:20px 30px; display:flex; justify-content:space-between;
                  align-items:center; }
        .header h1 { font-size:20px; }
        .header .user-info { font-size:13px; opacity:.8; }
        .header a { color:white; text-decoration:none; margin-left:16px; font-size:13px; }

        .container { max-width:1400px; margin:0 auto; padding:20px; }

        .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
                 gap:16px; margin-bottom:24px; }
        .stat-card { background:white; border-radius:12px; padding:20px; box-shadow:0 2px 8px rgba(0,0,0,.06); }
        .stat-card .num { font-size:28px; font-weight:700; color:#667eea; }
        .stat-card .lab { font-size:13px; color:#888; margin-top:4px; }

        .search-box { background:white; border-radius:12px; padding:20px;
                      box-shadow:0 2px 8px rgba(0,0,0,.06); margin-bottom:20px; }
        .search-box h3 { font-size:15px; margin-bottom:12px; color:#555; }
        .filters { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:12px; }
        .filters input, .filters select {
            padding:8px 12px; border:2px solid #e0e0e0; border-radius:8px; font-size:13px; }
        .filters input { flex:1; min-width:200px; }
        .btn { padding:8px 20px; border:none; border-radius:8px; cursor:pointer;
               font-weight:600; font-size:13px; }
        .btn-primary { background:#667eea; color:white; }
        .btn-primary:hover { background:#5a6fd6; }
        .btn-success { background:#2ecc71; color:white; }
        .btn-warning { background:#f39c12; color:white; }
        .btn-danger { background:#e74c3c; color:white; }
        .btn-sm { padding:5px 12px; font-size:12px; }

        .actions { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }

        .table-wrap { background:white; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,.06);
                      overflow-x:auto; }
        table { width:100%; border-collapse:collapse; font-size:13px; }
        th { background:#f8f9fe; text-align:left; padding:12px 14px; font-weight:600;
             color:#555; border-bottom:2px solid #eee; white-space:nowrap; }
        td { padding:10px 14px; border-bottom:1px solid #f0f0f0; }
        tr:hover { background:#f8f9fe; }
        .badge { display:inline-block; padding:3px 10px; border-radius:20px; font-size:11px;
                 font-weight:600; }
        .badge-9001 { background:#e3f2fd; color:#1565c0; }
        .badge-14001 { background:#e8f5e9; color:#2e7d32; }
        .badge-45001 { background:#fff3e0; color:#e65100; }
        .badge-abierta { background:#e8f5e9; color:#1b5e20; }
        .badge-cerrada { background:#fce4ec; color:#c62828; }
        .badge-adjudicada { background:#fff3e0; color:#e65100; }
        .badge-desierta { background:#f3e5f5; color:#6a1b9a; }

        .magochic-panel { background:white; border-radius:12px; padding:20px;
                          box-shadow:0 2px 8px rgba(0,0,0,.06); margin-bottom:20px;
                          border-left:4px solid #e74c3c; }
        .magochic-panel h3 { color:#e74c3c; font-size:15px; margin-bottom:10px; }
        .magochic-filters { display:flex; flex-wrap:wrap; gap:10px; align-items:end; }
        .magochic-filters label { font-size:12px; font-weight:600; color:#555; display:block; margin-bottom:4px; }
        .magochic-filters div { display:flex; flex-direction:column; }
        .magochic-filters input, .magochic-filters select {
            padding:6px 10px; border:2px solid #e0e0e0; border-radius:6px; font-size:12px; }

        .pagination { display:flex; justify-content:center; gap:8px; padding:16px; }
        .pagination a { padding:6px 12px; border:1px solid #ddd; border-radius:6px;
                        text-decoration:none; color:#555; font-size:13px; }
        .pagination a:hover { background:#667eea; color:white; border-color:#667eea; }
        .pagination .active { background:#667eea; color:white; border-color:#667eea; }

        .info-bar { background:#fff8e1; border:1px solid #ffd54f; padding:10px 16px;
                    border-radius:8px; font-size:13px; margin-bottom:16px; }

        @media (max-width:768px) {
            .container { padding:10px; }
            .filters { flex-direction:column; }
            .filters input { min-width:auto; }
            .magochic-filters { flex-direction:column; }
        }
    </style>
</head>
<body>
<div class="header">
    <div>
        <h1>🔍 ISO Scanner — Mercado Público</h1>
        <div class="user-info">Usuario: {{ session.username }} — Último scrape: {{ ultimo_scrape }}</div>
    </div>
    <div>
        <a href="{{ url_for('export_csv') }}">⬇ Exportar CSV</a>
        <a href="{{ url_for('logout') }}">Cerrar sesión</a>
    </div>
</div>

<div class="container">
    {% if error %}<div class="info-bar">⚠ {{ error }}</div>{% endif %}

    <!-- Stats -->
    <div class="stats">
        <div class="stat-card"><div class="num">{{ stats.total }}</div><div class="lab">Total licitaciones</div></div>
        <div class="stat-card"><div class="num">{{ stats.abiertas }}</div><div class="lab">Abiertas</div></div>
        <div class="stat-card"><div class="num">{{ stats.iso_opts }}</div><div class="lab">Oportunidades ISO</div></div>
        <div class="stat-card"><div class="num">{{ stats.this_week }}</div><div class="lab">Esta semana</div></div>
    </div>

    <!-- Magochic Panel -->
    <div class="magochic-panel">
        <h3>🎯 Filtros Magochic — Aseo Industrial</h3>
        <form method="GET">
            <div class="magochic-filters">
                <div>
                    <label>Palabras clave</label>
                    <input type="text" name="q" value="{{ request.args.get('q','') }}"
                           placeholder="aseo, limpieza, sanitización...">
                </div>
                <div>
                    <label>Norma ISO</label>
                    <select name="norma">
                        <option value="">Todas</option>
                        <option value="9001" {% if request.args.get('norma')=='9001' %}selected{% endif %}>ISO 9001</option>
                        <option value="14001" {% if request.args.get('norma')=='14001' %}selected{% endif %}>ISO 14001</option>
                        <option value="45001" {% if request.args.get('norma')=='45001' %}selected{% endif %}>ISO 45001</option>
                    </select>
                </div>
                <div>
                    <label>Estado</label>
                    <select name="estado">
                        <option value="">Todos</option>
                        <option value="abierta" {% if request.args.get('estado')=='abierta' %}selected{% endif %}>Abierta</option>
                        <option value="cerrada" {% if request.args.get('estado')=='cerrada' %}selected{% endif %}>Cerrada</option>
                        <option value="adjudicada" {% if request.args.get('estado')=='adjudicada' %}selected{% endif %}>Adjudicada</option>
                    </select>
                </div>
                <div>
                    <label>Monto mínimo</label>
                    <input type="number" name="monto_min" value="{{ request.args.get('monto_min','') }}"
                           placeholder="1.000.000" style="width:120px">
                </div>
                <div>
                    <label>Monto máximo</label>
                    <input type="number" name="monto_max" value="{{ request.args.get('monto_max','') }}"
                           placeholder="100.000.000" style="width:120px">
                </div>
                <div>
                    <label>Organismo</label>
                    <input type="text" name="organismo" value="{{ request.args.get('organismo','') }}"
                           placeholder="Municipalidad, MOP, Salud...">
                </div>
                <div>
                    <button type="submit" class="btn btn-primary">Filtrar</button>
                </div>
            </div>
        </form>
    </div>

    <!-- Search general -->
    <div class="search-box">
        <h3>📋 Búsqueda general</h3>
        <form method="GET">
            <div class="filters">
                <input type="text" name="search" value="{{ request.args.get('search','') }}"
                       placeholder="Buscar en nombre, organismo, código...">
                <select name="norma">
                    <option value="">Todas las normas</option>
                    <option value="9001" {% if request.args.get('norma')=='9001' %}selected{% endif %}>ISO 9001</option>
                    <option value="14001" {% if request.args.get('norma')=='14001' %}selected{% endif %}>ISO 14001</option>
                    <option value="45001" {% if request.args.get('norma')=='45001' %}selected{% endif %}>ISO 45001</option>
                </select>
                <select name="estado">
                    <option value="">Todos los estados</option>
                    <option value="abierta" {% if request.args.get('estado')=='abierta' %}selected{% endif %}>Abierta</option>
                    <option value="cerrada" {% if request.args.get('estado')=='cerrada' %}selected{% endif %}>Cerrada</option>
                    <option value="adjudicada" {% if request.args.get('estado')=='adjudicada' %}selected{% endif %}>Adjudicada</option>
                </select>
            </div>
            <div class="actions">
                <input type="hidden" name="q" value="{{ request.args.get('q','') }}">
                <input type="hidden" name="organismo" value="{{ request.args.get('organismo','') }}">
                <input type="hidden" name="monto_min" value="{{ request.args.get('monto_min','') }}">
                <input type="hidden" name="monto_max" value="{{ request.args.get('monto_max','') }}">
                <button type="submit" class="btn btn-primary">Buscar</button>
                <a href="{{ url_for('dashboard') }}" class="btn btn-sm">Limpiar</a>
            </div>
        </form>
    </div>

    <!-- Scrape actions -->
    <div class="actions" style="margin-bottom:16px;">
        <a href="{{ url_for('scrape') }}" class="btn btn-warning">🔄 Scrapear ahora</a>
        <a href="{{ url_for('scrape', modo='profundo') }}" class="btn btn-warning">🔍 Scrapear profundo</a>
    </div>

    <!-- Table -->
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Código</th>
                    <th>Nombre</th>
                    <th>Organismo</th>
                    <th>Publicación</th>
                    <th>Cierre</th>
                    <th>Monto</th>
                    <th>Norma</th>
                    <th>Estado</th>
                    <th>Región</th>
                </tr>
            </thead>
            <tbody>
                {% if rows %}
                {% for r in rows %}
                <tr>
                    <td><a href="{{ r.url }}" target="_blank" style="color:#667eea;">{{ r.codigo }}</a></td>
                    <td>{{ r.nombre[:80] }}{% if r.nombre|length > 80 %}...{% endif %}</td>
                    <td>{{ r.organismo[:40] }}{% if r.organismo|length > 40 %}...{% endif %}</td>
                    <td>{{ r.FechaPublicacion[:10] if r.FechaPublicacion else '' }}</td>
                    <td>{{ r.FechaCierre[:10] if r.FechaCierre else '' }}</td>
                    <td>${{ "{:,}".format(r.monto) if r.monto else 0 }}</td>
                    <td>{% if r.norma %}<span class="badge badge-{{ r.norma }}">ISO {{ r.norma }}</span>{% endif %}</td>
                    <td><span class="badge badge-{{ r.estado }}">{{ r.estado }}</span></td>
                    <td>{{ r.region if r.region else 'N/A' }}</td>
                </tr>
                {% endfor %}
                {% else %}
                <tr><td colspan="9" style="text-align:center;padding:30px;color:#999;">
                    No hay licitaciones. Haz click en "Scrapear ahora" para buscar.
                </td></tr>
                {% endif %}
            </tbody>
        </table>
    </div>

    <!-- Pagination -->
    {% if total_pages > 1 %}
    <div class="pagination">
        {% for p in range(1, total_pages + 1) %}
        <a href="{{ url_for('dashboard', page=p, **request.args) }}"
           class="{% if p == page %}active{% endif %}">{{ p }}</a>
        {% endfor %}
    </div>
    {% endif %}
</div>
</body>
</html>
"""

# ─── Routes ─────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        if username in USERS and USERS[username] == pw_hash:
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("dashboard"))
        return render_template_string(LOGIN_HTML, error="Usuario o contraseña incorrectos")
    return render_template_string(LOGIN_HTML, error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    conn = get_db()
    page = request.args.get("page", 1, type=int)
    per_page = 50

    # Build query
    where = []
    params = []

    search = request.args.get("search", "").strip()
    norma = request.args.get("norma", "").strip()
    estado = request.args.get("estado", "").strip()
    q = request.args.get("q", "").strip()
    organismo = request.args.get("organismo", "").strip()
    monto_min = request.args.get("monto_min", "", type=str).strip()
    monto_max = request.args.get("monto_max", "", type=str).strip()

    if search:
        where.append("(nombre LIKE ? OR organismo LIKE ? OR codigo LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if norma:
        where.append("norma = ?")
        params.append(norma)
    if estado:
        where.append("estado = ?")
        params.append(estado)
    if q:
        where.append("(nombre LIKE ? OR keywords LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if organismo:
        where.append("organismo LIKE ?")
        params.append(f"%{organismo}%")
    if monto_min:
        where.append(f"monto >= ?")
        params.append(int(re.sub(r'[^0-9]', '', monto_min)))
    if monto_max:
        where.append(f"monto <= ?")
        params.append(int(re.sub(r'[^0-9]', '', monto_max)))

    where_clause = " WHERE " + " AND ".join(where) if where else ""

    # Stats (defaults in case of error)
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
        pass

    # Query
    count = conn.execute(f"SELECT COUNT(*) FROM licitaciones{where_clause}", params).fetchone()[0]
    total_pages = max(1, (count + per_page - 1) // per_page)
    offset = (page - 1) * per_page

    rows = conn.execute(
        f"SELECT * FROM licitaciones{where_clause} ORDER BY FechaPublicacion DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    conn.close()

    # Preserve all params in pagination
    args = request.args.copy()
    args.pop("page", None)

    return render_template_string(DASHBOARD_HTML, **locals())


@app.route("/scrape")
@login_required
def scrape():
    modo = request.args.get("modo", "rapido")
    start = time.time()
    nuevas = scrap_mercadopublico(modo=modo)
    duration = int(time.time() - start)

    conn = get_db()
    encontradas = conn.execute("SELECT COUNT(*) FROM licitaciones").fetchone()[0]
    conn.execute(
        "INSERT INTO scraping_log (fecha, encontradas, nuevas, duracion) VALUES (?, ?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), encontradas, nuevas, duration)
    )
    conn.commit()
    conn.close()

    flash(f"✅ Scrapeo completo: {nuevas} nuevas licitaciones encontradas en {duration}s")
    return redirect(url_for("dashboard"))


@app.route("/export")
@login_required
def export_csv():
    conn = get_db()
    rows = conn.execute("SELECT * FROM licitaciones ORDER BY FechaPublicacion DESC").fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Código", "Nombre", "Organismo", "Publicación", "Cierre",
                      "Estado", "Monto", "Categoría", "Región", "Norma", "URL"])
    for r in rows:
        writer.writerow([r["codigo"], r["nombre"], r["organismo"],
                         r["FechaPublicacion"], r["FechaCierre"], r["estado"],
                         r["monto"], r["categoria"], r["region"], r["norma"], r["url"]])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"chilecompra_iso_{datetime.now().strftime('%Y%m%d')}.csv"
    )


# ─── Scraper ────────────────────────────────────────────────────────────

CATEGORIAS_ISO = {
    "9001": ["calidad", "gestión de calidad", "iso 9001", "sistema de gestión de calidad",
             "sgc", "norma iso 9001", "procedimiento calidad", "auditoría calidad"],
    "14001": ["ambiental", "gestión ambiental", "iso 14001", "medio ambiente", "sga",
              "norma iso 14001", "residuos", "impacto ambiental"],
    "45001": ["seguridad", "salud ocupacional", "iso 45001", "sst", "prevención riesgos",
              "norma iso 45001", "sgsst", "higiene", "seguridad laboral"],
}

def detectar_norma(texto):
    """Detecta qué norma ISO aplica según keywords"""
    texto = texto.lower()
    normas = []
    for norma, keywords in CATEGORIAS_ISO.items():
        if any(kw in texto for kw in keywords):
            normas.append(norma)
    return ",".join(normas[:3]) if normas else None

def detectar_estado(texto, dias_cierre=None):
    """Detecta estado de la licitación"""
    texto = texto.lower()
    if "adjudic" in texto or "adjud" in texto:
        return "adjudicada"
    if "desiert" in texto or "declarada desierta" in texto:
        return "desierta"
    if "cerrada" in texto or "cerrado" in texto or "finalizada" in texto:
        return "cerrada"
    if "publicada" in texto or "abierta" in texto or "en curso" in texto:
        return "abierta"
    return "abierta"  # default

def limpiar_monto(texto):
    """Extrae número de un texto de monto"""
    nums = re.findall(r'\d+', texto.replace('.', '').replace('$', ''))
    return int(nums[0]) if nums else 0

def scrap_mercadopublico(modo="rapido"):
    """Scrapea licitaciones de Mercado Público"""
    conn = get_db()
    nuevas = 0
    pages = 3 if modo == "rapido" else 10

    for page in range(1, pages + 1):
        try:
            # Búsqueda general
            url = f"https://www.mercadopublico.cl/Home/ResultadosBusqueda?pagina={page}&tipoOrden=4&tipoBusqueda=1"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Buscar tablas de resultados
            tables = soup.find_all("table")
            if not tables:
                # Intenta por divs
                items = soup.find_all("div", class_=re.compile(r"resultado|licitacion|item", re.I))
            else:
                items = tables[0].find_all("tr")[1:]  # skip header

            for item in items[:30]:
                try:
                    texto = item.get_text(" ", strip=True)

                    # Extraer código
                    codigo_match = re.search(r'(\d{6,}-\d{1,4}-[A-Za-z0-9]+)', texto)
                    if not codigo_match:
                        continue
                    codigo = codigo_match.group(1)

                    # Extraer nombre
                    links = item.find_all("a")
                    nombre = links[0].get_text(strip=True) if links else "Sin nombre"
                    url_lic = "https://www.mercadopublico.cl" + links[0].get("href", "") if links else ""

                    # Extraer organismo
                    organismo = ""
                    org_match = re.search(r'Organismo\s*:*\s*([^\n]+)', texto, re.I)
                    if org_match:
                        organismo = org_match.group(1).strip()

                    # Fechas
                    fec_publicacion = ""
                    fec_cierre = ""
                    fp = re.search(r'(?:Publicación|Publicado)\s*:*\s*(\d{2}[-/]\d{2}[-/]\d{2,4})', texto, re.I)
                    fc = re.search(r'(?:Cierre|Cierre de)\s*:*\s*(\d{2}[-/]\d{2}[-/]\d{2,4})', texto, re.I)
                    if fp: fec_publicacion = fp.group(1)
                    if fc: fec_cierre = fc.group(1)

                    # Monto
                    monto = 0
                    monto_match = re.search(r'(?:Monto|Presupuesto)\s*:*\s*\$?([0-9.,]+)', texto, re.I)
                    if monto_match:
                        monto = limpiar_monto(monto_match.group(1))

                    # Estado
                    estado = detectar_estado(texto)

                    # Norma
                    norma = detectar_norma(texto + " " + nombre)

                    # Región
                    region = ""
                    reg_match = re.search(r'(?:Región|Region)\s*:*\s*([^\n]+)', texto, re.I)
                    if reg_match:
                        region = reg_match.group(1).strip()

                    # Categoria
                    categoria = ""
                    cat_match = re.search(r'(?:Categoría|Categoria)\s*:*\s*([^\n]+)', texto, re.I)
                    if cat_match:
                        categoria = cat_match.group(1).strip()

                    # Insertar
                    try:
                        conn.execute("""
                            INSERT OR IGNORE INTO licitaciones
                            (codigo, nombre, organismo, FechaPublicacion, FechaCierre,
                             estado, monto, categoria, region, norma, keywords, url)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (codigo, nombre[:200], organismo[:100],
                              fec_publicacion, fec_cierre, estado,
                              monto, categoria[:50], region[:50], norma,
                              texto[:500], url_lic))
                        if conn.total_changes > 0:
                            nuevas += 1
                    except Exception:
                        pass

                except Exception:
                    continue

        except Exception:
            continue

    conn.commit()
    conn.close()
    return nuevas


# ─── Main ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Iniciando ChileCompra ISO Scanner...")
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
