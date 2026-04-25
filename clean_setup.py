#!/usr/bin/env python3
"""
Setup completo del ChileCompra ISO Scanner.
Ejecutar en la VPS: python3 chilecompra_clean_setup.py
"""
import os, json, sqlite3, requests, time
from datetime import datetime, timedelta

TICKET = "F8537A18-6766-4DEF-9E59-426B4FEE2844"
BASE = "https://api.mercadopublico.cl/servicios/v1/publico"
PROJ_DIR = os.path.expanduser("~/chilecompra-iso-scanner")
DB_PATH = os.path.join(PROJ_DIR, "data", "chilecompra.db")

# Keywords ISO
KEYWORDS = {
    "9001": ["iso 9001", "calidad", "sgc", "gestión de calidad", "norma 9001"],
    "14001": ["iso 14001", "ambiental", "sga", "gestión ambiental", "norma 14001"],
    "45001": ["iso 45001", "sst", "seguridad y salud", "ohsas", "norma 45001"],
    "normas": ["sistemas de gestión", "certificación", "implementación", "auditoría", "norma iso"],
    "chilecompra": ["licitación", "concurso público", "proveedor", "contratación pública"],
}

def setup_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS licitaciones (
            codigo TEXT PRIMARY KEY,
            nombre TEXT,
            organismo TEXT,
            estado TEXT,
            fecha_publicacion TEXT,
            fecha_cierre TEXT,
            tipo TEXT,
            monto INTEGER,
            categoria TEXT,
            descripcion TEXT,
            url TEXT,
            fecha_scraped TEXT DEFAULT CURRENT_TIMESTAMP,
            iso_relevante TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scraping_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            encontradas INTEGER,
            nuevas INTEGER,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn

def date_range(start, end):
    """Generate dates from start to end inclusive."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)

def scrape_day(conn, fecha, verbose=True):
    """Scrape a single day, all pages."""
    fecha_str = fecha.strftime("%d%m%Y")
    total_encontradas = 0
    total_nuevas = 0
    pagina = 1
    
    while pagina <= 20:  # max 20 pages = 2000 licitaciones/day
        url = f"{BASE}/licitaciones.json?fecha={fecha_str}&pagina={pagina}&ticket={TICKET}"
        
        for attempt in range(3):
            try:
                resp = requests.get(url, timeout=30)
                if resp.status_code == 429:
                    wait = 5 * (attempt + 1)
                    if verbose: print(f"    Rate limited, esperando {wait}s...")
                    time.sleep(wait)
                    continue
                data = resp.json()
                break
            except Exception as e:
                if verbose: print(f"    Error: {e}, reintentando...")
                time.sleep(2)
        else:
            if verbose: print(f"    Falló tras 3 intentos, saltando")
            break
        
        # Check for API error
        codigo = data.get("Codigo")
        if codigo is not None and codigo != 200:
            if verbose: print(f"    API error: Codigo={codigo}")
            break
        
        listado = data.get("Listado", [])
        if not listado:
            if verbose: print(f"    Página {pagina}: sin datos, terminando")
            break
        
        if verbose: print(f"    Página {pagina}: {len(listado)} licitaciones")
        total_encontradas += len(listado)
        
        nuevas = 0
        for lic in listado:
            cod = lic.get("Codigo", "")
            nom = lic.get("Nombre", "")
            org = lic.get("Organismo", "")
            est = lic.get("Estado", "")
            fp = lic.get("FechaPublicacion", "")
            fc = lic.get("FechaCierre", "")
            tip = lic.get("Tipo", "")
            cat = lic.get("Categoria", "")
            des = lic.get("Descripcion", "")
            url_l = lic.get("Url", "")
            
            # Detectar relevancia ISO
            iso_rel = ""
            texto_busqueda = (nom + " " + des + " " + cat).lower()
            for key, kws in KEYWORDS.items():
                for kw in kws:
                    if kw in texto_busqueda:
                        iso_rel = key
                        break
                if iso_rel:
                    break
            
            try:
                monto = float(lic.get("Monto", 0) or 0)
            except:
                monto = 0
            
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO licitaciones
                    (codigo, nombre, organismo, estado, fecha_publicacion, fecha_cierre,
                     tipo, monto, categoria, descripcion, url, iso_relevante)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (cod, nom, org, est, fp, fc, tip, monto, cat, des, url_l, iso_rel))
                if conn.total_changes > 0:
                    nuevas += 1
            except Exception as e:
                if verbose: print(f"    DB Error: {e}")
        
        conn.commit()
        total_nuevas += nuevas
        if verbose: print(f"    → {nuevas} nuevas")
        
        pagina += 1
        time.sleep(0.3)  # avoid rate limiting between pages
    
    return total_encontradas, total_nuevas

def run():
    print("=" * 60)
    print("CHILECOMPRA ISO SCANNER - Setup y Scrape")
    print("=" * 60)
    
    conn = setup_db()
    print(f"✓ Base de datos lista: {DB_PATH}")
    
    # Count existing
    c = conn.execute("SELECT COUNT(*) FROM licitaciones")
    existentes = c.fetchone()[0]
    print(f"✓ Licitaciones existentes: {existentes}")
    
    # Scrape últimos 30 días
    hoy = datetime.now()
    inicio = hoy - timedelta(days=30)
    
    print(f"\n→ Scrapeando desde {inicio.strftime('%d/%m/%Y')} hasta {hoy.strftime('%d/%m/%Y')}")
    total_enc = 0
    total_nue = 0
    
    for fecha in date_range(inicio, hoy):
        print(f"\n📅 {fecha.strftime('%A %d/%m/%Y')}:")
        enc, nue = scrape_day(conn, fecha)
        total_enc += enc
        total_nue += nue
        print(f"  → Encontradas: {enc} | Nuevas: {nue}")
        time.sleep(0.5)  # between days
    
    # Log
    conn.execute("INSERT INTO scraping_log (fecha, encontradas, nuevas) VALUES (?, ?, ?)",
                 (hoy.strftime("%Y-%m-%d"), total_enc, total_nue))
    conn.commit()
    
    print("\n" + "=" * 60)
    print(f"RESUMEN FINAL")
    print(f"  Licitaciones encontradas: {total_enc}")
    print(f"  Licitaciones nuevas: {total_nue}")
    print(f"  Total en DB: {existentes + total_nue}")
    print("=" * 60)
    
    # Mostrar ISO relevantes
    c = conn.execute("SELECT iso_relevante, COUNT(*) FROM licitaciones WHERE iso_relevante != '' GROUP BY iso_relevante")
    iso_counts = c.fetchall()
    if iso_counts:
        print("\n📊 Licitaciones ISO-relevantes:")
        for iso, count in iso_counts:
            print(f"  {iso}: {count}")
    
    conn.close()

if __name__ == "__main__":
    run()
