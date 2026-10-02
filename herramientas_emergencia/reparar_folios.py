"""
REPARAR CONTADOR DE FOLIOS - Entradas y Salidas
------------------------------------------------
Soluciona el error: "UNIQUE constraint failed: entradas.folio" (o salidas.folio)

CAUSA:
La app genera el siguiente folio (ENT-000001, SAL-000001, etc.) leyendo un
contador guardado en la tabla `folios` (columna `ultimo`) y sumándole 1.
Si alguna importación se interrumpió a la mitad (por un error, un corte, etc.)
antes de terminar de actualizar ese contador, éste queda "atrasado" respecto
a los folios que ya existen de verdad en `entradas`/`salidas`. Al capturar
una entrada o salida nueva, la app intenta usar un folio que ya está en uso
y SQLite lo rechaza con UNIQUE constraint failed.

SOLUCIÓN:
Este script recalcula el contador leyendo el folio más alto que realmente
existe en cada tabla (entradas y salidas) y ajusta `folios.ultimo` para que
coincida. Es seguro ejecutarlo cuantas veces se necesite: solo AVANZA el
contador si detecta que está atrasado, nunca lo retrocede.

USO:
    python reparar_folios.py
"""

import sqlite3
import re
from pathlib import Path


def obtener_max_folio(conn, tabla, prefijo):
    """Obtiene el número más alto usado en los folios de una tabla,
    ej. de 'ENT-013828' devuelve 13828."""
    c = conn.cursor()
    filas = c.execute(f"SELECT folio FROM {tabla} WHERE folio LIKE '{prefijo}-%'").fetchall()

    maximo = 0
    patron = re.compile(rf'^{prefijo}-(\d+)$')

    for (folio,) in filas:
        if not folio:
            continue
        m = patron.match(folio.strip())
        if m:
            numero = int(m.group(1))
            if numero > maximo:
                maximo = numero

    return maximo


def reparar(conn, tipo, tabla, prefijo):
    c = conn.cursor()

    # Asegura que exista la fila del contador
    c.execute("INSERT OR IGNORE INTO folios (tipo, ultimo) VALUES (?, 0)", (tipo,))

    actual = c.execute("SELECT ultimo FROM folios WHERE tipo = ?", (tipo,)).fetchone()[0]
    maximo_real = obtener_max_folio(conn, tabla, prefijo)

    print(f"\n{tabla.upper()}:")
    print(f"  Contador actual (folios.ultimo): {actual}")
    print(f"  Folio más alto real en la tabla: {maximo_real}")

    if maximo_real > actual:
        c.execute("UPDATE folios SET ultimo = ? WHERE tipo = ?", (maximo_real, tipo))
        conn.commit()
        print(f"  ✅ Corregido: {actual} → {maximo_real}")
    else:
        print(f"  ✅ Ya estaba correcto, no se modificó.")


def main():
    print("\n" + "=" * 60)
    print("🔧 REPARADOR DE CONTADOR DE FOLIOS")
    print("=" * 60)

    script_dir = Path(__file__).parent
    archivo_db = script_dir / 'almacen.db'

    if not archivo_db.exists():
        print(f"❌ No encontré {archivo_db}")
        return

    conn = sqlite3.connect(str(archivo_db))

    reparar(conn, 'entrada', 'entradas', 'ENT')
    reparar(conn, 'salida', 'salidas', 'SAL')

    conn.close()

    print("\n" + "=" * 60)
    print("✅ LISTO. Ya puedes capturar entradas/salidas nuevas sin error.")
    print("=" * 60)


if __name__ == "__main__":
    main()
