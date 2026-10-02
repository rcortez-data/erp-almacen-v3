# NEGOCIO · Punto de venta para tienditas

Prototipo funcional del punto de venta para una tienda de barrio. Está pensado para validar rápidamente el flujo de caja antes de conectar productos, inventario, usuarios y ventas con el backend Flask del ERP.

## Qué incluye esta primera versión

- Catálogo de productos con búsqueda instantánea.
- Filtros por categoría y accesos rápidos para los productos más vendidos.
- Carrito persistente en `localStorage` para no perder la captura al recargar.
- Ajuste de cantidades, eliminación de productos y cálculo de subtotal/total.
- Cobro simulado con efectivo, tarjeta o transferencia.
- Resumen de venta guardado localmente y número de ticket generado.
- Diseño responsive pensado para una laptop de mostrador, tablet o celular.

## Ejecutar en esta PC

Desde PowerShell:

```powershell
cd 'C:\Users\Almacen\Desktop\ERP\erp_almacen_v3\LOGINSSS\NEGOCIO'
\.\INICIAR_NEGOCIO.ps1
```

Después abre `http://localhost:4173`.

También puede abrirse como archivo directamente, aunque el servidor local ofrece una experiencia más cercana a la integración final con Flask.

## Próximo paso de integración

El prototipo usa datos demo en `app.js`. La siguiente fase debe sustituirlos por endpoints del ERP:

1. `GET /negocio/api/productos` para catálogo y existencias.
2. `POST /negocio/api/ventas` para confirmar una venta.
3. Validación de stock y descuentos en servidor.
4. Impresión de ticket y corte de caja.

La especificación de producto y el prompt reutilizable están en `PROMPT_MAESTRO_POS_TIENDA.md`.
