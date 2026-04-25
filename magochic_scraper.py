#!/usr/bin/env python3
"""
ChileCompra ISO Scanner v2 - Datos Abiertos
Escáner de licitaciones públicas enfocado en oportunidades de certificación ISO
para empresas de aseo industrial. Estrategia Magochic.

Fuente: Datos abiertos ChileCompra
- API pública: https://api.mercadopublico.cl/servicios/v1/publico/
- Datos abiertos: https://datos-abiertos.chilecompra.cl/
"""
import os, sys, re, json, sqlite3, requests, gzip, io, csv
import urllib.parse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── Configuración ──────────────────────────────────────────────────
PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(PROJ_DIR, "data")
DB_PATH = os.path.join(DB_DIR, "chilecompra.db")
LOG_PATH = os.path.join(DB_DIR, "scraper.log")

# Ticket API (proporcionado por ChileCompra)
TICKET = os.environ.get("CHILECOMPRA_TICKET", "F8537A18-6766-4DEF-9E59-426B4FEE2844")
API_BASE = "https://api.mercadopublico.cl/servicios/v1/publico"

# Keywords de detección ISO para empresas de aseo industrial
ISO_KEYWORDS = {
    "9001": [
        r"iso\s*9001", r"norma\s*9001", r"sgc", r"calidad", r"gesti[óo]n\s+de?\s*la?\s*calidad",
        r"sistema\s+de?\s*gesti[óo]n\s+de?\s*la?\s*calidad", r"certificaci[óo]n\s+9001",
        r"gesti[óo]n\s+de?\s*calidad", r"control\s+de?\s*calidad",
    ],
    "14001": [
        r"iso\s*14001", r"norma\s*14001", r"ambiental", r"gesti[óo]n\s+ambiental",
        r"sistema\s+de?\s*gesti[óo]n\s+ambiental", r"medio\s+ambiente",
        r"certificaci[óo]n\s+14001", r"sga",
    ],
    "45001": [
        r"iso\s*45001", r"norma\s*45001", r"sst", r"seguridad\s+salud",
        r"salud\s+ocupacional", r"seguridad\s+en\s+el\s+trabajo",
        r"gesti[óo]n\s+de?\s*seguridad", r"certificaci[óo]n\s+45001",
        r"ohsas", r"prevenci[óo]n\s+de?\s*riesgos",
    ],
    "normas": [
        r"sistema\s+de?\s*gesti[óo]n", r"certificaci[óo]n\s+iso",
        r"implementaci[óo]n\s+iso", r"auditor[ií]a\s+iso",
        r"normas\s+iso", r"gestion\s+calidad", r"mejora\s+continua",
    ],
}

# Categorías ChileCompra relevantes para aseo industrial
CATEGORIAS_ASEO = [
    "servicio aseo", "limpieza industrial", "limpieza instalaciones",
    "sanitizacion", "saneamiento", "mantencion", "aseo industrial",
    "servicio limpieza", "limpieza", "mantenimiento",
]

# ─── Utilidades ─────────────────────────────────────────────────────
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass

