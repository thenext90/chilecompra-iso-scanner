#!/usr/bin/env python3
"""Replace scrap_mercadopublico function and remove BeautifulSoup import"""
with open('/home/alwyzon/chilecompra-iso-scanner/app.py') as f:
    lines = f.readlines()

# Remove BeautifulSoup import
lines = [l for l in lines if 'from bs4 import BeautifulSoup' not in l]

# Find function boundaries
func_start = None
func_end = None
for i, line in enumerate(lines):
    if line.strip().startswith('def scrap_mercadopublico'):
        func_start = i
    if func_start is not None and func_end is None:
        # Stop at next def, @app, # section, or if __name__
        if i > func_start and (line.strip().startswith('def ') or 
                               line.strip().startswith('@app.') or
                               line.strip().startswith('# ---') or
                               line.strip().startswith('if __name__')):
            func_end = i
            break

if func_start is None:
    print("ERROR: scrap_mercadopublico not found")
    exit(1)
if func_end is None:
    func_end = len(lines)

new_func = '''def scrap_mercadopublico(modo="rapido", conn=None):
    """Scrape licitaciones usando API oficial de Mercado P\\u00fablico"""
    TICKET = "F8537A18-6766-4DEF-9E59-426B4FEE2844"
    BASE = "https://api.mercadopublico.cl/servicios/v1/publico"
    DIAS = {"rapido": 3, "completo": 14}
    dias = DIAS.get(modo, 7)
    
    if conn is None:
        conn = get_db()
    
    import requests, time
    from datetime import datetime, timedelta
    
    keywords = [
        "aseo", "limpieza", "sanitizacion", "desinfeccion", "saneamiento",
        "jardineria", "mantencion", "mantenimiento", "servicio",
        "gestion", "calidad", "seguridad", "medio ambiente",
        "consulta", "asesoria", "auditoria", "certificacion", "norma",
        "iso", "higiene", "industrial", "faena", "operacion",
        "residuos", "reciclaje", "limpieza", "aseo industrial",
        "aseo integral", "servicios generales", "limpieza industrial"
    ]
    
    hoy = datetime.now()
    nuevas = 0
    total_dia = 0
    
    for i in range(dias):
        dia = hoy - timedelta(days=i)
        fecha_str = dia.strftime("%d%m%Y")
        url = f"{BASE}/licitaciones.json?fecha={fecha_str}&pagina=1&ticket={TICKET}"
        
        try:
            resp = requests.get(url, timeout=20)
            data = resp.json()
            if data.get("Codigo") != 200:
                continue
        except:
            continue
        
        listado = data.get("Listado", [])
        if not listado:
            continue
        
        for lic in listado:
            codigo_externo = lic.get("CodigoExterno", "")
            nombre = lic.get("Nombre", "")
            cod_estado = lic.get("CodigoEstado", 0)
            fecha_cierre = lic.get("FechaCierre", "")
            
            nombre_lower = nombre.lower()
            
            # Estado mapping
            estado_map = {5: "Publicada", 6: "Cerrada", 7: "Adjudicada", 8: "Desierta"}
            estado = estado_map.get(cod_estado, f"Estado_{cod_estado}")
            
            # Detectar norma ISO potencial
            iso_detect = ""
            if "seguridad" in nombre_lower:
                iso_detect = "ISO 45001"
            elif "calidad" in nombre_lower and "gestion" in nombre_lower:
                iso_detect = "ISO 9001"
            elif "medio ambiente" in nombre_lower or "ambiental" in nombre_lower:
                iso_detect = "ISO 14001"
            elif "iso" in nombre_lower:
                iso_detect = "ISO"
            
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO licitaciones (codigo, nombre, estado, fecha, organismo, norma, monto) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (codigo_externo, nombre[:200], estado, dia.strftime("%Y-%m-%d"), "", iso_detect, 0.0)
                )
                nuevas += 1
            except:
                pass
        
        total_dia += len(listado)
        time.sleep(0.3)
    
    conn.commit()
    return nuevas

'''

new_lines = lines[:func_start] + [new_func] + lines[func_end:]
with open('/home/alwyzon/chilecompra-iso-scanner/app.py', 'w') as f:
    f.writelines(new_lines)

print(f"OK - Replaced function (lines {func_start+1}-{func_end} -> {len(new_func.split(chr(10)))-1} lines)")
print(f"Total lines: {len(new_lines)}")
