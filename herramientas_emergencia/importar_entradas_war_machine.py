#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[PRUEBA] IMPORTAR / SINCRONIZAR ENTRADAS DESDE WAR MACHINE
=============================================================
Este es un script de PRUEBA, parte del proceso para armar el importador
final (se arma con el comando "Crea el script final" más adelante).

Lee la hoja "Entradas" del Excel "War Machine 2026 OK.xlsm" y sincroniza
la tabla 'entradas' del ERP.

COLUMNAS DE LA HOJA "Entradas" (encabezados en fila 1):
  A=Codigo  B=Producto  C=Descripción  D=Cantidad  E=Unidad  F=Fecha
  G=Precio unitario  H=Importe  I=Moneda  J=Orden de compra  K=Factura
  L=Proveedor  M=Departamento  N=Uso  O=Folio  P=DESCRIPCION COMPLETA
  Q=FACTURA/REMISION  R=FOLIO REQUISICION

MAPEO A LA TABLA 'entradas':
  producto_id       <- se busca por código (A) en productos.codigo
  cantidad           <- D
  cantidad_piezas    <- D (igual que cantidad, como hace la app normalmente)
  precio_unitario     <- G
  importe             <- H
  orden_compra        <- J
  no_factura           <- K
  no_requisicion       <- R (Folio Requisición)
  proveedor_nombre_historico <- L (tal cual; NO se agrega nada a la tabla
                                    'proveedores', igual que en productos)
  departamento         <- M (tal cual, tal como viene tu ERP hoy)
  observaciones        <- "Uso: {N}" si N trae dato
  fecha                <- F

SERVICIOS (código sin producto en el catálogo):
  Si el código (A) no existe en productos -> se marca es_servicio=1,
  producto_id=NULL, concepto_servicio = "{Producto} {Descripción}"
  SIN modificar ese texto (tal cual venga del Excel).

SOBRESCRITURA / NO DUPLICAR (definido por el usuario: "sobreescribelas"):
  Cada fila del Excel se identifica con una llave estable:
    folio_excel = "ENTRADAS-<numero de fila>"
  Si ya existe una entrada con ese folio_excel -> se SOBRESCRIBE con los
  datos actuales del Excel (ajustando el stock solo por la DIFERENCIA
  entre la cantidad anterior y la nueva, para no descuadrar el inventario).

  Como en tu base ya había entradas cargadas antes de tener este folio_excel
  (13,565 de 13,884 ya lo traen, el resto no), para esas filas "huérfanas"
  se intenta un EMPATE por datos naturales (mismo producto + cantidad +
  fecha + no_factura). Si hay una sola coincidencia, se adopta esa fila
  (se le pone su folio_excel para la próxima vez) y se sobrescribe.
  Si no hay ninguna coincidencia -> se inserta como entrada nueva.

STOCK:
  Sí se ajusta stock_actual (confirmado por el usuario), sumando la
  cantidad en entradas nuevas, o la DIFERENCIA cuando se sobrescribe una
  entrada ya existente (para no aplicar el mismo movimiento dos veces).

USO:
    python herramientas_emergencia/importar_entradas_war_machine.py
"""

import sys
import os
import openpyxl
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db

ARCHIVO_EXCEL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "War Machine 2026 OK.xlsm"
)


def limpiar(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto if texto else None


def concatenar(producto, descripcion):
    partes = [p for p in (limpiar(producto), limpiar(descripcion)) if p]
    return " ".join(partes)


def a_fecha_sql(valor):
    """Convierte el valor de fecha del Excel a 'YYYY-MM-DD'. Si no se puede, regresa None."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, (int, float)):
        # Fecha guardada como número serial de Excel (base 1899-12-30)
        try:
            from datetime import timedelta
            fecha = datetime(1899, 12, 30) + timedelta(days=float(valor))
            return fecha.strftime("%Y-%m-%d")
        except Exception:
            return None
    texto = str(valor).strip()
    return texto or None


def a_numero(valor):
    if isinstance(valor, (int, float)):
        return float(valor)
    return 0.0


