#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ACTUALIZAR CONVERSIONES DE PRODUCTOS
=====================================

Script para configurar rápidamente productos con conversión de unidades.

Ejemplo:
  Rafia: llega en KILO, se usa en PIEZA, factor 4

Uso:
    python actualizar_conversiones_productos.py
"""

import sqlite3
import sys

def configurar_conversiones():
    """Configura productos con conversión de unidades"""
    
    conn = sqlite3.connect("almacen.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 80)
    print("CONFIGURAR CONVERSIONES DE UNIDADES EN PRODUCTOS")
    print("=" * 80)
    
    # Lista de conversiones a aplicar
    conversiones = [
        {
            'codigo': 'RAF',
            'nombre': 'RAFIA',
            'unidad_medida': 'PIEZA',
            'unidad_compra': 'KILO',
            'factor': 4.0,
            'descripcion': '4 kilos = 1 pieza'
        },
        # Agrega más aquí según necesites:
        # {
        #     'codigo': 'TEL',
        #     'nombre': 'TELA',
        #     'unidad_medida': 'METRO',
        #     'unidad_compra': 'ROLLO',
        #     'factor': 50.0,
        #     'descripcion': '50 metros = 1 rollo'
        # },
    ]
    
    print("\n📋 CONVERSIONES A APLICAR:")
    print("-" * 80)
    
    for i, conv in enumerate(conversiones, 1):
        print(f"\n{i}. {conv['nombre']} ({conv['codigo']})")
        print(f"   Unidad de Medida: {conv['unidad_medida']}")
        print(f"   Unidad de Compra: {conv['unidad_compra']}")
        print(f"   Factor: {conv['factor']} → {conv['descripcion']}")
    
    print("\n" + "=" * 80)
    respuesta = input("\n¿Continuar con la actualización? (escribe SI): ").strip().upper()
    
    if respuesta != 'SI':
        print("Cancelado. No se hizo ningún cambio.")
        conn.close()
        return
    
    # Aplicar conversiones
    print("\n⏳ Aplicando conversiones...")
    print("-" * 80)
    
    actualizados = 0
    no_encontrados = []
    
    for conv in conversiones:
        # Buscar producto
        cursor.execute("SELECT id FROM productos WHERE codigo = ?", (conv['codigo'],))
        producto = cursor.fetchone()
        
        if not producto:
            no_encontrados.append(conv['codigo'])
            print(f"❌ {conv['nombre']} ({conv['codigo']}): NO ENCONTRADO")
            continue
        
        # Actualizar
        cursor.execute("""
            UPDATE productos 
            SET unidad_medida = ?, 
                unidad_compra = ?, 
                factor_conversion = ?
            WHERE id = ?
        """, (conv['unidad_medida'], conv['unidad_compra'], conv['factor'], producto['id']))
        
        actualizados += 1
        print(f"✓ {conv['nombre']} ({conv['codigo']}): ACTUALIZADO")
        print(f"  {conv['unidad_compra']} → {conv['unidad_medida']} (factor: {conv['factor']})")
    
    conn.commit()
    
    print("\n" + "=" * 80)
    print("✅ RESULTADO")
    print("=" * 80)
    print(f"\nProductos actualizados: {actualizados}")
    if no_encontrados:
        print(f"Productos no encontrados: {', '.join(no_encontrados)}")
    
    print("\n" + "=" * 80)
    print("PRÓXIMAS ACCIONES:")
    print("-" * 80)
    print("\n1. Abre ERP → Entradas → Nueva entrada")
    print("2. Selecciona un producto con conversión (ej: RAFIA)")
    print("3. Verifica que la interfaz muestre la conversión")
    print("4. Captura cantidad en unidad de compra (ej: 412 kilos)")
    print("5. Sistema debería mostrar la conversión automáticamente")
    print("\n✅ ¡LISTO!")
    
    conn.close()

if __name__ == "__main__":
    try:
        configurar_conversiones()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)
