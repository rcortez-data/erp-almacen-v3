from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from routes.auth import login_required
from database import get_db, next_folio, log_actividad
from routes.inventario import construir_busqueda_dinamica
from constantes import MAQUINAS
from datetime import datetime, date
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
        return redirect(url_for('salidas.index'))
    try:
        conn.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE id=?",
                    (salida['cantidad'], salida['producto_id']))
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
    return redirect(url_for('salidas.index'))


@salidas_bp.route('/')
@login_required
def index():
    fecha_ini = request.args.get('fecha_ini', '')
    fecha_fin = request.args.get('fecha_fin', '')
    q = request.args.get('q', '').strip()
    q_resp = request.args.get('q_resp', '').strip()
    q_area = request.args.get('q_area', '').strip()
    q_vale = request.args.get('q_vale', '').strip()
    pagina = request.args.get('pagina', 1, type=int)
    registros_por_pagina = 50
    
    conn = get_db()
    select_sql = """
        SELECT s.*, p.codigo, p.codigo_barras, p.descripcion, p.unidad_medida,
               p.unidad_compra, p.factor_conversion,
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
    filtro_activo = bool(fecha_ini or fecha_fin or q or q_resp or q_area or q_vale)
    
    conn.close()
    return render_template('salidas/index.html', salidas=salidas,
                           fecha_ini=fecha_ini, fecha_fin=fecha_fin, q=q, q_resp=q_resp,
                           q_area=q_area, q_vale=q_vale,
                           total_cantidad=total_cantidad,
                           total_ajustes=total_ajustes,
                           total_vales=total_vales,
                           filtro_activo=filtro_activo,
                           areas_lista=areas_lista,
                           pagina_actual=pagina, total_paginas=total_paginas,
                           total_registros=total_registros, registros_pagina=len(salidas))


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
            f"SELECT id, codigo, descripcion, unidad_medida, stock_actual FROM productos WHERE activo=1 AND id IN ({marks}) ORDER BY codigo",
            ids
        ).fetchall()
        orden_balance = {pid: posicion for posicion, pid in enumerate(ids)}
        productos = sorted(productos, key=lambda producto: orden_balance.get(producto['id'], len(ids)))
    hoy = date.today()
    periodo = request.values.get('periodo') or hoy.strftime('%Y-%m')
    try:
        anio, mes = (int(x) for x in periodo.split('-', 1))
        ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1]).isoformat()
    except (ValueError, TypeError):
        periodo = hoy.strftime('%Y-%m')
        ultimo_dia = hoy.isoformat()

    existencias = {}
    inicios_mes = {}
    entradas_periodo = {}
    for producto in productos:
        inicio = conn.execute(
            "SELECT cantidad FROM dashboard_consumo_inicio WHERE producto_id=? AND grupo='caldera' AND anio=?",
            (producto['id'], anio)
        ).fetchone()
        movimientos = conn.execute("""
            SELECT
              COALESCE((SELECT SUM(cantidad) FROM entradas WHERE producto_id=? AND strftime('%Y', COALESCE(fecha_vale,fecha))=? AND COALESCE(fecha_vale,fecha) <= ?),0) AS entradas,
              COALESCE((SELECT SUM(cantidad) FROM salidas WHERE producto_id=? AND strftime('%Y', COALESCE(fecha_vale,fecha))=? AND DATE(COALESCE(fecha_vale,fecha)) BETWEEN ? AND ?),0) AS salidas
        """, (producto['id'], str(anio), ultimo_dia, producto['id'], str(anio), f'{anio}-{mes:02d}-01', ultimo_dia)).fetchone()
        base_anio = float(inicio['cantidad'] if inicio else 0)
        entradas_antes = conn.execute("SELECT COALESCE(SUM(COALESCE(cantidad_piezas,cantidad)),0) FROM entradas WHERE producto_id=? AND strftime('%Y',COALESCE(fecha_vale,fecha))=? AND DATE(COALESCE(fecha_vale,fecha)) < ?", (producto['id'], str(anio), f'{anio}-{mes:02d}-01')).fetchone()[0] or 0
        salidas_antes = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM salidas WHERE producto_id=? AND strftime('%Y',COALESCE(fecha_vale,fecha))=? AND DATE(COALESCE(fecha_vale,fecha)) < ?", (producto['id'], str(anio), f'{anio}-{mes:02d}-01')).fetchone()[0] or 0
        inicios_mes[producto['id']] = base_anio + float(entradas_antes) - float(salidas_antes)
        entradas_periodo[producto['id']] = float(conn.execute(
            "SELECT COALESCE(SUM(COALESCE(cantidad_piezas, cantidad)),0) FROM entradas WHERE producto_id=? AND DATE(COALESCE(fecha_vale,fecha)) BETWEEN ? AND ?",
            (producto['id'], f'{anio}-{mes:02d}-01', ultimo_dia)
        ).fetchone()[0] or 0)
        existencias[producto['id']] = inicios_mes[producto['id']] + entradas_periodo[producto['id']] - float(movimientos['salidas'] or 0)

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
                    SELECT id FROM salidas
                    WHERE producto_id=? AND tipo_movimiento='consumo_fisico'
                      AND area='CALDERA' AND fecha_vale=?
                """, (producto['id'], ultimo_dia)).fetchone()
                if existe:
                    continue
                conn.execute("UPDATE folios SET ultimo=ultimo+1 WHERE tipo='salida'")
                numero = conn.execute("SELECT ultimo FROM folios WHERE tipo='salida'").fetchone()[0]
                folio = f'SAL-{str(numero).zfill(6)}'
                conn.execute("""
                    INSERT INTO salidas
                    (folio, producto_id, cantidad, responsable, area, no_vale, tipo_vale,
                     tipo_movimiento, usuario_id, observaciones, fecha, fecha_vale)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (folio, producto['id'], cantidad, 'CONSUMO FISICO', 'CALDERA', no_vale,
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
            r['producto_id']: r['cantidad'] for r in conn.execute(
                f"SELECT producto_id, cantidad FROM salidas WHERE producto_id IN ({marks}) AND tipo_movimiento='consumo_fisico' AND area='CALDERA' AND fecha_vale=?",
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
                           entradas_periodo=entradas_periodo)


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
            'orden_compra': request.form.get('orden_compra', ''),
            'no_factura': request.form.get('no_factura', ''),
            'no_remision': request.form.get('no_remision', ''),
            'tipo_movimiento': request.form.get('tipo_movimiento', 'normal'),
            'observaciones': request.form.get('observaciones', ''),
            'fecha_vale': request.form.get('fecha_vale') or session.get(DOC_KEY, {}).get('fecha_vale', datetime.now().date().isoformat()),
        }
        session.modified = True

        if accion == 'agregar_item':
            pid = request.form.get('producto_id')
            cantidad = request.form.get('cantidad')
            if not pid or not cantidad:
                flash('Selecciona un producto de la lista y captura la cantidad.', 'danger')
            else:
                prod = conn.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()
                if not prod:
                    flash('El producto seleccionado no existe.', 'danger')
                else:
                    cantidad = float(cantidad)
                    cart = session.get(CART_KEY, [])
                    cart.append({
                        'producto_id': prod['id'], 'codigo': prod['codigo'],
                        'codigo_barras': prod['codigo_barras'],
                        'descripcion': prod['descripcion'],
                        'unidad_medida': prod['unidad_medida'],
                        'unidad_compra': prod['unidad_compra'],
                        'factor_conversion': prod['factor_conversion'],
                        'cantidad': cantidad,
                        'stock_actual': prod['stock_actual'],
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
                SELECT e.producto_id, SUM(e.cantidad) AS cantidad,
                       p.codigo, p.codigo_barras, p.descripcion, p.unidad_medida,
                       p.unidad_compra, p.factor_conversion, p.stock_actual
                FROM entradas e JOIN productos p ON p.id=e.producto_id
                WHERE p.activo=1 AND TRIM(UPPER({columna}))=TRIM(UPPER(?))
                GROUP BY e.producto_id, p.codigo, p.codigo_barras, p.descripcion,
                         p.unidad_medida, p.unidad_compra, p.factor_conversion, p.stock_actual
                ORDER BY p.codigo
            """, (documento_valor,)).fetchall()
            if not filas:
                flash(f'No se encontraron productos activos para {documento_tipo.upper()} {documento_valor}.', 'warning')
            else:
                cart = session.get(CART_KEY, [])
                existentes = {item['producto_id'] for item in cart}
                agregados = 0
                omitidos = 0
                for prod in filas:
                    if prod['producto_id'] in existentes:
                        omitidos += 1
                        continue
                    cantidad_seleccionada = request.form.get(f"producto_cantidad_{prod['producto_id']}")
                    try:
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
                        'factor_conversion': prod['factor_conversion'], 'cantidad': cantidad_seleccionada,
                        'stock_actual': prod['stock_actual'],
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
                        (folio, producto_id, cantidad, responsable, area, no_vale, tipo_vale, maquina,
                         orden_compra, no_factura, no_remision, tipo_movimiento, usuario_id, observaciones, fecha, fecha_vale)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (folio, item['producto_id'], item['cantidad'], doc.get('responsable'), area,
                          doc.get('no_vale'), doc.get('tipo_vale') or 'normal', doc.get('maquina') or None,
                          doc.get('orden_compra') or None, doc.get('no_factura') or None, doc.get('no_remision') or None,
                          tipo_mov, session['user_id'], doc.get('observaciones'), fecha_sql, fecha_vale))
                    conn.execute(
                        "UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?",
                        (item['cantidad'], item['producto_id']))
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
            (folio, producto_id, cantidad, responsable, area, no_vale, tipo_vale, maquina,
             no_factura, no_remision, tipo_movimiento, usuario_id, observaciones, fecha, fecha_vale)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (folio, pid, cantidad, responsable, area or None, no_vale, tipo_vale, maquina or None,
              (data.get('no_factura') or '').strip() or None,
              (data.get('no_remision') or '').strip() or None,
              tipo_mov, session['user_id'], (data.get('observaciones') or '').strip() or None,
              fecha_sql, fecha_vale))
        conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?", (cantidad, pid))
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
        WHERE TRIM(e.{columna}) <> '' AND UPPER(e.{columna}) LIKE UPPER(?)
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
               SUM(e.cantidad) AS cantidad, p.stock_actual
        FROM entradas e JOIN productos p ON p.id=e.producto_id
        WHERE p.activo=1 AND TRIM(UPPER({columna}))=TRIM(UPPER(?))
        GROUP BY p.id, p.codigo, p.descripcion, p.unidad_medida, p.stock_actual
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
    conn = get_db()
    salida = conn.execute("""
        SELECT s.*, p.codigo, p.codigo_barras, p.descripcion, p.unidad_medida,
               p.unidad_compra, p.factor_conversion,
               u.nombre as usuario_nombre
        FROM salidas s
        JOIN productos p ON s.producto_id=p.id
        LEFT JOIN usuarios u ON s.usuario_id=u.id
        WHERE s.id=?
    """, (sid,)).fetchone()
    conn.close()
    if not salida:
        flash('Registro no encontrado.', 'danger')
        return redirect(url_for('salidas.index'))
    return render_template('salidas/detalle.html', salida=salida)


