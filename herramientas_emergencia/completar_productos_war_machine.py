#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[PRUEBA] COMPLETAR PRODUCTOS FALTANTES / CON DATOS VACÍOS (War Machine)
==========================================================================
Este es un script de PRUEBA, parte del proceso para armar el importador
final (se arma con el comando "Crea el script final" más adelante).

Resuelve dos casos, usando las hojas "Entradas" y "Salidas" del Excel
"War Machine 2026 OK.xlsm" (no usa Catalogo ni Maquinados, esos ya se
procesaron en importar_productos_war_machine.py):

CASO A - Productos que YA EXISTEN pero con descripción vacía
  (ej. código 'RAF' con descripcion=''). Se completan SOLO los campos
  que estén vacíos (nunca se sobrescribe lo que ya tiene datos):
    descripcion   <- "{Producto} {Descripción}" de la primera coincidencia
                      encontrada en Entradas o Salidas
    unidad_medida  <- Unidad de esa misma fila, si la tenía vacía
    departamento    <- Departamento de Entradas, si lo tenía vacío

CASO B - Códigos que NO EXISTEN como producto en absoluto
  Se crean como producto nuevo:
    descripcion    <- "{Producto} {Descripción}" (primera coincidencia)
    unidad_medida   <- Unidad encontrada, o 'PIEZA' si no hay ninguna
    departamento     <- Departamento de Entradas si existe
    stock_actual      <- SUMA de todas las cantidades en Entradas MENOS
                          la SUMA de todas las cantidades en Salidas de
                          ese código, en TODO el Excel (confirmado por
                          el usuario)

  Las entradas/salidas que ya se habían importado marcadas como
  "servicio" (es_servicio=1, producto_id=NULL) porque su código no
  existía, se RE-LIGAN al producto recién creado (es_servicio=0,
  producto_id=<nuevo>) usando folio_excel para identificar exactamente
  cada fila. Esto NO vuelve a tocar stock_actual (ya se calculó directo
  con la suma neta), así que no hay doble conteo.

  El usuario pidió crear TODOS los códigos encontrados (incluida
  "basura" tipo pruebas) para limpiarlos manualmente después.

USO:
    python herramientas_emergencia/completar_productos_war_machine.py
