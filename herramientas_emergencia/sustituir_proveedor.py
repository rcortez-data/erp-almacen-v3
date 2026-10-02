"""
SUSTITUIR PROVEEDOR - Reasigna entradas de un proveedor viejo/histórico a uno nuevo
------------------------------------------------------------------------------------
Pensado para tu flujo de trabajo: das de alta proveedores conforme van llegando
facturas (con el nombre correcto), y más adelante quieres "corregir" entradas
viejas que:
  a) Quedaron con un NOMBRE HISTÓRICO (archivado) tras el reseteo de proveedores, o
  b) Quedaron ligadas a un proveedor mal capturado/duplicado,
para que apunten al proveedor correcto ya existente (o a uno nuevo que se crea
en el momento).

MODOS DE USO:

  1) Reasignar por NOMBRE HISTÓRICO (el que se ve como "archivado" en el ERP):
     python sustituir_proveedor.py --historico "Joel Guerrero" --destino "HIPRO SA de CV"

  2) Reasignar por ID de un proveedor viejo (duplicado, mal escrito, etc.):
     python sustituir_proveedor.py --origen-id 7 --destino "HIPRO SA de CV"

  3) Reasignar hacia un proveedor que YA EXISTE (por su ID exacto):
     python sustituir_proveedor.py --historico "Joel Guerrero" --destino-id 3

En cualquier modo: si --destino es un nombre y ya existe un proveedor con ese
nombre exacto, se reutiliza; si no existe, se crea automáticamente.

Si usas --origen-id, ese proveedor viejo se queda sin ninguna entrada apuntándole
(ya se movieron todas al nuevo) y puedes borrarlo después desde Proveedores si
ya no lo necesitas.

Antes de aplicar cualquier cambio se muestra un resumen y se pide confirmación.
"""
import sys
import argparse
from database import get_db


def columna_existe(conn, tabla, columna):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()]
    return columna in cols


def obtener_o_crear_proveedor_destino(conn, destino_nombre, destino_id):
    if destino_id:
        row = conn.execute("SELECT id, nombre FROM proveedores WHERE id=?", (destino_id,)).fetchone()
        if not row:
            print(f"❌ No existe ningún proveedor con id {destino_id}.")
            sys.exit(1)
        return row['id'], row['nombre'], False

    nombre = destino_nombre.strip()
    row = conn.execute("SELECT id, nombre FROM proveedores WHERE UPPER(nombre)=UPPER(?)", (nombre,)).fetchone()
    if row:
        return row['id'], row['nombre'], False

    cur = conn.execute("INSERT INTO proveedores (nombre) VALUES (?)", (nombre,))
    conn.commit()
    return cur.lastrowid, nombre, True


def main():
    parser = argparse.ArgumentParser(
        description="Reasigna entradas de un proveedor histórico/viejo a uno nuevo o existente.")
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument('--historico', help='Nombre histórico (archivado) a reemplazar, tal como aparece en el ERP')
    origen.add_argument('--origen-id', type=int, help='ID de un proveedor viejo/duplicado ya existente en la tabla')

    destino = parser.add_mutually_exclusive_group(required=True)
    destino.add_argument('--destino', help='Nombre del proveedor correcto (se usa si existe, o se crea si no)')
    destino.add_argument('--destino-id', type=int, help='ID de un proveedor correcto que ya existe')

    args = parser.parse_args()

    conn = get_db()

    if not columna_existe(conn, 'entradas', 'proveedor_nombre_historico'):
        conn.execute("ALTER TABLE entradas ADD COLUMN proveedor_nombre_historico TEXT")
        conn.commit()
        print("Columna 'proveedor_nombre_historico' agregada a 'entradas'.\n")

    destino_id, destino_nombre, se_creo = obtener_o_crear_proveedor_destino(conn, args.destino, args.destino_id)

    if args.historico:
        afectadas = conn.execute(
            "SELECT COUNT(*) FROM entradas WHERE proveedor_id IS NULL AND proveedor_nombre_historico = ?",
            (args.historico,)
        ).fetchone()[0]
        origen_desc = f"nombre histórico '{args.historico}'"
    else:
        origen_row = conn.execute("SELECT nombre FROM proveedores WHERE id=?", (args.origen_id,)).fetchone()
        if not origen_row:
            print(f"❌ No existe ningún proveedor con id {args.origen_id}.")
            conn.close()
            sys.exit(1)
        afectadas = conn.execute(
            "SELECT COUNT(*) FROM entradas WHERE proveedor_id = ?", (args.origen_id,)
        ).fetchone()[0]
        origen_desc = f"proveedor '{origen_row['nombre']}' (id {args.origen_id})"

    print("=" * 70)
    print("  SUSTITUIR PROVEEDOR")
    print("=" * 70)
    print(f"\n  Origen:  {origen_desc}")
    print(f"  Destino: '{destino_nombre}' (id {destino_id}){'  [se creará ahora]' if se_creo else '  [ya existía]'}")
    print(f"\n  Entradas que se van a reasignar: {afectadas}")
    print("=" * 70)

    if afectadas == 0:
        print("\nNo hay ninguna entrada que coincida con el origen indicado. No se hizo nada.")
        conn.close()
        return

    resp = input("\n¿Confirmas la reasignación? (escribe SI): ").strip().upper()
    if resp != 'SI':
        print("Cancelado. No se hizo ningún cambio.")
        conn.close()
        return

    if args.historico:
        conn.execute("""
            UPDATE entradas SET proveedor_id = ?, proveedor_nombre_historico = NULL
            WHERE proveedor_id IS NULL AND proveedor_nombre_historico = ?
        """, (destino_id, args.historico))
    else:
        conn.execute("""
            UPDATE entradas SET proveedor_id = ?, proveedor_nombre_historico = NULL
            WHERE proveedor_id = ?
        """, (destino_id, args.origen_id))

    conn.commit()
    conn.close()

    print(f"\n✅ Listo: {afectadas} entrada(s) reasignada(s) a '{destino_nombre}'.")
    if not args.historico:
        print(f"   El proveedor viejo (id {args.origen_id}) ya no tiene ninguna entrada asociada;")
        print("   si ya no lo necesitas, puedes borrarlo desde la sección Proveedores.")


if __name__ == "__main__":
    main()
