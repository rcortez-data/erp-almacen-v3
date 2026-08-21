# Plan de salida controlada de ERP V3

## Reglas

- V2 no se modifica directamente.
- El primer destino es `erp_almacen_v2_test_reporte`.
- Cada despliegue requiere respaldo SQLite verificado y plan de regreso.
- PostgreSQL se prueba en una base vacia de laboratorio antes de cambiar el motor del ERP.

## Validaciones tecnicas automatizadas

1. `python -m pytest -q`
2. `python scripts/db_preflight.py`
3. `python scripts/production_preflight.py`
4. `python scripts/backup_sqlite.py`
5. `python scripts/verify_backup.py RUTA_DEL_RESPALDO`

El preflight debe bloquear la liberacion mientras exista una cuenta con `admin123`.

## Validacion humana obligatoria

- Cuadrar el punto de partida de junio contra inventario fisico.
- Validar una entrada, una salida y una requisicion con documentos reales de prueba.
- Probar perfiles administrador, almacen, compras y consulta.
- Cerrar junio, comprobar julio y probar una reapertura con motivo.
- Comparar existencias, folios, entradas, salidas y reportes contra V2.
- Firmar la aceptacion de almacen y administracion.

## Despliegue de preproduccion

1. Generar paquete con `python scripts/build_release.py`.
2. Respaldar completamente `erp_almacen_v2_test_reporte`.
3. Actualizar solo el codigo; conservar su base y secretos por separado.
4. Ejecutar migraciones al iniciar V3.
5. Trabajar varios dias en pruebas y documentar diferencias.

## PostgreSQL

1. Preparar una instancia vacia exclusivamente de laboratorio.
2. Definir `DATABASE_URL` sin guardarla en el repositorio.
3. Ejecutar `MIGRAR_LAB_A_POSTGRES.bat`.
4. Comparar los conteos mostrados por las 19 tablas.
5. Ejecutar pruebas funcionales contra el nuevo motor antes de autorizar el cambio.

## Regreso a V2

- Detener V3.
- Restaurar el respaldo previo de codigo y base del entorno de prueba.
- Confirmar integridad SQLite y conteos.
- Registrar el motivo del rollback y las operaciones realizadas durante la ventana.
