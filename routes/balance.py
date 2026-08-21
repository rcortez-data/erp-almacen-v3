import calendar
import csv
import io
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, Response
from routes.auth import login_required, rol_required
from database import get_db, log_actividad
from routes.inventario import construir_busqueda_dinamica

balance_bp = Blueprint('balance', __name__, url_prefix='/balance')

SEL_KEY = 'balance_ids'          # productos seleccionados para el balance mensual
TITLE_KEY = 'balance_tipo_reporte'

MESES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
         'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def _rango_mes(anio, mes):
    inicio = date(anio, mes, 1)
    fin = date(anio, mes, calendar.monthrange(anio, mes)[1])
    return inicio.isoformat(), fin.isoformat()


def _mes_anterior(anio, mes):
    if mes == 1:
        return anio - 1, 12
    return anio, mes - 1


def _factor_conversion(producto):
    try:
        factor = float(producto['factor_conversion'] or 0)
    except (TypeError, ValueError):
        return None
    return factor if producto['unidad_compra'] and factor > 0 else None


def _unidad_es_pieza(producto):
    return (producto['unidad_medida'] or '').strip().upper() in ('PIEZA', 'PIEZAS', 'PZA', 'PZAS')


def _redondear_unidad_stock(valor, producto):
    if valor is None:
        return None
    if _unidad_es_pieza(producto):
        return round(float(valor))
    return round(float(valor), 4)


def _a_unidad_stock(valor_compra, producto):
    """Convierte unidad de compra a unidad de stock.

    En productos como PLAYO: unidad_compra=KG, unidad_medida=PIEZA,
    factor_conversion=2.5 significa 1 pieza = 2.5 KG.
    """
    factor = _factor_conversion(producto)
    if not factor:
        return None
    return _redondear_unidad_stock(float(valor_compra) / factor, producto)


def _a_unidad_compra(valor_stock, producto, redondear_pieza=True):
    factor = _factor_conversion(producto)
    if not factor or valor_stock is None:
        return None
    valor = float(valor_stock) * factor
    if redondear_pieza and _unidad_es_pieza(producto):
        return round(valor)
    return round(valor, 2)


def _valor_manual_balance(form, producto, campo):
    """Lee inicio/salidas del formulario aceptando piezas o unidad compra.

    Si existe un valor en *_compra (ej. KG), ese tiene prioridad y se convierte
    a unidad de stock. Si no, usa el campo normal en unidad de stock.
    """
    pid = producto['id']
    compra_raw = (form.get(f'{campo}_compra_{pid}') or '').strip()
    if compra_raw != '':
        return _a_unidad_stock(float(compra_raw), producto)
    raw = (form.get(f'{campo}_{pid}') or '').strip()
    if raw == '':
        return None
    return float(raw)


def _estado_periodo(conn, anio, mes):
    row = conn.execute(
        "SELECT * FROM cierres_mensuales_periodos WHERE anio=? AND mes=?",
        (anio, mes),
    ).fetchone()
    return row


def _periodo_cerrado(conn, anio, mes):
    row = _estado_periodo(conn, anio, mes)
    return bool(row and row['estado'] == 'cerrado')


def _resumen_periodo(conn, anio, mes):
    total = conn.execute("SELECT COUNT(*) FROM productos WHERE activo=1").fetchone()[0]
    cerrados = conn.execute("""
        SELECT COUNT(*) FROM conteos_fisicos cf
        JOIN productos p ON p.id=cf.producto_id
        WHERE p.activo=1 AND cf.anio=? AND cf.mes=? AND cf.salidas_manual IS NOT NULL
    """, (anio, mes)).fetchone()[0]
    return {'total': total, 'cerrados': cerrados, 'pendientes': max(0, total - cerrados)}


def _productos_por_ids_en_orden(conn, ids):
    """Devuelve productos respetando el orden de la lista recibida."""
    if not ids:
        return []
    placeholders = ','.join('?' * len(ids))
    productos = conn.execute(
        f"SELECT * FROM productos WHERE id IN ({placeholders})",
        ids,
    ).fetchall()
    por_id = {p['id']: p for p in productos}
    return [por_id[pid] for pid in ids if pid in por_id]


