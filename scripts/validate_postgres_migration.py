"""Compara conteos y agregados criticos entre SQLite y PostgreSQL."""

import os
import sqlite3
from decimal import Decimal
from pathlib import Path
from dotenv import load_dotenv
import psycopg

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')

TABLES = [
    'usuarios', 'categorias', 'proveedores', 'productos', 'montacargas', 'areas',
    'folios', 'folios_diarios', 'requisiciones', 'requisicion_items',
    'requisicion_item_recepciones', 'entradas', 'salidas', 'vales_montacargas',
    'conteos_fisicos', 'cierres_mensuales_periodos', 'bloques_balance',
    'bloque_productos', 'actividad',
]
AGGREGATES = {
    'productos.stock_actual': 'SELECT COALESCE(SUM(stock_actual),0) FROM productos',
    'productos.precio_unitario': 'SELECT COALESCE(SUM(precio_unitario),0) FROM productos',
    'entradas.cantidad': 'SELECT COALESCE(SUM(cantidad),0) FROM entradas',
    'entradas.importe': 'SELECT COALESCE(SUM(importe),0) FROM entradas',
    'salidas.cantidad': 'SELECT COALESCE(SUM(cantidad),0) FROM salidas',
    'requisicion_items.cantidad': 'SELECT COALESCE(SUM(cantidad),0) FROM requisicion_items',
}


def normalized(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.0001'))


def main():
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise RuntimeError('DATABASE_URL no esta configurada.')
    sqlite_conn = sqlite3.connect(ROOT / 'almacen.db')
    pg_conn = psycopg.connect(url)
    errors = []
    try:
        for table in TABLES:
            left = sqlite_conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            right = pg_conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if left != right:
                errors.append(f'{table}: SQLite={left}, PostgreSQL={right}')
        for name, query in AGGREGATES.items():
            left = normalized(sqlite_conn.execute(query).fetchone()[0])
            right = normalized(pg_conn.execute(query).fetchone()[0])
            if left != right:
                errors.append(f'{name}: SQLite={left}, PostgreSQL={right}')
    finally:
        sqlite_conn.close(); pg_conn.close()
    if errors:
        print('VALIDACION POSTGRESQL: NO APROBADA')
        for error in errors: print(f'- {error}')
        return 1
    print('VALIDACION POSTGRESQL: APROBADA')
    print(f'- {len(TABLES)} tablas con conteos iguales')
    print(f'- {len(AGGREGATES)} agregados criticos iguales')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
