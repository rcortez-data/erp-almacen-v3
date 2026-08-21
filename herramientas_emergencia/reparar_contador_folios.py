#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
REPARAR CONTADOR DE FOLIOS
===========================

Script para corregir el contador de folios cuando hay error de duplicado.

El problema: El contador se adelantó pero no todas las entradas se guardaron.
Solución: Reiniciar el contador al valor correcto.
"""

import sqlite3
import sys

def reparar_folios():
    """Repara el contador de folios"""
    
    conn = sqlite3.connect("almacen.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 80)
    print("REPARAR CONTADOR DE FOLIOS")
    print("=" * 80)
    
    # Encontrar el folio más alto actualmente usado
    cursor.execute("""
        SELECT MAX(CAST(SUBSTR(folio, 5) AS INTEGER)) as max_folio
        FROM entradas 
        WHERE folio LIKE 'ENT-%'
    """)
    
    result = cursor.fetchone()
    max_folio = result['max_folio'] if result['max_folio'] else 0
    
    print(f"\n📊 ANÁLISIS:")
    print(f"  Folio más alto usado: ENT-{str(max_folio).zfill(6)}")
    
    # Ver contador actual
    cursor.execute("SELECT ultimo FROM folios WHERE tipo = 'entrada'")
    contador = cursor.fetchone()['ultimo']
    print(f"  Contador actual: {contador}")
    print(f"  Diferencia: {contador - max_folio} folios de diferencia")
    
    # Próximo folio correcto
    proximo_correcto = max_folio + 1
    print(f"\n✓ Próximo folio CORRECTO debe ser: ENT-{str(proximo_correcto).zfill(6)}")
    
    print("\n" + "=" * 80)
    respuesta = input("\n¿Reparar el contador? (escribe SI): ").strip().upper()
    
    if respuesta != 'SI':
        print("Cancelado. No se hizo ningún cambio.")
        conn.close()
        return
    
    # Actualizar el contador
    print(f"\n⏳ Actualizando contador...")
    cursor.execute("UPDATE folios SET ultimo = ? WHERE tipo = 'entrada'", (max_folio,))
    conn.commit()
    
    # Verificar
    cursor.execute("SELECT ultimo FROM folios WHERE tipo = 'entrada'")
    nuevo_contador = cursor.fetchone()['ultimo']
    
    print(f"\n✅ REPARACIÓN COMPLETADA:")
    print(f"  Contador anterior: {contador}")
    print(f"  Contador nuevo: {nuevo_contador}")
    print(f"  Próximo folio será: ENT-{str(nuevo_contador + 1).zfill(6)}")
    
    print("\n" + "=" * 80)
    print("✅ ¡LISTO! Ahora puedes guardar entradas sin error de duplicado")
    
    conn.close()

if __name__ == "__main__":
    try:
        reparar_folios()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)
