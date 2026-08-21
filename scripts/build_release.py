"""Construye un ZIP de codigo sin bases, secretos, sesiones ni respaldos."""

import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    '.pytest_cache', '__pycache__', 'backups_db', 'exports', 'flask_session',
    'logs', 'release_packages', 'backups_formularios_fase2_20260806_015801',
    'backups_requisiciones_reportes_fase2_20260806_020057',
}
EXCLUDED_NAMES = {'.env', '.secret_key', 'almacen.db'}
EXCLUDED_SUFFIXES = {'.pyc', '.db', '.zip'}


def build(output_dir):
    output_dir = Path(output_dir).resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    destination = output_dir / f'erp_almacen_v3_release_{stamp}.zip'
    included = []
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob('*')):
            relative = path.relative_to(ROOT)
            if path.is_dir() or any(part in EXCLUDED_DIRS for part in relative.parts):
                continue
            if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            archive.write(path, relative)
            included.append(str(relative))
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    manifest = {'created_at': datetime.now().isoformat(timespec='seconds'),
                'zip': str(destination), 'sha256': digest, 'files': included}
    destination.with_suffix('.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return destination


if __name__ == '__main__':
    result = build(ROOT / 'release_packages')
    print(f'Paquete creado: {result}')
