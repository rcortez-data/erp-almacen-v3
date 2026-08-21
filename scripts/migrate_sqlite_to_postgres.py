"""Migracion transaccional de SQLite a PostgreSQL con validacion de conteos."""

import argparse
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

TABLES = [
    'usuarios', 'categorias', 'proveedores', 'productos', 'montacargas', 'areas',
    'folios', 'folios_diarios', 'requisiciones', 'requisicion_items',
    'requisicion_item_recepciones', 'entradas', 'salidas', 'vales_montacargas',
    'conteos_fisicos', 'cierres_mensuales_periodos', 'bloques_balance',
    'bloque_productos', 'actividad',
]


def sqlite_columns(conn, table):
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]


def migrate(sqlite_path, database_url, schema_path, replace=False):
    try:
        import psycopg
        from psycopg import sql
    except ImportError as error:
        raise RuntimeError('Instala psycopg[binary] antes de migrar.') from error
    source = sqlite3.connect(f'file:{Path(sqlite_path).resolve()}?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        source.close()
        raise RuntimeError('SQLite no paso integrity_check.')
    target = psycopg.connect(database_url)
    counts = {}
    try:
        with target.transaction():
            schema_sql = Path(schema_path).read_text(encoding='utf-8')
            schema_sql = '\n'.join(
                line for line in schema_sql.splitlines()
                if line.strip().upper() not in {'BEGIN;', 'COMMIT;'}
            )
            target.execute(schema_sql)
            existing = sum(target.execute(
                sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))
            ).fetchone()[0] for table in TABLES)
            if existing and not replace:
                raise RuntimeError('PostgreSQL no esta vacio. Usa --replace solo en laboratorio.')
            if replace:
                target.execute(sql.SQL('TRUNCATE {} RESTART IDENTITY CASCADE').format(
                    sql.SQL(', ').join(map(sql.Identifier, reversed(TABLES)))
                ))
            for table in TABLES:
                source_cols = sqlite_columns(source, table)
                target_cols = [row[0] for row in target.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position
                """, (table,)).fetchall()]
                missing = sorted(set(source_cols) - set(target_cols))
                if missing:
                    raise RuntimeError(f'El schema PostgreSQL no contiene {table}.{missing}')
                columns = [column for column in source_cols if column in target_cols]
                rows = source.execute(f'SELECT * FROM "{table}"').fetchall()
                if rows:
                    copy_sql = sql.SQL('COPY {} ({}) FROM STDIN').format(
                        sql.Identifier(table), sql.SQL(', ').join(map(sql.Identifier, columns))
                    )
                    with target.cursor().copy(copy_sql) as copy:
                        for row in rows:
                            copy.write_row([row[column] for column in columns])
                actual = target.execute(
                    sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))
                ).fetchone()[0]
                if actual != len(rows):
                    raise RuntimeError(f'{table}: SQLite={len(rows)}, PostgreSQL={actual}')
                counts[table] = actual
            for table in TABLES:
                if 'id' in sqlite_columns(source, table):
                    target.execute(sql.SQL("""
                        SELECT setval(pg_get_serial_sequence({table_literal}, 'id'),
                                      COALESCE((SELECT MAX(id) FROM {table}), 1), true)
                    """).format(table_literal=sql.Literal(table), table=sql.Identifier(table)))
        return counts
    finally:
        source.close()
        target.close()


def main():
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / '.env')
    parser = argparse.ArgumentParser()
    parser.add_argument('--sqlite', default=str(root / 'almacen.db'))
    parser.add_argument('--database-url', default=os.environ.get('DATABASE_URL'))
    parser.add_argument('--schema', default=str(root / 'migrations' / 'postgres_schema_v1.sql'))
    parser.add_argument('--replace', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.database_url:
        parser.error('Define DATABASE_URL o usa --database-url.')
    if not args.apply:
        parser.error('La migracion requiere --apply para confirmar.')
    counts = migrate(args.sqlite, args.database_url, args.schema, args.replace)
    print('MIGRACION POSTGRESQL APROBADA')
    for table, count in counts.items():
        print(f'- {table}: {count}')


if __name__ == '__main__':
    main()
