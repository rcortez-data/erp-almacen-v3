# Correcciones de producción — 2026-09-29

## Objetivo

Corregir la interpretación de salidas del producto `PLA18` cuando existen
vales históricos capturados en kilos y vales nuevos que guardan un snapshot de
conversión.

## Cambios realizados

- `routes/balance.py`
  - Usa `cantidad_stock` únicamente cuando el vale tiene snapshot de
    conversión (`unidad_compra_movimiento` y `factor_conversion_movimiento`).
  - Los vales antiguos sin snapshot convierten `cantidad` desde kilos a
    piezas usando la configuración vigente del producto.
  - Agosto de 2026 conserva su cierre histórico; septiembre y los periodos
    posteriores manejan correctamente vales mixtos.

- `routes/salidas.py`
  - Corrige sumas, eliminación y edición de salidas para usar la misma regla
    de conversión.

- `templates/salidas/index.html` y `templates/salidas/detalle.html`
  - Un vale histórico como `SAL-056432` se muestra como `40 PIEZAS = 100 KILOS`
    en lugar de `100 PIEZAS`.

- `SERVIDOR_V3_SIN_VENTANA.ps1`
  - Elimina la ruta fija de Python de la computadora anterior.
  - Detecta el entorno virtual local o un Python disponible en el sistema.

- `PREPARAR_ENTORNO.ps1`
  - Reconstruye un `.venv` trasladado desde otra computadora e instala
    `requirements.txt`.

## Despliegue en la PC de producción

1. Respaldar `almacen.db` antes de actualizar.
2. Detener el ERP.
3. Aplicar este commit, sin reemplazar la base de datos.
4. Ejecutar una vez `PREPARAR_ENTORNO.ps1` si la PC tiene un `.venv` copiado o
   si faltan dependencias.
5. Ejecutar `INICIAR_PRODUCCION_V3.bat`.
6. Validar `http://127.0.0.1:5000/health` y revisar `SAL-056432`.

## Verificación

La aplicación respondió `HTTP 200` en `/health` después de reiniciar y el
balance de `PLA18` quedó con la conversión coherente entre piezas y kilos.

Este commit no contiene `almacen.db`, respaldos ni `.venv`.
