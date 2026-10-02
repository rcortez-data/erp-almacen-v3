#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[PRUEBA] AGRUPAR REQUISICIONES DESDE FORMATO_REQUISICIONES_CHIDO_1.xlsm
==========================================================================
Este es un script de PRUEBA (parte del proceso, igual que los de War
Machine — se consolida en el script final cuando se indique).

PROBLEMA QUE RESUELVE:
  La hoja "2026" de este Excel tiene UN RENGLÓN POR MATERIAL, y varios
  renglones pueden compartir el mismo número de requisición (columna
  "No."). En tu base de datos, cada folio ya existe como requisición,
  pero solo quedó guardado el PRIMER material de cada grupo — el resto
  se perdió. Este script agrupa por folio y completa las partidas que
  faltan.

COLUMNAS DE LA HOJA "2026" (encabezados en fila 1):
  A=No. (folio)  B=Fecha de requisición  C=Cantidad  D=Unidad
  E=Material (descripción)  F=Estatus  G=Fecha de recibido  H=Estatus 2

QUÉ HACE:
  - Agrupa todos los renglones por folio (columna "No.").
  - Si el folio YA EXISTE como requisición en la base:
      Se REEMPLAZA su lista de partidas (requisicion_items) completa,
      por el grupo completo del Excel (no se agregan encima de la que
      ya había, para no duplicar la partida que sí se guardó bien).
      NO SE TOCAN los demás campos de la requisición (departamento,
      solicitante, asunto, OC, factura, estado manual, etc.) — esos
      se conservan tal cual ya los tengas capturados.
  - Si el folio NO EXISTE todavía:
      Se crea una requisición nueva con ese folio, fecha de requisición,
      y todas sus partidas. El "asunto" se llena con la descripción del
      primer material (mismo criterio que ya usa tu sistema).
  - cantidad_recibida de cada partida se llena según la columna
    "Estatus" de esa fila (Entregado -> recibida completa, cualquier
    otra cosa -> 0), ya que esta hoja no liga partidas a un producto
    del catálogo (son puro texto libre).

USO:
    python herramientas_emergencia/agrupar_requisiciones_chido.py