def _calcular_fila(conn, producto, anio, mes):
    """Calcula inicio + entradas - salidas manuales = existencia final."""
    inicio_mes, fin_mes = _rango_mes(anio, mes)
    pid = producto['id']

    # 1) El cierre del mes anterior es la existencia inicial del mes consultado.
    anio_ant, mes_ant = _mes_anterior(anio, mes)
    conteo_ant = conn.execute(
        "SELECT existencia_fisica FROM conteos_fisicos WHERE producto_id=? AND anio=? AND mes=?",
        (pid, anio_ant, mes_ant)).fetchone()
    referencia_caldera = conn.execute("""
        SELECT cantidad FROM dashboard_consumo_inicio d
        JOIN bloque_productos bp ON bp.producto_id=d.producto_id AND bp.bloque_id=2
        WHERE d.producto_id=? AND d.grupo='caldera' AND d.anio=?
    """, (pid, anio)).fetchone()
    if conteo_ant and not referencia_caldera:
        existencia_inicio = conteo_ant['existencia_fisica']
        inicio_es_estimado = False
    else:
        if referencia_caldera:
            factor = _factor_conversion(producto)
            entradas_anteriores = conn.execute(
                "SELECT COALESCE(SUM(COALESCE(cantidad_piezas, cantidad)),0) FROM entradas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) >= ? AND DATE(COALESCE(fecha_vale, fecha)) < ?",
                (pid, f'{anio}-01-01', inicio_mes)).fetchone()[0]
            salidas_anteriores = conn.execute(
                "SELECT COALESCE(SUM(cantidad),0) FROM salidas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) >= ? AND DATE(COALESCE(fecha_vale, fecha)) < ?",
                (pid, f'{anio}-01-01', inicio_mes)).fetchone()[0]
            existencia_inicio = float(referencia_caldera['cantidad'] or 0) + float(entradas_anteriores or 0) - float(salidas_anteriores or 0)
            inicio_es_estimado = False
        else:
        # Estimación: retrocede desde el stock actual usando movimientos registrados desde el inicio del mes.
        # Ojo: el stock siempre se mueve en piezas (unidad_medida), por eso usamos cantidad_piezas
        # (que es igual a "cantidad" para productos sin conversión de unidad).
            factor = _factor_conversion(producto)
            if factor:
                entradas_post = conn.execute(
                    "SELECT COALESCE(SUM(cantidad),0) FROM entradas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) >= ?",
                    (pid, inicio_mes)).fetchone()[0] / factor
            else:
                entradas_post = conn.execute(
                    "SELECT COALESCE(SUM(COALESCE(cantidad_piezas, cantidad)),0) FROM entradas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) >= ?",
                    (pid, inicio_mes)).fetchone()[0]
            salidas_post = conn.execute(
                "SELECT COALESCE(SUM(cantidad),0) FROM salidas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) >= ?",
                (pid, inicio_mes)).fetchone()[0]
            existencia_inicio = producto['stock_actual'] - entradas_post + salidas_post
            inicio_es_estimado = True

    # 2) Entradas registradas durante el mes (en piezas, que es como se mueve el stock)
    entradas_mes = conn.execute(
        "SELECT COALESCE(SUM(COALESCE(cantidad_piezas, cantidad)),0) FROM entradas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) BETWEEN ? AND ?",
        (pid, inicio_mes, fin_mes)).fetchone()[0]

    # 2b) Si el producto se compra en otra unidad (ej. kilos), también mostramos ese total
    entradas_mes_compra = None
    if producto['unidad_compra']:
        entradas_mes_compra = conn.execute(
            "SELECT COALESCE(SUM(cantidad),0) FROM entradas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) BETWEEN ? AND ?",
            (pid, inicio_mes, fin_mes)).fetchone()[0]
        factor = _factor_conversion(producto)
        if factor:
            entradas_mes = _redondear_unidad_stock(entradas_mes_compra / factor, producto)

    # 3) Salidas registradas en el ERP, en unidad de inventario.
    salidas_registradas = conn.execute(
        "SELECT COALESCE(SUM(cantidad),0) FROM salidas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) BETWEEN ? AND ?",
        (pid, inicio_mes, fin_mes)).fetchone()[0]
    salidas_registradas_compra = None

    # 4) Físico capturado de ESTE mes (si ya se guardó)
    conteo_actual = conn.execute(
        """SELECT existencia_fisica, salidas_manual, existencia_inicio
           FROM conteos_fisicos WHERE producto_id=? AND anio=? AND mes=?""",
        (pid, anio, mes)).fetchone()
    inicio_guardado = bool(conteo_actual and conteo_actual['existencia_inicio'] is not None)
    if inicio_guardado:
        existencia_inicio = conteo_actual['existencia_inicio']
        inicio_es_estimado = False
    salidas_manual = conteo_actual['salidas_manual'] if conteo_actual else None
    # Productos.stock_actual es la existencia oficial; el cierre físico queda
    # solo como referencia histórica/auditable.
    existencia_esperada = existencia_inicio + entradas_mes - salidas_registradas
    existencia_final = existencia_esperada
    diferencia_salidas = None
    if salidas_manual is not None:
        diferencia_salidas = round(salidas_manual - salidas_registradas, 2)

    return {
        'producto_id': pid, 'codigo': producto['codigo'], 'descripcion': producto['descripcion'],
        'unidad_medida': producto['unidad_medida'],
        'unidad_compra': producto['unidad_compra'], 'factor_conversion': producto['factor_conversion'],
        'entradas_mes_compra': round(entradas_mes_compra, 2) if entradas_mes_compra is not None else None,
        'existencia_inicio_compra': _a_unidad_compra(existencia_inicio, producto),
        'existencia_inicio': round(existencia_inicio, 2), 'inicio_es_estimado': inicio_es_estimado,
        'inicio_guardado': inicio_guardado,
        'entradas_mes': round(entradas_mes, 2),
        'salidas_registradas': round(salidas_registradas, 2),
        'salidas_registradas_compra': round(salidas_registradas_compra, 2) if salidas_registradas_compra is not None else None,
        'salidas_manual': salidas_manual, 'existencia_final': existencia_final,
        'existencia_esperada': round(existencia_esperada, 2),
        'diferencia_stock': round(float(existencia_final or 0) - float(existencia_esperada or 0), 2),
        'salidas_manual_compra': _a_unidad_compra(salidas_manual, producto),
        'existencia_final_compra': _a_unidad_compra(existencia_final, producto, redondear_pieza=False),
        'diferencia_salidas': diferencia_salidas,
    }


