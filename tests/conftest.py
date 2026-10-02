"""
Configuración de tests para pytest.
Define fixtures compartidas.
"""

import pytest
import os
from app import app
import database


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Cliente de prueba para Flask."""
    test_db = tmp_path / 'almacen_test.db'
    monkeypatch.setattr(database, 'DB_PATH', str(test_db))
    database.init_db()
    conn = database.get_db()
    conn.execute('UPDATE usuarios SET debe_cambiar_password=0')
    conn.commit(); conn.close()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def runner():
    """Runner para comandos CLI."""
    return app.test_cli_runner()


@pytest.fixture
def auth_client(client):
    """Cliente autenticado como admin."""
    client.post('/login', data={
        'username': 'admin',
        'password': 'admin123'
    })
    return client
