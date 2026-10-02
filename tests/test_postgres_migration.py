"""Validaciones estaticas del paquete de migracion PostgreSQL."""

import database
from scripts.migrate_sqlite_to_postgres import TABLES, sqlite_columns


def test_migrador_cubre_todas_las_tablas_de_negocio(client):
    conn = database.get_db()
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    conn.close()
    assert tables == set(TABLES)


def test_schema_postgres_incluye_cierres_y_roles():
    from pathlib import Path
    schema = (Path(__file__).resolve().parents[1] / 'migrations' / 'postgres_schema_v1.sql').read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS cierres_mensuales_periodos' in schema
    assert "'almacen', 'compras', 'produccion', 'mantenimiento', 'consulta'" in schema
    assert 'salidas_manual NUMERIC' in schema