def _guardar_cierre_producto(conn, producto, anio, mes, inicio, salidas, usuario_id):
    """Guarda un cierre mensual ya validado y devuelve su existencia final."""
    fila = _calcular_fila(conn, producto, anio, mes)
    existencia_final = inicio + fila['entradas_mes'] - salidas
    if existencia_final < 0:
        raise ValueError(f"Las salidas de {producto['codigo']} superan la existencia disponible.")
    conn.execute("""
        INSERT INTO conteos_fisicos
            (producto_id, anio, mes, existencia_fisica, salidas_manual,
             existencia_inicio, entradas_mes, usuario_id)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(producto_id, anio, mes)
        DO UPDATE SET existencia_fisica=excluded.existencia_fisica,
                      salidas_manual=excluded.salidas_manual,
                      existencia_inicio=excluded.existencia_inicio,
                      entradas_mes=excluded.entradas_mes,
                      usuario_id=excluded.usuario_id, fecha=CURRENT_TIMESTAMP
    """, (producto['id'], anio, mes, existencia_final, salidas,
          inicio, fila['entradas_mes'], usuario_id))
    return existencia_final


@balance_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    conn = get_db()
    hoy = date.today()
    anio = int(request.values.get('anio', hoy.year))
    mes = int(request.values.get('mes', hoy.month))

    if request.method == 'POST':
        accion = request.form.get('accion')

        if accion in {'guardar_cierre', 'guardar_fisicos'} and _periodo_cerrado(conn, anio, mes):
            conn.close()
            flash('Este periodo esta cerrado. Un administrador debe reabrirlo antes de modificarlo.', 'danger')
            return redirect(url_for('balance.index', anio=anio, mes=mes))

        if accion == 'agregar_producto':
            pid = request.form.get('producto_id')
            if pid:
                ids = session.get(SEL_KEY, [])
                if int(pid) not in ids:
                    ids.append(int(pid))
                    session[SEL_KEY] = ids
                    session.modified = True
                session[TITLE_KEY] = 'inventario'
            conn.close()
            return redirect(url_for('balance.index', anio=anio, mes=mes))

        elif accion == 'limpiar_seleccion':
            session.pop(SEL_KEY, None)
            session[TITLE_KEY] = 'inventario'
            conn.close()
            return redirect(url_for('balance.index', anio=anio, mes=mes))

        elif accion in {'guardar_cierre', 'guardar_fisicos'}:
            conn.close()
            flash('El balance es de consulta y auditoría. Para corregir una diferencia registra una Entrada o Salida de ajuste.', 'warning')
            return redirect(url_for('balance.index', anio=anio, mes=mes))

    ids = session.get(SEL_KEY, [])
    filas = []
    if ids:
        for p in _productos_por_ids_en_orden(conn, ids):
            filas.append(_calcular_fila(conn, p, anio, mes))

    total_consumo = sum(f['salidas_manual'] for f in filas if f['salidas_manual'] is not None)
    total_existencia_final = sum(
        f['existencia_final'] for f in filas if f['existencia_final'] is not None
    )
    total_consumo_compra = sum(
        f['salidas_manual'] * f['factor_conversion']
        for f in filas
        if f['salidas_manual'] is not None and f['unidad_compra'] and f['factor_conversion']
    )
    todos_capturados = bool(filas) and all(f['salidas_manual'] is not None for f in filas)
    periodo = _estado_periodo(conn, anio, mes)
    resumen_periodo = _resumen_periodo(conn, anio, mes)
    conn.close()
    return render_template('balance/index.html', filas=filas, anio=anio, mes=mes,
                           meses=MESES, total_consumo=total_consumo,
                           total_existencia_final=total_existencia_final,
                           total_consumo_compra=total_consumo_compra,
                           todos_capturados=todos_capturados,
                           tipo_reporte=session.get(TITLE_KEY, 'inventario'),
                           anio_actual=hoy.year, periodo=periodo,
                           resumen_periodo=resumen_periodo)


