"""
DIAGNOSTICAR FACTURA - Muestra línea por línea qué está sumando el sistema
para una factura/remisión/OC/requisición específica, para compararlo contra
el documento físico.

Uso:
    python diagnosticar_factura.py 4140
    python diagnosticar_factura.py 4140 --exacto
    python diagnosticar_factura.py 4140 --fecha 2026-07-29

Por default busca coincidencia PARCIAL en no_factura (igual que el buscador
del ERP), sin filtrar por fecha, para que veas TODO lo que existe con ese
número en cualquier fecha. Usa --exacto para exigir coincidencia exacta, y
--fecha para limitar a un día en particular.
"""
import sys
import sqlite3
from pathlib import Path


def subtotal_real(cantidad, precio_unitario, importe):
    """Misma lógica que usa el ERP: si hay precio_unitario, cantidad*precio
    manda (es el dato confiable); si no, se cae al importe guardado."""
    cantidad = cantidad or 0
    precio_unitario = precio_unitario or 0
    if precio_unitario:
        return round(cantidad * precio_unitario, 2)
    return round(importe or 0, 2)


def main():
    if len(sys.argv) < 2:
        print("Uso: python diagnosticar_factura.py <numero_factura> [--exacto] [--fecha YYYY-MM-DD]")
        return

    numero = sys.argv[1]
    exacto = '--exacto' in sys.argv
    fecha = None
    if '--fecha' in sys.argv:
        idx = sys.argv.index('--fecha')
        fecha = sys.argv[idx + 1]

    db_path = Path(__file__).parent / 'almacen.db'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if exacto:
        condicion = "e.no_factura = ?"
        valor = numero
    else:
        condicion = "e.no_factura LIKE ?"
        valor = f"%{numero}%"

    query = f"""
        SELECT e.id, e.folio, e.fecha, e.no_factura, e.no_remision, e.orden_compra,
               e.cantidad, e.precio_unitario, e.importe,
               p.codigo, p.descripcion, pr.nombre as proveedor
        FROM entradas e
        JOIN productos p ON e.producto_id = p.id
        LEFT JOIN proveedores pr ON e.proveedor_id = pr.id
        WHERE {condicion}
    """
    params = [valor]
    if fecha:
        query += " AND DATE(e.fecha) = ?"
        params.append(fecha)
    query += " ORDER BY e.fecha, e.id"

    filas = c.execute(query, params).fetchall()
    conn.close()

    if not filas:
        print(f"No se encontró ninguna entrada con factura {'=' if exacto else 'que contenga'} '{numero}'"
              + (f" en la fecha {fecha}" if fecha else ""))
        return

    print("=" * 100)
    print(f"  DIAGNÓSTICO — factura {'exacta' if exacto else 'parcial (LIKE)'} '{numero}'"
          + (f"  |  fecha: {fecha}" if fecha else "  |  todas las fechas"))
    print("=" * 100)

    total_subtotal = 0
    facturas_distintas = set()
    fechas_distintas = set()

    for f in filas:
        sub = subtotal_real(f['cantidad'], f['precio_unitario'], f['importe'])
        iva = round(sub * 0.16, 2)
        total = round(sub + iva, 2)
        total_subtotal += sub
        facturas_distintas.add(f['no_factura'])
        fechas_distintas.add(str(f['fecha'])[:10])

        print(f"\n  Folio {f['folio']}  (id {f['id']})")
        print(f"    Fecha:          {f['fecha']}")
        print(f"    Factura:        '{f['no_factura']}'   <- ojo si no es EXACTAMENTE tu número")
        print(f"    Producto:       {f['codigo']} - {f['descripcion']}")
        print(f"    Proveedor:      {f['proveedor'] or '—'}")
        print(f"    Cantidad:       {f['cantidad']}")
        print(f"    Precio unit.:   ${f['precio_unitario'] or 0:,.2f}")
        print(f"    Importe guardado en BD: ${f['importe'] or 0:,.2f}")
        print(f"    -> Subtotal usado por el ERP: ${sub:,.2f}  |  IVA: ${iva:,.2f}  |  Total: ${total:,.2f}")

    print("\n" + "-" * 100)
    print(f"  TOTAL {len(filas)} renglón(es) encontrados")
    print(f"  Suma de subtotales: ${total_subtotal:,.2f}")
    print(f"  IVA (16%):          ${round(total_subtotal*0.16, 2):,.2f}")
    print(f"  TOTAL con IVA:      ${round(total_subtotal*1.16, 2):,.2f}")
    print("-" * 100)

    if len(facturas_distintas) > 1:
        print(f"\n  ⚠️  AVISO: encontré {len(facturas_distintas)} valores DIFERENTES en 'no_factura' que")
        print(f"      coinciden con tu búsqueda (coincidencia parcial): {sorted(facturas_distintas)}")
        print("      Si alguno no es tu factura real, usa --exacto para descartarlos.")

    if len(fechas_distintas) > 1 and not fecha:
        print(f"\n  ⚠️  AVISO: estas líneas están repartidas en {len(fechas_distintas)} fechas distintas:")
        print(f"      {sorted(fechas_distintas)}")
        print("      Si solo esperabas una fecha, revisa si alguna línea se capturó con la fecha equivocada.")

    print("=" * 100)


if __name__ == "__main__":
    main()
