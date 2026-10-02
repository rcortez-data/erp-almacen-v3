# ERP Almacen v3 lab - Fase 3: preparacion para migrar base de datos

Fecha: 2026-08-06

## Objetivo

Preparar el sistema para que en el futuro pueda pasar de SQLite a un motor mas robusto, como PostgreSQL, sin romper el ERP v2 real ni detener el uso diario.

En esta fase NO se cambia el motor de base de datos. El lab v3 sigue usando SQLite.

## Cambio aplicado ahora

- `database.py` ya no deja fija la ruta `almacen.db` de forma rigida.
- La base puede apuntar a otra ruta usando la variable:
  - `ERP_DATABASE_PATH`
- Se agrego una variable de motor:
  - `ERP_DB_BACKEND=sqlite`
- Si alguien intenta usar otro motor antes de desarrollar la capa completa, el sistema se detiene con un mensaje claro en vez de fallar a medias.
- `app.py` ahora inicializa la base usando la ruta configurada en `database.py`.
- La app carga `.env` al iniciar para poder manejar configuracion sin tocar codigo.
- Se agregaron herramientas de preparacion:
  - `scripts/db_preflight.py`
  - `scripts/export_sqlite_csv.py`
  - `migrations/postgres_schema_v1.sql`
  - `python scripts\db_preflight.py`
  - `python scripts\export_sqlite_csv.py`
  - `docs/RUNBOOK_MIGRAR_A_POSTGRESQL.md`

## Por que esto ayuda

Antes:

- El sistema siempre buscaba `almacen.db` junto al codigo.
- Era mas dificil levantar ambientes de prueba con otra base.
- Preparar PostgreSQL implicaba tocar muchos puntos a la vez.

Ahora:

- Podemos probar con una copia de base sin tocar la real.
- Podemos separar configuracion de codigo.
- Podemos avanzar hacia una capa de datos compatible con otros motores.

## Inventario de tablas principales detectadas

- `usuarios`
- `actividad`
- `categorias`
- `productos`
- `proveedores`
- `entradas`
- `salidas`
- `montacargas`
- `vales_montacargas`
- `areas`
- `conteos_fisicos`
- `folios`
- `folios_diarios`
- `requisiciones`
- `requisicion_items`
- `requisicion_item_recepciones`
- `bloques_balance`
- `bloque_productos`

## Riesgos antes de migrar a PostgreSQL

1. SQL especifico de SQLite
   - `PRAGMA`
   - `AUTOINCREMENT`
   - `INSERT OR IGNORE`
   - `DATE(campo)` sobre texto
   - `sqlite_master`

2. Fechas guardadas como texto
   - En PostgreSQL conviene usar `timestamp` o `date`.
   - Hay registros con fecha vacia o nula; Reportes ya se hizo tolerante a eso.

3. Folios consecutivos
   - En multiusuario hay que protegerlos mejor para evitar duplicados.
   - PostgreSQL puede usar transacciones, bloqueos o secuencias.

4. Archivos y sesiones locales
   - `flask_session/` vive en disco.
   - Para empresa conectada conviene evaluar sesiones en servidor/cache.

5. Roles
   - Hoy todo esta reducido a `admin`.
   - Para otros departamentos hay que reabrir roles/permisos por modulo.

## Ruta recomendada

### Fase 3A - Preparacion segura

- Mantener SQLite.
- Separar configuracion de base.
- Documentar SQL incompatible.
- Agregar pruebas sobre rutas principales.
- Agregar respaldo automatizado antes de migraciones.

### Fase 3B - Capa de datos

- Crear funciones helper para diferencias SQLite/PostgreSQL:
  - obtener columnas
  - crear indices
  - insertar si no existe
  - fechas
  - folios
- Reemplazar gradualmente SQL especifico de SQLite en dashboard, reportes,
  balance y migraciones de esquema.

### Fase 3C - Prueba PostgreSQL local

- Crear base PostgreSQL de laboratorio.
- Migrar schema.
- Copiar datos desde SQLite.
- Comparar conteos por tabla.
- Probar entradas, salidas, requisiciones, reportes y balance.

### Fase 3D - Empresa conectada

- Definir departamentos reales.
- Definir permisos por rol.
- Definir si sera:
  - servidor local en la empresa
  - VPN/red interna
  - nube/online
  - hibrido

## Regla de seguridad

Nada de esta fase debe tocar el ERP v2 real ni reemplazar `almacen.db` productivo. Todo se prueba primero en:

`C:\Users\Almacen\Desktop\ERP\erp_almacen_v3_lab`
