#!/usr/bin/env python3
"""Rewrite scrap_mercadopublico to use the API and clean up BeautifulSoup imports"""
import re

with open('/home/alwyzon/chilecompra-iso-scanner/app.py') as f:
    content = f.read()

# 1) Remove BeautifulSoup import line
old_import = "from bs4 import BeautifulSoup\n"
if old_import in content:
    content = content.replace(old_import, "")
    print("1) Removed BeautifulSoup import")
else:
    print("1) BeautifulSoup import not found")

# 2) Replace the scrap_mercadopublico function
old_func_pattern = r"def scrap_mercadopublico\(.*?\).*?"
old_start = content.find("def scrap_mercadopublico")
if old_start < 0:
    print("ERROR: scrap_mercadopublico not found")
    exit(1)

# Find end: next def or section header ───
rest = content[old_start:]
end_match = re.search(r'\n(?=def |@app\.route|# ────)', rest)
if end_match:
    old_func_text = rest[:end_match.start()]
else:
    old_func_text = rest  # use rest of file

print(f"2) Old function: {len(old_func_text)} chars, ends at offset {old_start+len(old_func_text)}")

new_func = '''def scrap_mercadopublico(modo="completo", conn=None):
    """Scrape licitaciones using Mercado Publico API v1"""
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
    total_dia = 0  # Track total in range for return
    
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
            
            # Check keywords
            nombre_lower = nombre.lower()
            kw_match = ""
            for kw in keywords:
                if kw in nombre_lower:
                    kw_match = kw
                    break
            
            # Estado mapping
            estado_map = {5: "Publicada", 6: "Cerrada", 7: "Adjudicada", 8: "Desierta"}
            estado = estado_map.get(cod_estado, f"Estado_{cod_estado}")
            
            # Detect potential ISO (seguridad, calidad, medio ambiente)
            iso_detect = ""
            if "seguridad" in nombre_lower:
                iso_detect = "ISO 45001"
            elif "calidad" in nombre_lower and "gestión" in nombre_lower:
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
        time.sleep(0.3)  # Rate limit
    
    conn.commit()
    return nuevas  # Returns count of newly inserted licitaciones
'''

content = content.replace(old_func_text, new_func)
with open('/home/alwyzon/chilecompra-iso-scanner/app.py', 'w') as f:
    f.write(content)

print(f"3) Replaced with new function ({len(new_func)} chars)")
print("Done!")
