#!/usr/bin/env python3
"""
Procesa y estructura los datos de licitaciones de aseo industrial.
- Lee raw data de la API
- Obtiene detalles de cada licitación (monto, descripción, organismo)
- Detecta menciones ISO
- Guarda JSON estructurado
"""

import requests
import json
import re
import time
from datetime import datetime

TICKET = "CD89C6AC-C570-4BE6-BF0F-B25C35393FAB"
API_BASE = "https://api.mercadopublico.cl/servicios/v1/publico"
RAW_FILE = "licitaciones_raw_7dias.json"
OUTPUT_FILE = "licitaciones_aseo_estructurado.json"

PALABRAS_ISO = [
    "iso 9001", "iso9001", "certificación iso 9001",
    "iso 14001", "iso14001", "certificación iso 14001",
    "iso 45001", "iso45001", "certificación iso 45001",
    "norma iso", "certificación de calidad", "certificacion de calidad",
    "sistema de gestión", "gestión de calidad", "gestion de calidad",
    "sgc", "sga", "sst", "ohsas",
    "acreditación", "acreditacion",
    "certificado de calidad", "certificado calidad",
    "seguridad laboral", "salud ocupacional",
    "exigencia de certificación",
    "norma técnica", "norma tecnica",
    "control de calidad",
]

def extraer_tipo(codigo):
    """Extrae tipo de licitación del código"""
    codigo = codigo.upper()
    if "-LE" in codigo or codigo.endswith("LE"):
        return "LE"
    elif "-LP" in codigo or codigo.endswith("LP"):
        return "LP"
    elif "-LR" in codigo or codigo.endswith("LR"):
        return "LR"
    elif "-L1" in codigo or codigo.endswith("L1"):
        return "L1"
    elif "-CO" in codigo or codigo.endswith("CO"):
        return "CO"
    elif "-I2" in codigo or codigo.endswith("I2"):
        return "I2"
    elif "-B2" in codigo or codigo.endswith("B2"):
        return "B2"
    elif "-O1" in codigo:
        return "O1"
    elif "-O2" in codigo:
        return "O2"
    elif "-O3" in codigo:
        return "O3"
    else:
        # Buscar patrón
        m = re.search(r'-(L[EPR]|L1|CO|I2|B2|O[123])', codigo)
        return m.group(1) if m else ""

def detectar_iso(nombre, descripcion=""):
    """Detecta menciones ISO en nombre y descripción"""
    texto = (nombre + " " + descripcion).lower()
    encontradas = []
    for kw in PALABRAS_ISO:
        if kw in texto:
            encontradas.append(kw)
    return list(set(encontradas))

def obtener_detalle(codigo_externo):
    """Obtiene detalle de una licitación por su código externo"""
    url = f"{API_BASE}/licitacion.json?codigo={codigo_externo}&ticket={TICKET}"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            lic = data.get("Listado", [{}])[0] if isinstance(data.get("Listado"), list) else data
            
            # Extraer monto
            monto = 0
            for campo in ["Monto", "MontoEstimado", "MontoTotal", "Presupuesto"]:
                val = lic.get(campo, 0)
                if val:
                    try:
                        monto = int(float(str(val).replace(".", "")))
                        break
                    except:
                        pass
            
            # Si viene como dict con items
            if not monto:
                items = lic.get("Items", [])
                if items:
                    for item in items:
                        try:
                            monto += int(float(str(item.get("MontoTotal", 0) or "0").replace(".", "")))
                        except:
                            pass
            
            return {
                "organismo": lic.get("Organismo", lic.get("OrganismoPublico", "")),
                "monto": monto,
                "descripcion": lic.get("Descripcion", ""),
                "estado": lic.get("Estado", lic.get("CodigoEstado", "")),
                "fecha_cierre": lic.get("FechaCierre", ""),
                "fecha_publicacion": lic.get("FechaPublicacion", ""),
                "nombre_completo": lic.get("Nombre", ""),
            }
    except Exception as e:
        pass
    return {"organismo": "", "monto": 0, "descripcion": "", "estado": "", "fecha_cierre": "", "fecha_publicacion": "", "nombre_completo": ""}

def extraer_codigo_externo(codigo):
    """Extrae código externo del formato CodigoExterno"""
    # Algunos códigos vienen como "3794-60-LE26"
    return codigo