def setup_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS licitaciones (
            codigo TEXT PRIMARY KEY,
            nombre TEXT,
            organismo TEXT,
            rut_organismo TEXT,
            estado TEXT,
            fecha_publicacion TEXT,
            fecha_cierre TEXT,
            fecha_estimada TEXT,
            tipo TEXT,
            moneda TEXT,
            monto_estimado REAL,
            monto_adjudicado REAL,
            categoria TEXT,
            subcategoria TEXT,
            region TEXT,
            comuna TEXT,
            descripcion TEXT,
            url TEXT,
            contacto_nombre TEXT,
            contacto_email TEXT,
            contacto_telefono TEXT,
            oportunidades_pyme TEXT,
            codigo_lote TEXT,
            lote_nombre TEXT,
            norma TEXT,
            palabras_clave TEXT,
            fuente TEXT DEFAULT 'scraper',
            fecha_scraped TEXT DEFAULT (datetime('now', '-3 hours')),
            UNIQUE(codigo, codigo_lote)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scraping_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            fuente TEXT,
            encontradas INTEGER,
            nuevas INTEGER,
            errores INTEGER,
            detalle TEXT,
            timestamp TEXT DEFAULT (datetime('now', '-3 hours'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_lic_fecha ON licitaciones(fecha_publicacion)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_lic_norma ON licitaciones(norma)
    """)
    conn.commit()
    return conn

def safe_str(s, maxlen=500):
    if s is None: return ""
    s = str(s).strip()
    return s[:maxlen]

def safe_float(s):
    if s is None: return 0.0
    s = str(s).strip().replace(".", "").replace(",", ".").replace("$", "").strip()
    try: return float(s)
    except: return 0.0

def detectar_normas(texto):
    """Detecta qué normas ISO aplican al texto."""
    if not texto:
        return ""
    texto = texto.lower()
    encontradas = []
    for norma, patrones in ISO_KEYWORDS.items():
        for pat in patrones:
            if re.search(pat, texto):
                encontradas.append(norma)
                break
    return ",".join(encontradas) if encontradas else ""

def detectar_palabras_clave(texto):
    """Extrae palabras clave relevantes del texto."""
    if not texto:
        return ""
    texto = texto.lower()
    kws = []
    for cat in CATEGORIAS_ASEO:
        if cat in texto:
            kws.append(cat)
    # ISO keywords
    for norma, patrones in ISO_KEYWORDS.items():
        for pat in patrones:
            m = re.search(pat, texto)
            if m:
                kws.append(m.group())
                break
    return ", ".join(sorted(set(kws))) if kws else ""

# ─── Scrapers ────────────────────────────────────────────────────────

class ScraperAPI:
    """Scraper usando API pública de Mercado Público."""
    
    def __init__(self, conn, ticket=TICKET):
        self.conn = conn
        self.ticket = ticket
        self.nuevas = 0
        self.encontradas = 0
        self.errores = 0
    
    def buscar_fecha(self, fecha, pagina=1):
        """Busca licitaciones por fecha usando API v1."""
        fecha_str = fecha.strftime("%d%m%Y")
        url = f"{API_BASE}/licitaciones.json"
        
        params = {
            "fecha": fecha_str,
            "pagina": pagina,
            "ticket": self.ticket,
        }
        
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                log(f"  ⚠ Rate limited (HTTP 429)")
                return None
            else:
                log(f"  ⚠ HTTP {resp.status_code}")
                return None
        except Exception as e:
            log(f"  ✗ Error: {e}")
            return None
    
    def procesar_licitacion(self, lic):
        """Procesa y guarda una licitación."""
        texto_busqueda = " ".join([
            str(lic.get("Nombre", "")),
            str(lic.get("Descripcion", "")),
            str(lic.get("Categoria", "")),
            str(lic.get("SubCategoria", "")),
        ])
        
        normas = detectar_normas(texto_busqueda)
        palabras = detectar_palabras_clave(texto_busqueda)
        
        # Solo guardar si hay match ISO o es de categoría relevante
        if not normas and not palabras:
            self.encontradas += 1
            return
        
        codigo = safe_str(lic.get("CodigoExterno", lic.get("Codigo", "")))
        if not codigo:
            return
        
        try:
            self.conn.execute("""
                INSERT OR IGNORE INTO licitaciones
                (codigo, nombre, organismo, rut_organismo, estado,
                 fecha_publicacion, fecha_cierre, tipo, moneda,
                 monto_estimado, categoria, subcategoria,
                 descripcion, contacto_nombre, contacto_email,
                 contacto_telefono, oportunidades_pyme,
                 norma, palabras_clave, fuente)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                codigo,
                safe_str(lic.get("Nombre", ""), 300),
                safe_str(lic.get("Organismo", ""), 200),
                safe_str(lic.get("RutOrganismo", ""), 20),
                safe_str(lic.get("Estado", ""), 50),
                safe_str(lic.get("FechaPublicacion", ""), 20),
                safe_str(lic.get("FechaCierre", ""), 20),
                safe_str(lic.get("Tipo", ""), 50),
                safe_str(lic.get("Moneda", ""), 10),
                safe_float(lic.get("MontoEstimado", 0)),
                safe_str(lic.get("Categoria", ""), 100),
                safe_str(lic.get("SubCategoria", ""), 100),
                safe_str(lic.get("Descripcion", ""), 1000),
                safe_str(lic.get("ContactoNombre", ""), 100),
                safe_str(lic.get("ContactoEmail", ""), 100),
                safe_str(lic.get("ContactoTelefono", ""), 50),
                safe_str(lic.get("OportunidadPyME", ""), 50),
                normas,
                palabras,
                "api"
            ))
            if self.conn.total_changes > 0:
                self.nuevas += 1
                self.encontradas += 1
            else:
                self.encontradas += 1
        except Exception as e:
            self.errores += 1
            log(f"  ✗ DB Error: {e}")
    
    def run(self, dias=7, verbose=True):
        """Ejecuta búsqueda por rango de días."""
        hoy = datetime.now()
        if verbose: log(f"🔍 Buscando últimos {dias} días vía API...")
        
        for dia in range(dias):
            fecha = hoy - timedelta(days=dia)
            fecha_str = fecha.strftime("%d/%m/%Y")
            
            pagina = 1
            while pagina <= 10:
                if verbose: 
                    sys.stdout.write(f"\r  {fecha_str} pág.{pagina}... ")
                    sys.stdout.flush()
                
                data = self.buscar_fecha(fecha, pagina)
                if data is None:
                    break
                
                licitaciones = data.get("Licitaciones", [])
                if not licitaciones:
                    break
                
                for lic in licitaciones:
                    self.procesar_licitacion(lic)
                
                pagina += 1
                if pagina > data.get("TotalPaginas", 1):
                    break
            
            if verbose: 
                print(f"[{fecha_str}] {self.encontradas} encontradas, {self.nuevas} nuevas (acum)")
                self.conn.commit()
        
        self.conn.commit()
        return self.encontradas, self.nuevas, self.errores


class ScraperDatosAbiertos:
    """Scraper usando CSV de datos abiertos ChileCompra."""
    
    # URLs de datasets disponibles (ordenes de compra)
    DATASETS = [
        "https://s3.amazonaws.com/datos-abiertos-chilecompra/OrdenesDeCompra/OC_{year}.csv.gz",
        "https://s3.amazonaws.com/datos-abiertos-chilecompra/Licitaciones/Licitaciones_{year}.csv.gz",
    ]
    
    def __init__(self, conn):
        self.conn = conn
        self.nuevas = 0
        self.encontradas = 0
        self.errores = 0
    
    def detectar_relevancia(self, row):
        """Determina si una licitación es relevante para aseo industrial o ISO."""
        texto = " ".join([
            str(row.get("nombre", "")),
            str(row.get("descripcion", "")),
            str(row.get("categoria", row.get("Categoria", ""))),
        ]).lower()
        
        # Siempre detectar normas
        normas = detectar_normas(texto)
        palabras = detectar_palabras_clave(texto)
        
        # Si no tiene match, no es relevante
        if not normas and not palabras:
            return None, None
        
        return normas, palabras
    
    def procesar_fila(self, row):
        """Procesa una fila del CSV."""
        normas, palabras = self.detectar_relevancia(row)
        if normas is None:
            return
        
        codigo = safe_str(row.get("codigo", row.get("Codigo", "")))
        if not codigo:
            return
        
        try:
            self.conn.execute("""
                INSERT OR IGNORE INTO licitaciones
                (codigo, nombre, organismo, estado,
                 fecha_publicacion, fecha_cierre, tipo,
                 monto_estimado, categoria, descripcion,
                 region, comuna, norma, palabras_clave, fuente)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                codigo,
                safe_str(row.get("nombre", row.get("Nombre", "")), 300),
                safe_str(row.get("organismo", row.get("Organismo", "")), 200),
                safe_str(row.get("estado", row.get("Estado", "")), 50),
                safe_str(row.get("fechaPublicacion", row.get("FechaPublicacion", "")), 20),
                safe_str(row.get("fechaCierre", row.get("FechaCierre", "")), 20),
                safe_str(row.get("tipo", row.get("Tipo", "")), 50),
                safe_float(row.get("monto", row.get("Monto", 0))),
                safe_str(row.get("categoria", row.get("Categoria", "")), 100),
                safe_str(row.get("descripcion", row.get("Descripcion", "")), 1000),
                safe_str(row.get("region", row.get("Region", "")), 50),
                safe_str(row.get("comuna", row.get("Comuna", "")), 50),
                normas,
                palabras,
                "datos_abiertos"
            ))
            if self.conn.total_changes > 0:
                self.nuevas += 1
            self.encontradas += 1
        except Exception as e:
            self.errores += 1
    
    def descargar_procesar(self, year, verbose=True):
        """Descarga y procesa un año de datos abiertos."""
        for url_template in self.DATASETS:
            url = url_template.format(year=year)
            if verbose: log(f"📥 Descargando {url}...")
            
            try:
                resp = requests.get(url, timeout=300, stream=True)
                if resp.status_code != 200:
                    if verbose: log(f"  ⚠ No disponible (HTTP {resp.status_code})")
                    continue
                
                # Descomprimir y leer CSV
                gz_file = gzip.GzipFile(fileobj=io.BytesIO(resp.content))
                content = gz_file.read().decode("utf-8", errors="replace")
                
                reader = csv.DictReader(io.StringIO(content))
                count = 0
                for row in reader:
                    self.procesar_fila(row)
                    count += 1
                    if count % 10000 == 0:
                        if verbose:
                            print(f"\r  Procesadas {count:,} filas... ({self.nuevas} nuevas)", end="")
                        self.conn.commit()
                
                if verbose: print(f"\r  ✓ {count:,} filas procesadas, {self.nuevas} nuevas")
                self.conn.commit()
                
            except Exception as e:
                if verbose: log(f"  ✗ Error: {e}")
                self.errores += 1
    
    def run(self, years=None, verbose=True):
        """Ejecuta scraper de datos abiertos."""
        if years is None:
            current = datetime.now().year
            years = [current, current - 1]  # último 2 años
        
        for year in years:
            self.descargar_procesar(year, verbose)
        
        self.conn.commit()
        return self.encontradas, self.nuevas, self.errores


# ─── Main ────────────────────────────────────────────────────────────
def mostrar_stats(conn):
    """Muestra estadísticas de la base de datos."""
    print("\n" + "="*60)
    print("📊 ESTADÍSTICAS DE BASE DE DATOS")
    print("="*60)
    
    c = conn.execute("SELECT COUNT(*) FROM licitaciones")
    total = c.fetchone()[0]
    print(f"\nTotal licitaciones: {total:,}")
    
    if total == 0:
        return
    
    c = conn.execute("SELECT norma, COUNT(*) FROM licitaciones WHERE norma != '' GROUP BY norma ORDER BY COUNT(*) DESC")
    print(f"\nPor norma ISO:")
    for norma, cnt in c:
        print(f"  ISO {norma}: {cnt} licitaciones")
    
    c = conn.execute("SELECT COUNT(*) FROM licitaciones WHERE norma != ''")
    print(f"\nTotal ISO-relevantes: {c.fetchone()[0]:,}")
    
    c = conn.execute("SELECT monto_estimado, COUNT(*) FROM licitaciones WHERE monto_estimado > 0 GROUP BY monto_estimado ORDER BY COUNT(*) DESC LIMIT 1")
    top_count = c.fetchone()
    
    c = conn.execute("SELECT nombre, monto_estimado, organismo FROM licitaciones WHERE monto_estimado > 0 ORDER BY monto_estimado DESC LIMIT 5")
    print(f"\nTop 5 por monto:")
    for r in c:
        print(f"  ${r[1]:,.0f} | {r[2][:40] if r[2] else 'N/A'} | {r[0][:60]}")
    
    c = conn.execute("SELECT fuente, COUNT(*) FROM licitaciones GROUP BY fuente")
    print(f"\nPor fuente:")
    for f, cnt in c:
        print(f"  {f}: {cnt}")
    
    c = conn.execute("SELECT fecha_publicacion, COUNT(*) FROM licitaciones WHERE fecha_publicacion != '' GROUP BY fecha_publicacion ORDER BY fecha_publicacion DESC LIMIT 5")
    print(f"\nÚltimas fechas:")
    for f, cnt in c:
        print(f"  {f}: {cnt} licitaciones")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="ChileCompra ISO Scanner")
    parser.add_argument("--source", choices=["api", "datos_abiertos", "all"], default="api",
                        help="Fuente de datos (default: api)")
    parser.add_argument("--days", type=int, default=1,
                        help="Días hacia atrás (solo API, default: 1)")
    parser.add_argument("--years", type=int, nargs="+",
                        help="Años para datos abiertos (default: último 2)")
    parser.add_argument("--stats", action="store_true",
                        help="Solo mostrar estadísticas, no scrapear")
    parser.add_argument("--rapido", action="store_true",
                        help="Modo rápido: solo API, 1 día")
    
    args = parser.parse_args()
    
    conn = setup_db()
    
    if args.stats:
        mostrar_stats(conn)
        conn.close()
        return
    
    if args.rapido:
        args.source = "api"
        args.days = 1
    
    total_enc = 0
    total_nue = 0
    total_err = 0
    
    log(f"🚀 Iniciando ChileCompra ISO Scanner v2")
    log(f"   Fuente: {args.source}")
    
    if args.source in ("api", "all"):
        scraper = ScraperAPI(conn)
        enc, nue, err = scraper.run(dias=args.days)
        total_enc += enc
        total_nue += nue
        total_err += err
        log(f"📊 API: {enc} encontradas, {nue} nuevas, {err} errores")
    
    if args.source in ("datos_abiertos", "all"):
        scraper = ScraperDatosAbiertos(conn)
        enc, nue, err = scraper.run(years=args.years)
        total_enc += enc
        total_nue += nue
        total_err += err
        log(f"📊 Datos Abiertos: {enc} encontradas, {nue} nuevas, {err} errores")
    
    # Guardar log de la ejecución
    conn.execute("""
        INSERT INTO scraping_log (fecha, fuente, encontradas, nuevas, errores, detalle)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d"),
        args.source,
        total_enc,
        total_nue,
        total_err,
        f"dias={args.days}, years={args.years}"
    ))
    conn.commit()
    
    log(f"\n{'='*50}")
    log(f"📊 RESUMEN: {total_enc} encontradas | {total_nue} nuevas | {total_err} errores")
    log(f"{'='*50}")
    
    mostrar_stats(conn)
    conn.close()

if __name__ == "__main__":
    main()
