#!/usr/bin/env python3
"""scraping_montos.py — Scraper de detalle para licitaciones de ASEO"""
import os, json, time, requests, re
from datetime import datetime
from collections import Counter

TICKET = os.environ.get("CHILECOMPRA_TICKET", "")
API = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
DIR = "/home/alwyzon/chilecompra-iso-scanner/data"
OUT = f"{DIR}/licitaciones_con_detalle.json"
RAW = f"{DIR}/licitaciones_raw_7dias.json"

# Palabras de aseo (amplias, captan todo el rubro)
ASEO_KW = ["aseo","limpieza","sanitiz","desinfecc","fumigac","desratiz",
    "fosa","fosas","alcantarillad","camion limpia","hidrojet","hidroyet",
    "baño quimico","baños quimicos","control plagas","plagas",
    "higiene ambiental","limpieza de ca","limpieza de f","lavanderia","lavandería"]

ISO_KW = ["iso 9001","iso 14001","iso 45001","certificación de calidad",
    "certificacion de calidad","sistema de gestión de calidad","sgc",
    "sistema de gestion de calidad","norma iso","gestión de calidad",
    "gestion de calidad","seguridad laboral","salud ocupacional","ohsas",
    "sistema de gestión ambiental","certificado vigente","acreditación",
    "acreditacion","sello de calidad"]

def tiene_aseo(nombre):
    n = nombre.lower()
    return any(k in n for k in ASEO_KW)

def obtener_detalle(codigo):
    try:
        r = requests.get(f"{API}?Codigo={codigo}&ticket={TICKET}", timeout=15)
        if r.status_code == 200:
            lista = r.json().get("Listado", [])
            return lista[0] if lista else None
    except: pass
    return None

def detectar_iso(texto):
    if not texto: return []
    t = texto.lower()
    return list(set(k for k in ISO_KW if k in t))

# Cargar raw
with open(RAW) as f:
    raw = json.load(f)

# Agrupar por código único, clasificar tipo
unicas = {}
for lic in raw:
    cod = lic.get("CodigoExterno", "")
    nom = lic.get("Nombre", "")
    if not cod or cod in unicas: continue
    m = re.search(r"-(L[EPR]|L1|CO|I2)", cod)
    tipo = m.group(1) if m else "?"
    unicas[cod] = {"codigo": cod, "nombre": nom, "tipo": tipo}

print(f"Total únicas: {len(unicas)}")
print(f"Tipos: {dict(Counter(v['tipo'] for v in unicas.values()))}")

# Filtrar aseo en el nombre, solo LE+LP
aseo = [v for v in unicas.values() if tiene_aseo(v["nombre"])]
print(f"De aseo (todas): {len(aseo)}")
print(f"De aseo LE+LP: {sum(1 for v in aseo if v['tipo'] in ('LE','LP'))}")

# Procesar todas las de aseo (incluyendo otros tipos para ver montos)
resultados = []
for i, lic in enumerate(aseo):
    codigo = lic["codigo"]
    nombre = lic["nombre"]
    print(f"[{i+1}/{len(aseo)}] {lic['tipo']} {codigo} {nombre[:55]}")

    det = obtener_detalle(codigo)
    if not det:
        print(f"  ∅")
        continue

    comprador = det.get("Comprador", {})
    items = (det.get("Items", {}) or {}).get("Listado", []) or []
    fechas = det.get("Fechas", {})
    prohib = det.get("ProhibicionContratacion", "")

    textos = nombre + " " + prohib
    categorias = []
    prods = []
    for item in items:
        cat = item.get("Categoria", "")
        if cat: categorias.append(cat)
        textos += " " + item.get("Descripcion","") + " " + item.get("NombreProducto","")
        prods.append({"nombre": item.get("NombreProducto",""), "descripcion": item.get("Descripcion",""), "categoria": cat})
    categorias = list(set(categorias))
    iso = detectar_iso(textos)

    resultados.append({
        "codigo": codigo, "nombre": nombre, "tipo": lic["tipo"],
        "url": f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?Codigo={codigo}",
        "organismo": comprador.get("NombreOrganismo",""),
        "unidad": comprador.get("NombreUnidad",""),
        "region": comprador.get("RegionUnidad",""),
        "comuna": comprador.get("ComunaUnidad",""),
        "moneda": det.get("Moneda",""),
        "monto": det.get("MontoEstimado",None),
        "monto_visible": det.get("VisibilidadMonto",0),
        "estado": det.get("Estado",""),
        "fecha_cierre": fechas.get("FechaCierre",""),
        "categorias": categorias, "n_productos": len(prods),
        "productos": prods, "tiene_iso": len(iso)>0, "iso_detectado": iso,
    })
    if iso: print(f"  ISO: {iso}")
    time.sleep(0.2)

con_monto = [r for r in resultados if r["monto"] is not None and r["monto_visible"] == 1]
out = {"fecha": datetime.now().isoformat(), "total": len(resultados),
    "con_monto_visible": len(con_monto), "sin_monto": sum(1 for r in resultados if r["monto"] is None or r["monto_visible"] == 0),
    "con_iso": sum(1 for r in resultados if r["tiene_iso"]),
    "licitaciones": resultados}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n✅ {len(resultados)} | monto visible: {len(con_monto)} | ISO: {out['con_iso']} → {OUT}")
