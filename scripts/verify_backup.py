"""Verifica que un respaldo pueda abrirse y coincida con su manifiesto."""

import argparse
import json
import sqlite3
from pathlib import Path


def verify(path):
    path = Path(path).resolve()
    manifest_path = path.with_suffix('.json')
    if not path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError('Falta el respaldo o su manifiesto JSON.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Integridad SQLite invalida.')
        for table, expected in manifest['counts'].items():
            actual = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if actual != expected:
                raise RuntimeError(f'{table}: esperado {expected}, obtenido {actual}')
    finally:
        conn.close()
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('backup')
    args = parser.parse_args()
    verify(args.backup)
    print('RESTAURACION SIMULADA: APROBADA')


if __name__ == '__main__':
    main()