@balance_bp.route('/todos', methods=['GET', 'POST'])
@login_required
def todos_productos():
    """Captura paginada del cierre mensual para todo el catalogo activo."""
    conn = get_db()
    hoy = date.today()
    anio = int(request.values.get('anio', hoy.year))
    mes = int(request.values.get('mes', hoy.month))
    pagina = max(1, int(request.values.get('pagina', 1)))
    por_pagina = 100
    q = request.values.get('q', '').strip()

    if request.method == 'POST':
        conn.close()
        flash('El balance es de consulta y auditoría. Para corregir una diferencia registra una Entrada o Salida de ajuste.', 'warning')
        return redirect(url_for('balance.todos_productos', anio=anio, mes=mes, pagina=pagina, q=q))
        # Los cierres manuales anteriores se conservan como histórico, pero ya
        # no se permiten nuevos registros desde este módulo.
        if _periodo_cerrado(conn, anio, mes):
            conn.close()
            flash('Este periodo esta cerrado. Un administrador debe reabrirlo antes de modificarlo.', 'danger')
            return redirect(url_for('balance.todos_productos', anio=anio, mes=mes, pagina=pagina, q=q))
        guardados = 0
        errores = []
        for pid_raw in request.form.getlist('producto_ids'):
            try:
                pid = int(pid_raw)
                producto = conn.execute('SELECT * FROM productos WHERE id=? AND activo=1', (pid,)).fetchone()
                if not producto:
                    continue
                inicio = _valor_manual_balance(request.form, producto, 'inicio')
                salidas = _valor_manual_balance(request.form, producto, 'salidas')
                if inicio is None or salidas is None:
                    continue
                if inicio < 0 or salidas < 0:
                    raise ValueError('Inicio y salidas deben ser positivos.')
                _guardar_cierre_producto(conn, producto, anio, mes, inicio, salidas, session['user_id'])
                guardados += 1
            except (TypeError, ValueError) as error:
                errores.append(str(error))
        conn.commit()
        conn.close()
        if guardados:
            flash(f'Se guardaron {guardados} cierres de esta pagina.', 'success')
        if errores:
            flash(errores[0], 'danger')
        return redirect(url_for('balance.todos_productos', anio=anio, mes=mes, pagina=pagina, q=q))

    filtro = "WHERE activo=1"
    params = []
    if q:
        filtro += " AND (codigo LIKE ? OR descripcion LIKE ?)"
        params.extend([f'%{q}%', f'%{q}%'])
    total = conn.execute(f'SELECT COUNT(*) FROM productos {filtro}', params).fetchone()[0]
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = min(pagina, total_paginas)
    productos = conn.execute(
        f'SELECT * FROM productos {filtro} ORDER BY codigo LIMIT ? OFFSET ?',
        (*params, por_pagina, (pagina - 1) * por_pagina),
    ).fetchall()
    filas = [_calcular_fila(conn, producto, anio, mes) for producto in productos]
    periodo = _estado_periodo(conn, anio, mes)
    resumen_periodo = _resumen_periodo(conn, anio, mes)
    conn.close()
    return render_template(
        'balance/todos.html', filas=filas, anio=anio, mes=mes, meses=MESES,
        anio_actual=hoy.year, pagina=pagina, total_paginas=total_paginas,
        total=total, q=q, periodo=periodo, resumen_periodo=resumen_periodo,
    )


