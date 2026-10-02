"""Pruebas de las protecciones centrales de la aplicacion."""

from app import app
from routes.usuarios import _validar_password
from routes.inventario import normalizar_descripcion_duplicado
from routes.salidas import normalizar_vale_mantenimiento
import database


def test_csrf_rechaza_post_sin_token(client):
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        client.get('/login')
        response = client.post('/login', data={
            'username': 'admin',
            'password': 'admin123',
        })
        assert response.status_code == 400
        assert 'CSRF' in response.get_json()['error']
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_csrf_acepta_token_de_sesion(client):
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        client.get('/login')
        with client.session_transaction() as sess:
            token = sess['_csrf_token']
        response = client.post('/login', data={
            'username': 'usuario-inexistente',
            'password': 'incorrecta',
            '_csrf_token': token,
        })
        assert response.status_code == 200
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_validacion_password_configurable():
    with app.test_request_context('/'):
        app.config['PASSWORD_MIN_LENGTH'] = 8
        app.config['REQUIRE_STRONG_PASSWORD'] = True
        assert _validar_password('corta1') is not None
        assert _validar_password('sololetras') is not None
        assert _validar_password('12345678') is not None
        assert _validar_password('Abc12345') is None
        assert _validar_password('Segura2026') is None


def test_normalizacion_detecta_descripciones_equivalentes():
    assert normalizar_descripcion_duplicado('Tornillo Allen 1/4') == normalizar_descripcion_duplicado('TORNILLO ÁLLEN 1/4"')


def test_atajo_vale_mantenimiento_normaliza_prefijo():
    assert normalizar_vale_mantenimiento('123', True) == 'M 123'
    assert normalizar_vale_mantenimiento('m123', True) == 'M 123'
    assert normalizar_vale_mantenimiento('M 123', True) == 'M 123'
    assert normalizar_vale_mantenimiento('123', False) == '123'


