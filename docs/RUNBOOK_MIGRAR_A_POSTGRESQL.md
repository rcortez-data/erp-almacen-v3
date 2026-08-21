# Runbook - prueba controlada de migracion a PostgreSQL

Fecha: 2026-08-06

Este documento es la receta para migrar en laboratorio. No usar directo sobre
el ERP real sin respaldo y sin haber probado primero.

## 1. Preparar respaldo

Ejecutar:

```bat
python scripts\backup_sqlite.py
```

Resultado esperado:

- Se crea una copia en `backups_db`.

## 2. Revisar salud de SQLite

Ejecutar:

```bat
python scripts\db_preflight.py
```

Resultado ideal:

- `Integridad SQLite: ok`
- Sin duplicados criticos.
- Sin problemas de llaves foraneas.

Si aparecen fechas vacias, no siempre bloquean la migracion, pero hay que
decidir si se corrigen o si se migran como `NULL`.

## 3. Exportar datos

Ejecutar:

```bat
python scripts\export_sqlite_csv.py
```

Resultado esperado:

- Carpeta nueva en `exports\sqlite_export_FECHA_HORA`.
- Un CSV por tabla.
- `manifest.json` con conteo de filas por tabla.

## 4. Crear schema PostgreSQL de prueba

En una base PostgreSQL vacia de laboratorio:

```sql
\i migrations/postgres_schema_v1.sql
```

Tambien se puede ejecutar desde una herramienta grafica como pgAdmin.

## 5. Cargar datos

Orden recomendado de carga:

1. `usuarios`
2. `categorias`
3. `proveedores`
4. `productos`
5. `montacargas`
6. `areas`
7. `folios`
8. `folios_diarios`
9. `requisiciones`
10. `requisicion_items`
11. `requisicion_item_recepciones`
12. `entradas`
13. `salidas`
14. `vales_montacargas`
15. `conteos_fisicos`
16. `bloques_balance`
17. `bloque_productos`
18. `actividad`

## 6. Comparar conteos

Comparar `manifest.json` contra:

```sql
SELECT COUNT(*) FROM nombre_tabla;
```

La migracion no se considera valida hasta que los conteos coincidan.

## 7. Probar pantallas criticas

Con la base migrada en laboratorio, probar:

- Login
- Dashboard
- Inventario
- Nueva entrada
- Nueva salida
- Requisiciones
- Reportes
- Balance
- Impresiones criticas

## 8. Pendientes antes de operar con PostgreSQL real

El codigo todavia contiene SQL especifico de SQLite:

- Placeholders `?`
- `INSERT OR IGNORE`
- `PRAGMA`
- `sqlite_master`
- `DATE('now')`, `DATE(fecha)`, `strftime`
- `lastrowid`

Antes de usar PostgreSQL como motor activo, hay que terminar una capa de datos
que traduzca estas diferencias o migrar gradualmente las consultas.

## Recomendacion de despliegue futuro

Para empresa conectada, mi recomendacion inicial es:

- Servidor local dedicado en la empresa.
- PostgreSQL instalado en ese servidor.
- ERP accesible por red interna.
- Respaldos automaticos diarios.
- Despues evaluar acceso online/VPN si hace falta desde celular o fuera de planta.