@salidas_bp.route('/editar/<int:sid>', methods=['GET', 'POST'])
@login_required
def editar(sid):
    """Permite corregir por completo una salida ya registrada: producto, cantidad,
    responsable, folio de vale, tipo de movimiento, observaciones y fecha. Al cambiar
    producto o cantidad, el stock se ajusta automáticamente (se revierte el efecto
    anterior sobre el producto original y se aplica el nuevo)."""
    conn = get_db()
    salida = conn.execute("""
        SELECT s.*, p.codigo, p.codigo_barras, p.descripcion, p.unidad_medida,
               p.unidad_compra, p.factor_conversion
        FROM salidas s
        JOIN productos p ON s.producto_id=p.id
        WHERE s.id=?
    """, (sid,)).fetchone()
    areas_lista = conn.execute("SELECT * FROM areas WHERE activo=1 ORDER BY LOWER(nombre)").fetchall()
    if not salida:
        flash('Registro no encontrado.', 'danger')
        conn.close()
        return redirect(url_for('salidas.index'))

    if request.method == 'POST':
        f = request.form
        try:
            pid = f.get('producto_id')
            cantidad_raw = f.get('cantidad')
            responsable = (f.get('responsable') or '').strip()
            tipo_vale = f.get('tipo_vale') or salida['tipo_vale'] or 'normal'
            no_vale = normalizar_vale(f.get('no_vale') or '', tipo_vale)
            if not pid or not cantidad_raw:
                flash('Selecciona un producto de la lista y captura la cantidad.', 'danger')
                conn.close()
                return render_template('salidas/editar.html', salida=salida, areas_lista=areas_lista, maquinas=MAQUINAS)
            if not responsable:
                flash('El nombre de quien recibió es obligatorio.', 'danger')
                conn.close()
                return render_template('salidas/editar.html', salida=salida, areas_lista=areas_lista, maquinas=MAQUINAS)
            if not no_vale:
                flash('El folio de vale es obligatorio.', 'danger')
                conn.close()
                return render_template('salidas/editar.html', salida=salida, areas_lista=areas_lista, maquinas=MAQUINAS)

            pid = int(pid)
            cantidad = float(cantidad_raw)

            prod_nuevo = conn.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()
            if not prod_nuevo:
                flash('El producto seleccionado no existe.', 'danger')
                conn.close()
                return render_template('salidas/editar.html', salida=salida, areas_lista=areas_lista, maquinas=MAQUINAS)

            # Revertir el efecto en stock de la salida ORIGINAL (regresar la cantidad al producto original)
            conn.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE id=?",
                        (salida['cantidad'], salida['producto_id']))

            # Antes esto bloqueaba la edición si no había suficiente stock. Ya no bloquea:
            # solo avisa (el stock puede quedar en negativo si ya venía así de antes, por
            # ejemplo por datos importados o conteos pendientes de ajustar).
            stock_disponible = conn.execute(
                "SELECT stock_actual FROM productos WHERE id=?", (pid,)).fetchone()['stock_actual']
            if cantidad > stock_disponible:
                flash(f'Aviso: el stock de {prod_nuevo["codigo"]} queda en {round(stock_disponible - cantidad, 4)} '
                      f'{prod_nuevo["unidad_medida"]} (negativo). Se guardó de todas formas.', 'warning')

            conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?",
                        (cantidad, pid))

            fecha_vale = f.get('fecha_vale') or salida['fecha_vale'] or salida['fecha'][:10]
            tipo_mov = f.get('tipo_movimiento') or 'normal'
            area = (f.get('area') or '').strip() or None
            conn.execute("""
                UPDATE salidas SET
                    producto_id=?, cantidad=?, responsable=?, area=?, no_vale=?, tipo_vale=?, maquina=?,
                    no_factura=?, no_remision=?, tipo_movimiento=?, observaciones=?, fecha_vale=?
                WHERE id=?
            """, (pid, cantidad, responsable, area, no_vale, tipo_vale, f.get('maquina') or None,
                  f.get('no_factura') or None, f.get('no_remision') or None, tipo_mov,
                  f.get('observaciones') or None, fecha_vale, sid))
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_SALIDA', f"ID: {sid} | Folio: {salida['folio']}")
            flash('Salida actualizada correctamente.', 'success')
            conn.close()
            return redirect(url_for('salidas.detalle', sid=sid))
        except Exception as e:
            conn.rollback()
            flash(f'Error: {str(e)}', 'danger')

    conn.close()
    return render_template('salidas/editar.html', salida=salida, areas_lista=areas_lista, maquinas=MAQUINAS)
