#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para inicializar bloques predefinidos en el balance mensual.
Ejecutar una sola vez después de agregar las tablas bloques_balance y bloque_productos.

Uso:
    python inicializar_bloques.py
"""

from database import get_db
import sys

# Productos del BLOQUE 1: Insumos Producción (16 artículos)
PRODUCTOS_PRODUCCION = [
    "PLAYO 18''",
    "PLAYO 5\"",
    "CINTA CANELA",
    "CINTA DOBLE IMPACTO",
    "MASKING 3/4''",
    "MASKING 2''",
    "FLEJE BLANCO 5 mm",
    "FLEJE VERDE 8.7 mm",
    "ALAMBRE COBRIZADO 0.30",
    "ALAMBRE COBRIZADO 0.23",
    "ALAMBRE COBRIZADO 0.20",
    "ALAMBRE GALVANIZADO 0.20",
    "RAFIA",
    "ADHESIVO 8107",
    "HOT MELT",
    "ADHESIVO R-500",
]

# Productos del BLOQUE 2: Insumos Caldera (16 artículos)
PRODUCTOS_CALDERA = [
    "ALMIDON ALMEX",
    "ALMIDON CPI",
    "ANTIESPUMANTE",
    "SOSA",
    "BORAX",
    "RESINA 181",
    "RESINA 174",
    "RESINA 179",
    "SAL",
    "ADITIVO CF-7",
    "CINTA KADILEMA CTS-1006",
    "CINTA KADILEMA CTS-1003PS",
    "REC-405",
    "EP-6011",
    "CERA CASCADING WAX (sin uso)",
    "BIOCIDA",
]


def main():
    conn = get_db()
    c = conn.cursor()

    try:
        # ========================================
        # 1. Crear BLOQUE 1: Insumos Producción
        # ========================================
        print("📦 Creando Bloque 1: Insumos Producción...")
        c.execute("""
            INSERT OR IGNORE INTO bloques_balance (nombre, descripcion)
            VALUES (?, ?)
        """, ("Insumos Producción", "Artículos para fabricación y producción"))
        conn.commit()

        # Obtener ID del bloque recién creado
        bloque_1 = c.execute(
            "SELECT id FROM bloques_balance WHERE nombre=?",
            ("Insumos Producción",)
        ).fetchone()

        if not bloque_1:
            print("❌ Error: No se pudo crear el bloque 1")
            return False

        bloque_1_id = bloque_1['id']
        print(f"   ✓ Bloque creado con ID: {bloque_1_id}")

        # Asociar productos al bloque 1
        productos_encontrados = 0
        productos_no_encontrados = []
        
        for orden, desc in enumerate(PRODUCTOS_PRODUCCION, start=1):
            producto = c.execute(
                "SELECT id FROM productos WHERE descripcion LIKE ? LIMIT 1",
                (f"%{desc}%",)
            ).fetchone()

            if producto:
                c.execute("""
                    INSERT OR IGNORE INTO bloque_productos
                    (bloque_id, producto_id, orden)
                    VALUES (?, ?, ?)
                """, (bloque_1_id, producto['id'], orden))
                productos_encontrados += 1
                print(f"   ✓ [{orden:2d}] {desc}")
            else:
                productos_no_encontrados.append(desc)
                print(f"   ✗ [{orden:2d}] {desc} (NO ENCONTRADO)")

        conn.commit()
        print(f"   → {productos_encontrados}/16 productos asociados\n")

        # ========================================
        # 2. Crear BLOQUE 2: Insumos Caldera
        # ========================================
        print("🔧 Creando Bloque 2: Insumos Caldera...")
        c.execute("""
            INSERT OR IGNORE INTO bloques_balance (nombre, descripcion)
            VALUES (?, ?)
        """, ("Insumos Caldera", "Artículos para calderas y tratamiento de agua"))
        conn.commit()

        # Obtener ID del bloque recién creado
        bloque_2 = c.execute(
            "SELECT id FROM bloques_balance WHERE nombre=?",
            ("Insumos Caldera",)
        ).fetchone()

        if not bloque_2:
            print("❌ Error: No se pudo crear el bloque 2")
            return False

        bloque_2_id = bloque_2['id']
        print(f"   ✓ Bloque creado con ID: {bloque_2_id}")

        # Asociar productos al bloque 2
        productos_encontrados_2 = 0
        productos_no_encontrados_2 = []

        for orden, desc in enumerate(PRODUCTOS_CALDERA, start=1):
            producto = c.execute(
                "SELECT id FROM productos WHERE descripcion LIKE ? LIMIT 1",
                (f"%{desc}%",)
            ).fetchone()

            if producto:
                c.execute("""
                    INSERT OR IGNORE INTO bloque_productos
                    (bloque_id, producto_id, orden)
                    VALUES (?, ?, ?)
                """, (bloque_2_id, producto['id'], orden))
                productos_encontrados_2 += 1
                print(f"   ✓ [{orden:2d}] {desc}")
            else:
                productos_no_encontrados_2.append(desc)
                print(f"   ✗ [{orden:2d}] {desc} (NO ENCONTRADO)")

        conn.commit()
        print(f"   → {productos_encontrados_2}/16 productos asociados\n")

        # ========================================
        # 3. Resumen final
        # ========================================
        print("=" * 70)
        print(f"✓ INICIALIZACIÓN COMPLETADA")
        print("=" * 70)
        print(f"Bloque 1 (Insumos Producción): {productos_encontrados}/16 ✓")
        print(f"Bloque 2 (Insumos Caldera):    {productos_encontrados_2}/16 ✓")
        print(f"\nTotal: {productos_encontrados + productos_encontrados_2}/32 productos asociados")

        if productos_no_encontrados or productos_no_encontrados_2:
            print("\n⚠️  PRODUCTOS NO ENCONTRADOS:")
            if productos_no_encontrados:
                print("\n   Bloque 1:")
                for p in productos_no_encontrados:
                    print(f"      • {p}")
            if productos_no_encontrados_2:
                print("\n   Bloque 2:")
                for p in productos_no_encontrados_2:
                    print(f"      • {p}")
            print("\n💡 Tip: Verifica que los nombres exactos coincidan con los de la BD.")
            print("   Puedes buscar productos en: Inventario → Productos")
        else:
            print("\n✅ ¡Todos los productos fueron encontrados y asociados!")

        print("\n" + "=" * 70)
        print("Ahora puedes usar los bloques en Balance → Cargar bloques predefinidos")
        print("=" * 70)

        conn.close()
        return True

    except Exception as e:
        print(f"\n❌ Error durante la inicialización: {str(e)}")
        import traceback
        traceback.print_exc()
        conn.close()
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
