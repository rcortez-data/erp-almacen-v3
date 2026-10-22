from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from routes.auth import login_required
from database import get_db, next_folio, log_actividad
from routes.inventario import construir_busqueda_dinamica
from constantes import MAQUINAS
from datetime import datetime, date, timezone
import calendar

salidas_bp = Blueprint('salidas', __name__, url_prefix='/salidas')

CART_KEY = 'salida_cart'
DOC_KEY = 'salida_doc'


def normalizar_vale(no_vale, tipo_vale):
    valor = (no_vale or '').strip()
    if tipo_vale in ('mantenimiento', 'maquinados'):
        prefijo = 'M-'
    else:
        return valor
    valor_upper = valor.upper()
    if valor_upper.startswith(prefijo):
        numero = valor[len(prefijo):].strip()
    elif valor_upper.startswith('MAQ'):
        numero = valor[3:].strip().lstrip('-').strip()
    elif valor_upper.startswith('M'):
        numero = valor[1:].strip().lstrip('-').strip()
    else:
        numero = valor
    return f'{prefijo}{numero}' if numero else prefijo


def normalizar_vale_mantenimiento(no_vale, es_mantenimiento):
    """Normaliza el formato legible usado por el formulario de mantenimiento."""
    valor = (no_vale or '').strip()
    if not es_mantenimiento:
        return valor
    numero = valor.upper().removeprefix('M').lstrip('-').strip()
    return f'M {numero}'.strip() if numero else 'M'


def _factor_conversion(producto):
    try:
        factor = float(producto['factor_conversion'] or 0)
    except (TypeError, ValueError):
        return None
    return factor if producto['unidad_compra'] and factor > 0 else None


def _tipo_conversion(producto):
    return producto['tipo_conversion'] if 'tipo_conversion' in producto.keys() and producto['tipo_conversion'] else 'uso_a_compra'


def _stock_a_compra(cantidad_stock, producto):
    factor = _factor_conversion(producto)
    if not factor:
        return float(cantidad_stock or 0)
    if _tipo_conversion(producto) == 'compra_a_uso':
        return float(cantidad_stock or 0) / factor
    return float(cantidad_stock or 0) * factor


def _compra_a_stock(cantidad_compra, producto):
    factor = _factor_conversion(producto)
    if not factor:
        return float(cantidad_compra or 0)
    if _tipo_conversion(producto) == 'compra_a_uso':
        return float(cantidad_compra or 0) * factor
    return float(cantidad_compra or 0) / factor


def _cantidad_salida_stock(cantidad, producto):
    """Convierte la cantidad capturada de salida a la unidad que mueve stock."""
    return _compra_a_stock(cantidad, producto) if _factor_conversion(producto) else float(cantidad or 0)


def _cantidad_salida_compra_desde_form(form, producto):
    """Lee la salida aceptando unidad de compra o unidad de stock."""
    cantidad_raw = (form.get('cantidad') or '').strip()
    compra_raw = (form.get('cantidad_compra') or '').strip()
    factor = _factor_conversion(producto)
    if not cantidad_raw:
        if factor and compra_raw:
            return float(compra_raw)
        return None
    if factor:
        return _stock_a_compra(cantidad_raw, producto)
    return float(cantidad_raw)


def _cantidad_salida_db_desde_stock(cantidad_stock, producto):
    """Convierte una cantidad en unidad de inventario al valor que usa salidas.cantidad."""
    return _stock_a_compra(cantidad_stock, producto) if _factor_conversion(producto) else float(cantidad_stock or 0)


def _cantidad_salida_registrada_stock(salida, producto):
    """Devuelve el descuento real en unidad de inventario.

    ``cantidad_stock`` solo es confiable en salidas nuevas que guardaron el
    snapshot de conversión. En salidas históricas ese campo puede repetir la
    cantidad de compra, aunque el producto se controle en piezas.
    """
    if (salida['cantidad_stock'] is not None and
            salida['unidad_compra_movimiento'] and
            salida['factor_conversion_movimiento']):
        return float(salida['cantidad_stock'] or 0)
    return _cantidad_salida_stock(salida['cantidad'], producto)


def _sumar_entradas_stock(conn, producto, fecha_ini, fecha_fin_excl):
    """Suma entradas en la unidad de inventario, igual que Balance Mensual."""
    factor = _factor_conversion(producto)
    if factor:
        cantidad_compra = conn.execute("""
            SELECT COALESCE(SUM(cantidad),0)
            FROM entradas
            WHERE producto_id=?
              AND DATE(COALESCE(fecha_vale, fecha)) >= ?
              AND DATE(COALESCE(fecha_vale, fecha)) < ?
        """, (producto['id'], fecha_ini, fecha_fin_excl)).fetchone()[0] or 0
        return _compra_a_stock(cantidad_compra, producto)
    return float(conn.execute("""
        SELECT COALESCE(SUM(COALESCE(cantidad_piezas, cantidad)),0)
        FROM entradas
        WHERE producto_id=?
          AND DATE(COALESCE(fecha_vale, fecha)) >= ?
          AND DATE(COALESCE(fecha_vale, fecha)) < ?
    """, (producto['id'], fecha_ini, fecha_fin_excl)).fetchone()[0] or 0)


def _sumar_salidas_stock(conn, producto, fecha_ini, fecha_fin_excl):
    """Suma salidas en la unidad de inventario, igual que Balance Mensual."""
    filas = conn.execute("""
        SELECT cantidad, cantidad_stock, unidad_compra_movimiento,
               factor_conversion_movimiento
        FROM salidas
        WHERE producto_id=?
          AND DATE(COALESCE(fecha_vale, fecha)) >= ?
          AND DATE(COALESCE(fecha_vale, fecha)) < ?
    """, (producto['id'], fecha_ini, fecha_fin_excl)).fetchall()
    total = 0.0
    for fila in filas:
        if (fila['cantidad_stock'] is not None and
                fila['unidad_compra_movimiento'] and
                fila['factor_conversion_movimiento']):
            total += float(fila['cantidad_stock'] or 0)
        else:
            total += _cantidad_salida_stock(fila['cantidad'], producto)
    return total


def _inicio_mes_balance(conn, producto, anio, mes):
    """Calcula el inicio de mes tomando como punto de partida el último cierre físico."""
    inicio_mes = date(anio, mes, 1)
    cierre_anterior = conn.execute("""
        SELECT anio, mes, existencia_fisica
        FROM conteos_fisicos
        WHERE producto_id=?
          AND (anio < ? OR (anio=? AND mes < ?))
          AND existencia_fisica IS NOT NULL
        ORDER BY anio DESC, mes DESC
        LIMIT 1
    """, (producto['id'], anio, anio, mes)).fetchone()
    if cierre_anterior:
        base_anio = int(cierre_anterior['anio'])
        base_mes = int(cierre_anterior['mes'])
        if base_mes == 12:
            fecha_base = date(base_anio + 1, 1, 1)
        else:
            fecha_base = date(base_anio, base_mes + 1, 1)
        inicio = float(cierre_anterior['existencia_fisica'] or 0)
    else:
        inicio_anio = conn.execute("""
            SELECT cantidad
            FROM dashboard_consumo_inicio
            WHERE producto_id=? AND grupo='caldera' AND anio=?
        """, (producto['id'], anio)).fetchone()
        fecha_base = date(anio, 1, 1)
        inicio = float(inicio_anio['cantidad'] if inicio_anio else 0)

    if fecha_base.isoformat() < inicio_mes.isoformat():
        inicio += _sumar_entradas_stock(conn, producto, fecha_base.isoformat(), inicio_mes.isoformat())
        inicio -= _sumar_salidas_stock(conn, producto, fecha_base.isoformat(), inicio_mes.isoformat())
    return inicio