def test_salida_mantenimiento_completa_area_y_prefijo(auth_client):
    conn = database.get_db()
    producto_id = conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, ubicacion, stock_actual)
        VALUES ('MANT-1', 'Producto mantenimiento', 'PZA', 'PRUEBA 08', 10)
    """).lastrowid
    conn.commit(); conn.close()
    response = auth_client.post('/salidas/nuevo', data={
        'accion': 'agregar_item',
        'responsable': 'Técnico',
        'no_vale': '123',
        'area': '',
        'es_mantenimiento': 'on',
        'tipo_movimiento': 'normal',
        'producto_id': str(producto_id),
        'cantidad': '1',
    })
    assert response.status_code == 302
    with auth_client.session_transaction() as sess:
        assert sess['salida_doc']['no_vale'] == 'M 123'
        assert sess['salida_doc']['area'] == 'MANTENIMIENTO'
        assert sess['salida_doc']['es_mantenimiento'] is True


def test_salida_tiene_flujo_rapido_de_teclado(auth_client):
    response = auth_client.get('/salidas/nuevo')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="responsable" class="form-control" tabindex="1"' in html
    assert 'id="no_vale" class="form-control" tabindex="2"' in html
    assert 'id="area" class="form-control" tabindex="3"' in html
    assert 'id="buscador-producto" class="form-control" autocomplete="off" tabindex="4"' in html
    assert 'id="cantidad" class="form-control" min="0.25" step="0.25" tabindex="5"' in html
    assert "btnAgregar.click()" in html
    assert "e.key === 'ArrowDown'" in html
    assert "e.key === 'ArrowUp'" in html
    assert "resaltarResultado" in html
    assert "aria-selected" in html
    with auth_client.session_transaction() as sess:
        sess['salida_cart'] = [{
            'producto_id': 1, 'codigo': 'P-1', 'descripcion': 'Prueba',
            'unidad_medida': 'PZA', 'cantidad': 1, 'stock_actual': 2,
        }]
        sess['salida_doc'] = {'responsable': 'Persona', 'no_vale': 'V-1', 'area': 'AREA'}
    response = auth_client.get('/salidas/nuevo')
    html = response.get_data(as_text=True)
    buscador = html.split('id="buscador-producto"', 1)[1].split('>', 1)[0]
    assert 'autofocus' in buscador


def test_vale_montacargas_recuerda_campos_repetitivos(auth_client):
    conn = database.get_db()
    area_id = conn.execute("INSERT INTO areas (nombre) VALUES ('AREA RAPIDA')").lastrowid
    montacargas_id = conn.execute("INSERT INTO montacargas (nombre) VALUES ('MC RAPIDO')").lastrowid
    conn.commit(); conn.close()
    response = auth_client.post('/vales-montacargas/nuevo', data={
        'responsable': 'Operador frecuente',
        'no_vale': 'V-1',
        'area_id': str(area_id),
        'montacargas_id': str(montacargas_id),
        'cantidad': '2',
        'fecha_captura': '2026-08-07T10:00',
    })
    assert response.status_code == 302
    with auth_client.session_transaction() as sess:
        doc = sess['vale_mc_doc']
        assert doc['responsable'] == 'Operador frecuente'
        assert doc['area_id'] == str(area_id)
        assert doc['montacargas_id'] == str(montacargas_id)
        assert doc['no_vale'] == ''


def test_entradas_ofrece_guardar_y_capturar_otra(auth_client):
    response = auth_client.get('/entradas/nuevo')
    assert response.status_code == 200
    assert b'Guardar y capturar otra entrada' in response.data
    assert b'Guardar y volver al listado' in response.data


def test_pantalla_muestra_productos_duplicados(auth_client):
    conn = database.get_db()
    conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, ubicacion, stock_actual)
        VALUES ('DUP-1', 'Tornillo Allen 1/4', 'PZA', 'PRUEBA 01', 3)
    """)
    conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, ubicacion, stock_actual)
        VALUES ('DUP-2', 'TORNILLO ÁLLEN 1/4"', 'PZA', 'PRUEBA 02', 5)
    """)
    conn.commit(); conn.close()
    response = auth_client.get('/inventario/duplicados')
    assert response.status_code == 200
    assert b'DUP-1' in response.data
    assert b'DUP-2' in response.data
    assert b'Stock combinado: 8.0' in response.data
    assert b'Dar de baja' in response.data
    assert b'name="ids"' in response.data
    assert b'Dar de baja seleccionados' in response.data


def test_admin_da_de_baja_duplicado_y_guarda_usuario_fecha(auth_client):
    conn = database.get_db()
    cursor = conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, ubicacion, stock_actual)
        VALUES ('DUP-BORRAR', 'Producto duplicado temporal', 'PZA', 'PRUEBA 03', 0)
    """)
    producto_id = cursor.lastrowid
    conn.commit(); conn.close()
    response = auth_client.post(
        f'/inventario/baja/{producto_id}',
        headers={'Referer': '/inventario/duplicados'},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b'dado de baja' in response.data
    conn = database.get_db()
    producto = conn.execute(
        'SELECT activo, baja_por, baja_fecha, baja_folio FROM productos WHERE id=?',
        (producto_id,),
    ).fetchone()
    conn.close()
    assert producto['activo'] == 0
    assert producto['baja_por'] == 'Administrador'
    assert producto['baja_fecha']
    assert producto['baja_folio'] == 'BAJA DIRECTA'


def test_baja_multiple_desde_duplicados_conserva_registros(auth_client):
    conn = database.get_db()
    ids = []
    for codigo, descripcion in (
        ('DUP-LOTE-1', 'Tuerca hexagonal 3/8'),
        ('DUP-LOTE-2', 'TUERCA HEXAGONAL 3/8"'),
    ):
        ids.append(conn.execute("""
            INSERT INTO productos (codigo, descripcion, unidad_medida, ubicacion, stock_actual)
            VALUES (?, ?, 'PZA', 'PRUEBA LOTE', 1)
        """, (codigo, descripcion)).lastrowid)
    conn.commit(); conn.close()
    response = auth_client.post('/inventario/baja-multiple', data={'ids': [str(i) for i in ids]})
    assert response.status_code == 302
    conn = database.get_db()
    productos = conn.execute(
        'SELECT activo, baja_por, baja_fecha FROM productos WHERE id IN (?, ?)', ids
    ).fetchall()
    conn.close()
    assert len(productos) == 2
    assert all(p['activo'] == 0 and p['baja_por'] == 'Administrador' and p['baja_fecha'] for p in productos)


def test_eliminar_entrada_deja_auditoria_detallada(auth_client):
    conn = database.get_db()
    producto_id = conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, ubicacion, stock_actual)
        VALUES ('AUD-ENT', 'Producto auditoria entrada', 'PZA', 'PRUEBA 04', 10)
    """).lastrowid
    entrada_id = conn.execute("""
        INSERT INTO entradas (folio, producto_id, cantidad, cantidad_piezas, usuario_id)
        VALUES ('AUD-ENT-1', ?, 2, 2, 1)
    """, (producto_id,)).lastrowid
    conn.commit(); conn.close()
    response = auth_client.post(f'/entradas/eliminar/{entrada_id}')
    assert response.status_code == 302
    conn = database.get_db()
    registro = conn.execute("""
        SELECT accion, detalle, timestamp FROM actividad
        WHERE accion='ELIMINAR_ENTRADA' ORDER BY id DESC LIMIT 1
    """).fetchone()
    conn.close()
    assert f'Producto ID: {producto_id}' in registro['detalle']
    assert 'Cantidad: 2.0' in registro['detalle']
    assert registro['timestamp']


def test_eliminar_salida_deja_auditoria_detallada(auth_client):
    conn = database.get_db()
    producto_id = conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, ubicacion, stock_actual)
        VALUES ('AUD-SAL', 'Producto auditoria salida', 'PZA', 'PRUEBA 05', 8)
    """).lastrowid
    salida_id = conn.execute("""
        INSERT INTO salidas (folio, producto_id, cantidad, responsable, usuario_id)
        VALUES ('AUD-SAL-1', ?, 3, 'Prueba', 1)
    """, (producto_id,)).lastrowid
    conn.commit(); conn.close()
    response = auth_client.post(f'/salidas/eliminar/{salida_id}')
    assert response.status_code == 302
    conn = database.get_db()
    registro = conn.execute("""
        SELECT accion, detalle, timestamp FROM actividad
        WHERE accion='ELIMINAR_SALIDA' ORDER BY id DESC LIMIT 1
    """).fetchone()
    conn.close()
    assert f'Producto ID: {producto_id}' in registro['detalle']
    assert 'Cantidad: 3.0' in registro['detalle']
    assert registro['timestamp']