@balance_bp.route('/todos/exportar.csv')
@login_required
def exportar_todos_csv():
    """Exporta el cierre completo; las filas sin captura quedan como pendientes."""
    hoy = date.today()
    anio = int(request.args.get('anio', hoy.year))
    mes = int(request.args.get('mes', hoy.month))
    conn = get_db()
    productos = conn.execute('SELECT * FROM productos WHERE activo=1 ORDER BY codigo').fetchall()
    salida = io.StringIO()
    writer = csv.writer(salida)
    writer.writerow(['codigo', 'descripcion', 'unidad', 'inicio_mes', 'entradas_mes',
                     'salidas_manual', 'existencia_final', 'estado'])
    for producto in productos:
        fila = _calcular_fila(conn, producto, anio, mes)
        writer.writerow([
            fila['codigo'], fila['descripcion'], fila['unidad_medida'],
            fila['existencia_inicio'], fila['entradas_mes'],
            '' if fila['salidas_manual'] is None else fila['salidas_manual'],
            '' if fila['existencia_final'] is None else fila['existencia_final'],
            'pendiente' if fila['salidas_manual'] is None else 'cerrado',
        ])
    conn.close()
    contenido = '\ufeff' + salida.getvalue()
    return Response(
        contenido, mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename=stock_{anio}_{mes:02d}.csv'},
    )


@balance_bp.route('/periodo/cerrar', methods=['POST'])
@login_required
@rol_required('admin', 'almacen')
def cerrar_periodo():
    anio = int(request.form['anio'])
    mes = int(request.form['mes'])
    conn = get_db()
    resumen = _resumen_periodo(conn, anio, mes)
    if resumen['cerrados'] == 0:
        conn.close()
        flash('No se puede cerrar un mes sin al menos un producto capturado.', 'danger')
        return redirect(url_for('balance.todos_productos', anio=anio, mes=mes))
    conn.execute("""
        INSERT INTO cierres_mensuales_periodos
            (anio, mes, estado, cerrado_por, cerrado_en)
        VALUES (?, ?, 'cerrado', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(anio, mes) DO UPDATE SET
            estado='cerrado', cerrado_por=excluded.cerrado_por,
            cerrado_en=CURRENT_TIMESTAMP
    """, (anio, mes, session['user_id']))
    conn.commit()
    conn.close()
    log_actividad(
        session['user_id'], 'CIERRE_MENSUAL',
        f'{MESES[mes]} {anio}: {resumen["cerrados"]} cerrados, {resumen["pendientes"]} pendientes',
    )
    flash(f'{MESES[mes]} {anio} quedo cerrado y protegido contra cambios.', 'success')
    return redirect(url_for('balance.todos_productos', anio=anio, mes=mes))


