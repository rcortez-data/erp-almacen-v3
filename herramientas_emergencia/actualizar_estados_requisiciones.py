#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ACTUALIZAR ESTADOS DE REQUISICIONES (una sola vez / retroactivo)
====================================================================
El cambio automático a "Revisión" que se agregó a la captura de entradas
(routes/entradas.py -> _vincular_con_requisicion) SOLO se dispara cuando
alguien captura una entrada nueva desde el formulario. Las entradas que
ya existían de antes (por ejemplo, las importadas desde War Machine) nunca
pasaron por ahí, así que sus requisiciones se quedaron con el estado viejo
aunque ya tengan entradas ligadas.

Este script revisa TODAS las requisiciones existentes, busca sus entradas
ligadas por número de folio (misma lógica que la pantalla de detalle) y
actualiza el estado a 'revision' en las que ya tienen entradas pero seguían
en 'pendiente'. NO toca las que ya están en 'revision', 'parcial' o
'completa' (para no perder ese avance si ya se habían movido más).

Es seguro correrlo varias veces (solo actualiza lo que haga falta).

USO:
    python herramientas_emergencia/actualizar_estados_requisiciones.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db


def normalizar(texto):
    if not texto:
        return ""
    return str(texto).strip().upper().replace("-", "").replace(" ", "")


def main():
    print("=" * 80)
    print("ACTUALIZAR ESTADOS DE REQUISICIONES (retroactivo)")
    print("=" * 80)

    conn = get_db()
    cursor = conn.cursor()

    requisiciones = cursor.execute("SELECT * FROM requisiciones").fetchall()

    entradas = cursor.execute("""
        SELECT no_requisicion FROM entradas
        WHERE no_requisicion IS NOT NULL AND TRIM(no_requisicion) != ''
    """).fetchall()
    folios_con_entrada = {normalizar(e["no_requisicion"]) for e in entradas}

    a_actualizar = []
    for r in requisiciones:
        folio_norm = normalizar(str(r["folio"]))
        tiene_entrada = folio_norm in folios_con_entrada
        if tiene_entrada and r["estado"] not in ("revision", "parcial", "completa"):
            a_actualizar.append(r)

    print(f"\nTotal de requisiciones: {len(requisiciones)}")
    print(f"Entradas con número de requisición: {len(entradas)}")
    print(f"Requisiciones a pasar a REVISIÓN: {len(a_actualizar)}")

    print("\nEjemplos (primeras 10):")
    for r in a_actualizar[:10]:
        print(f"  AL-{r['folio']} | estado actual: {r['estado']} | asunto: {r['asunto'] or '-'}")

    if not a_actualizar:
        print("\nNo hay nada que actualizar.")
        conn.close()
        return

    print("\n" + "=" * 80)
    respuesta = input("\n¿Confirmar actualización? (escribe SI): ").strip().upper()
    if respuesta != "SI":
        print("Cancelado. No se hizo ningún cambio.")
        conn.close()
        return

    for r in a_actualizar:
        cursor.execute("UPDATE requisiciones SET estado='revision' WHERE id=?", (r["id"],))
    conn.commit()
    conn.close()

    print(f"\n✅ {len(a_actualizar)} requisición(es) actualizada(s) a REVISIÓN.")


if __name__ == "__main__":
    main()