def test_reporte_diario_separa_totales_mxn_y_usd(auth_client):
    conn = database.get_db()
    producto_id = conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, ubicacion)
        VALUES ('MONEDA-1', 'Producto monedas', 'PZA', 'PRUEBA 06')
    """).lastrowid
    conn.execute("""
        INSERT INTO entradas
            (folio, producto_id, cantidad, precio_unitario, importe, no_factura,
             moneda, aplica_iva, usuario_id, fecha)
        VALUES ('MXN-1', ?, 1, 100, 100, 'FAC-MXN', 'MXN', 1, 1, '2026-08-07 10:00:00')
    """, (producto_id,))
    conn.execute("""
        INSERT INTO entradas
            (folio, producto_id, cantidad, precio_unitario, importe, no_factura,
             moneda, aplica_iva, usuario_id, fecha)
        VALUES ('USD-1', ?, 1, 50, 50, 'FAC-USD', 'USD', 0, 1, '2026-08-07 11:00:00')
    """, (producto_id,))
    conn.commit(); conn.close()
    response = auth_client.get('/entradas/reporte_diario?fecha=2026-08-07')
    assert response.status_code == 200
    assert b'$116.00 MXN' in response.data
    assert b'$50.00 USD' in response.data
    assert b'incl.' not in response.data


def test_totales_reporte_diario_solo_aparecen_en_ultima_pagina(auth_client):
    conn = database.get_db()
    producto_id = conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, ubicacion)
        VALUES ('PAG-TOTAL', 'Producto paginacion', 'PZA', 'PRUEBA 07')
    """).lastrowid
    for numero in range(51):
        conn.execute("""
            INSERT INTO entradas
                (folio, producto_id, cantidad, precio_unitario, importe, no_factura,
                 moneda, aplica_iva, usuario_id, fecha)
            VALUES (?, ?, 1, 1, 1, ?, 'MXN', 1, 1, '2026-08-08 10:00:00')
        """, (f'PAG-{numero}', producto_id, f'FAC-{numero}'))
    conn.commit(); conn.close()
    primera = auth_client.get('/entradas/reporte_diario?fecha=2026-08-08&pagina=1')
    ultima = auth_client.get('/entradas/reporte_diario?fecha=2026-08-08&pagina=2')
    assert b'Totales MXN:' not in primera.data
    assert b'Totales MXN:' in ultima.data
    assert b'table-footer-group' not in ultima.data