def _salidas_return_url():
    return_to = request.values.get('return_to') or ''
    if return_to.startswith('/salidas'):
        return return_to
    return url_for('salidas.index')


@salidas_bp.route('/eliminar/<int:sid>', methods=['POST'])
@login_required
def eliminar(sid):
    """Elimina una salida capturada por error. Revierte su efecto en el stock del
    producto (regresa la cantidad que esa salida había descontado) y borra el registro."""
    conn = get_db()
    salida = conn.execute("SELECT * FROM salidas WHERE id=?", (sid,)).fetchone()
    if not salida:
        flash('Registro no encontrado.', 'danger')
        conn.close()
        return redirect(_salidas_return_url())
    try:
        producto = conn.execute("SELECT * FROM productos WHERE id=?", (salida['producto_id'],)).fetchone()
        cantidad_stock = (_cantidad_salida_registrada_stock(salida, producto)
                          if producto else salida['cantidad'])
        conn.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE id=?",
                    (cantidad_stock, salida['producto_id']))
        conn.execute("DELETE FROM salidas WHERE id=?", (sid,))
        conn.commit()
        log_actividad(
            session['user_id'], 'ELIMINAR_SALIDA',
            f"ID: {sid} | Folio: {salida['folio']} | Producto ID: {salida['producto_id']} | Cantidad: {salida['cantidad']}",
        )
        flash(f"Salida (folio {salida['folio']}) eliminada y stock revertido.", 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    conn.close()
    return redirect(_salidas_return_url())


@salidas_bp.route('/')
@login_required
def index():
    fecha_ini = request.args.get('fecha_ini', '')
    fecha_fin = request.args.get('fecha_fin', '')
    q = request.args.get('q', '').strip()
    q_resp = request.args.get('q_resp', '').strip()
    q_area = request.args.get('q_area', '').strip()
    q_vale = request.args.get('q_vale', '').strip()
    solo_h = request.args.get('solo_h') in ('1', 'true', 'on', 'si')
    salida_ids_reporte = _ids_salidas_reporte(request.args)
    reporte_todos = request.args.get('reporte_todos') in ('1', 'true', 'on', 'si')
    pagina = request.args.get('pagina', 1, type=int)
    registros_por_pagina = 50
    
    conn = get_db()
    select_sql = """
        SELECT s.*, p.codigo, p.codigo_barras, p.descripcion, p.unidad_medida,
               p.unidad_compra, p.factor_conversion, p.tipo_conversion,
               COALESCE(p.stock_origen, 'ALMACEN') AS stock_origen,
               p.producto_origen_id,
               u.nombre as usuario_nombre
    """
    from_sql = """
        FROM salidas s
        JOIN productos p ON s.producto_id=p.id
        LEFT JOIN usuarios u ON s.usuario_id=u.id
        WHERE 1=1
    """
    where_sql = ""
    params = []
    if fecha_ini:
        where_sql += " AND DATE(COALESCE(s.fecha_vale, s.fecha)) >= ?"; params.append(fecha_ini)
    if fecha_fin:
        where_sql += " AND DATE(COALESCE(s.fecha_vale, s.fecha)) <= ?"; params.append(fecha_fin)
    if q:
        cond, cond_params = construir_busqueda_dinamica(q, ["p.codigo", "p.codigo_barras", "p.descripcion", "s.folio"])
        if cond:
            where_sql += f" AND {cond}"
            params += cond_params
    if q_resp:
        cond, cond_params = construir_busqueda_dinamica(q_resp, ["s.responsable"])
        if cond:
            where_sql += f" AND {cond}"
            params += cond_params
    if q_area:
        cond, cond_params = construir_busqueda_dinamica(q_area, ["s.area"])
        if cond:
            where_sql += f" AND {cond}"
            params += cond_params
    if q_vale:
        cond, cond_params = construir_busqueda_dinamica(q_vale, ["s.no_vale", "s.no_factura", "s.no_remision", "s.maquina"])
        if cond:
            where_sql += f" AND {cond}"
            params += cond_params
    if solo_h:
        where_sql += " AND COALESCE(p.stock_origen, 'ALMACEN') = 'H'"

    total_registros = conn.execute(
        f"SELECT COUNT(*) as total {from_sql} {where_sql}",
        params
    ).fetchone()['total']
    total_paginas = (total_registros + registros_por_pagina - 1) // registros_por_pagina
    
    if pagina < 1:
        pagina = 1
    elif pagina > total_paginas and total_paginas > 0:
        pagina = total_paginas
    
    offset = (pagina - 1) * registros_por_pagina
    salidas = conn.execute(
        f"{select_sql} {from_sql} {where_sql} ORDER BY s.fecha DESC LIMIT ? OFFSET ?",
        params + [registros_por_pagina, offset]
    ).fetchall()
    areas_lista = conn.execute("SELECT * FROM areas WHERE activo=1 ORDER BY LOWER(nombre)").fetchall()
    totales = conn.execute(f"""
        SELECT COALESCE(SUM(s.cantidad), 0) AS total_cantidad,
               SUM(CASE WHEN s.tipo_movimiento = 'ajuste' THEN 1 ELSE 0 END) AS total_ajustes,
               COUNT(DISTINCT NULLIF(TRIM(s.no_vale), '')) AS total_vales
        {from_sql} {where_sql}
    """, params).fetchone()
    total_cantidad = round(totales['total_cantidad'] or 0, 2)
    total_ajustes = totales['total_ajustes'] or 0
    total_vales = totales['total_vales'] or 0
    filtro_activo = bool(fecha_ini or fecha_fin or q or q_resp or q_area or q_vale or solo_h)
    
    conn.close()
    return render_template('salidas/index.html', salidas=salidas,
                           fecha_ini=fecha_ini, fecha_fin=fecha_fin, q=q, q_resp=q_resp,
                           q_area=q_area, q_vale=q_vale, solo_h=solo_h,
                           salida_ids_reporte=salida_ids_reporte, reporte_todos=reporte_todos,
                           total_cantidad=total_cantidad,
                           total_ajustes=total_ajustes,
                           total_vales=total_vales,
                           filtro_activo=filtro_activo,
                           areas_lista=areas_lista,
                           pagina_actual=pagina, total_paginas=total_paginas,
                           total_registros=total_registros, registros_pagina=len(salidas))


def _ids_salidas_reporte(args):
    ids = []
    for raw in args.getlist('salida_ids'):
        for value in str(raw).split(','):
            try:
                producto_id = int(value)
            except (TypeError, ValueError):
                continue
            if producto_id > 0 and producto_id not in ids:
                ids.append(producto_id)
    return ids


def _cantidad_salida_reporte(salida):
    snapshot = salida['cantidad_stock'] is not None and salida['unidad_compra_movimiento'] and salida['factor_conversion_movimiento']
    if snapshot:
        return float(salida['cantidad_stock'] or 0)
    factor = salida['factor_conversion']
    if salida['unidad_compra'] and factor:
        if salida['tipo_conversion'] == 'compra_a_uso':
            return float(salida['cantidad'] or 0) * float(factor)
        return float(salida['cantidad'] or 0) / float(factor)
    return float(salida['cantidad'] or 0)


def _datos_conversion_salida_reporte(salida):
    """Devuelve la cantidad en unidad de compra para mostrar conversiones."""
    unidad_compra = salida['unidad_compra_movimiento'] or salida['unidad_compra']
    factor = salida['factor_conversion_movimiento'] or salida['factor_conversion']
    if not unidad_compra or not factor:
        return None, None
    return float(salida['cantidad'] or 0), unidad_compra


@salidas_bp.route('/reporte')
@login_required
def reporte():
    fecha_ini = request.args.get('fecha_ini', '').strip()
    fecha_fin = request.args.get('fecha_fin', '').strip()
    q = request.args.get('q', '').strip()
    q_resp = request.args.get('q_resp', '').strip()
    q_area = request.args.get('q_area', '').strip()
    q_vale = request.args.get('q_vale', '').strip()
    solo_h = request.args.get('solo_h') in ('1', 'true', 'on', 'si')
    reporte_todos = request.args.get('reporte_todos') in ('1', 'true', 'on', 'si')
    salida_ids = _ids_salidas_reporte(request.args)

    where_sql = "WHERE 1=1"
    params = []
    if fecha_ini:
        where_sql += " AND DATE(COALESCE(s.fecha_vale, s.fecha)) >= ?"
        params.append(fecha_ini)
    if fecha_fin:
        where_sql += " AND DATE(COALESCE(s.fecha_vale, s.fecha)) <= ?"
        params.append(fecha_fin)
    if salida_ids and not reporte_todos:
        placeholders = ','.join('?' for _ in salida_ids)
        where_sql += f" AND s.id IN ({placeholders})"
        params.extend(salida_ids)
    if q:
        cond, cond_params = construir_busqueda_dinamica(q, ['p.codigo', 'p.codigo_barras', 'p.descripcion', 's.folio'])
        if cond:
            where_sql += f" AND {cond}"
            params.extend(cond_params)
    if q_resp:
        cond, cond_params = construir_busqueda_dinamica(q_resp, ['s.responsable'])
        if cond:
            where_sql += f" AND {cond}"
            params.extend(cond_params)
    if q_area:
        cond, cond_params = construir_busqueda_dinamica(q_area, ['s.area'])
        if cond:
            where_sql += f" AND {cond}"
            params.extend(cond_params)
    if q_vale:
        cond, cond_params = construir_busqueda_dinamica(q_vale, ['s.no_vale', 's.no_factura', 's.no_remision', 's.maquina'])
        if cond:
            where_sql += f" AND {cond}"
            params.extend(cond_params)
    if solo_h:
        where_sql += " AND COALESCE(p.stock_origen, 'ALMACEN') = 'H'"

    conn = get_db()
    filas = conn.execute(f"""
        SELECT s.*, p.codigo, p.codigo_barras, p.descripcion, p.unidad_medida,
               p.unidad_compra, p.factor_conversion, p.tipo_conversion,
               COALESCE(p.stock_origen, 'ALMACEN') AS stock_origen,
               u.nombre AS usuario_nombre
        FROM salidas s
        JOIN productos p ON s.producto_id=p.id
        LEFT JOIN usuarios u ON s.usuario_id=u.id
        {where_sql}
        ORDER BY COALESCE(s.fecha_vale, s.fecha) DESC, s.id DESC
    """, params).fetchall()
    conn.close()

    movimientos = []
    for fila in filas:
        movimiento = dict(fila)
        movimiento['cantidad_salida'] = _cantidad_salida_reporte(fila)
        movimiento['cantidad_compra_reporte'], movimiento['unidad_compra_reporte'] = _datos_conversion_salida_reporte(fila)
        movimientos.append(movimiento)
    productos_reporte = sorted({fila['codigo'] for fila in movimientos})
    total_cantidad = sum(fila['cantidad_salida'] for fila in movimientos)
    resumen_por_producto = {}
    for movimiento in movimientos:
        producto_id = movimiento['producto_id']
        resumen = resumen_por_producto.setdefault(producto_id, {
            'codigo': movimiento['codigo'],
            'descripcion': movimiento['descripcion'],
            'unidad_medida': movimiento['unidad_medida'],
            'cantidad_salida': 0,
            'cantidad_compra': 0,
            'unidad_compra': movimiento['unidad_compra_reporte'],
            'tiene_conversion': False,
        })
        resumen['cantidad_salida'] += movimiento['cantidad_salida']
        if movimiento['cantidad_compra_reporte'] is not None:
            resumen['cantidad_compra'] += movimiento['cantidad_compra_reporte']
            resumen['tiene_conversion'] = True
            resumen['unidad_compra'] = resumen['unidad_compra'] or movimiento['unidad_compra_reporte']
    resumen_productos = sorted(resumen_por_producto.values(), key=lambda item: item['codigo'])
    fechas_movimientos = [
        str(movimiento['fecha_vale'] or movimiento['fecha'] or '')[:10]
        for movimiento in movimientos
    ]
    fecha_hasta_reporte = fecha_fin or (max(fechas_movimientos) if fechas_movimientos else '')
    movimientos_por_producto = [
        {
            **resumen,
            'movimientos': [
                movimiento for movimiento in movimientos
                if movimiento['producto_id'] == producto_id
            ],
        }
        for producto_id, resumen in sorted(
            resumen_por_producto.items(), key=lambda item: item[1]['codigo']
        )
    ]
    return render_template(
        'salidas/reporte.html', movimientos=movimientos,
        fecha_ini=fecha_ini, fecha_fin=fecha_fin, q=q, q_resp=q_resp,
        q_area=q_area, q_vale=q_vale, solo_h=solo_h,
        salida_ids=salida_ids, reporte_todos=reporte_todos,
        productos_reporte=productos_reporte,
        total_cantidad=total_cantidad, resumen_productos=resumen_productos,
        movimientos_por_producto=movimientos_por_producto,
        fecha_hasta_reporte=fecha_hasta_reporte,
        ahora=datetime.now(timezone.utc),
    )


@salidas_bp.route('/consumo-mensual', methods=['GET', 'POST'])
@login_required
def consumo_mensual():
    """Captura el consumo fisico mensual de los productos seleccionados en Balance."""
    conn = get_db()
    ids = [int(pid) for pid in session.get('balance_ids', []) if str(pid).isdigit()]
    if not ids:
        ids = [row['producto_id'] for row in conn.execute("""
            SELECT bp.producto_id
            FROM bloque_productos bp JOIN productos p ON p.id=bp.producto_id
            WHERE bp.bloque_id=2 AND p.activo=1
            ORDER BY bp.orden, p.codigo
        """).fetchall()]
    productos = []
    if ids:
        marks = ','.join('?' for _ in ids)
        productos = conn.execute(
            f"SELECT id, codigo, descripcion, unidad_medida, unidad_compra, factor_conversion, tipo_conversion, stock_actual FROM productos WHERE activo=1 AND id IN ({marks}) ORDER BY codigo",
            ids
        ).fetchall()
        orden_balance = {pid: posicion for posicion, pid in enumerate(ids)}
        productos = sorted(productos, key=lambda producto: orden_balance.get(producto['id'], len(ids)))
    hoy = date.today()
    periodo = request.values.get('periodo') or hoy.strftime('%Y-%m')
    try:
        anio, mes = (int(x) for x in periodo.split('-', 1))
        primer_dia = date(anio, mes, 1).isoformat()
        ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1]).isoformat()
        if mes == 12:
            siguiente_mes = date(anio + 1, 1, 1).isoformat()
        else:
            siguiente_mes = date(anio, mes + 1, 1).isoformat()
    except (ValueError, TypeError):
        periodo = hoy.strftime('%Y-%m')
        anio, mes = hoy.year, hoy.month
        primer_dia = date(anio, mes, 1).isoformat()
        ultimo_dia = hoy.isoformat()
        siguiente_mes = (date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)).isoformat()

    existencias = {}
    inicios_mes = {}
    entradas_periodo = {}
    consumo_registrado = {}
    consumo_registrado_compra = {}
    for producto in productos:
        inicio_mes = _inicio_mes_balance(conn, producto, anio, mes)
        entradas_mes = _sumar_entradas_stock(conn, producto, primer_dia, siguiente_mes)
        salidas_mes = _sumar_salidas_stock(conn, producto, primer_dia, siguiente_mes)
        inicios_mes[producto['id']] = inicio_mes
        entradas_periodo[producto['id']] = entradas_mes
        consumo_registrado[producto['id']] = salidas_mes
        factor = _factor_conversion(producto)
        if factor:
            consumo_registrado_compra[producto['id']] = _stock_a_compra(salidas_mes, producto)
        existencias[producto['id']] = inicio_mes + entradas_mes - salidas_mes

    if request.method == 'POST':
        if not productos:
            flash('Primero selecciona productos en Balance Mensual.', 'warning')
            conn.close()
            return redirect(url_for('salidas.consumo_mensual', periodo=periodo))
        try:
            no_vale = f'CONSUMO-CALDERA-{periodo}'
            creadas = 0
            anio_inicio = int(periodo[:4])
            for producto in productos:
                inicio_raw = request.form.get(f'inicio_{producto["id"]}')
                inicio_existente = conn.execute(
                    "SELECT cantidad FROM dashboard_consumo_inicio WHERE producto_id=? AND grupo='caldera' AND anio=?",
                    (producto['id'], anio_inicio)
                ).fetchone()
                if anio_inicio and mes == 1 and inicio_raw not in (None, '') and not inicio_existente:
                    conn.execute("""
                        INSERT INTO dashboard_consumo_inicio
                        (producto_id, grupo, anio, cantidad, actualizado_at)
                        VALUES (?, 'caldera', ?, ?, CURRENT_TIMESTAMP)
                    """, (producto['id'], anio_inicio, float(inicio_raw or 0)))
                cantidad_raw = request.form.get(f'cantidad_{producto["id"]}')
                if cantidad_raw in (None, ''):
                    continue
                cantidad = float(cantidad_raw)
                if cantidad < 0:
                    raise ValueError(f'La cantidad de {producto["codigo"]} no puede ser negativa.')
                existe = conn.execute("""
                    SELECT id, cantidad FROM salidas
                    WHERE producto_id=? AND tipo_movimiento='consumo_fisico'
                      AND area='CALDERA' AND fecha_vale=?
                """, (producto['id'], ultimo_dia)).fetchone()
                cantidad_db = _cantidad_salida_db_desde_stock(cantidad, producto)
                if existe:
                    cantidad_stock_anterior = _cantidad_salida_stock(existe['cantidad'], producto)
                    diferencia_stock = cantidad - cantidad_stock_anterior
                    conn.execute("""
                        UPDATE salidas
                        SET cantidad=?, usuario_id=?, observaciones=?, fecha=?
                        WHERE id=?
                    """, (
                        cantidad_db, session['user_id'],
                        'Consumo fisico mensual actualizado desde Balance Mensual',
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), existe['id']
                    ))
                    conn.execute(
                        "UPDATE productos SET stock_actual=stock_actual-? WHERE id=?",
                        (diferencia_stock, producto['id']))
                    creadas += 1
                    continue
                conn.execute("UPDATE folios SET ultimo=ultimo+1 WHERE tipo='salida'")
                numero = conn.execute("SELECT ultimo FROM folios WHERE tipo='salida'").fetchone()[0]
                folio = f'SAL-{str(numero).zfill(6)}'
                conn.execute("""
                    INSERT INTO salidas
                    (folio, producto_id, cantidad, cantidad_stock, unidad_compra_movimiento,
                     factor_conversion_movimiento, tipo_conversion_movimiento, responsable, area, no_vale, tipo_vale,
                     tipo_movimiento, usuario_id, observaciones, fecha, fecha_vale)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (folio, producto['id'], cantidad_db, cantidad, producto['unidad_compra'], producto['factor_conversion'], producto['tipo_conversion'] or 'uso_a_compra', 'CONSUMO FISICO', 'CALDERA', no_vale,
                      'caldera', 'consumo_fisico', session['user_id'],
                      'Consumo fisico mensual capturado desde Balance Mensual',
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ultimo_dia))
                conn.execute("UPDATE productos SET stock_actual=stock_actual-? WHERE id=?", (cantidad, producto['id']))
                creadas += 1
            conn.commit()
            log_actividad(session['user_id'], 'CONSUMO_FISICO_MENSUAL', f'Periodo: {periodo} | Registros: {creadas}')
            flash(f'{creadas} consumo(s) físico(s) registrados para {periodo}.', 'success')
        except Exception as error:
            conn.rollback()
            flash(f'No se pudo registrar el consumo físico: {error}', 'danger')
        conn.close()
        return redirect(url_for('salidas.consumo_mensual', periodo=periodo))

    existentes = {}
    inicios = {}
    if productos:
        marks = ','.join('?' for _ in productos)
        existentes = {
            r['producto_id']: float(r['cantidad']) for r in conn.execute(
                f"""
                SELECT s.producto_id, COALESCE(s.cantidad_stock, s.cantidad) AS cantidad,
                       p.unidad_compra, p.factor_conversion, p.tipo_conversion
                FROM salidas s JOIN productos p ON p.id=s.producto_id
                WHERE s.producto_id IN ({marks})
                  AND s.tipo_movimiento='consumo_fisico'
                  AND s.area='CALDERA'
                  AND s.fecha_vale=?
                """,
                [r['id'] for r in productos] + [ultimo_dia]
            ).fetchall()
        }
        inicios = {
            r['producto_id']: r['cantidad'] for r in conn.execute(
                f"SELECT producto_id, cantidad FROM dashboard_consumo_inicio WHERE grupo='caldera' AND anio=? AND producto_id IN ({marks})",
                [int(periodo[:4])] + [r['id'] for r in productos]
            ).fetchall()
        }
    conn.close()
    return render_template('salidas/consumo_mensual.html', productos=productos,
                           periodo=periodo, ultimo_dia=ultimo_dia, existentes=existentes,
                           inicios=inicios, inicios_mes=inicios_mes, existencias=existencias,
                           entradas_periodo=entradas_periodo,
                           consumo_registrado=consumo_registrado,
                           consumo_registrado_compra=consumo_registrado_compra)


@salidas_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    """
    Vale de salida con varios productos a la vez (como Entradas): se van
    agregando productos a una lista en sesión y hasta el final se guardan
    todos juntos, cada uno con su propio folio pero compartiendo el mismo
    vale/responsable/área. Al terminar de guardar, NO se regresa al listado:
    se limpia todo y se queda en esta misma página lista para el siguiente vale.
    """
    conn = get_db()
    areas_lista = conn.execute("SELECT * FROM areas WHERE activo=1 ORDER BY LOWER(nombre)").fetchall()

    if request.method == 'POST':
        accion = request.form.get('accion')

        # Los datos del vale (responsable, área, folio de vale, etc.) se
        # guardan en sesión cada vez que se envía el formulario, igual que
        # en Entradas, para no perderlos si se agregan varios productos.
        es_mantenimiento = request.form.get('es_mantenimiento') == 'on'
        es_maquinados = request.form.get('es_maquinados') == 'on'
        tipo_vale = 'maquinados' if es_maquinados else ('mantenimiento' if es_mantenimiento else 'normal')
        no_vale = normalizar_vale(request.form.get('no_vale', ''), tipo_vale)
        area_doc = 'MAQUINADOS' if tipo_vale == 'maquinados' else ('MANTENIMIENTO' if tipo_vale == 'mantenimiento' else request.form.get('area', ''))
        session[DOC_KEY] = {
            'responsable': request.form.get('responsable', ''),
            'area': area_doc,
            'no_vale': no_vale,
            'tipo_vale': tipo_vale,
            'es_mantenimiento': es_mantenimiento,
            'es_maquinados': es_maquinados,
            'maquina': request.form.get('maquina', ''),
            'maquina_otro': request.form.get('maquina_otro', ''),
            'proveedor': request.form.get('proveedor', ''),
            'orden_compra': request.form.get('orden_compra', ''),
            'no_factura': request.form.get('no_factura', ''),
            'no_remision': request.form.get('no_remision', ''),
            'tipo_movimiento': request.form.get('tipo_movimiento', 'normal'),
            'observaciones': request.form.get('observaciones', ''),
            'fecha_vale': request.form.get('fecha_vale') or session.get(DOC_KEY, {}).get('fecha_vale', datetime.now().date().isoformat()),
        }
        session.modified = True
        doc = session.get(DOC_KEY, {})

        if accion == 'agregar_item':
            pid = request.form.get('producto_id')
            if not pid:
                flash('Selecciona un producto de la lista y captura la cantidad.', 'danger')
            else:
                prod = conn.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()
                if not prod:
                    flash('El producto seleccionado no existe.', 'danger')
                else:
                    cantidad = _cantidad_salida_compra_desde_form(request.form, prod)
                    if cantidad is None or cantidad <= 0:
                        flash('Captura una cantidad mayor a 0.', 'danger')
                        conn.close()
                        return redirect(url_for('salidas.nuevo'))
                    cart = session.get(CART_KEY, [])
                    cart.append({
                        'producto_id': prod['id'], 'codigo': prod['codigo'],
                        'codigo_barras': prod['codigo_barras'],
                        'descripcion': prod['descripcion'],
                        'unidad_medida': prod['unidad_medida'],
                        'unidad_compra': prod['unidad_compra'],
                        'factor_conversion': prod['factor_conversion'],
                        'tipo_conversion': prod['tipo_conversion'] or 'uso_a_compra',
                        'cantidad': cantidad,
                        'stock_actual': prod['stock_actual'],
                        'stock_origen': prod['stock_origen'],
                        'orden_compra': doc.get('orden_compra', ''),
                        'no_factura': doc.get('no_factura', ''),
                        'no_remision': doc.get('no_remision', ''),
                    })
                    session[CART_KEY] = cart
                    session.modified = True
                    flash(f"{prod['codigo']} agregado a la lista.", 'success')
            conn.close()
            return redirect(url_for('salidas.nuevo'))

        elif accion in ('agregar_documento', 'agregar_documento_seleccionados'):
            documento_tipo = request.form.get('documento_tipo')
            documento_valor = (request.form.get('documento_valor') or '').strip()
            columnas = {'oc': 'e.orden_compra', 'factura': 'e.no_factura', 'remision': 'e.no_remision'}
            columna = columnas.get(documento_tipo)
            if not columna or not documento_valor:
                flash('Selecciona OC o factura y captura el número del documento.', 'danger')
                conn.close()
                return redirect(url_for('salidas.nuevo'))
            filas = conn.execute(f"""
                SELECT e.producto_id,
                       SUM(e.cantidad) AS cantidad,
                       p.codigo, p.codigo_barras, p.descripcion, p.unidad_medida,
                       p.unidad_compra, p.factor_conversion, p.tipo_conversion, p.stock_actual,
                       COALESCE(p.stock_origen, 'ALMACEN') AS stock_origen
                FROM entradas e JOIN productos p ON p.id=e.producto_id
                WHERE p.activo=1 AND TRIM(UPPER({columna}))=TRIM(UPPER(?))
                GROUP BY e.producto_id, p.codigo, p.codigo_barras, p.descripcion,
                         p.unidad_medida, p.unidad_compra, p.factor_conversion, p.tipo_conversion, p.stock_actual, p.stock_origen
                ORDER BY p.codigo
            """, (documento_valor,)).fetchall()
            documento_item = conn.execute(f"""
                SELECT MAX(NULLIF(TRIM(e.orden_compra), '')) AS orden_compra,
                       MAX(NULLIF(TRIM(e.no_factura), '')) AS no_factura,
                       MAX(NULLIF(TRIM(e.no_remision), '')) AS no_remision
                FROM entradas e WHERE TRIM(UPPER({columna}))=TRIM(UPPER(?))
            """, (documento_valor,)).fetchone()
            if not filas:
                flash(f'No se encontraron productos activos para {documento_tipo.upper()} {documento_valor}.', 'warning')
            else:
                cart = session.get(CART_KEY, [])
                existentes = {item['producto_id'] for item in cart}
                productos_seleccionados = None
                if accion == 'agregar_documento_seleccionados':
                    productos_seleccionados = {
                        int(pid) for pid in request.form.getlist('producto_ids')
                        if pid.isdigit()
                    }
                agregados = 0
                omitidos = 0
                for prod in filas:
                    if productos_seleccionados is not None and prod['producto_id'] not in productos_seleccionados:
                        continue
                    if prod['producto_id'] in existentes:
                        omitidos += 1
                        continue
                    cantidad_seleccionada = request.form.get(f"producto_cantidad_{prod['producto_id']}")
                    cantidad_stock = request.form.get(f"producto_cantidad_stock_{prod['producto_id']}")
                    try:
                        if prod['unidad_compra'] and prod['factor_conversion'] and cantidad_stock and not cantidad_seleccionada:
                            cantidad_seleccionada = _cantidad_salida_db_desde_stock(float(cantidad_stock), prod)
                        else:
                            cantidad_seleccionada = float(cantidad_seleccionada) if cantidad_seleccionada else float(prod['cantidad'])
                    except (TypeError, ValueError):
                        cantidad_seleccionada = 0
                    if cantidad_seleccionada <= 0 or cantidad_seleccionada > float(prod['cantidad']):
                        omitidos += 1
                        continue
                    cart.append({
                        'producto_id': prod['producto_id'], 'codigo': prod['codigo'],
                        'codigo_barras': prod['codigo_barras'], 'descripcion': prod['descripcion'],
                        'unidad_medida': prod['unidad_medida'], 'unidad_compra': prod['unidad_compra'],
                        'factor_conversion': prod['factor_conversion'], 'tipo_conversion': prod['tipo_conversion'] or 'uso_a_compra',
                        'cantidad': cantidad_seleccionada,
                        'stock_actual': prod['stock_actual'],
                        'stock_origen': prod['stock_origen'],
                        'orden_compra': documento_item['orden_compra'] if documento_item else None,
                        'no_factura': documento_item['no_factura'] if documento_item else None,
                        'no_remision': documento_item['no_remision'] if documento_item else None,
                    })
                    existentes.add(prod['producto_id'])
                    agregados += 1
                session[CART_KEY] = cart
                session.modified = True
                texto = f'Se agregaron {agregados} producto(s) de {documento_tipo.upper()} {documento_valor}.'
                if omitidos:
                    texto += f' {omitidos} ya estaban en la salida y se omitieron.'
                flash(texto, 'success')
            conn.close()
            return redirect(url_for('salidas.nuevo'))

        elif accion == 'quitar_item':
            idx = int(request.form.get('idx', -1))
            cart = session.get(CART_KEY, [])
            if 0 <= idx < len(cart):
                cart.pop(idx)
                session[CART_KEY] = cart
                session.modified = True
            conn.close()
            return redirect(url_for('salidas.nuevo'))

        elif accion == 'guardar_todo':
            cart = session.get(CART_KEY, [])
            doc = session.get(DOC_KEY, {})
            if not cart:
                flash('Agrega al menos un producto a la lista antes de guardar.', 'danger')
                conn.close()
                return redirect(url_for('salidas.nuevo'))
            if not (doc.get('responsable') or '').strip():
                flash('El nombre de quien recibe el material es obligatorio.', 'danger')
                conn.close()
                return redirect(url_for('salidas.nuevo'))
            if not (doc.get('no_vale') or '').strip():
                flash('El folio de vale es obligatorio (mínimo 1 carácter).', 'danger')
                conn.close()
                return redirect(url_for('salidas.nuevo'))
            if doc.get('tipo_vale') == 'mantenimiento' and not (doc.get('no_vale') or '')[2:].strip():
                flash('Captura el número del vale de mantenimiento después de "M-".', 'danger')
                conn.close()
                return redirect(url_for('salidas.nuevo'))
            if doc.get('tipo_vale') == 'maquinados' and not (doc.get('no_vale') or '')[2:].strip():
                flash('Captura el número del vale de maquinados después de "M-".', 'danger')
                conn.close()
                return redirect(url_for('salidas.nuevo'))
            if doc.get('tipo_vale') == 'maquinados' and not (doc.get('maquina') or '').strip():
                flash('Selecciona la máquina para el vale de maquinados.', 'danger')
                conn.close()
                return redirect(url_for('salidas.nuevo'))
            if doc.get('tipo_vale') == 'maquinados' and doc.get('maquina') == 'Otros' and not (doc.get('maquina_otro') or '').strip():
                flash('Especifica cuál es la máquina en el campo "Otros".', 'danger')
                conn.close()
                return redirect(url_for('salidas.nuevo'))
            try:
                tipo_mov = doc.get('tipo_movimiento') or 'normal'
                area = (doc.get('area') or '').strip() or None
                fecha_sql = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                fecha_vale = doc.get('fecha_vale') or datetime.now().date().isoformat()
                folios_generados = []
                for item in cart:
                    conn.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo = 'salida'")
                    num = conn.execute("SELECT ultimo FROM folios WHERE tipo = 'salida'").fetchone()[0]
                    folio = f"SAL-{str(num).zfill(6)}"
                    conn.execute("""
                        INSERT INTO salidas
                        (folio, producto_id, cantidad, cantidad_stock, unidad_compra_movimiento,
                         factor_conversion_movimiento, tipo_conversion_movimiento,
                         responsable, area, no_vale, tipo_vale, maquina,
                         maquina_otro, proveedor,
                         orden_compra, no_factura, no_remision, tipo_movimiento, usuario_id, observaciones, fecha, fecha_vale)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (folio, item['producto_id'], item['cantidad'],
                          _cantidad_salida_stock(item['cantidad'], item), item.get('unidad_compra'),
                          item.get('factor_conversion'), item.get('tipo_conversion') or 'uso_a_compra',
                          doc.get('responsable'), area,
                          doc.get('no_vale'), doc.get('tipo_vale') or 'normal', doc.get('maquina') or None,
                          doc.get('maquina_otro') if doc.get('maquina') == 'Otros' else None, doc.get('proveedor') or None,
                          item.get('orden_compra') or doc.get('orden_compra') or None,
                          item.get('no_factura') or doc.get('no_factura') or None,
                          item.get('no_remision') or doc.get('no_remision') or None,
                          tipo_mov, session['user_id'], doc.get('observaciones'), fecha_sql, fecha_vale))
                    conn.execute(
                        "UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?",
                        (_cantidad_salida_stock(item['cantidad'], item), item['producto_id']))
                    folios_generados.append(folio)
                conn.commit()
                log_actividad(session['user_id'], 'SALIDA',
                              f"Folios: {', '.join(folios_generados)} | Vale: {doc.get('no_vale') or '-'} | Tipo: {tipo_mov}")
                # Se limpia todo para el siguiente vale (responsable, no. de vale, área,
                # observaciones), EXCEPTO la fecha: si la cambiaste a mano, se queda así
                # para los siguientes vales en vez de regresar a "ahora" cada vez. Solo
                # vuelve a la fecha/hora actual si cierras sesión o le das "Usar fecha y hora actuales".
                fecha_para_siguiente = doc.get('fecha_vale')
                session.pop(CART_KEY, None)
                session.pop(DOC_KEY, None)
                session[DOC_KEY] = {
                    'responsable': '',
                    'area': '',
                    'no_vale': 'M-' if doc.get('tipo_vale') in ('mantenimiento', 'maquinados') else '',
                    'tipo_vale': doc.get('tipo_vale') or 'normal',
                    'es_mantenimiento': doc.get('tipo_vale') == 'mantenimiento',
                    'es_maquinados': doc.get('tipo_vale') == 'maquinados',
                    'maquina': doc.get('maquina') if doc.get('tipo_vale') == 'maquinados' else '',
                    'no_factura': '',
                    'no_remision': '',
                    'orden_compra': '',
                    'fecha_vale': fecha_para_siguiente,
                }
                flash(f"{len(folios_generados)} salida(s) registradas correctamente (vale {doc.get('no_vale')}).", 'success')
                conn.close()
                return redirect(url_for('salidas.nuevo'))
            except Exception as e:
                conn.rollback()
                flash(f'Error: {str(e)}', 'danger')
                conn.close()
                return redirect(url_for('salidas.nuevo'))

    doc = session.get(DOC_KEY, {})
    cart = session.get(CART_KEY, [])
    conn.close()
    ahora = datetime.now().strftime('%Y-%m-%dT%H:%M')
    return render_template('salidas/form.html', doc=doc, cart=cart, ahora=ahora, areas_lista=areas_lista, maquinas=MAQUINAS)


