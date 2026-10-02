"""Valida bloqueadores tecnicos antes de iniciar V3 como produccion."""

import os
import sqlite3
import sys
from pathlib import Path
from werkzeug.security import check_password_hash

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get('ERP_DATABASE_PATH', ROOT / 'almacen.db')).resolve()


def main():
    errores = []
    avisos = []
    if os.environ.get('DEBUG', 'False').lower() == 'true':
        errores.append('DEBUG debe estar en False.')
    secret = os.environ.get('SECRET_KEY', '')
    key_file = ROOT / '.secret_key'
    if not secret and key_file.exists():
        secret = key_file.read_text(encoding='utf-8').strip()
    if len(secret) < 32 or secret == 'tu-clave-secreta-segura-aqui':
        errores.append('SECRET_KEY ausente, corta o de ejemplo.')
    if not DB_PATH.is_file():
        errores.append(f'No existe la base: {DB_PATH}')
    else:
        conn = sqlite3.connect(DB_PATH)
        integridad = conn.execute('PRAGMA integrity_check').fetchone()[0]
        if integridad != 'ok':
            errores.append(f'Integridad SQLite: {integridad}')
        admins = conn.execute("SELECT COUNT(*) FROM usuarios WHERE rol='admin' AND activo=1").fetchone()[0]
        if admins < 1:
            errores.append('No existe ningun administrador activo.')
        for username, password_hash in conn.execute("SELECT username, password FROM usuarios WHERE activo=1"):
            if check_password_hash(password_hash, 'admin123'):
                errores.append(f'El usuario {username} conserva la contrasena temporal admin123.')
        cambios = conn.execute(
            "SELECT COUNT(*) FROM usuarios WHERE activo=1 AND debe_cambiar_password=1"
        ).fetchone()[0]
        if cambios:
            errores.append(f'Hay {cambios} usuario(s) con cambio de contrasena pendiente.')
        pendientes = conn.execute("""
            SELECT COUNT(*) FROM cierres_mensuales_periodos WHERE estado='abierto'
        """).fetchone()[0]
        if pendientes:
            avisos.append(f'Hay {pendientes} periodo(s) mensual(es) reabierto(s).')
        conn.close()
    backup_dir = ROOT / 'backups_db'
    if not backup_dir.is_dir():
        errores.append('No existe la carpeta backups_db.')

    print('ERP V3 - PREFLIGHT DE PRODUCCION')
    for aviso in avisos:
        print(f'AVISO: {aviso}')
    for error in errores:
        print(f'BLOQUEADOR: {error}')
    if errores:
        print(f'RESULTADO: NO APROBADO ({len(errores)} bloqueador(es))')
        return 1
    print('RESULTADO: APROBADO')
    return 0


if __name__ == '__main__':
    sys.exit(main())