def test_impresion_reporte_diario_incluye_todas_las_filas_y_totales(auth_client):
    conn = database.get_db()
    producto_id = conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, ubicacion)
        VALUES ('PRINT-TOTAL', 'Producto impresion', 'PZA', 'PRUEBA 08')
    """).lastrowid
    for numero in range(51):
        conn.execute("""
            INSERT INTO entradas
                (folio, producto_id, cantidad, precio_unitario, importe, no_factura,
                 moneda, aplica_iva, usuario_id, fecha)
            VALUES (?, ?, 1, 1, 1, ?, 'MXN', 1, 1, '2026-08-09 10:00:00')
        """, (f'PRINT-{numero}', producto_id, f'FAC-PRINT-{numero}'))
    conn.commit(); conn.close()

    response = auth_client.get('/entradas/reporte_diario?fecha=2026-08-09&pagina=1&imprimir=1')
    assert response.status_code == 200
    assert b'FAC-PRINT-0' in response.data
    assert b'FAC-PRINT-50' in response.data
    assert b'Totales MXN:' in response.data
    assert b'window.print()' in response.data


def test_cookies_de_sesion_con_banderas_seguras():
    assert app.config['SESSION_COOKIE_HTTPONLY'] is True
    assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'


def test_paginas_criticas_renderizan_con_token_csrf(auth_client):
    for url in (
        '/dashboard', '/inventario/', '/entradas/', '/salidas/',
        '/requisiciones/', '/reportes/', '/balance/',
    ):
        response = auth_client.get(url)
        assert response.status_code == 200, url
        assert b'name="csrf-token"' in response.data, url


def _sesion_con_rol(client, rol):
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = f'prueba-{rol}'
        sess['nombre'] = f'Prueba {rol}'
        sess['rol'] = rol


def test_consulta_no_puede_modificar_inventario(client):
    _sesion_con_rol(client, 'consulta')
    response = client.post('/inventario/baja/999999')
    assert response.status_code == 403


def test_almacen_puede_operar_inventario(client):
    _sesion_con_rol(client, 'almacen')
    response = client.post('/inventario/baja/999999')
    assert response.status_code != 403


def test_compras_limitado_a_sus_modulos(client):
    _sesion_con_rol(client, 'compras')
    assert client.post('/inventario/baja/999999').status_code == 403
    assert client.post('/proveedores/eliminar/999999').status_code != 403


def test_admin_puede_crear_usuario_con_rol_compras(client):
    _sesion_con_rol(client, 'admin')
    response = client.post('/usuarios/nuevo', data={
        'nombre': 'Usuario Compras',
        'username': 'compras.prueba',
        'rol': 'compras',
        'password': 'Compras2026',
        'confirm': 'Compras2026',
    })
    assert response.status_code == 302
    conn = database.get_db()
    usuario = conn.execute(
        "SELECT rol FROM usuarios WHERE username='compras.prueba'"
    ).fetchone()
    conn.close()
    assert usuario['rol'] == 'compras'


def test_admin_puede_crear_roles_departamentales(client):
    _sesion_con_rol(client, 'admin')
    for rol in ('produccion', 'mantenimiento'):
        response = client.post('/usuarios/nuevo', data={
            'nombre': f'Usuario {rol}',
            'username': f'{rol}.prueba',
            'rol': rol,
            'password': 'Departamento2026',
            'confirm': 'Departamento2026',
        })
        assert response.status_code == 302
    conn = database.get_db()
    roles = {
        fila['rol'] for fila in conn.execute(
            "SELECT rol FROM usuarios WHERE username IN ('produccion.prueba', 'mantenimiento.prueba')"
        ).fetchall()
    }
    conn.close()
    assert roles == {'produccion', 'mantenimiento'}


def test_roles_departamentales_son_solo_lectura(client):
    for rol in ('produccion', 'mantenimiento'):
        _sesion_con_rol(client, rol)
        assert client.get('/inventario/').status_code == 200
        assert client.post('/inventario/baja/999999').status_code == 403
        assert client.post('/proveedores/eliminar/999999').status_code == 403
        assert client.post('/usuarios/nuevo', data={}).status_code == 403


def test_no_se_puede_desactivar_ultimo_admin(client):
    _sesion_con_rol(client, 'admin')
    response = client.post('/usuarios/editar/1', data={
        'nombre': 'Administrador',
        'activo': '0',
        'rol': 'consulta',
        'password': '',
        'confirm': '',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'ultimo administrador activo' in response.data
    conn = database.get_db()
    usuario = conn.execute('SELECT rol, activo FROM usuarios WHERE id=1').fetchone()
    conn.close()
    assert usuario['rol'] == 'admin'
    assert usuario['activo'] == 1


def test_consulta_ve_modulo_en_modo_solo_lectura(client):
    _sesion_con_rol(client, 'consulta')
    response = client.get('/inventario/')
    assert response.status_code == 200
    assert b'modo-solo-lectura' in response.data
    assert b'Modo solo lectura' in response.data


def test_acceso_denegado_se_registra_en_auditoria(client):
    _sesion_con_rol(client, 'compras')
    response = client.post('/inventario/baja/999999')
    assert response.status_code == 403
    conn = database.get_db()
    registro = conn.execute("""
        SELECT accion, detalle FROM actividad
        WHERE usuario_id=1 ORDER BY id DESC LIMIT 1
    """).fetchone()
    conn.close()
    assert registro['accion'] == 'ACCESO_DENEGADO'
    assert 'POST /inventario/baja/999999' in registro['detalle']