"""

import sys
import os
import openpyxl
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, set_folio_counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOMBRES_EXCEL = (
    "FORMATO REQUISICIONES CHIDO_1.xlsm",
    "FORMATO_REQUISICIONES_CHIDO_1.xlsm",
)
ARCHIVO_EXCEL = next(
    (os.path.join(BASE_DIR, nombre) for nombre in NOMBRES_EXCEL
     if os.path.exists(os.path.join(BASE_DIR, nombre))),
    os.path.join(BASE_DIR, NOMBRES_EXCEL[0]),
)

HOJA = "2026"


def limpiar(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto if texto else None


def a_fecha_sql(valor):
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d")
    texto = str(valor).strip()
    return texto or None


def a_numero(valor):
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).strip())
    except (ValueError, TypeError):
        pass
    return 0.0


def leer_y_agrupar(wb):
    ws = wb[HOJA]
    grupos = {}  # folio -> {"fecha": ..., "items": [...]}
    for row in ws.iter_rows(min_row=2, min_col=1, max_col=8, values_only=True):
        folio, fecha, cantidad, unidad, material, estatus, fecha_recibido, estatus2 = row
        if folio is None:
            continue
        try:
            folio = int(folio)
        except (ValueError, TypeError):
            continue
        material = limpiar(material)
        if not material:
            continue
        grupo = grupos.setdefault(folio, {"fecha": a_fecha_sql(fecha), "items": []})
        entregado = (limpiar(estatus) or "").upper() == "ENTREGADO"
        cant = a_numero(cantidad)
        grupo["items"].append({
            "cantidad": cant,
            "unidad": limpiar(unidad) or "",
            "descripcion": material,
            "cantidad_recibida": cant if entregado else 0.0,
        })
    return grupos


def main():
    print("=" * 80)
    print("[PRUEBA] AGRUPAR REQUISICIONES POR FOLIO (FORMATO_REQUISICIONES_CHIDO_1.xlsm)")
    print("=" * 80)

    if not os.path.exists(ARCHIVO_EXCEL):
        print(f"\n❌ No se encontró el archivo: {ARCHIVO_EXCEL}")
        return

    print(f"\n📊 Cargando '{os.path.basename(ARCHIVO_EXCEL)}'...")
    wb = openpyxl.load_workbook(ARCHIVO_EXCEL, data_only=True, read_only=True)
    print(f"  Leyendo hoja '{HOJA}' y agrupando por folio...")
    grupos = leer_y_agrupar(wb)
    wb.close()
    total_items_excel = sum(len(g["items"]) for g in grupos.values())
    print(f"  ✓ {len(grupos)} folios únicos, {total_items_excel} partidas en total")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, folio FROM requisiciones")
    existentes = {row["folio"]: row["id"] for row in cursor.fetchall()}

    a_completar = []   # folios que ya existen: (rid, folio, items, items_actuales)
    a_crear = []       # folios nuevos: (folio, fecha, items)

    for folio, grupo in grupos.items():
        if folio in existentes:
            rid = existentes[folio]
            items_actuales = cursor.execute(
                "SELECT COUNT(*) c FROM requisicion_items WHERE requisicion_id=?", (rid,)
            ).fetchone()["c"]
            if items_actuales != len(grupo["items"]):
                a_completar.append((rid, folio, grupo["items"], items_actuales))
        else:
            a_crear.append((folio, grupo["fecha"], grupo["items"]))

    print("\n" + "=" * 80)
    print("📝 RESUMEN:")
    print("=" * 80)
    print(f"  Requisiciones existentes a completar (partidas): {len(a_completar)}")
    for rid, folio, items, actuales in a_completar[:10]:
        print(f"    AL-{folio} | tenía {actuales} partida(s) -> quedará con {len(items)}")
    print(f"\n  Requisiciones nuevas a crear: {len(a_crear)}")
    for folio, fecha, items in a_crear[:10]:
        print(f"    AL-{folio} | fecha={fecha} | {len(items)} partida(s)")

    print("\n" + "=" * 80)
    respuesta = input("\n¿Confirmar cambios? (escribe SI): ").strip().upper()
    if respuesta != "SI":
        print("Cancelado. No se hizo ningún cambio.")
        conn.close()
        return

    print("\n⏳ Aplicando cambios...")
    completadas = 0
    creadas = 0
    errores = []

    for rid, folio, items, _actuales in a_completar:
        try:
            cursor.execute("DELETE FROM requisicion_items WHERE requisicion_id=?", (rid,))
            for idx, it in enumerate(items, start=1):
                cursor.execute("""
                    INSERT INTO requisicion_items
                        (requisicion_id, orden, cantidad, unidad, descripcion, cantidad_recibida)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (rid, idx, it["cantidad"], it["unidad"], it["descripcion"], it["cantidad_recibida"]))
            completadas += 1
        except Exception as e:
            errores.append((f"AL-{folio}", str(e)))

    for folio, fecha, items in a_crear:
        try:
            asunto = items[0]["descripcion"] if items else None
            cursor.execute("""
                INSERT INTO requisiciones (folio, fecha_requisicion, asunto, estado)
                VALUES (?, ?, ?, 'pendiente')
            """, (folio, fecha, asunto))
            rid = cursor.lastrowid
            for idx, it in enumerate(items, start=1):
                cursor.execute("""
                    INSERT INTO requisicion_items
                        (requisicion_id, orden, cantidad, unidad, descripcion, cantidad_recibida)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (rid, idx, it["cantidad"], it["unidad"], it["descripcion"], it["cantidad_recibida"]))
            creadas += 1
        except Exception as e:
            errores.append((f"AL-{folio}", str(e)))

    conn.commit()
    conn.close()

    if grupos:
        set_folio_counter('requisicion', max(grupos))

    print("\n" + "=" * 80)
    print("✅ COMPLETADO")
    print("=" * 80)
    print(f"  Requisiciones completadas (partidas reemplazadas): {completadas}")
    print(f"  Requisiciones nuevas creadas:                       {creadas}")
    if errores:
        print(f"\n⚠️  {len(errores)} errores:")
        for folio, err in errores[:20]:
            print(f"    {folio}: {err}")


if __name__ == "__main__":
    main()
