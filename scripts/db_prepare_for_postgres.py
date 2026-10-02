r"""
Prepara datos del lab para una prueba de migracion a PostgreSQL.

Uso diagnostico:
  python scripts\db_prepare_for_postgres.py

Uso aplicando cambios:
  python scripts\db_prepare_for_postgres.py --apply

Cambios que puede aplicar:
  1. Entradas/salidas con fecha vacia:
     - coloca fecha tecnica 1900-01-01 00:00:00
     - agrega marca en observaciones sin borrar observacion previa
  2. bloque_productos con producto inexistente:
     - elimina solo esos renglones del bloque mensual
     - no elimina productos, entradas, salidas ni movimientos

Con --apply crea respaldo automatico antes de modificar almacen.db.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from datetime import datetime


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.environ.get("ERP_DATABASE_PATH") or os.environ.get("DATABASE_PATH") or os.path.join(PROJECT_DIR, "almacen.db")
TECHNICAL_DATE = "1900-01-01 00:00:00"
DATE_NOTE = "[MIGRACION_DB: fecha original vacia; se asigno fecha tecnica 1900-01-01]"


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def backup_db(db_path: str) -> str:
    backup_dir = os.path.join(PROJECT_DIR, "backups_db")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backup_dir, f"almacen_pre_postgres_prepare_{stamp}.db")
    shutil.copy2(db_path, dst)
    return dst


def empty_date_rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return conn.execute(
        f"""
        SELECT id, folio, observaciones
        FROM {table}
        WHERE fecha IS NULL OR TRIM(fecha) = ''
        ORDER BY id
        """
    ).fetchall()


def orphan_bloque_productos(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT bp.id, bp.bloque_id, bp.producto_id, bp.orden, b.nombre AS bloque
        FROM bloque_productos bp
        LEFT JOIN productos p ON p.id = bp.producto_id
        LEFT JOIN bloques_balance b ON b.id = bp.bloque_id
        WHERE bp.producto_id IS NOT NULL AND p.id IS NULL
        ORDER BY bp.bloque_id, bp.orden, bp.id
        """
    ).fetchall()


def with_note(observaciones: str | None) -> str:
    text = (observaciones or "").strip()
    if DATE_NOTE in text:
        return text
    if text:
        return f"{text} {DATE_NOTE}"
    return DATE_NOTE


def repair_empty_dates(conn: sqlite3.Connection, table: str) -> int:
    rows = empty_date_rows(conn, table)
    for row in rows:
        conn.execute(
            f"UPDATE {table} SET fecha=?, observaciones=? WHERE id=?",
            (TECHNICAL_DATE, with_note(row["observaciones"]), row["id"]),
        )
    return len(rows)


def cleanup_orphans(conn: sqlite3.Connection) -> int:
    rows = orphan_bloque_productos(conn)
    if not rows:
        return 0
    ids = [row["id"] for row in rows]
    placeholders = ",".join("?" for _ in ids)
    conn.execute(f"DELETE FROM bloque_productos WHERE id IN ({placeholders})", ids)
    return len(ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Preparar SQLite ERP para prueba PostgreSQL")
    parser.add_argument("--db", default=DEFAULT_DB, help="Ruta de almacen.db")
    parser.add_argument("--apply", action="store_true", help="Aplicar cambios despues de respaldar")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f"ERROR: no existe la base: {db_path}")
        return 2

    conn = connect(db_path)
    try:
        entradas = empty_date_rows(conn, "entradas")
        salidas = empty_date_rows(conn, "salidas")
        orphans = orphan_bloque_productos(conn)

        print("Preparacion PostgreSQL - diagnostico")
        print(f"Base: {db_path}")
        print(f"Entradas con fecha vacia: {len(entradas)}")
        print(f"Salidas con fecha vacia: {len(salidas)}")
        print(f"Bloque_productos huerfanos: {len(orphans)}")

        if not args.apply:
            print("Modo diagnostico: no se modifico nada.")
            print("Para aplicar cambios: python scripts\\db_prepare_for_postgres.py --apply")
            return 1 if (entradas or salidas or orphans) else 0

        backup_path = backup_db(db_path)
        fixed_entradas = repair_empty_dates(conn, "entradas")
        fixed_salidas = repair_empty_dates(conn, "salidas")
        removed_orphans = cleanup_orphans(conn)
        conn.commit()

        print(f"Respaldo creado: {backup_path}")
        print(f"Entradas reparadas: {fixed_entradas}")
        print(f"Salidas reparadas: {fixed_salidas}")
        print(f"Bloque_productos huerfanos eliminados: {removed_orphans}")
        print("Preparacion aplicada.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