def run():
    print("=" * 65)
    print("  PROCESANDO LICITACIONES DE ASEO INDUSTRIAL")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 65)
    
    # Cargar datos raw
    with open(RAW_FILE, "r") as f:
        raw_data = json.load(f)
    
    print(f"\nDatos raw cargados: {len(raw_data)} registros")
    
    # Filtrar solo aseo/limpieza
    terminos_aseo = ["aseo", "limpie", "sanitiz", "desinfecc", "higiene", 
                     "fosa", "baño quimico", "baños quimicos"]
    
    lic_aseo = []
    for r in raw_data:
        nombre = r.get("Nombre", "").lower()
        if any(t in nombre for t in terminos_aseo):
            lic_aseo.append(r)
    
    print(f"Filtradas (aseo/limpieza): {len(lic_aseo)}")
    
    # Obtener detalles de cada una (con límite para no saturar)
    detalladas = []
    MAX_DETALLES = 50  # Límite para no hacer 268 requests
    
    print("\n→ Obteniendo detalles (monto, descripción, organismo)...")
    
    for i, lic in enumerate(lic_aseo[:MAX_DETALLES]):
        codigo = lic.get("CodigoExterno", "")
        if not codigo:
            continue
        
        detalle = obtener_detalle(codigo)
        time.sleep(0.3)  # respeto al servidor
        
        nombre = detalle.get("nombre_completo") or lic.get("Nombre", "")
        desc = detalle.get("descripcion", "")
        iso = detectar_iso(nombre, desc)
        tipo = extraer_tipo(codigo)
        
        entry = {
            "codigo": codigo,
            "nombre": nombre,
            "tipo": tipo,
            "organismo": detalle["organismo"],
            "monto": detalle["monto"],
            "estado": detalle["estado"],
            "fecha_publicacion": detalle["fecha_publicacion"],
            "fecha_cierre": detalle["fecha_cierre"],
            "descripcion": desc[:300] if desc else "",
            "coincidencias_iso": iso,
            "tiene_iso": len(iso) > 0,
            "url": f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?Codigo={codigo}",
        }
        detalladas.append(entry)
        
        if (i+1) % 10 == 0:
            print(f"  Procesadas {i+1}/{min(len(lic_aseo), MAX_DETALLES)}...")
    
    # Clasificar
    con_iso = [d for d in detalladas if d["tiene_iso"]]
    sin_iso = [d for d in detalladas if not d["tiene_iso"]]
    
    # Contar por tipo
    tipos = {}
    for d in detalladas:
        t = d["tipo"] or "Sin tipo"
        tipos[t] = tipos.get(t, 0) + 1
    
    # Monto total
    monto_total = sum(d["monto"] for d in detalladas if d["monto"])
    
    output = {
        "fecha_generacion": datetime.now().isoformat(),
        "fuente": "API Mercado Público (v1) - últimos 7 días",
        "total_encontradas": len(lic_aseo),
        "total_con_detalle": len(detalladas),
        "con_requisitos_iso": len(con_iso),
        "sin_requisitos_iso": len(sin_iso),
        "monto_total_detectado": monto_total,
        "resumen_por_tipo": tipos,
        "licitaciones": detalladas,
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # Mostrar resumen
    print("\n" + "=" * 65)
    print("  📊 RESUMEN FINAL")
    print("=" * 65)
    print(f"  Total licitaciones de aseo encontradas (7 días): {len(lic_aseo)}")
    print(f"  Con detalle obtenido: {len(detalladas)}")
    print(f"  Con requisitos ISO: {len(con_iso)}")
    print(f"  Monto total detectado: ${monto_total:,.0f}")
    print(f"\n  Por tipo:")
    for t, c in sorted(tipos.items()):
        print(f"    {t}: {c}")
    
    if con_iso:
        print(f"\n  🎯 CON REQUISITOS ISO ({len(con_iso)}):")
        print(f"  {'='*60}")
        for r in con_iso:
            m = f"${r['monto']:,.0f}" if r['monto'] else "Sin monto"
            t = r['tipo'] or "?"
            print(f"\n  [{t}] {r['nombre'][:70]}")
            print(f"      Org: {r['organismo'][:45]}")
            print(f"      Monto: {m}")
            print(f"      ISO: {', '.join(r['coincidencias_iso'][:3])}")
    
    print(f"\n  ✅ JSON guardado: {OUTPUT_FILE}")
    print()

if __name__ == "__main__":
    run()