"""

import sys
import os
import openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db

ARCHIVO_EXCEL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "War Machine 2026 OK.xlsm"
)

UNIDAD_DEFECTO = "PIEZA"


def limpiar(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto if texto else None


def concatenar(producto, descripcion):
    partes = [p for p in (limpiar(producto), limpiar(descripcion)) if p]
    return " ".join(partes)


def a_numero(valor):
    if isinstance(valor, (int, float)):
        return float(valor)
    return 0.0


def recolectar(wb):
    """
    Recorrido de Entradas y Salidas. Arma:
      info[codigo]  = {descripcion, unidad, departamento, suma_entradas, suma_salidas}
      folios_entradas[codigo] = [folio_excel, ...]
      folios_salidas[codigo]  = [folio_excel, ...]
    """
    info = {}
    folios_entradas = {}
    folios_salidas = {}

    def registro(codigo):
        if codigo not in info:
            info[codigo] = {
                "descripcion": None, "unidad": None, "departamento": None,
                "suma_entradas": 0.0, "suma_salidas": 0.0
            }
        return info[codigo]

    ws = wb["Entradas"]
    fila_num = 1
    for row in ws.iter_rows(min_row=2, min_col=1, max_col=13, values_only=True):
        fila_num += 1
        codigo = limpiar(row[0])
        if not codigo:
            continue
        r = registro(codigo)
        r["suma_entradas"] += a_numero(row[3])
        if not r["descripcion"]:
            desc = concatenar(row[1], row[2])
            if desc:
                r["descripcion"] = desc
        if not r["unidad"]:
            r["unidad"] = limpiar(row[4])
        if not r["departamento"]:
            r["departamento"] = limpiar(row[12])
        folios_entradas.setdefault(codigo, []).append(f"ENTRADAS-{fila_num:06d}")

    ws = wb["Salidas"]
    fila_num = 1
    for row in ws.iter_rows(min_row=2, min_col=1, max_col=10, values_only=True):
        fila_num += 1
        codigo = limpiar(row[0])
        if not codigo:
            continue
        r = registro(codigo)
        r["suma_salidas"] += a_numero(row[3])
        if not r["descripcion"]:
            desc = concatenar(row[1], row[2])
            if desc:
                r["descripcion"] = desc
        if not r["unidad"]:
            r["unidad"] = limpiar(row[4])
        folios_salidas.setdefault(codigo, []).append(f"SALIDAS-{fila_num:06d}")

    return info, folios_entradas, folios_salidas


def main():
    print("=" * 80)
    print("[PRUEBA] COMPLETAR PRODUCTOS FALTANTES / CON DATOS VACÍOS")
    print("=" * 80)

    if not os.path.exists(ARCHIVO_EXCEL):
        print(f"\n❌ No se encontró el archivo: {ARCHIVO_EXCEL}")
        return

    print(f"\n📊 Cargando '{os.path.basename(ARCHIVO_EXCEL)}'...")
    wb = openpyxl.load_workbook(ARCHIVO_EXCEL, data_only=True, read_only=True)
    print("  Recolectando información de Entradas + Salidas por código...")
    info_por_codigo, folios_entradas, folios_salidas = recolectar(wb)
    print(f"  ✓ {len(info_por_codigo)} códigos únicos encontrados en movimientos")
    wb.close()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, codigo, descripcion, unidad_medida, departamento FROM productos")
    productos_existentes = {row["codigo"]: dict(row) for row in cursor.fetchall()}

    # --- CASO A: completar productos existentes con campos vacíos ---
    a_completar = []
    for codigo, prod in productos_existentes.items():
        info = info_por_codigo.get(codigo)
        if not info:
            continue
        necesita_desc = not limpiar(prod["descripcion"])
        necesita_unidad = not limpiar(prod["unidad_medida"])
        necesita_depto = not limpiar(prod["departamento"])
        if necesita_desc or necesita_unidad or necesita_depto:
            a_completar.append({
                "id": prod["id"], "codigo": codigo,
                "descripcion": info["descripcion"] if necesita_desc else None,
                "unidad": info["unidad"] if necesita_unidad else None,
                "departamento": info["departamento"] if necesita_depto else None,
            })

    # --- CASO B: códigos que no existen como producto ---
    a_crear = []
    for codigo, info in info_por_codigo.items():
        if codigo in productos_existentes:
            continue
        stock_neto = round(info["suma_entradas"] - info["suma_salidas"], 4)
        a_crear.append({
            "codigo": codigo,
            "descripcion": info["descripcion"] or codigo,
            "unidad": info["unidad"] or UNIDAD_DEFECTO,
            "departamento": info["departamento"],
            "stock": stock_neto,
        })

    print("\n" + "=" * 80)
    print("📝 RESUMEN:")
    print("=" * 80)
    print(f"  CASO A - Productos existentes a completar: {len(a_completar)}")
    for x in a_completar[:8]:
        print(f"    {x['codigo']} | desc->{x['descripcion']!r} | unidad->{x['unidad']!r} | depto->{x['departamento']!r}")
    print(f"\n  CASO B - Productos nuevos a crear: {len(a_crear)}")
    for x in a_crear[:15]:
        print(f"    {x['codigo']} | {x['descripcion'][:55]!r} | unidad={x['unidad']} | depto={x['departamento']} | stock={x['stock']}")

    print("\n" + "=" * 80)
    respuesta = input("\n¿Confirmar cambios? (escribe SI): ").strip().upper()
    if respuesta != "SI":
        print("Cancelado. No se hizo ningún cambio.")
        conn.close()
        return

    print("\n⏳ Aplicando cambios...")
    completados = 0
    creados = 0
    reenlazadas_entradas = 0
    reenlazadas_salidas = 0
    errores = []

    for x in a_completar:
        try:
            campos = []
            valores = []
            if x["descripcion"]:
                campos.append("descripcion = ?")
                valores.append(x["descripcion"])
            if x["unidad"]:
                campos.append("unidad_medida = ?")
                valores.append(x["unidad"])
            if x["departamento"]:
                campos.append("departamento = ?")
                valores.append(x["departamento"])
            if campos:
                valores.append(x["id"])
                cursor.execute(f"UPDATE productos SET {', '.join(campos)} WHERE id = ?", valores)
                completados += 1
        except Exception as e:
            errores.append((x["codigo"], str(e)))

    for x in a_crear:
        try:
            cursor.execute("""
                INSERT INTO productos (codigo, descripcion, unidad_medida, departamento, stock_actual, activo)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (x["codigo"], x["descripcion"], x["unidad"], x["departamento"], x["stock"]))
            nuevo_id = cursor.lastrowid
            creados += 1

            for folio_excel in folios_entradas.get(x["codigo"], []):
                cursor.execute("""
                    UPDATE entradas SET producto_id = ?, es_servicio = 0
                    WHERE folio_excel = ? AND es_servicio = 1 AND producto_id IS NULL
                """, (nuevo_id, folio_excel))
                if cursor.rowcount:
                    reenlazadas_entradas += cursor.rowcount

            for folio_excel in folios_salidas.get(x["codigo"], []):
                cursor.execute("""
                    UPDATE salidas SET producto_id = ?, es_servicio = 0
                    WHERE folio_excel = ? AND es_servicio = 1 AND producto_id IS NULL
                """, (nuevo_id, folio_excel))
                if cursor.rowcount:
                    reenlazadas_salidas += cursor.rowcount

        except Exception as e:
            errores.append((x["codigo"], str(e)))

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print("✅ COMPLETADO")
    print("=" * 80)
    print(f"  Productos completados (CASO A):        {completados}")
    print(f"  Productos creados (CASO B):             {creados}")
    print(f"  Entradas re-ligadas al nuevo producto:  {reenlazadas_entradas}")
    print(f"  Salidas re-ligadas al nuevo producto:   {reenlazadas_salidas}")
    if errores:
        print(f"\n⚠️  {len(errores)} errores:")
        for cod, err in errores[:20]:
            print(f"    {cod}: {err}")


if __name__ == "__main__":
    main()
