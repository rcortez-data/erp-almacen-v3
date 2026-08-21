#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
IMPORTAR PRODUCTOS DESDE WAR MACHINE (Catalogo + Maquinados)
==============================================================

Lee el Excel "War Machine 2026 OK.xlsm" y carga/actualiza la tabla
'productos' del ERP para que se vean reflejados en la hoja de Productos
(y por lo tanto en el módulo de Inventario / Stocks).

FUENTES EN EL EXCEL:
  Hoja "Catalogo" (encabezados en fila 20, datos desde fila 21):
    D=Código  E=Producto  F=Descripción  G=Cantidad  H=Unidad
    I=Departamento  J=Categoria  K=Ubicación

  Hoja "Maquinados" (encabezados en fila 23, datos desde fila 24):
    C=Código  D=Producto  E=Descripción  F=Cantidad  G=Ubicación  H=Máquina
    (no trae Departamento/Categoria -> se asignan fijos, ver abajo)

  Hoja "Entradas" (encabezados en fila 1):
    A=Codigo  L=Proveedor
    -> se usa para obtener el proveedor más reciente de cada código de
       producto. NO se agrega nada a la tabla 'proveedores'; el nombre
       se guarda tal cual en productos.proveedor_nombre_historico.

REGLAS DE MAPEO (confirmadas con el usuario):
  - descripcion final del producto = "{Producto} {Descripción}" concatenado
  - Catalogo:   departamento = columna I (tal cual),  categoria = columna J (tal cual)
  - Maquinados: departamento = "MAQUINADO" (fijo),    categoria = columna H (Máquina)
  - stock_actual se actualiza con la columna Cantidad de cada hoja
  - Si el código YA existe en productos -> se SOBRESCRIBEN descripcion,
    departamento, categoria, proveedor y stock_actual con lo del Excel
  - Si el código NO existe -> se inserta como producto nuevo

IMPORTANTE - LISTAS MAESTRAS (categorias / proveedores):
  Este script YA NO agrega renglones nuevos a las tablas 'categorias' ni
  'proveedores'. La información de categoria/departamento/proveedor del
  Excel SIEMPRE se conserva (nunca se pierde), pero:
    - categoria_id solo se llena si el texto del Excel coincide
      (sin importar mayúsculas/acentos) con una categoría que YA existe
      en la tabla 'categorias'. Si no hay coincidencia, categoria_id
      queda en NULL y el texto tal cual del Excel se guarda en
      productos.categoria_nombre_historico.
    - proveedor_nombre_historico se llena siempre con el texto tal cual
      del Excel, pero nunca se crea un renglón nuevo en 'proveedores'.
    - departamento es un campo de texto libre en productos (no existe
      tabla de departamentos), así que no hay ninguna "lista" que
      pueda crecer con este campo.

USO:
    python herramientas_emergencia/importar_productos_war_machine.py
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

DEPARTAMENTO_FIJO_MAQUINADOS = "MAQUINADO"


