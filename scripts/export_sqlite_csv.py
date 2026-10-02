r"""
Exporta todas las tablas de SQLite a CSV.

Uso:
  python scripts\export_sqlite_csv.py
  python scripts\export_sqlite_csv.py --db C:\ruta\a\almacen.db --out exports\sqlite_20260806

No modifica la base. Genera un CSV por tabla y un manifest.json con conteos.
Estos archivos sirven para una migracion controlada a PostgreSQL.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from datetime import datetime


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.environ.get("ERP_DATABASE_PATH") or os.environ.get("DATABASE_PATH") or os.path.join(PROJECT_DIR, "almacen.db")


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Exportar SQLite ERP a CSV")
    parser.add_argument("--db", default=DEFAULT_DB, help="Ruta de almacen.db")
    parser.add_argument("--out", default="", help="Carpeta destino")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f"ERROR: no existe la base: {db_path}")
        return 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out or os.path.join(PROJECT_DIR, "exports", f"sqlite_export_{timestamp}")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_db": db_path,
        "tables": [],
    }

    try:
        for table in table_names(conn):
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            columns = rows[0].keys() if rows else [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
            csv_path = os.path.join(out_dir, f"{safe_name(table)}.csv")
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                for row in rows:
                    writer.writerow([row[col] for col in columns])
            manifest["tables"].append({
                "name": table,
                "rows": len(rows),
                "file": os.path.basename(csv_path),
                "columns": list(columns),
            })
            print(f"{table}: {len(rows)} -> {csv_path}")
    finally:
        conn.close()

    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Manifest: {manifest_path}")
    print("Exportacion terminada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