@balance_bp.route('/periodo/reabrir', methods=['POST'])
@login_required
@rol_required('admin')
def reabrir_periodo():
    anio = int(request.form['anio'])
    mes = int(request.form['mes'])
    motivo = request.form.get('motivo', '').strip()
    if len(motivo) < 8:
        flash('Indica un motivo de reapertura de al menos 8 caracteres.', 'danger')
        return redirect(url_for('balance.todos_productos', anio=anio, mes=mes))
    conn = get_db()
    conn.execute("""
        UPDATE cierres_mensuales_periodos
        SET estado='abierto', reabierto_por=?, reabierto_en=CURRENT_TIMESTAMP,
            motivo_reapertura=?
        WHERE anio=? AND mes=? AND estado='cerrado'
    """, (session['user_id'], motivo, anio, mes))
    cambio = conn.total_changes
    conn.commit()
    conn.close()
    if cambio:
        log_actividad(session['user_id'], 'REAPERTURA_MENSUAL', f'{MESES[mes]} {anio}: {motivo}')
        flash(f'{MESES[mes]} {anio} fue reabierto.', 'warning')
    return redirect(url_for('balance.todos_productos', anio=anio, mes=mes))


@balance_bp.route('/quitar', methods=['POST'])
@login_required
def quitar():
    pid = int(request.form.get('producto_id'))
    anio = request.form.get('anio')
    mes = request.form.get('mes')
    ids = session.get(SEL_KEY, [])
    if pid in ids:
        ids.remove(pid)
        session[SEL_KEY] = ids
        session.modified = True
    return redirect(url_for('balance.index', anio=anio, mes=mes))


@balance_bp.route('/cargar_bloque/<int:bloque_id>', methods=['POST'])
@login_required
def cargar_bloque(bloque_id):
    """Carga automáticamente todos los productos de un bloque predefinido."""
    anio = request.form.get('anio')
    mes = request.form.get('mes')
    
    conn = get_db()
    # Obtener productos del bloque ordenados
    productos = conn.execute("""
        SELECT p.id FROM productos p
        JOIN bloque_productos bp ON p.id = bp.producto_id
        WHERE bp.bloque_id = ?
        ORDER BY bp.orden
    """, (bloque_id,)).fetchall()
    conn.close()
    
    # Agregar a la selección (evitar duplicados)
    ids = session.get(SEL_KEY, [])
    agregados = 0
    for p in productos:
        if p['id'] not in ids:
            ids.append(p['id'])
            agregados += 1
    
    if ids:
        session[SEL_KEY] = ids
        session.modified = True
    session[TITLE_KEY] = 'produccion' if bloque_id == 1 else 'caldera' if bloque_id == 2 else 'inventario'
    
    flash(f'Se cargaron {agregados} producto(s) del bloque.', 'success')
    return redirect(url_for('balance.index', anio=anio, mes=mes))




@balance_bp.route('/imprimir')
@login_required
def imprimir():
    conn = get_db()
    anio = int(request.args.get('anio'))
    mes = int(request.args.get('mes'))
    ids = [int(i) for i in request.args.get('productos', '').split(',') if i]
    tipo_reporte = request.args.get('tipo', 'inventario')
    titulos = {
        'produccion': 'REPORTE MENSUAL DE PRODUCCIÓN',
        'caldera': 'REPORTE MENSUAL DE CALDERA',
        'inventario': 'REPORTE MENSUAL DE INVENTARIO',
    }
    titulo_reporte = titulos.get(tipo_reporte, titulos['inventario'])
    filas = []
    if ids:
        for p in _productos_por_ids_en_orden(conn, ids):
            filas.append(_calcular_fila(conn, p, anio, mes))
    total_consumo = sum(f['salidas_manual'] for f in filas if f['salidas_manual'] is not None)
    total_existencia_final = sum(
        f['existencia_final'] for f in filas if f['existencia_final'] is not None
    )
    total_consumo_compra = sum(
        f['salidas_manual'] * f['factor_conversion']
        for f in filas
        if f['salidas_manual'] is not None and f['unidad_compra'] and f['factor_conversion']
    )
    conn.close()
    from datetime import datetime as dt
    return render_template('balance/imprimir.html', filas=filas, anio=anio, mes=mes,
                           meses=MESES, total_consumo=total_consumo,
                           total_existencia_final=total_existencia_final,
                           total_consumo_compra=total_consumo_compra,
                           titulo_reporte=titulo_reporte,
                           now=dt.now().strftime('%d/%m/%Y %H:%M'))


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ADMINISTRACIÓN DE BLOQUES PREDEFINIDOS
# ---------------------------------------------------------------------------

