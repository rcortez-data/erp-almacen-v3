"""Respaldo consistente de SQLite con integridad, manifiesto y retencion."""

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def create_backup(database, output_dir, retention=30):
    database = Path(database).resolve()
    output_dir = Path(output_dir).resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    destination = output_dir / f'almacen_auto_{stamp}.db'
    source = sqlite3.connect(f'file:{database}?mode=ro', uri=True)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        integrity = target.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok':
            raise RuntimeError(f'El respaldo no paso integridad: {integrity}')
        tables = [r[0] for r in target.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        counts = {table: target.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}
    finally:
        target.close()
        source.close()
    manifest = {
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'source': str(database), 'backup': str(destination),
        'sha256': _sha256(destination), 'integrity': 'ok', 'counts': counts,
    }
    destination.with_suffix('.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    backups = sorted(output_dir.glob('almacen_auto_*.db'), reverse=True)
    for old in backups[max(1, retention):]:
        old.unlink()
        old.with_suffix('.json').unlink(missing_ok=True)
    return destination


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', default=str(root / 'almacen.db'))
    parser.add_argument('--output', default=str(root / 'backups_db'))
    parser.add_argument('--retention', type=int, default=30)
    args = parser.parse_args()
    path = create_backup(args.database, args.output, args.retention)
    print(f'Respaldo verificado: {path}')


if __name__ == '__main__':
    main()
