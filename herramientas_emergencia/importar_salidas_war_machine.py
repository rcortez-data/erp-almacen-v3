#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[PRUEBA] IMPORTAR / SINCRONIZAR SALIDAS DESDE WAR MACHINE
=============================================================
Este es un script de PRUEBA, parte del proceso para armar el importador
final (se arma con el comando "Crea el script final" más adelante).

Lee la hoja "Salidas" del Excel "War Machine 2026 OK.xlsm" y sincroniza
la tabla 'salidas' del ERP.

COLUMNAS DE LA HOJA "Salidas" (encabezados en fila 1):
  A=Código  B=Producto  C=Descripción  D=Cantidad  E=Unidad  F=Fecha
  G=No. Vale  H=Solicitante  I=Departamento  J=Uso

MAPEO A LA TABLA 'salidas':
  producto_id    <- se busca por código (A) en productos.codigo
  cantidad        <- D
  responsable      <- H (Solicitante). Si viene vacío, se usa "SIN ESPECIFICAR"
                       (la columna es NOT NULL en la tabla).
  area              <- I (Departamento de la hoja Salidas, tal cual;
                          NO se copia del producto)
  no_vale            <- G
  observaciones       <- "Uso: {J}" si J trae dato
  fecha                <- F

SERVICIOS (código sin producto en el catálogo):
  Si el código (A) no existe en productos -> se marca es_servicio=1,
  producto_id=NULL, concepto_servicio = "{Producto} {Descripción}"
  SIN modificar ese texto (tal cual venga del Excel).
  (Se agregaron las columnas es_servicio/concepto_servicio a 'salidas',
  igual que ya existían en 'entradas', para poder hacer esto.)

SOBRESCRITURA / NO DUPLICAR (definido por el usuario: "sobreescribelas"):
  Cada fila del Excel se identifica con una llave estable:
    folio_excel = "SALIDAS-<numero de fila>"
  Si ya existe una salida con ese folio_excel -> se SOBRESCRIBE.
  Como tu tabla 'salidas' no traía folio_excel usado (estaba vacío en
  las 51,467 salidas existentes), la primera corrida hace el empate por
  datos naturales (mismo producto + cantidad + fecha + no_vale). Si hay
  una sola coincidencia, se adopta esa fila (se le pone su folio_excel
  para la próxima vez) y se sobrescribe. Si no hay coincidencia, se
  inserta como salida nueva.

STOCK:
  Se ajusta stock_actual restando la cantidad (confirmado por el
  usuario), o la DIFERENCIA cuando se sobrescribe una salida ya
  existente (para no aplicar el mismo movimiento dos veces).

USO:
    python herramientas_emergencia/importar_salidas_war_machine.py