@salidas_bp.route('/api/movil/registrar', methods=['POST'])
@login_required
def api_movil_registrar():
    data = request.get_json(silent=True) or {}
    try:
        pid = int(data.get('producto_id') or 0)
        cantidad = float(data.get('cantidad') or 0)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Producto o cantidad inválida.'}), 400

    responsable = (data.get('responsable') or '').strip()
    tipo_vale = (data.get('tipo_vale') or 'normal').strip().lower()
    if tipo_vale not in ('normal', 'mantenimiento', 'maquinados'):
        tipo_vale = 'normal'
    no_vale = normalizar_vale(data.get('no_vale') or '', tipo_vale)
    maquina = (data.get('maquina') or '').strip()
    area = (data.get('area') or '').strip()
    if tipo_vale == 'mantenimiento':
        area = 'MANTENIMIENTO'
    elif tipo_vale == 'maquinados':
        area = 'MAQUINADOS'

    if not pid:
        return jsonify({'ok': False, 'error': 'Selecciona o escanea un producto.'}), 400
    if cantidad <= 0:
        return jsonify({'ok': False, 'error': 'Captura una cantidad mayor a 0.'}), 400
    if not responsable:
        return jsonify({'ok': False, 'error': 'Captura quién recibió el material.'}), 400
    if not no_vale or no_vale == 'M-':
        return jsonify({'ok': False, 'error': 'Captura el folio de vale.'}), 400
    if tipo_vale == 'maquinados' and not maquina:
        return jsonify({'ok': False, 'error': 'Selecciona la máquina para maquinados.'}), 400

    conn = get_db()
    prod = conn.execute("SELECT * FROM productos WHERE id=? AND activo=1", (pid,)).fetchone()
    if not prod:
        conn.close()
        return jsonify({'ok': False, 'error': 'El producto no existe o está archivado.'}), 404

    try:
        fecha_sql = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        fecha_vale = (data.get('fecha_vale') or '').strip() or datetime.now().date().isoformat()
        tipo_mov = (data.get('tipo_movimiento') or 'normal').strip() or 'normal'
        conn.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo = 'salida'")
        num = conn.execute("SELECT ultimo FROM folios WHERE tipo = 'salida'").fetchone()[0]
        folio = f"SAL-{str(num).zfill(6)}"
        conn.execute("""
            INSERT INTO salidas
            (folio, producto_id, cantidad, cantidad_stock, unidad_compra_movimiento,
             factor_conversion_movimiento, tipo_conversion_movimiento, responsable, area, no_vale, tipo_vale, maquina,
             no_factura, no_remision, tipo_movimiento, usuario_id, observaciones, fecha, fecha_vale)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (folio, pid, cantidad, _cantidad_salida_stock(cantidad, prod), prod['unidad_compra'],
              prod['factor_conversion'], prod['tipo_conversion'] or 'uso_a_compra', responsable, area or None, no_vale, tipo_vale, maquina or None,
              (data.get('no_factura') or '').strip() or None,
              (data.get('no_remision') or '').strip() or None,
              tipo_mov, session['user_id'], (data.get('observaciones') or '').strip() or None,
              fecha_sql, fecha_vale))
        cantidad_stock = _cantidad_salida_stock(cantidad, prod)
        conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?", (cantidad_stock, pid))
        stock_nuevo = conn.execute("SELECT stock_actual FROM productos WHERE id=?", (pid,)).fetchone()['stock_actual']
        conn.commit()
        log_actividad(session['user_id'], 'SALIDA_MOVIL',
                      f"Folio: {folio} | {prod['codigo']} | Cantidad: {cantidad} | Vale: {no_vale}")
        return jsonify({
            'ok': True,
            'folio': folio,
            'stock_actual': stock_nuevo,
            'unidad_medida': prod['unidad_medida'],
            'mensaje': f'Salida {folio} registrada.'
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        conn.close()


@salidas_bp.route('/cancelar_captura')
@login_required
def cancelar_captura():
    session.pop(CART_KEY, None)
    session.pop(DOC_KEY, None)
    flash('Captura cancelada.', 'warning')
    return redirect(url_for('salidas.index'))


@salidas_bp.route('/api/documentos-entrada')
@login_required
def api_documentos_entrada():
    tipo = request.args.get('tipo', 'oc')
    q = (request.args.get('q') or '').strip()
    columnas = {'oc': 'orden_compra', 'factura': 'no_factura', 'remision': 'no_remision'}
    columna = columnas.get(tipo)
    if not columna or len(q) < 2:
        return jsonify([])
    conn = get_db()
    filas = conn.execute(f"""
        SELECT TRIM(e.{columna}) AS valor, COUNT(DISTINCT e.producto_id) AS productos
        FROM entradas e
        JOIN productos p ON p.id=e.producto_id
        WHERE p.activo=1
          AND COALESCE(e.es_servicio, 0)=0
          AND TRIM(e.{columna}) <> ''
          AND UPPER(e.{columna}) LIKE UPPER(?)
        GROUP BY TRIM(e.{columna}) ORDER BY MAX(e.id) DESC LIMIT 12
    """, (f'%{q}%',)).fetchall()
    conn.close()
    return jsonify([dict(fila) for fila in filas])


@salidas_bp.route('/api/documento-productos')
@login_required
def api_documento_productos():
    tipo = request.args.get('tipo', 'oc')
    valor = (request.args.get('valor') or '').strip()
    columnas = {'oc': 'e.orden_compra', 'factura': 'e.no_factura', 'remision': 'e.no_remision'}
    columna = columnas.get(tipo)
    if not columna or not valor:
        return jsonify([])
    conn = get_db()
    filas = conn.execute(f"""
        SELECT p.id, p.codigo, p.descripcion, p.unidad_medida,
               SUM(e.cantidad) AS cantidad,
               p.unidad_compra, p.factor_conversion, p.tipo_conversion, p.stock_actual,
               COALESCE(p.stock_origen, 'ALMACEN') AS stock_origen
        FROM entradas e JOIN productos p ON p.id=e.producto_id
        WHERE p.activo=1 AND TRIM(UPPER({columna}))=TRIM(UPPER(?))
        GROUP BY p.id, p.codigo, p.descripcion, p.unidad_medida, p.unidad_compra, p.factor_conversion, p.tipo_conversion, p.stock_actual, p.stock_origen
        ORDER BY p.codigo
    """, (valor,)).fetchall()
    documentos = conn.execute(f"""
        SELECT MAX(NULLIF(TRIM(e.orden_compra), '')) AS orden_compra,
               MAX(NULLIF(TRIM(e.no_factura), '')) AS no_factura,
               MAX(NULLIF(TRIM(e.no_remision), '')) AS no_remision
        FROM entradas e
        WHERE TRIM(UPPER({columna}))=TRIM(UPPER(?))
    """, (valor,)).fetchone()
    conn.close()
    return jsonify({'productos': [dict(fila) for fila in filas], 'documentos': dict(documentos or {})})


@salidas_bp.route('/detalle/<int:sid>')
@login_required
def detalle(sid):
    return_to = _salidas_return_url()
    conn = get_db()
    salida = conn.execute("""
        SELECT s.*, p.codigo, p.codigo_barras, p.descripcion, p.unidad_medida,
               p.unidad_compra, p.factor_conversion, p.tipo_conversion,
               u.nombre as usuario_nombre
        FROM salidas s
        JOIN productos p ON s.producto_id=p.id
        LEFT JOIN usuarios u ON s.usuario_id=u.id
        WHERE s.id=?
    """, (sid,)).fetchone()
    conn.close()
    if not salida:
        flash('Registro no encontrado.', 'danger')
        return redirect(return_to)
    return render_template('salidas/detalle.html', salida=salida, return_to=return_to)


@salidas_bp.route('/editar/<int:sid>', methods=['GET', 'POST'])
@login_required
def editar(sid):
    """Permite corregir por completo una salida ya registrada: producto, cantidad,
    responsable, folio de vale, tipo de movimiento, observaciones y fecha. Al cambiar
    producto o cantidad, el stock se ajusta automáticamente (se revierte el efecto
    anterior sobre el producto original y se aplica el nuevo)."""
    return_to = _salidas_return_url()
    conn = get_db()
    salida = conn.execute("""
        SELECT s.*, p.codigo, p.codigo_barras, p.descripcion, p.unidad_medida,
               p.unidad_compra, p.factor_conversion, p.tipo_conversion
        FROM salidas s
        JOIN productos p ON s.producto_id=p.id
        WHERE s.id=?
    """, (sid,)).fetchone()
    areas_lista = conn.execute("SELECT * FROM areas WHERE activo=1 ORDER BY LOWER(nombre)").fetchall()
    if not salida:
        flash('Registro no encontrado.', 'danger')
        conn.close()
        return redirect(return_to)

    if request.method == 'POST':
        f = request.form
        try:
            pid = f.get('producto_id')
            responsable = (f.get('responsable') or '').strip()
            tipo_vale = f.get('tipo_vale') or salida['tipo_vale'] or 'normal'
            no_vale = normalizar_vale(f.get('no_vale') or '', tipo_vale)
            if not pid:
                flash('Selecciona un producto de la lista y captura la cantidad.', 'danger')
                conn.close()
                return render_template('salidas/editar.html', salida=salida, areas_lista=areas_lista, maquinas=MAQUINAS, return_to=return_to)
            if not responsable:
                flash('El nombre de quien recibió es obligatorio.', 'danger')
                conn.close()
                return render_template('salidas/editar.html', salida=salida, areas_lista=areas_lista, maquinas=MAQUINAS, return_to=return_to)
            if not no_vale:
                flash('El folio de vale es obligatorio.', 'danger')
                conn.close()
                return render_template('salidas/editar.html', salida=salida, areas_lista=areas_lista, maquinas=MAQUINAS, return_to=return_to)

            pid = int(pid)

            prod_nuevo = conn.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()
            if not prod_nuevo:
                flash('El producto seleccionado no existe.', 'danger')
                conn.close()
                return render_template('salidas/editar.html', salida=salida, areas_lista=areas_lista, maquinas=MAQUINAS, return_to=return_to)
            cantidad = _cantidad_salida_compra_desde_form(f, prod_nuevo)
            if cantidad is None or cantidad <= 0:
                flash('Captura una cantidad mayor a 0.', 'danger')
                conn.close()
                return render_template('salidas/editar.html', salida=salida, areas_lista=areas_lista, maquinas=MAQUINAS, return_to=return_to)

            # Revertir el efecto en stock de la salida ORIGINAL (regresar la cantidad al producto original)
            cantidad_stock_original = _cantidad_salida_registrada_stock(salida, salida)
            conn.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE id=?",
                        (cantidad_stock_original, salida['producto_id']))

            # Antes esto bloqueaba la edición si no había suficiente stock. Ya no bloquea:
            # solo avisa (el stock puede quedar en negativo si ya venía así de antes, por
            # ejemplo por datos importados o conteos pendientes de ajustar).
            stock_disponible = conn.execute(
                "SELECT stock_actual FROM productos WHERE id=?", (pid,)).fetchone()['stock_actual']
            cantidad_stock = _cantidad_salida_stock(cantidad, prod_nuevo)
            if cantidad_stock > stock_disponible:
                flash(f'Aviso: el stock de {prod_nuevo["codigo"]} queda en {round(stock_disponible - cantidad_stock, 4)} '
                      f'{prod_nuevo["unidad_medida"]} (negativo). Se guardó de todas formas.', 'warning')

            conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?",
                        (cantidad_stock, pid))

            fecha_vale = f.get('fecha_vale') or salida['fecha_vale'] or salida['fecha'][:10]
            tipo_mov = f.get('tipo_movimiento') or 'normal'
            area = (f.get('area') or '').strip() or None
            maquina = (f.get('maquina') or '').strip()
            maquina_otro = (f.get('maquina_otro') or '').strip() if maquina == 'Otros' else None
            proveedor = (f.get('proveedor') or '').strip() or None
            conn.execute("""
                UPDATE salidas SET
                    producto_id=?, cantidad=?, cantidad_stock=?, unidad_compra_movimiento=?, factor_conversion_movimiento=?, tipo_conversion_movimiento=?,
                    responsable=?, area=?, no_vale=?, tipo_vale=?, maquina=?, maquina_otro=?, proveedor=?,
                    no_factura=?, no_remision=?, tipo_movimiento=?, observaciones=?, fecha_vale=?
                WHERE id=?
            """, (pid, cantidad, cantidad_stock, prod_nuevo['unidad_compra'], prod_nuevo['factor_conversion'],
                  prod_nuevo['tipo_conversion'] or 'uso_a_compra', responsable, area, no_vale, tipo_vale, maquina, maquina_otro, proveedor,
                  f.get('no_factura') or None, f.get('no_remision') or None, tipo_mov,
                  f.get('observaciones') or None, fecha_vale, sid))
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_SALIDA', f"ID: {sid} | Folio: {salida['folio']}")
            flash('Salida actualizada correctamente.', 'success')
            conn.close()
            return redirect(url_for('salidas.detalle', sid=sid, return_to=return_to))
        except Exception as e:
            conn.rollback()
            flash(f'Error: {str(e)}', 'danger')

    conn.close()
    return render_template('salidas/editar.html', salida=salida, areas_lista=areas_lista, maquinas=MAQUINAS, return_to=return_to)
