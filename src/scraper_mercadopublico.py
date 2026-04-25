#!/usr/bin/env python3
"""
Scraper de Mercado Público - Buscador de licitaciones
Molty / CMS Consultores
"""

import requests
import json
import re
import sys
import os
import time
from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path

# Config
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / data
DATA_DIR.mkdir(exist_ok=True)

# Headers para simular navegador
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'es-CL,es;q=0.9,en;q=0.8',
}

# Palabras clave ISO
ISO_KEYWORDS = [
    'iso 9001', 'iso 14001', 'iso 45001', 'norma iso', 'certificacion',
    'sistema de gestion de calidad', 'sistema de gestion ambiental',
    'sistema de gestion de seguridad', 'sgc', 'sga', 'sst',
    'gestion de calidad', 'gestion ambiental', 'seguridad y salud',
    'norma chilena', 'acreditacion', 'certificado'
]

# Rubros
RUBROS = {
    'aseo': ['aseo', 'limpie', 'jardine', 'saneamiento', 'higiene',
             'desratizac', 'desinfecc', 'fumigac', 'residuos', 'sanitizac'],
    'construccion': ['obra', 'construcc', 'reparacion', 'mantencion',
                     'paviment', 'edificio', 'infraestructura'],
    'seguridad': ['seguridad', 'vigilancia', 'guardia', 'cctv', 'camaras'],
}


def search_mercadopublico(query, max_pages=3):
    """Busca licitaciones en mercadopublico.cl"""
    resultados = []
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # URL de búsqueda del portal público
    for page in range(1, max_pages + 1):
        try:
            url = f'https://www.mercadopublico.cl/Home/ResultadosBusqueda'
            params = {
                'texto': query,
                'pagina': page,
                'tipoFiltro': '3',
                'orden': '0'
            }
            
            # Intentamos GET primero (el portal a veces carga diferente)
            resp = session.get(url, params=params, timeout=30)
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                items = soup.find_all('div', class_=re.compile('licitacion|resultado|item', re.I))
                
                if not items:
                    # Buscar en tablas
                    tables = soup.find_all('table')
                    for table in tables:
                        rows = table.find_all('tr')
                        for row in rows:
                            cells = row.find_all('td')
                            if cells:
                                resultados.append({
                                    'html': str(row)[:500],
                                    'fuente': 'tabla'
                                })
                
                for item in items:
                    text = item.get_text(' ', strip=True)
                    resultados.append({
                        'texto': text[:500],
                        'html': str(item)[:300],
                        'pagina': page
                    })
            
            time.sleep(1)  # Delay para no saturar
            
        except Exception as e:
            print(f'Error pagina {page}: {e}')
    
    return resultados


def check_iso_mentions(text):
    """Revisa si un texto menciona palabras clave ISO"""
    text_lower = text.lower()
    encontradas = []
    for kw in ISO_KEYWORDS:
        if kw in text_lower:
            encontradas.append(kw)
    return encontradas


def check_rubro(text):
    """Revisa a qué rubro pertenece un texto"""
    text_lower = text.lower()
    for rubro, palabras in RUBROS.items():
        for palabra in palabras:
            if palabra in text_lower:
                return rubro
    return None