def leer_entradas(wb):
    ws = wb["Entradas"]
    filas = []
    fila_num = 1  # la fila 1 es encabezado
    for row in ws.iter_rows(min_row=2, min_col=1, max_col=18, values_only=True):
        fila_num += 1
        (codigo, producto, descripcion, cantidad, unidad, fecha, precio_unitario,
         importe, moneda, orden_compra, factura, proveedor, departamento, uso,
         folio, desc_completa, factura_remision, folio_requisicion) = row

        codigo = limpiar(codigo)
        if not codigo:
            continue

        filas.append({
            "fila_excel": fila_num,
            "folio_excel": f"ENTRADAS-{fila_num:06d}",
            "codigo": codigo,
            "concepto": concatenar(producto, descripcion),
            "cantidad": a_numero(cantidad),
            "precio_unitario": a_numero(precio_unitario),
            "importe": a_numero(importe),
            "orden_compra": limpiar(orden_compra),
            "no_factura": limpiar(factura),
            "no_requisicion": limpiar(folio_requisicion),
            "proveedor": limpiar(proveedor),
            "departamento": limpiar(departamento),
            "uso": limpiar(uso),
            "fecha": a_fecha_sql(fecha),
        })
    return filas


def main():
    print("=" * 80)
    print("[PRUEBA] IMPORTAR / SINCRONIZAR ENTRADAS DESDE WAR MACHINE")
    print("=" * 80)

    if not os.path.exists(ARCHIVO_EXCEL):
        print(f"\n❌ No se encontró el archivo: {ARCHIVO_EXCEL}")
        return

    print(f"\n📊 Cargando '{os.path.basename(ARCHIVO_EXCEL)}'...")
    wb = openpyxl.load_workbook(ARCHIVO_EXCEL, data_only=True, read_only=True)
    print("  Leyendo hoja 'Entradas'...")
    filas = leer_entradas(wb)
    print(f"  ✓ {len(filas)} filas leídas")
    wb.close()

    conn = get_db()
    cursor = conn.cursor()

    # Mapa código -> producto_id
    cursor.execute("SELECT id, codigo FROM productos")
    prod_por_codigo = {row["codigo"]: row["id"] for row in cursor.fetchall()}

    # Entradas existentes ya tagueadas con folio_excel (match directo)
    cursor.execute("""
        SELECT id, folio_excel, producto_id, cantidad, es_servicio
        FROM entradas WHERE folio_excel IS NOT NULL AND folio_excel != ''
    """)
    existentes_por_folio_excel = {}
    for row in cursor.fetchall():
        existentes_por_folio_excel[row["folio_excel"]] = dict(row)

    # TODAS las entradas existentes (tengan o no folio_excel viejo) quedan disponibles
    # para el empate por datos naturales. Si una fila del Excel empata aquí, se le
    # asigna folio_excel nuevo y consistente para que la próxima corrida ya matchee directo.
    cursor.execute("""
        SELECT id, folio_excel, producto_id, cantidad, fecha, no_factura, es_servicio
        FROM entradas
    """)
    huerfanas_por_llave = {}
    for row in cursor.fetchall():
        llave = (row["producto_id"], round(row["cantidad"] or 0, 4), row["fecha"], row["no_factura"])
        huerfanas_por_llave.setdefault(llave, []).append(dict(row))

    # Clasificar cada fila del Excel
    a_insertar = []
    a_actualizar_directo = []   # match por folio_excel
    a_actualizar_empate = []    # match por llave natural (huérfana)
    marcadas_servicio = 0

    for f in filas:
        producto_id = prod_por_codigo.get(f["codigo"])
        f["es_servicio"] = 0 if producto_id else 1
        f["producto_id"] = producto_id
        if f["es_servicio"]:
            marcadas_servicio += 1

        match_directo = existentes_por_folio_excel.get(f["folio_excel"])
        if match_directo:
            f["_match"] = match_directo
            a_actualizar_directo.append(f)
            continue

        llave = (producto_id, round(f["cantidad"], 4), f["fecha"], f["no_factura"])
        candidatos = huerfanas_por_llave.get(llave)
        if candidatos:
            f["_match"] = candidatos.pop(0)  # se "consume" para no reusarlo
            a_actualizar_empate.append(f)
        else:
            a_insertar.append(f)

    print("\n" + "=" * 80)
    print("📝 RESUMEN:")
    print("=" * 80)
    print(f"  Filas leídas del Excel:                    {len(filas)}")
    print(f"  Marcadas como SERVICIO (código sin producto): {marcadas_servicio}")
    print(f"  Coinciden por folio_excel (ya sincronizadas antes, se sobrescriben): {len(a_actualizar_directo)}")
    print(f"  Coinciden por datos naturales (entradas antiguas sin folio_excel, se adoptan y sobrescriben): {len(a_actualizar_empate)}")
    print(f"  NUEVAS a insertar:                          {len(a_insertar)}")

    print("\n  Ejemplos de NUEVAS (primeras 5):")
    for f in a_insertar[:5]:
        print(f"    fila {f['fila_excel']} | {f['codigo']} | cant={f['cantidad']} | fecha={f['fecha']} | factura={f['no_factura']} | servicio={bool(f['es_servicio'])}")

    print("\n" + "=" * 80)
    respuesta = input("\n¿Confirmar sincronización? (escribe SI): ").strip().upper()
    if respuesta != "SI":
        print("Cancelado. No se hizo ningún cambio.")
        conn.close()
        return

    print("\n⏳ Aplicando cambios...")
    insertados = 0
    actualizados = 0
    errores = []
    stock_ajustes = {}  # producto_id -> delta acumulado

    def acumular_stock(producto_id, delta):
        if producto_id and delta:
            stock_ajustes[producto_id] = stock_ajustes.get(producto_id, 0) + delta

    for f in a_insertar:
        try:
            cursor.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo = 'entrada'")
            num = cursor.execute("SELECT ultimo FROM folios WHERE tipo='entrada'").fetchone()[0]
            folio = f"ENT-{str(num).zfill(6)}"
            cursor.execute("""
                INSERT INTO entradas
                    (folio, producto_id, es_servicio, concepto_servicio, cantidad,
                     cantidad_piezas, precio_unitario, importe, no_requisicion,
                     no_factura, orden_compra, proveedor_nombre_historico,
                     departamento, observaciones, folio_excel, fecha)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                folio, f["producto_id"], f["es_servicio"],
                f["concepto"] if f["es_servicio"] else None,
                f["cantidad"], f["cantidad"], f["precio_unitario"], f["importe"],
                f["no_requisicion"], f["no_factura"], f["orden_compra"], f["proveedor"],
                f["departamento"], (f"Uso: {f['uso']}" if f["uso"] else None),
                f["folio_excel"], f["fecha"]
            ))
            insertados += 1
            if not f["es_servicio"]:
                acumular_stock(f["producto_id"], f["cantidad"])
        except Exception as e:
            errores.append((f["folio_excel"], str(e)))

    for f in a_actualizar_directo + a_actualizar_empate:
        try:
            anterior = f["_match"]
            cursor.execute("""
                UPDATE entradas
                SET producto_id=?, es_servicio=?, concepto_servicio=?, cantidad=?,
                    cantidad_piezas=?, precio_unitario=?, importe=?, no_requisicion=?,
                    no_factura=?, orden_compra=?, proveedor_nombre_historico=?,
                    departamento=?, observaciones=?, folio_excel=?, fecha=?
                WHERE id=?
            """, (
                f["producto_id"], f["es_servicio"],
                f["concepto"] if f["es_servicio"] else None,
                f["cantidad"], f["cantidad"], f["precio_unitario"], f["importe"],
                f["no_requisicion"], f["no_factura"], f["orden_compra"], f["proveedor"],
                f["departamento"], (f"Uso: {f['uso']}" if f["uso"] else None),
                f["folio_excel"], f["fecha"], anterior["id"]
            ))
            actualizados += 1

            # Ajuste de stock solo por la diferencia (evita duplicar el movimiento)
            era_servicio_antes = bool(anterior["es_servicio"])
            es_servicio_ahora = bool(f["es_servicio"])
            cantidad_antes = anterior["cantidad"] or 0
            producto_antes = anterior["producto_id"]

            if not era_servicio_antes and producto_antes:
                acumular_stock(producto_antes, -cantidad_antes)  # revertir movimiento viejo
            if not es_servicio_ahora and f["producto_id"]:
                acumular_stock(f["producto_id"], f["cantidad"])  # aplicar movimiento nuevo

        except Exception as e:
            errores.append((f["folio_excel"], str(e)))

    for producto_id, delta in stock_ajustes.items():
        if delta:
            cursor.execute(
                "UPDATE productos SET stock_actual = stock_actual + ? WHERE id=?",
                (delta, producto_id)
            )

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print("✅ SINCRONIZACIÓN COMPLETADA")
    print("=" * 80)
    print(f"  Entradas insertadas:   {insertados}")
    print(f"  Entradas actualizadas: {actualizados}")
    print(f"  Productos con ajuste de stock: {len(stock_ajustes)}")
    if errores:
        print(f"\n⚠️  {len(errores)} errores:")
        for llave, err in errores[:20]:
            print(f"    {llave}: {err}")


if __name__ == "__main__":
    main()
