# ChileCompra ISO Scanner

Buscador/scraper de oportunidades ISO en ChileCompra/Mercado Público.

## 🎯 Objetivo

Detectar licitaciones públicas en ChileCompra que requieran certificaciones ISO (9001, 14001, 45001) en los rubros de aseo industrial, limpieza y servicios relacionados.

## 📁 Estructura

```
├── scripts/         # Scripts de scraping y procesamiento
│   └── procesar_aseo.py    # Procesa datos de licitaciones de aseo
├── data/           # Datos estructurados en JSON
│   ├── licitaciones_aseo_estructurado.json  # 306 licitaciones procesadas
│   └── licitaciones_raw_7dias.json          # 9.494 registros crudos
└── README.md
```

## 📊 Últimos resultados (25/04/2026)

- **306 licitaciones** de aseo/limpieza en últimos 7 días
- **36 LE+LP** (licitaciones públicas con posible pago)
- **14 convenios marco** (L1, LR, CO)
- Fuente: API v1 Mercado Público

## 🔄 Actualización automática

El script se ejecuta periódicamente vía cron en la VPS para mantener los datos actualizados.

## 🔑 API Key

Ticket ChileCompra: CD89C6AC-C570-4BE6-BF0F-B25C35393FAB
