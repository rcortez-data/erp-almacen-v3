#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CONVERTIR SERVICIOS IMPORTADOS
==============================

Convierte servicios que fueron importados como PRODUCTOS
(código = "SERVICIO") a SERVICIOS REALES (es_servicio = 1).

Busca en el Excel los conceptos correctos y los asigna.
"""

import sqlite3
import openpyxl
import sys

def convertir_servicios():
    """Convierte servicios importados como productos → servicios reales"""
    
    conn = sqlite3.connect("almacen.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 80)
    print("CONVERTIR SERVICIOS IMPORTADOS COMO PRODUCTOS → SERVICIOS REALES")
    print("=" * 80)
    
    # Paso 1: Buscar producto "SERVICIO"
    print("\n🔍 PASO 1: Buscando producto 'SERVICIO'...")
    cursor.execute("""
        SELECT id, codigo, descripcion FROM productos 
        WHERE UPPER(codigo) = 'SERVICIO'
    """)
    
    prod_servicio = cursor.fetchone()
    
    if not prod_servicio:
        print("❌ No se encontró producto con código 'SERVICIO'")
        print("\nEsto significa:")
        print("  • Los servicios no se importaron con ese código")
        print("  • Probablemente se importaron correctamente ya")
        print("  • O están bajo otro nombre")
        conn.close()
        return
    
    prod_id = prod_servicio['id']
    print(f"✓ Encontrado: ID {prod_id}, Código '{prod_servicio['codigo']}'")
    
    # Paso 2: Buscar entradas de este producto
    print("\n📋 PASO 2: Buscando entradas con este producto...")
    cursor.execute("""
        SELECT e.id, e.folio, e.no_factura, e.cantidad, e.precio_unitario,
               e.es_servicio, e.concepto_servicio, e.fecha
        FROM entradas e
        WHERE e.producto_id = ?
        ORDER BY e.no_factura DESC, e.id DESC
    """, (prod_id,))
    
    entradas = cursor.fetchall()
    
    if not entradas:
        print(f"❌ No hay entradas con producto 'SERVICIO'")
        conn.close()
        return
    
    print(f"✓ Encontradas {len(entradas)} entradas")
    
    # Paso 3: Cargar Excel para obtener conceptos correctos
    print("\n📊 PASO 3: Cargando Excel para obtener conceptos correctos...")
    
    archivo_excel = "War Machine 2026 OK.xlsm"
    
    try:
        wb = openpyxl.load_workbook(archivo_excel, data_only=True)
        ws = wb['Entradas']
        
        # Crear mapeo de factura → concepto completo
        mapeo_servicios = {}
        
        for row in range(2, ws.max_row + 1):
            codigo = ws.cell(row, 1).value
            factura = ws.cell(row, 11).value
            desc_completa = ws.cell(row, 16).value
            
            if codigo and str(codigo).strip().upper() == "SERVICIO" and factura:
                mapeo_servicios[str(factura).strip()] = desc_completa
        
        print(f"✓ Encontrados {len(mapeo_servicios)} servicios en Excel")
        wb.close()
        
    except Exception as e:
        print(f"⚠️  No se pudo cargar Excel: {e}")
        print("Continuaré sin conceptos del Excel")
        mapeo_servicios = {}
    
    # Paso 4: Mostrar qué se va a cambiar
    print("\n" + "=" * 80)
    print("📝 RESUMEN DE CAMBIOS:")
    print("=" * 80)
    
    cambios_a_hacer = []
    
    for entrada in entradas:
        factura_key = str(entrada['no_factura']).strip() if entrada['no_factura'] else None
        concepto_nuevo = mapeo_servicios.get(factura_key, f"Servicio Factura {factura_key}")
        
        cambios_a_hacer.append({
            'entrada_id': entrada['id'],
            'folio': entrada['folio'],
            'factura': entrada['no_factura'],
            'concepto_nuevo': concepto_nuevo,
            'precio': entrada['precio_unitario']
        })
        
        print(f"\n{entrada['folio']} | Factura {entrada['no_factura']}")
        print(f"  Nuevo concepto: {concepto_nuevo}")
        print(f"  Precio: ${entrada['precio_unitario']}")
        print(f"  Cambios: es_servicio: 0→1, concepto_servicio: vacío→'{concepto_nuevo}', producto_id: {prod_id}→NULL")
    
    # Paso 5: Pedir confirmación
    print("\n" + "=" * 80)
    print(f"\nTOTAL A CONVERTIR: {len(cambios_a_hacer)} servicios")
    respuesta = input("\n¿Confirmar conversión? (escribe SI): ").strip().upper()
    
    if respuesta != 'SI':
        print("Cancelado. No se hizo cambios.")
        conn.close()
        return
    
    # Paso 6: Aplicar cambios
    print(f"\n⏳ Aplicando {len(cambios_a_hacer)} cambios...")
    
    cambios_exitosos = 0
    
    for cambio in cambios_a_hacer:
        try:
            cursor.execute("""
                UPDATE entradas
                SET es_servicio = 1,
                    concepto_servicio = ?,
                    producto_id = NULL
                WHERE id = ?
            """, (cambio['concepto_nuevo'], cambio['entrada_id']))
            
            cambios_exitosos += 1
            print(f"  ✓ {cambio['folio']} - Convertido")
            
        except Exception as e:
            print(f"  ❌ {cambio['folio']} - Error: {e}")
    
    conn.commit()
    
    # Paso 7: Resumen final
    print("\n" + "=" * 80)
    print("✅ RESUMEN FINAL:")
    print("=" * 80)
    print(f"\nCambios exitosos: {cambios_exitosos}/{len(cambios_a_hacer)}")
    
    if cambios_exitosos == len(cambios_a_hacer):
        print("\n✅ ¡CONVERSIÓN COMPLETADA EXITOSAMENTE!")
        print("\nAhora:")
        print("  1. Abre el ERP")
        print("  2. Ve a Entradas")
        print("  3. Busca factura 11026")
        print("  4. Verifica que es_servicio = 1 y tiene el concepto correcto")
    else:
        print(f"\n⚠️  {len(cambios_a_hacer) - cambios_exitosos} cambios fallaron")
        print("Verifica los errores arriba")
    
    conn.close()

if __name__ == "__main__":
    try:
        convertir_servicios()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
