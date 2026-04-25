#!/usr/bin/env python3
"""
Runner principal ChileCompra ISO Scanner.
Ejecuta scraping completo (últimos 7 días) y guarda JSON estructurado.
"""

import requests
import json
import re
import time
import os
from datetime import datetime, timedelta

TICKET = "CD89C6AC-C570-4BE6-BF0F-B25C35393FAB"
BASE_URL = "https://api.mercadopublico.cl/servicios/v1/publico"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

RAW_FILE = os.path.join(DATA_DIR, "licitaciones_raw_7dias.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "licitaciones_aseo_estructurado.json")

TERMINOS_ASEO = ["aseo", "limpie", "sanitiz", "desinfecc", "higiene",
                 "fosa", "baño quimico", "baños quimicos", "limpia", "desratiz"]

PALABRAS_ISO = [
    "iso 9001", "iso9001", "certificación iso 9001", "certificación iso 14001",
    "iso 14001", "iso14001", "iso 45001", "iso45001", "certificación iso 45001",
    "norma iso", "certificación de calidad", "certificacion de calidad",
    "sistema de gestión", "sgc", "sga", "sst", "ohsas",
    "acreditación", "acreditacion", "certificado de calidad",
    "seguridad laboral", "salud ocupacional",
    "exigencia de certificación",
]

def run():
    print("=" * 65)
    print("  CHILECOMPRA ISO SCANNER")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 65)

    os.makedirs(DATA_DIR, exist_ok=True)

    # 1. Scrapear últimos 7 días
    hoy = datetime.now()
    resultados = []
    headers = {"User-Agent": "Mozilla/5.0"}

    print("\n📡 Obteniendo licitaciones (últimos 7 días)...")
    for i in range(7):
        dia = hoy - timedelta(days=i)
        fecha = dia.strftime("%d%m%Y")
        for pagina in [1, 2]:
            url = f"{BASE_URL}/licitaciones.json?fecha={fecha}&pagina={pagina}&ticket={TICKET}"
            try:
                r = requests.get(url, headers=headers, timeout=30)
                if r.status_code == 200:
                    data = r.json()
                    lista = data.get("Listado", [])
                    resultados.extend(lista)
                    print(f"  {dia.strftime('%d/%m')} (p{pagina}): {len(lista)} lic.")
            except:
                pass
            time.sleep(0.5)

    print(f"\n  Total crudo: {len(resultados)} licitaciones")

    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    # 2. Filtrar por aseo
    lic_aseo = []
    for r in resultados:
        nombre = r.get("Nombre", "").lower()
        if any(t in nombre for t in TERMINOS_ASEO):
            lic_aseo.append(r)

    print(f"  Aseo/limpieza: {len(lic_aseo)}")

    # 3. Estructurar
    detalladas = []
    for lic in lic_aseo:
        codigo = lic.get("CodigoExterno", "")
        nombre = lic.get("Nombre", "")
        tipo = ""
        if "-LE" in codigo or codigo.endswith("LE"):
            tipo = "LE"
        elif "-LP" in codigo or codigo.endswith("LP"):
            tipo = "LP"
        elif "-LR" in codigo or codigo.endswith("LR"):
            tipo = "LR"
        elif "-L1" in codigo or codigo.endswith("L1"):
            tipo = "L1"
        elif "-CO" in codigo or codigo.endswith("CO"):
            tipo = "CO"
        elif "-I2" in codigo or codigo.endswith("I2"):
            tipo = "I2"
        else:
            m = re.search(r'-(L[EPR]|L1|CO|I2|B2|O[123])', codigo)
            tipo = m.group(1) if m else ""

        # Detectar ISO
        iso = []
        nombre_lower = nombre.lower()
        for kw in PALABRAS_ISO:
            if kw in nombre_lower:
                iso.append(kw)

        detalladas.append({
            "codigo": codigo,
            "nombre": nombre,
            "tipo": tipo,
            "fecha_cierre": lic.get("FechaCierre", ""),
            "codigo_estado": lic.get("CodigoEstado", ""),
            "coincidencias_iso": list(set(iso)),
            "tiene_iso": len(iso) > 0,
            "url": f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?Codigo={codigo}",
        })

    # Clasificar
    con_iso = [d for d in detalladas if d["tiene_iso"]]
    sin_iso = [d for d in detalladas if not d["tiene_iso"]]

    tipos = {}
    for d in detalladas:
        t = d["tipo"] or "Sin tipo"
        tipos[t] = tipos.get(t, 0) + 1

    output = {
        "fecha_generacion": datetime.now().isoformat(),
        "fuente": "API Mercado Público v1 - últimos 7 días",
        "total_encontradas": len(resultados),
        "total_aseo": len(lic_aseo),
        "total_con_iso": len(con_iso),
        "resumen_por_tipo": tipos,
        "licitaciones_aseo": detalladas,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n  📊 RESULTADOS:")
    print(f"     Total licitaciones (7 días): {len(resultados)}")
    print(f"     De aseo/limpieza: {len(lic_aseo)}")
    print(f"     Con posibles requisitos ISO: {len(con_iso)}")
    print(f"     Por tipo: {json.dumps(tipos, ensure_ascii=False)}")
    print(f"\n  ✅ Guardado: {OUTPUT_FILE}")

if __name__ == "__main__":
    run()
