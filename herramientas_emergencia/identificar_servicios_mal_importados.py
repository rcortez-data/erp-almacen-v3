#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
IDENTIFICAR SERVICIOS MAL IMPORTADOS
====================================

Busca servicios que fueron importados como PRODUCTOS (código = "SERVICIO")
y deberían ser SERVICIOS (es_servicio = 1).

Muestra qué necesita corregirse.
"""

import sqlite3
import sys

def identificar():
    """Identifica servicios mal importados"""
    
    conn = sqlite3.connect("almacen.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 80)
    print("IDENTIFICAR SERVICIOS MAL IMPORTADOS")
    print("=" * 80)
    
    # Buscar productos con código "SERVICIO"
    cursor.execute("""
        SELECT id, codigo, descripcion FROM productos 
        WHERE UPPER(codigo) = 'SERVICIO'
    """)
    
    prod_servicio = cursor.fetchone()
    
    if not prod_servicio:
        print("\n❌ No se encontró producto con código 'SERVICIO'")
        print("\nEsto significa:")
        print("  • Los servicios NO se importaron como producto 'SERVICIO'")
        print("  • Probablemente se simplificaron a otros nombres")
        print("  • Se necesita análisis más profundo")
        conn.close()
        return
    
    prod_id = prod_servicio['id']
    
    print(f"\n✓ Encontrado producto 'SERVICIO' (ID {prod_id})")
    print(f"  Descripción: {prod_servicio['descripcion']}")
    
    # Buscar entradas de este producto
    cursor.execute("""
        SELECT e.id, e.folio, e.no_factura, e.cantidad, e.precio_unitario,
               e.es_servicio, e.concepto_servicio, e.fecha
        FROM entradas e
        WHERE e.producto_id = ?
        ORDER BY e.no_factura DESC, e.id DESC
    """, (prod_id,))
    
    entradas = cursor.fetchall()
    
    if not entradas:
        print(f"\n❌ No hay entradas con producto 'SERVICIO'")
        conn.close()
        return
    
    print(f"\n📊 Entradas encontradas: {len(entradas)}")
    print("-" * 80)
    
    mal_importadas = []
    
    for entrada in entradas:
        print(f"\n{entrada['folio']} | Factura: {entrada['no_factura']}")
        print(f"  ID: {entrada['id']}")
        print(f"  Cantidad: {entrada['cantidad']}")
        print(f"  Precio: ${entrada['precio_unitario']}")
        print(f"  es_servicio: {entrada['es_servicio']}")
        print(f"  concepto_servicio: {entrada['concepto_servicio']}")
        
        # Si es_servicio = 0, está mal importado
        if not entrada['es_servicio']:
            print(f"  ⚠️  MAL IMPORTADO (debe ser servicio, no producto)")
            mal_importadas.append(entrada)
    
    print("\n" + "=" * 80)
    print(f"\n📊 RESUMEN:")
    print(f"  Total de entradas: {len(entradas)}")
    print(f"  Mal importadas: {len(mal_importadas)}")
    
    if mal_importadas:
        print(f"\n🛠️ NECESITA CORRECCIÓN:")
        
        # Información para corrección
        print(f"\nIDs de entradas a corregir:")
        ids = [str(e['id']) for e in mal_importadas]
        print(f"  {', '.join(ids)}")
        
        print(f"\nFacturas afectadas:")
        facturas = set(e['no_factura'] for e in mal_importadas if e['no_factura'])
        for f in sorted(facturas):
            print(f"  • {f}")
    
    print("\n" + "=" * 80)
    print("✅ Análisis completado")
    print("\nPróximo paso: Usar script de corrección para convertir estos")
    print("servicios de PRODUCTOS a SERVICIOS correctamente.")
    
    conn.close()

if __name__ == "__main__":
    try:
        identificar()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)
