"""Pruebas del cierre mensual de existencias."""

import database
from routes.balance import _calcular_fila


def _crear_producto_y_movimientos():
    conn = database.get_db()
    cursor = conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, stock_actual)
        VALUES ('BAL-001', 'Producto balance', 'PZA', 100)
    """)
    pid = cursor.lastrowid
    conn.execute("""
        INSERT INTO conteos_fisicos
            (producto_id, anio, mes, existencia_fisica, salidas_manual, usuario_id)
        VALUES (?, 2026, 6, 80, 10, 1)
    """, (pid,))
    conn.execute("""
        INSERT INTO entradas (folio, producto_id, cantidad, cantidad_piezas, usuario_id, fecha)
        VALUES ('ENT-BAL-001', ?, 20, 20, 1, '2026-07-10 10:00:00')
    """, (pid,))
    conn.commit()
    producto = conn.execute('SELECT * FROM productos WHERE id=?', (pid,)).fetchone()
    return conn, producto


def test_formula_inicio_mas_entradas_menos_salidas(client):
    conn, producto = _crear_producto_y_movimientos()
    fila = _calcular_fila(conn, producto, 2026, 7)
    assert fila['existencia_inicio'] == 80
    assert fila['entradas_mes'] == 20
    assert fila['salidas_manual'] is None

    conn.execute("""
        INSERT INTO conteos_fisicos
            (producto_id, anio, mes, existencia_fisica, salidas_manual, usuario_id)
        VALUES (?, 2026, 7, 85, 15, 1)
    """, (producto['id'],))
    conn.commit()
    fila = _calcular_fila(conn, producto, 2026, 7)
    conn.close()
    assert fila['existencia_final'] == 85  # 80 + 20 - 15


def test_cierre_anterior_es_inicio_del_mes_siguiente(client):
    conn, producto = _crear_producto_y_movimientos()
    conn.execute("""
        INSERT INTO conteos_fisicos
            (producto_id, anio, mes, existencia_fisica, salidas_manual, usuario_id)
        VALUES (?, 2026, 7, 85, 15, 1)
    """, (producto['id'],))
    conn.commit()
    agosto = _calcular_fila(conn, producto, 2026, 8)
    conn.close()
    assert agosto['existencia_inicio'] == 85
    assert agosto['inicio_es_estimado'] is False


def test_punto_de_partida_manual_tiene_prioridad(client):
    conn, producto = _crear_producto_y_movimientos()
    conn.execute("""
        INSERT INTO conteos_fisicos
            (producto_id, anio, mes, existencia_fisica, salidas_manual,
             existencia_inicio, entradas_mes, usuario_id)
        VALUES (?, 2026, 7, 125, 15, 120, 20, 1)
    """, (producto['id'],))
    conn.commit()
    julio = _calcular_fila(conn, producto, 2026, 7)
    conn.close()
    assert julio['existencia_inicio'] == 120
    assert julio['existencia_final'] == 125  # 120 + 20 - 15
    assert julio['inicio_guardado'] is True


def test_guardar_junio_manual_crea_cierre_y_encadena_julio(client):
    conn = database.get_db()
    cursor = conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, stock_actual)
        VALUES ('BAL-JUN', 'Inicio manual junio', 'PZA', 0)
    """)
    pid = cursor.lastrowid
    conn.commit()
    conn.close()
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['nombre'] = 'Administrador'
        sess['rol'] = 'admin'
        sess['balance_ids'] = [pid]

    response = client.post('/balance/', data={
        'accion': 'guardar_cierre',
        'anio': '2026',
        'mes': '6',
        f'inicio_{pid}': '250',
        f'salidas_{pid}': '30',
    })
    assert response.status_code == 302
    conn = database.get_db()
    cierre = conn.execute("""
        SELECT existencia_inicio, salidas_manual, existencia_fisica
        FROM conteos_fisicos WHERE producto_id=? AND anio=2026 AND mes=6
    """, (pid,)).fetchone()
    producto = conn.execute('SELECT * FROM productos WHERE id=?', (pid,)).fetchone()
    julio = _calcular_fila(conn, producto, 2026, 7)
    conn.close()
    assert tuple(cierre) == (250, 30, 220)
    assert julio['existencia_inicio'] == 220


def test_vista_paginada_y_exportacion_csv(auth_client):
    conn = database.get_db()
    conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, stock_actual)
        VALUES ('BAL-TODOS', 'Producto catalogo completo', 'PZA', 10)
    """)
    conn.commit()
    conn.close()
    pagina = auth_client.get('/balance/todos?anio=2026&mes=6&q=BAL-TODOS')
    assert pagina.status_code == 200
    assert b'BAL-TODOS' in pagina.data
    assert b'Guardar esta' in pagina.data
    csv_response = auth_client.get('/balance/todos/exportar.csv?anio=2026&mes=6')
    assert csv_response.status_code == 200
    assert csv_response.mimetype == 'text/csv'
    assert b'BAL-TODOS' in csv_response.data


def test_cerrar_bloquea_y_admin_puede_reabrir(client):
    conn = database.get_db()
    cursor = conn.execute("""
        INSERT INTO productos (codigo, descripcion, unidad_medida, stock_actual)
        VALUES ('BAL-CIERRE', 'Prueba cierre periodo', 'PZA', 50)
    """)
    pid = cursor.lastrowid
    conn.execute("""
        INSERT INTO conteos_fisicos
            (producto_id, anio, mes, existencia_fisica, salidas_manual,
             existencia_inicio, entradas_mes, usuario_id)
        VALUES (?, 2026, 6, 45, 5, 50, 0, 1)
    """, (pid,))
    conn.commit()
    conn.close()
    with client.session_transaction() as sess:
        sess['user_id'] = 1; sess['rol'] = 'admin'; sess['nombre'] = 'Admin'; sess['username'] = 'admin'
        sess['balance_ids'] = [pid]

    assert client.post('/balance/periodo/cerrar', data={'anio': 2026, 'mes': 6}).status_code == 302
    bloqueado = client.post('/balance/', data={
        'accion': 'guardar_cierre', 'anio': 2026, 'mes': 6,
        f'inicio_{pid}': 50, f'salidas_{pid}': 10,
    }, follow_redirects=True)
    assert b'periodo esta cerrado' in bloqueado.data
    assert client.post('/balance/periodo/reabrir', data={
        'anio': 2026, 'mes': 6, 'motivo': 'Ajuste de inventario fisico',
    }).status_code == 302
    conn = database.get_db()
    periodo = conn.execute("SELECT estado, motivo_reapertura FROM cierres_mensuales_periodos").fetchone()
    conn.close()
    assert periodo['estado'] == 'abierto'
    assert periodo['motivo_reapertura'] == 'Ajuste de inventario fisico'
