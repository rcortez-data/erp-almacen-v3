#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RECUPERAR DEPARTAMENTOS EN ENTRADAS
====================================

Este script llena el campo 'departamento' en la tabla 'entradas'
basándose en los departamentos históricos (o actuales) de los productos.

QUÉ HACE:
  1. Para cada entrada, busca el producto vinculado
  2. Obtiene su departamento:
     a) Si tiene departamento actual → lo usa
     b) Si está archivado → recupera de 'departamento_nombre_historico'
  3. Completa el campo 'departamento' en la entrada

ESTRATEGIA:
  • Si entrada no tiene departamento:
    └─ Busca el producto de esa entrada
    └─ Copia su departamento (actual o histórico)

  • Entradas sin producto:
    └─ Se asigna departamento por defecto: "PRODUCCIÓN"

RESULTADO:
  ✅ Todas las entradas tienen departamento
  ✅ Reporte diario muestra departamento completo
  ✅ No se pierden datos históricos

USO:
    python recuperar_departamentos_entradas.py
"""

from database import get_db
import sys

def main():
    conn = get_db()
    cursor = conn.cursor()
    
    # Configurar row factory para obtener filas como diccionarios
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    
    print("=" * 80)
    print("RECUPERAR DEPARTAMENTOS EN ENTRADAS")
    print("=" * 80)
    
    # 1. Contar entradas sin departamento
    cursor.execute("""
        SELECT COUNT(*) as total FROM entradas 
        WHERE departamento IS NULL OR departamento = ''
    """)
    row = cursor.fetchone()
    total_sin_depto = row['total'] if row else 0
    
    print(f"\n📊 ANÁLISIS:")
    print(f"  Entradas SIN departamento: {total_sin_depto}")
    
    # 2. Ver cuáles productos tienen departamento histórico
    cursor.execute("""
        SELECT COUNT(DISTINCT id) as total FROM productos
        WHERE departamento_nombre_historico IS NOT NULL 
        AND departamento_nombre_historico != ''
    """)
    row = cursor.fetchone()
    productos_con_historico = row['total'] if row else 0
    print(f"  Productos con departamento histórico: {productos_con_historico}")
    
    # 3. Ver departamentos disponibles
    cursor.execute("""
        SELECT DISTINCT departamento FROM productos
        WHERE departamento IS NOT NULL AND departamento != ''
        ORDER BY departamento
    """)
    deptos_actuales = [row['departamento'] for row in cursor.fetchall()]
    print(f"  Departamentos actuales en productos: {deptos_actuales if deptos_actuales else '(ninguno)'}")
    
    cursor.execute("""
        SELECT DISTINCT departamento_nombre_historico FROM productos
        WHERE departamento_nombre_historico IS NOT NULL 
        AND departamento_nombre_historico != ''
        ORDER BY departamento_nombre_historico
    """)
    deptos_historicos = [row['departamento_nombre_historico'] for row in cursor.fetchall()]
    print(f"  Departamentos históricos: {deptos_historicos if deptos_historicos else '(ninguno)'}")
    
    if not total_sin_depto:
        print("\n✅ Todas las entradas ya tienen departamento. No hay nada que hacer.")
        conn.close()
        return
    
    # Confirmar
    print("\n" + "=" * 80)
    print("¿CONFIRMAS?")
    print("Se llenará 'departamento' en entradas vacías usando:")
    print("  • Departamento actual del producto (si existe)")
    print("  • Departamento histórico del producto (si está archivado)")
    print("  • Departamento por defecto 'PRODUCCIÓN' (si no hay producto)")
    print("=" * 80)
    
    resp = input("\n¿Continuar? (escribe SI): ").strip().upper()
    if resp != 'SI':
        print("Cancelado. No se hizo ningún cambio.")
        conn.close()
        return
    
    # ACTUALIZACIÓN 1: Entradas con producto → copiar departamento
    print("\n⏳ Paso 1: Llenando departamento desde productos...")
    
    cursor.execute("""
        UPDATE entradas SET departamento = COALESCE(
            (SELECT p.departamento FROM productos p WHERE p.id = entradas.producto_id),
            (SELECT p.departamento_nombre_historico FROM productos p WHERE p.id = entradas.producto_id),
            'PRODUCCIÓN'
        )
        WHERE (departamento IS NULL OR departamento = '')
        AND producto_id IS NOT NULL
    """)
    actualizadas_1 = cursor.rowcount
    conn.commit()
    print(f"  ✓ {actualizadas_1} entradas actualizadas desde productos")
    
    # ACTUALIZACIÓN 2: Entradas sin producto → departamento por defecto
    print("\n⏳ Paso 2: Asignando departamento por defecto a entradas sin producto...")
    
    cursor.execute("""
        UPDATE entradas SET departamento = 'PRODUCCIÓN'
        WHERE (departamento IS NULL OR departamento = '')
        AND producto_id IS NULL
    """)
    actualizadas_2 = cursor.rowcount
    conn.commit()
    print(f"  ✓ {actualizadas_2} entradas asignadas a 'PRODUCCIÓN'")
    
    # Verificación final
    print("\n⏳ Paso 3: Verificación final...")
    
    cursor.execute("SELECT COUNT(*) as total FROM entradas WHERE departamento IS NULL OR departamento = ''")
    row = cursor.fetchone()
    aun_sin_depto = row['total'] if row else 0
    
    cursor.execute("""
        SELECT departamento, COUNT(*) as total FROM entradas
        WHERE departamento IS NOT NULL AND departamento != ''
        GROUP BY departamento
        ORDER BY total DESC
    """)
    distribucion = cursor.fetchall()
    
    print(f"\n  Entradas aún sin departamento: {aun_sin_depto}")
    print(f"\n  Distribución de departamentos:")
    for row in distribucion:
        print(f"    • {row['departamento']}: {row['total']} entradas")
    
    print("\n" + "=" * 80)
    print("✅ LISTO")
    print(f"   Total actualizado: {actualizadas_1 + actualizadas_2} entradas")
    print(f"   Ahora el reporte diario mostrará departamento en todas las entradas")
    print("=" * 80)
    
    conn.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)
