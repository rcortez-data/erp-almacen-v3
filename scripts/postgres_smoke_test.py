"""Prueba lectura/escritura del ERP usando PostgreSQL y limpia su registro temporal."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')
os.environ['ERP_DB_BACKEND'] = 'postgres'

from app import app
from database import get_db

URLS = [
    '/dashboard', '/inventario/', '/entradas/', '/salidas/', '/requisiciones/',
    '/reportes/', '/balance/', '/balance/todos', '/usuarios/', '/proveedores/',
    '/montacargas/', '/vales-montacargas/', '/areas/',
]


def main():
    app.config['TESTING'] = True; app.config['WTF_CSRF_ENABLED'] = False
    name = '__PRUEBA_POSTGRES_TEMPORAL__'
    try:
        with app.test_client() as client:
            with client.session_transaction() as session:
                session.update(user_id=1, username='admin', nombre='Administrador',
                               rol='admin', debe_cambiar_password=False)
            for url in URLS:
                response = client.get(url)
                if response.status_code != 200:
                    raise RuntimeError(f'{url}: HTTP {response.status_code}')
            response = client.post('/areas/api/crear', data={'nombre': name})
            if response.status_code != 200 or not response.get_json().get('id'):
                raise RuntimeError(f'Escritura PostgreSQL: HTTP {response.status_code}')
    finally:
        db = get_db()
        db.execute('DELETE FROM areas WHERE nombre=?', (name,))
        db.execute("DELETE FROM actividad WHERE accion='NUEVA_AREA' AND detalle LIKE ?", (f'%{name}%',))
        db.commit(); db.close()
    print(f'POSTGRESQL SMOKE TEST: APROBADO ({len(URLS)} pantallas + escritura)')


if __name__ == '__main__':
    main()