def limpiar(valor):
    """Convierte a texto limpio (sin espacios extra) o None."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto if texto else None


def concatenar_descripcion(producto, descripcion):
    partes = [p for p in (limpiar(producto), limpiar(descripcion)) if p]
    return " ".join(partes)


def leer_catalogo(wb):
    """Devuelve lista de dicts leídos de la hoja Catalogo (desde fila 21)."""
    ws = wb["Catalogo"]
    filas = []
    for row in ws.iter_rows(min_row=21, min_col=4, max_col=11, values_only=True):
        codigo, producto, descripcion, cantidad, unidad, departamento, categoria, ubicacion = row
        codigo = limpiar(codigo)
        if not codigo:
            continue
        filas.append({
            "codigo": codigo,
            "descripcion": concatenar_descripcion(producto, descripcion),
            "stock": cantidad if isinstance(cantidad, (int, float)) else 0,
            "unidad": limpiar(unidad) or "PIEZA",
            "departamento": limpiar(departamento),
            "categoria": limpiar(categoria),
            "ubicacion": limpiar(ubicacion),
            "origen": "Catalogo",
        })
    return filas


def leer_maquinados(wb):
    """Devuelve lista de dicts leídos de la hoja Maquinados (desde fila 24)."""
    ws = wb["Maquinados"]
    filas = []
    for row in ws.iter_rows(min_row=24, min_col=3, max_col=8, values_only=True):
        codigo, producto, descripcion, cantidad, ubicacion, maquina = row
        codigo = limpiar(codigo)
        if not codigo:
            continue
        filas.append({
            "codigo": codigo,
            "descripcion": concatenar_descripcion(producto, descripcion),
            "stock": cantidad if isinstance(cantidad, (int, float)) else 0,
            "unidad": "PIEZA",
            "departamento": DEPARTAMENTO_FIJO_MAQUINADOS,
            "categoria": limpiar(maquina),
            "ubicacion": limpiar(ubicacion),
            "origen": "Maquinados",
        })
    return filas


def leer_proveedor_por_codigo(wb):
    """
    Recorre la hoja Entradas y arma {codigo: proveedor_mas_reciente}.
    Se queda con la ÚLTIMA fila encontrada de cada código (la hoja está
    capturada en orden cronológico, así que la última fila = la más
    reciente). No se agrega nada a la tabla 'proveedores' con esto.
    """
    ws = wb["Entradas"]
    mapa = {}
    for row in ws.iter_rows(min_row=2, min_col=1, max_col=12, values_only=True):
        codigo = limpiar(row[0])       # columna A
        proveedor = limpiar(row[11])   # columna L
        if codigo and proveedor:
            mapa[codigo] = proveedor  # la última fila del código gana
    return mapa


def buscar_categoria_existente(cursor, nombre, cache):
    """
    Busca una categoría YA EXISTENTE en la tabla 'categorias' (comparación
    sin distinguir mayúsculas/acentos). Si no existe, regresa None y NO
    crea nada nuevo: el nombre tal cual del Excel se conserva por separado
    en categoria_nombre_historico.
    """
    if not nombre:
        return None
    clave = nombre.strip().upper()
    if clave in cache:
        return cache[clave]
    cursor.execute(
        "SELECT id FROM categorias WHERE UPPER(nombre) = ?", (clave,)
    )
    row = cursor.fetchone()
    resultado = row["id"] if row else None
    cache[clave] = resultado
    return resultado


def main():
    print("=" * 80)
    print("IMPORTAR PRODUCTOS DESDE WAR MACHINE (Catalogo + Maquinados)")
    print("=" * 80)

    if not os.path.exists(ARCHIVO_EXCEL):
        print(f"\n❌ No se encontró el archivo: {ARCHIVO_EXCEL}")
        return

    print(f"\n📊 Cargando '{os.path.basename(ARCHIVO_EXCEL)}'...")
    wb = openpyxl.load_workbook(ARCHIVO_EXCEL, data_only=True, read_only=True)

    print("  Leyendo hoja 'Catalogo'...")
    filas_catalogo = leer_catalogo(wb)
    print(f"  ✓ {len(filas_catalogo)} productos leídos")

    print("  Leyendo hoja 'Maquinados'...")
    filas_maquinados = leer_maquinados(wb)
    print(f"  ✓ {len(filas_maquinados)} productos leídos")

    print("  Leyendo proveedores de hoja 'Entradas'...")
    mapa_proveedores = leer_proveedor_por_codigo(wb)
    print(f"  ✓ {len(mapa_proveedores)} códigos con proveedor identificado")

    wb.close()

    for f in filas_catalogo + filas_maquinados:
        f["proveedor"] = mapa_proveedores.get(f["codigo"])

    todas_filas = filas_catalogo + filas_maquinados

    # Detectar códigos duplicados entre las dos hojas (por si acaso)
    vistos = {}
    duplicados = []
    for f in todas_filas:
        if f["codigo"] in vistos:
            duplicados.append(f["codigo"])
        vistos[f["codigo"]] = f
    if duplicados:
        print(f"\n⚠️  {len(duplicados)} códigos aparecen en ambas hojas; se usará el de Maquinados (se procesa al final).")

    conn = get_db()
    cursor = conn.cursor()

    # Contar cuántos ya existen vs cuántos son nuevos
    cursor.execute("SELECT codigo FROM productos")
    existentes = {row["codigo"] for row in cursor.fetchall()}

    a_actualizar = [f for f in todas_filas if f["codigo"] in existentes]
    a_insertar = [f for f in todas_filas if f["codigo"] not in existentes]

    print("\n" + "=" * 80)
    print("📝 RESUMEN DE CAMBIOS:")
    print("=" * 80)
    print(f"  Productos a ACTUALIZAR (código ya existe): {len(a_actualizar)}")
    print(f"  Productos a INSERTAR (código nuevo):        {len(a_insertar)}")
    print(f"  (No se agregará ningún renglón nuevo a 'categorias' ni 'proveedores')")

    print("\n  Ejemplos (primeros 5 a insertar):")
    for f in a_insertar[:5]:
        print(f"    [{f['origen']}] {f['codigo']} | {f['descripcion'][:60]} | depto={f['departamento']} | cat={f['categoria']} | stock={f['stock']}")

    print("\n  Ejemplos (primeros 5 a actualizar):")
    for f in a_actualizar[:5]:
        print(f"    [{f['origen']}] {f['codigo']} | {f['descripcion'][:60]} | depto={f['departamento']} | cat={f['categoria']} | stock={f['stock']}")

    print("\n" + "=" * 80)
    respuesta = input("\n¿Confirmar importación? (escribe SI): ").strip().upper()
    if respuesta != "SI":
        print("Cancelado. No se hizo ningún cambio.")
        conn.close()
        return

    cache_categorias = {}
    actualizados = 0
    insertados = 0
    sin_categoria_conocida = set()
    errores = []

    print("\n⏳ Aplicando cambios...")

    for f in todas_filas:
        try:
            categoria_id = buscar_categoria_existente(cursor, f["categoria"], cache_categorias)
            if f["categoria"] and categoria_id is None:
                sin_categoria_conocida.add(f["categoria"])

            if f["codigo"] in existentes:
                cursor.execute("""
                    UPDATE productos
                    SET descripcion = ?,
                        departamento = ?,
                        categoria_id = ?,
                        categoria_nombre_historico = ?,
                        departamento_nombre_historico = ?,
                        proveedor_nombre_historico = ?,
                        unidad_medida = ?,
                        ubicacion = COALESCE(?, ubicacion),
                        stock_actual = ?
                    WHERE codigo = ?
                """, (
                    f["descripcion"], f["departamento"], categoria_id, f["categoria"],
                    f["departamento"], f["proveedor"], f["unidad"], f["ubicacion"],
                    f["stock"], f["codigo"]
                ))
                actualizados += 1
            else:
                cursor.execute("""
                    INSERT INTO productos
                        (codigo, descripcion, categoria_id, categoria_nombre_historico,
                         unidad_medida, ubicacion, departamento, departamento_nombre_historico,
                         proveedor_nombre_historico, stock_actual, activo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    f["codigo"], f["descripcion"], categoria_id, f["categoria"],
                    f["unidad"], f["ubicacion"], f["departamento"], f["departamento"],
                    f["proveedor"], f["stock"]
                ))
                insertados += 1
                existentes.add(f["codigo"])  # evita doble insert si se repite el código

        except Exception as e:
            errores.append((f["codigo"], str(e)))

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print("✅ IMPORTACIÓN COMPLETADA")
    print("=" * 80)
    print(f"  Productos actualizados: {actualizados}")
    print(f"  Productos insertados:   {insertados}")
    print(f"  Categorías/proveedores nuevos agregados a listas maestras: 0 (por diseño)")
    if sin_categoria_conocida:
        print(f"\n  ℹ️  {len(sin_categoria_conocida)} valores de categoría del Excel no existen")
        print("     todavía en tu tabla 'categorias'. Se guardaron en categoria_nombre_historico")
        print("     de cada producto, pero categoria_id quedó vacío. Ejemplos:")
        for nombre in list(sin_categoria_conocida)[:10]:
            print(f"       - {nombre}")
    if errores:
        print(f"\n⚠️  {len(errores)} errores durante la importación:")
        for codigo, err in errores[:20]:
            print(f"    {codigo}: {err}")


if __name__ == "__main__":
    main()
