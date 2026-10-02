"""Restaura SQLite de forma controlada; ejecutar solamente con el ERP detenido."""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
try:
    from scripts.verify_backup import verify
except ImportError:
    from verify_backup import verify


def restore(backup, destination):
    backup = Path(backup).resolve(); destination = Path(destination).resolve()
    verify(backup)
    if destination.exists():
        safety = destination.with_name(
            f'{destination.stem}_pre_restore_{datetime.now():%Y%m%d_%H%M%S}{destination.suffix}'
        )
        source = sqlite3.connect(f'file:{destination}?mode=ro', uri=True)
        target = sqlite3.connect(safety)
        source.backup(target); target.close(); source.close()
    source = sqlite3.connect(f'file:{backup}?mode=ro', uri=True)
    target = sqlite3.connect(destination)
    source.backup(target); target.close(); source.close()
    check = sqlite3.connect(f'file:{destination}?mode=ro', uri=True)
    integrity = check.execute('PRAGMA integrity_check').fetchone()[0]; check.close()
    if integrity != 'ok':
        raise RuntimeError(f'Restauracion invalida: {integrity}')
    return destination


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('backup'); parser.add_argument('--destination', default=str(root / 'almacen.db'))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        parser.error('Usa --apply y confirma que el ERP esta detenido.')
    print(f'Restaurado: {restore(args.backup, args.destination)}')