"""

import sys
import os
import openpyxl
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db

ARCHIVO_EXCEL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "War Machine 2026 OK.xlsm"
)

RESPONSABLE_DEFECTO = "SIN ESPECIFICAR"


def limpiar(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto if texto else None


def concatenar(producto, descripcion):
    partes = [p for p in (limpiar(producto), limpiar(descripcion)) if p]
    return " ".join(partes)


def a_fecha_sql(valor):
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, (int, float)):
        try:
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


def leer_salidas(wb):
    ws = wb["Salidas"]
    filas = []
    fila_num = 1  # fila 1 = encabezado
    for row in ws.iter_rows(min_row=2, min_col=1, max_col=10, values_only=True):
        fila_num += 1
        codigo, producto, descripcion, cantidad, unidad, fecha, no_vale, solicitante, departamento, uso = row

        codigo = limpiar(codigo)
        if not codigo:
            continue

        filas.append({
            "fila_excel": fila_num,
            "folio_excel": f"SALIDAS-{fila_num:06d}",
            "codigo": codigo,
            "concepto": concatenar(producto, descripcion),
            "cantidad": a_numero(cantidad),
            "responsable": limpiar(solicitante) or RESPONSABLE_DEFECTO,
            "area": limpiar(departamento),
            "no_vale": limpiar(no_vale),
            "uso": limpiar(uso),
            "fecha": a_fecha_sql(fecha),
        })
    return filas


def main():
    print("=" * 80)
    print("[PRUEBA] IMPORTAR / SINCRONIZAR SALIDAS DESDE WAR MACHINE")
    print("=" * 80)

    if not os.path.exists(ARCHIVO_EXCEL):
        print(f"\n❌ No se encontró el archivo: {ARCHIVO_EXCEL}")
        return

    print(f"\n📊 Cargando '{os.path.basename(ARCHIVO_EXCEL)}'...")
    wb = openpyxl.load_workbook(ARCHIVO_EXCEL, data_only=True, read_only=True)
    print("  Leyendo hoja 'Salidas'...")
    filas = leer_salidas(wb)
    print(f"  ✓ {len(filas)} filas leídas")
    wb.close()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, codigo FROM productos")
    prod_por_codigo = {row["codigo"]: row["id"] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT id, folio_excel, producto_id, cantidad, es_servicio
        FROM salidas WHERE folio_excel IS NOT NULL AND folio_excel != ''
    """)
    existentes_por_folio_excel = {row["folio_excel"]: dict(row) for row in cursor.fetchall()}

    # TODAS las salidas existentes quedan disponibles para el empate por datos naturales
    cursor.execute("""
        SELECT id, producto_id, cantidad, fecha, no_vale, es_servicio
        FROM salidas
    """)
    candidatos_por_llave = {}
    for row in cursor.fetchall():
        llave = (row["producto_id"], round(row["cantidad"] or 0, 4), row["fecha"], row["no_vale"])
        candidatos_por_llave.setdefault(llave, []).append(dict(row))

    a_insertar = []
    a_actualizar_directo = []
    a_actualizar_empate = []
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

        llave = (producto_id, round(f["cantidad"], 4), f["fecha"], f["no_vale"])
        candidatos = candidatos_por_llave.get(llave)
        if candidatos:
            f["_match"] = candidatos.pop(0)
            a_actualizar_empate.append(f)
        else:
            a_insertar.append(f)

    print("\n" + "=" * 80)
    print("📝 RESUMEN:")
    print("=" * 80)
    print(f"  Filas leídas del Excel:                    {len(filas)}")
    print(f"  Marcadas como SERVICIO (código sin producto): {marcadas_servicio}")
    print(f"  Coinciden por folio_excel (ya sincronizadas antes, se sobrescriben): {len(a_actualizar_directo)}")
    print(f"  Coinciden por datos naturales (se adoptan y sobrescriben): {len(a_actualizar_empate)}")
    print(f"  NUEVAS a insertar:                          {len(a_insertar)}")

    print("\n  Ejemplos de NUEVAS (primeras 5):")
    for f in a_insertar[:5]:
        print(f"    fila {f['fila_excel']} | {f['codigo']} | cant={f['cantidad']} | fecha={f['fecha']} | vale={f['no_vale']} | servicio={bool(f['es_servicio'])}")

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
    stock_ajustes = {}

    def acumular_stock(producto_id, delta):
        if producto_id and delta:
            stock_ajustes[producto_id] = stock_ajustes.get(producto_id, 0) + delta

    for f in a_insertar:
        try:
            cursor.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo = 'salida'")
            num = cursor.execute("SELECT ultimo FROM folios WHERE tipo='salida'").fetchone()[0]
            folio = f"SAL-{str(num).zfill(6)}"
            cursor.execute("""
                INSERT INTO salidas
                    (folio, producto_id, es_servicio, concepto_servicio, cantidad,
                     responsable, area, no_vale, observaciones, folio_excel, fecha)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                folio, f["producto_id"], f["es_servicio"],
                f["concepto"] if f["es_servicio"] else None,
                f["cantidad"], f["responsable"], f["area"], f["no_vale"],
                (f"Uso: {f['uso']}" if f["uso"] else None),
                f["folio_excel"], f["fecha"]
            ))
            insertados += 1
            if not f["es_servicio"]:
                acumular_stock(f["producto_id"], -f["cantidad"])
        except Exception as e:
            errores.append((f["folio_excel"], str(e)))

    for f in a_actualizar_directo + a_actualizar_empate:
        try:
            anterior = f["_match"]
            cursor.execute("""
                UPDATE salidas
                SET producto_id=?, es_servicio=?, concepto_servicio=?, cantidad=?,
                    responsable=?, area=?, no_vale=?, observaciones=?, folio_excel=?, fecha=?
                WHERE id=?
            """, (
                f["producto_id"], f["es_servicio"],
                f["concepto"] if f["es_servicio"] else None,
                f["cantidad"], f["responsable"], f["area"], f["no_vale"],
                (f"Uso: {f['uso']}" if f["uso"] else None),
                f["folio_excel"], f["fecha"], anterior["id"]
            ))
            actualizados += 1

            era_servicio_antes = bool(anterior["es_servicio"])
            es_servicio_ahora = bool(f["es_servicio"])
            cantidad_antes = anterior["cantidad"] or 0
            producto_antes = anterior["producto_id"]

            if not era_servicio_antes and producto_antes:
                acumular_stock(producto_antes, cantidad_antes)  # revertir resta vieja
            if not es_servicio_ahora and f["producto_id"]:
                acumular_stock(f["producto_id"], -f["cantidad"])  # aplicar resta nueva

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
    print(f"  Salidas insertadas:   {insertados}")
    print(f"  Salidas actualizadas: {actualizados}")
    print(f"  Productos con ajuste de stock: {len(stock_ajustes)}")
    if errores:
        print(f"\n⚠️  {len(errores)} errores:")
        for llave, err in errores[:20]:
            print(f"    {llave}: {err}")


if __name__ == "__main__":
    main()
