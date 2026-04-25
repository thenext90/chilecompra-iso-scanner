#!/usr/bin/env python3
"""Replace scrap_mercadopublico with API version"""
import re

with open('/home/alwyzon/chilecompra-iso-scanner/app.py') as f:
    content = f.read()

# Find the old function
old_start = content.find("def scrap_mercadopublico")
if old_start < 0:
    print("ERROR: function not found")
    exit(1)

rest = content[old_start:]
# Find where it ends: next def, @, or section header
end_match = re.search(r'\n(?=def |@|\n# ─── )', rest)
if end_match:
    old_func = rest[:end_match.start()]
else:
    old_func = rest

print(f"Old function: {len(old_func)} chars")

# New function using API
new_func = '''def scrap_mercadopublico():
    """Scrape licitaciones from Mercado Público API v1"""
    API_TICKET = "F8537A18-6766-4DEF-9E59-426B4FEE2844"
    API_BASE = "https://api.mercadopublico.cl/servicios/v1/publico"
    DIAS_ATRAS = 7  # Cuantos días mirar hacia atrás
    conn = get_db()
    total_guardadas = 0

    # Palabras clave para detectar licitaciones de interés ISO
    keywords = [
        "aseo", "limpieza", "sanitizacion", "desinfeccion", "saneamiento",
        "jardineria", "mantencion", "mantenimiento", "servicio",
        "gestión", "gestion", "calidad", "seguridad", "medio ambiente",
        "consulta", "asesoria", "auditoria", "certificacion", "norma",
        "iso", "higiene", "industrial", "faena", "operacion"
    ]

    from datetime import datetime, timedelta
    import requests
    import json

    hoy = datetime.now()
    for i in range(DIAS_ATRAS):
        dia = hoy - timedelta(days=i)
        fecha_str = dia.strftime("%d%m%Y")
        url = f"{API_BASE}/licitaciones.json?fecha={fecha_str}&pagina=1&ticket={API_TICKET}"
        
        try:
            r = requests.get(url, timeout=15)
            data = r.json()
            if data.get("Codigo") != 200:
                print(f"  [{fecha_str}] API error: {data.get('Mensaje','unknown')}")
                continue
        except Exception as e:
            print(f"  [{fecha_str}] Error: {e}")
            continue

        listado = data.get("Listado", [])
        if not listado:
            print(f"  [{fecha_str}] Sin datos")
            continue

        guardadas = 0
        for lic in listado:
            codigo = lic.get("CodigoExterno", "")
            nombre = lic.get("Nombre", "")
            estado = lic.get("CodigoEstado", 0)
            cierre = lic.get("FechaCierre", "")

            # Verificar si alguna keyword está en el nombre
            nombre_lower = nombre.lower()
            palabra_clave = ""
            for kw in keywords:
                if kw in nombre_lower:
                    palabra_clave = kw
                    break

            # Determinar estado texto
            estado_map = {5: "Publicada", 6: "Cerrada", 7: "Adjudicada", 8: "Desierta", 15: "Suspendida"}
            estado_txt = estado_map.get(estado, f"Estado_{estado}")
            estado_simple = estado_txt
            
            # Determinar si es abierta
            es_abierta = estado == 5

            # Guardar todas las licitaciones (con filtro opcional después)
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO licitaciones 
                    (codigo, nombre, estado, fecha_publicacion, fecha_cierre, 
                     organismo, norma, monto, es_abierta, palabra_clave)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (codigo, nombre[:200], estado_simple, dia.strftime("%Y-%m-%d"),
                     cierre[:19] if cierre else "",
                     "",  # organismo - no disponible en listado
                     "",  # norma - se asigna después
                     0.0,  # monto - no disponible en listado
                     1 if es_abierta else 0,
                     palabra_clave)
                )
                guardadas += 1
                total_guardadas += 1
            except Exception as e:
                pass

        conn.commit()
        print(f"  [{fecha_str}] {len(listado)} items, {guardadas} guardadas")
        
        # Pequeña pausa para no saturar
        import time
        time.sleep(0.5)

    # Registrar en log
    try:
        from datetime import datetime as dt
        conn.execute(
            "INSERT INTO scraping_log (fecha, total_guardadas) VALUES (?, ?)",
            (dt.now().isoformat()[:19], total_guardadas)
        )
        conn.commit()
    except Exception:
        pass

    return f"API scrape completado. {total_guardadas} licitaciones guardadas en {DIAS_ATRAS} dias."
'''

content = content.replace(old_func, new_func)
with open('/home/alwyzon/chilecompra-iso-scanner/app.py', 'w') as f:
    f.write(content)

print("OK - Function replaced")
print(f"New function: {len(new_func)} chars")