def buscar_empresa(nombre_empresa, rubro=None):
    """Busca licitaciones de una empresa específica"""
    print(f'\n{"="*60}')
    print(f'  BUSCANDO: {nombre_empresa}')
    print(f'  Fecha: {datetime.now().strftime("%d-%m-%Y %H:%M")}')
    print(f'{"="*60}')
    
    # Búsquedas
    queries = [nombre_empresa]
    if rubro and rubro in RUBROS:
        queries.append(f'{nombre_empresa} {rubro}')
    
    todos_resultados = []
    for q in queries:
        print(f'\nBuscando: "{q}"...')
        resultados = search_mercadopublico(q)
        print(f'  Resultados encontrados: {len(resultados)}')
        todos_resultados.extend(resultados)
        
        # Analizar menciones ISO
        iso_count = 0
        for r in resultados:
            text = r.get('texto', '')
            if text:
                menciones = check_iso_mentions(text)
                if menciones:
                    iso_count += 1
                    r['menciones_iso'] = menciones
                    print(f'  * ISO detectado: {menciones[0]}')
    
    # Resumen
    print(f'\n--- RESUMEN ---')
    print(f'  Total resultados: {len(todos_resultados)}')
    iso_items = [r for r in todos_resultados if r.get('menciones_iso')]
    print(f'  Con menciones ISO: {len(iso_items)}')
    
    if iso_items:
        print(f'\n  OPORTUNIDADES ISO DETECTADAS:')
        for item in iso_items[:10]:
            print(f'    - {item["texto"][:100]}...')
    
    # Guardar resultados
    output_file = DATA_DIR / f'busqueda_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'empresa': nombre_empresa,
            'fecha': datetime.now().isoformat(),
            'total_resultados': len(todos_resultados),
            'iso_detectados': len(iso_items),
            'resultados': todos_resultados
        }, f, ensure_ascii=False, indent=2)
    print(f'\nResultados guardados en: {output_file}')
    
    return todos_resultados


def analizar_mercado(rubro='aseo'):
    """Análisis general del mercado por rubro"""
    print(f'\n{"="*60}')
    print(f'  ANALISIS DE MERCADO: {rubro.upper()}')
    print(f'  Fecha: {datetime.now().strftime("%d-%m-%Y %H:%M")}')
    print(f'{"="*60}')
    
    todas_licitaciones = []
    keywords = RUBROS.get(rubro, [rubro])
    
    for kw in keywords[:3]:  # Limitar a 3 palabras clave
        print(f'\nBuscando: "{kw}"...')
        resultados = search_mercadopublico(kw, max_pages=1)
        print(f'  {len(resultados)} resultados')
        for r in resultados:
            text = r.get('texto', '')
            if text:
                menciones = check_iso_mentions(text)
                if menciones:
                    r['menciones_iso'] = menciones
        todas_licitaciones.extend(resultados)
        time.sleep(1)
    
    # Estadísticas
    total = len(todas_licitaciones)
    con_iso = len([r for r in todas_licitaciones if r.get('menciones_iso')])
    
    print(f'\n--- ESTADISTICAS ---')
    print(f'  Rubro: {rubro}')
    print(f'  Total licitaciones: {total}')
    print(f'  Con menciones ISO: {con_iso}')
    if total > 0:
        print(f'  Porcentaje ISO: {con_iso/total*100:.1f}%')
    
    # Guardar
    output = DATA_DIR / f'analisis_{rubro}_{datetime.now().strftime("%Y%m%d")}.json'
    with open(output, 'w') as f:
        json.dump({
            'rubro': rubro,
            'fecha': datetime.now().isoformat(),
            'total': total,
            'con_iso': con_iso,
            'licitaciones': todas_licitaciones[:50]
        }, f, ensure_ascii=False, indent=2)
    print(f'\nAnalisis guardado: {output}')
    
    return todas_licitaciones


if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'empresa':
            nombre = sys.argv[2] if len(sys.argv) > 2 else 'Magochic'
            rubro = sys.argv[3] if len(sys.argv) > 3 else None
            buscar_empresa(nombre, rubro)
        elif cmd == 'analisis':
            rubro = sys.argv[2] if len(sys.argv) > 2 else 'aseo'
            analizar_mercado(rubro)
        elif cmd == 'test':
            resultados = search_mercadopublico('Magochic', max_pages=1)
            for r in resultados:
                print(json.dumps(r, ensure_ascii=False)[:200])
                print('---')
        else:
            print('Comandos: empresa, analisis, test')
    else:
        print('Scraper Mercado Publico')
        print('Uso:')
        print('  python3 src/scraper_mercadopublico.py empresa "Mago Chic" aseo')
        print('  python3 src/scraper_mercadopublico.py analisis aseo')
        print('  python3 src/scraper_mercadopublico.py test')
