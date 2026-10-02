r"""
Revision previa a migracion de base de datos.

Uso:
  python scripts\db_preflight.py
  python scripts\db_preflight.py --db C:\ruta\a\almacen.db

No modifica datos. Solo lee SQLite y reporta riesgos comunes antes de migrar
a PostgreSQL u otro motor robusto.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.environ.get("ERP_DATABASE_PATH") or os.environ.get("DATABASE_PATH") or os.path.join(PROJECT_DIR, "almacen.db")


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int | float | str | None:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def check_null_dates(conn: sqlite3.Connection, table: str) -> int:
    cols = table_columns(conn, table)
    if "fecha" not in cols:
        return 0
    return int(scalar(conn, f"SELECT COUNT(*) FROM {table} WHERE fecha IS NULL OR TRIM(fecha)=''", ()) or 0)


def check_duplicate(conn: sqlite3.Connection, table: str, column: str) -> list[sqlite3.Row]:
    cols = table_columns(conn, table)
    if column not in cols:
        return []
    return conn.execute(
        f"""
        SELECT {column} AS valor, COUNT(*) AS total
        FROM {table}
        WHERE {column} IS NOT NULL AND TRIM(CAST({column} AS TEXT)) != ''
        GROUP BY {column}
        HAVING COUNT(*) > 1
        ORDER BY total DESC, valor
        LIMIT 20
        """
    ).fetchall()


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight de migracion ERP Almacen")
    parser.add_argument("--db", default=DEFAULT_DB, help="Ruta de almacen.db")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    print("ERP Almacen - preflight migracion")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base: {db_path}")

    if not os.path.exists(db_path):
        print("ERROR: no existe la base indicada.")
        return 2

    issues = 0
    conn = connect(db_path)
    try:
        integrity = scalar(conn, "PRAGMA integrity_check")
        print(f"Integridad SQLite: {integrity}")
        if integrity != "ok":
            issues += 1

        tables = table_names(conn)
        print(f"Tablas detectadas: {len(tables)}")
        for table in tables:
            count = scalar(conn, f"SELECT COUNT(*) FROM {table}") or 0
            null_dates = check_null_dates(conn, table)
            suffix = f" | fechas vacias: {null_dates}" if null_dates else ""
            print(f"- {table}: {count}{suffix}")
            if null_dates:
                issues += 1

        duplicate_checks = [
            ("productos", "codigo"),
            ("entradas", "folio"),
            ("salidas", "folio"),
            ("proveedores", "nombre"),
            ("usuarios", "username"),
            ("requisiciones", "folio"),
            ("montacargas", "nombre"),
            ("areas", "nombre"),
        ]
        for table, column in duplicate_checks:
            if table not in tables:
                continue
            duplicates = check_duplicate(conn, table, column)
            if duplicates:
                issues += 1
                print(f"Duplicados en {table}.{column}:")
                for row in duplicates:
                    print(f"  {row['valor']} -> {row['total']}")

        fk_issues = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_issues:
            issues += 1
            print("Problemas de llaves foraneas:")
            for row in fk_issues[:30]:
                print(f"  tabla={row[0]} rowid={row[1]} referencia={row[2]} fk={row[3]}")
            if len(fk_issues) > 30:
                print(f"  ... {len(fk_issues) - 30} mas")

    finally:
        conn.close()

    if issues:
        print(f"RESULTADO: revisar antes de migrar. Hallazgos: {issues}")
        return 1

    print("RESULTADO: base lista para una prueba de exportacion/migracion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
