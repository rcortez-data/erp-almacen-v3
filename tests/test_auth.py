"""
Tests para autenticación.
"""

import pytest
from routes.auth import login_required
from app import app


def test_login_page(client):
    """Test que la página de login es accesible."""
    response = client.get('/login')
    assert response.status_code == 200


def test_login_successful(client):
    """Test login exitoso con credenciales correctas."""
    response = client.post('/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    
    assert response.status_code == 200


def test_health_check(client):
    """Test que el endpoint de salud responde."""
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json['status'] == 'ok'


def test_login_required_protection(client):
    """Test que rutas protegidas requieren login."""
    # Intentar acceder a ruta protegida sin login
    response = client.get('/inventario/', follow_redirects=False)
    
    # Debería redirigir a login
    assert response.status_code in [302, 401]


def test_login_real_incluye_y_acepta_csrf(client):
    """El formulario independiente de login debe funcionar con CSRF activo."""
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        page = client.get('/login')
        assert b'name="_csrf_token"' in page.data
        with client.session_transaction() as sess:
            token = sess['_csrf_token']
        response = client.post('/login', data={
            'username': 'admin',
            'password': 'admin123',
            '_csrf_token': token,
        }, follow_redirects=False)
        assert response.status_code == 302
        assert '/dashboard' in response.headers['Location']
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_cambio_obligatorio_bloquea_hasta_actualizar_password(client):
    import database
    conn = database.get_db(); conn.execute('UPDATE usuarios SET debe_cambiar_password=1 WHERE id=1'); conn.commit(); conn.close()
    client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    response = client.get('/dashboard', follow_redirects=False)
    assert response.status_code == 302
    assert '/cambiar-password' in response.headers['Location']
    cambio = client.post('/cambiar-password', data={
        'actual': 'admin123', 'nueva': 'Nueva2026', 'confirmar': 'Nueva2026',
    })
    assert cambio.status_code == 302
    assert client.get('/dashboard').status_code == 200