@balance_bp.route('/bloques', methods=['GET', 'POST'])
@login_required
def administrar_bloques():
    """Vista para administrar bloques predefinidos: agregar/quitar productos."""
    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        accion = request.form.get('accion')

        if accion == 'agregar_producto':
            bloque_id = request.form.get('bloque_id')
            producto_id = request.form.get('producto_id')
            
            if bloque_id and producto_id:
                try:
                    # Obtener el orden máximo actual
                    max_orden = c.execute(
                        "SELECT MAX(orden) FROM bloque_productos WHERE bloque_id = ?",
                        (bloque_id,)
                    ).fetchone()
                    nuevo_orden = (max_orden[0] or 0) + 1
                    
                    # Agregar el producto
                    c.execute(
                        "INSERT INTO bloque_productos (bloque_id, producto_id, orden) VALUES (?, ?, ?)",
                        (bloque_id, producto_id, nuevo_orden)
                    )
                    conn.commit()
                    flash(f'Producto agregado al bloque.', 'success')
                except Exception as e:
                    flash(f'Error: {str(e)}', 'danger')

        elif accion == 'quitar_producto':
            bp_id = request.form.get('bp_id')
            if bp_id:
                c.execute("DELETE FROM bloque_productos WHERE id = ?", (bp_id,))
                conn.commit()
                flash('Producto removido del bloque.', 'success')

        elif accion == 'cambiar_orden':
            bp_id = request.form.get('bp_id')
            nueva_orden = request.form.get('nueva_orden')
            if bp_id and nueva_orden:
                try:
                    c.execute(
                        "UPDATE bloque_productos SET orden = ? WHERE id = ?",
                        (nueva_orden, bp_id)
                    )
                    conn.commit()
                    flash('Orden actualizado.', 'success')
                except Exception as e:
                    flash(f'Error: {str(e)}', 'danger')

        conn.close()
        return redirect(url_for('balance.administrar_bloques'))

    # GET: Mostrar bloques y sus productos
    bloques = c.execute("SELECT * FROM bloques_balance WHERE activo = 1 ORDER BY id").fetchall()
    
    bloques_con_productos = []
    for bloque in bloques:
        productos = c.execute("""
            SELECT bp.id, bp.orden, p.id as producto_id, p.codigo, p.descripcion
            FROM bloque_productos bp
            JOIN productos p ON bp.producto_id = p.id
            WHERE bp.bloque_id = ?
            ORDER BY bp.orden
        """, (bloque['id'],)).fetchall()
        bloques_con_productos.append({
            'bloque': bloque,
            'productos': productos
        })

    conn.close()
    return render_template('balance/bloques.html', bloques_con_productos=bloques_con_productos)


@balance_bp.route('/bloques/buscar_producto')
@login_required
def buscar_producto_bloque():
    """API para búsqueda de productos para agregar a bloques."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return {'resultados': []}

    conn = get_db()
    productos = conn.execute(
        """SELECT id, codigo, descripcion FROM productos 
           WHERE (codigo LIKE ? OR descripcion LIKE ?) AND activo = 1
           ORDER BY descripcion LIMIT 20""",
        (f'%{q}%', f'%{q}%')
    ).fetchall()
    conn.close()

    return {
        'resultados': [
            {'id': p['id'], 'codigo': p['codigo'], 'descripcion': p['descripcion']}
            for p in productos
        ]
    }
