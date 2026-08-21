r"""
Diagnostica y, opcionalmente, limpia referencias huerfanas que bloquearian
una migracion estricta a PostgreSQL.

Uso diagnostico:
  python scripts\db_cleanup_orphans.py

Uso aplicando cambios:
  python scripts\db_cleanup_orphans.py --apply

Por seguridad, con --apply crea un respaldo en backups_db antes de borrar.
Actualmente solo corrige relaciones derivadas/auxiliares que no deben bloquear
el inventario principal:
  - bloque_productos con producto_id inexistente
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from datetime import datetime


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.environ.get("ERP_DATABASE_PATH") or os.environ.get("DATABASE_PATH") or os.path.join(PROJECT_DIR, "almacen.db")


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def backup_db(db_path: str) -> str:
    backup_dir = os.path.join(PROJECT_DIR, "backups_db")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backup_dir, f"almacen_pre_cleanup_{stamp}.db")
    shutil.copy2(db_path, dst)
    return dst


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Limpieza controlada de huerfanos ERP")
    parser.add_argument("--db", default=DEFAULT_DB, help="Ruta de almacen.db")
    parser.add_argument("--apply", action="store_true", help="Aplicar limpieza despues de respaldar")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f"ERROR: no existe la base: {db_path}")
        return 2

    conn = connect(db_path)
    try:
        orphans = orphan_bloque_productos(conn)
        print(f"bloque_productos huerfanos: {len(orphans)}")
        for row in orphans[:50]:
            print(
                f"  id={row['id']} bloque={row['bloque'] or row['bloque_id']} "
                f"producto_id={row['producto_id']} orden={row['orden']}"
            )
        if len(orphans) > 50:
            print(f"  ... {len(orphans) - 50} mas")

        if not args.apply:
            print("Modo diagnostico: no se modifico nada.")
            print("Para aplicar limpieza: python scripts\\db_cleanup_orphans.py --apply")
            return 1 if orphans else 0

        if not orphans:
            print("No hay huerfanos que limpiar.")
            return 0

        backup_path = backup_db(db_path)
        ids = [row["id"] for row in orphans]
        placeholders = ",".join("?" for _ in ids)
        conn.execute(f"DELETE FROM bloque_productos WHERE id IN ({placeholders})", ids)
        conn.commit()
        print(f"Respaldo creado: {backup_path}")
        print(f"Registros eliminados de bloque_productos: {len(ids)}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
