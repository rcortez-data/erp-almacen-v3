from flask import Blueprint, render_template, session, request, redirect, url_for, flash
from routes.auth import login_required
from database import get_db
from datetime import date, timedelta, datetime
import json
from urllib.request import urlopen

dashboard_bp = Blueprint('dashboard', __name__)


def _tipo_cambio_usd(conn, fecha):
    """Obtiene el tipo de cambio histórico para el Dashboard, sin tocar Entradas."""
    row = conn.execute(
        "SELECT usd_mxn FROM dashboard_tipo_cambio WHERE fecha=?", (fecha,)
    ).fetchone()
    if row:
        return float(row['usd_mxn']), False
    try:
        with urlopen(f'https://api.frankfurter.app/{fecha}?from=USD&to=MXN', timeout=2) as response:
            data = json.loads(response.read().decode('utf-8'))
            rate = float(data['rates']['MXN'])
            conn.execute(
                "INSERT OR REPLACE INTO dashboard_tipo_cambio (fecha, usd_mxn, fuente) VALUES (?, ?, ?)",
                (fecha, rate, 'Frankfurter.app')
            )
            conn.commit()
            return rate, False
    except Exception:
        row = conn.execute(
            "SELECT usd_mxn FROM dashboard_tipo_cambio ORDER BY ABS(julianday(fecha)-julianday(?)) LIMIT 1",
            (fecha,)
        ).fetchone()
        return (float(row['usd_mxn']) if row else 1.0), not bool(row)


def _importe_mxn(conn, row):
    subtotal = float(row['subtotal'] or 0)
    moneda = (row['moneda'] or 'MXN').upper()
    if moneda in ('USD', 'US', 'DOLAR', 'DOLARES', 'DÓLAR', 'DÓLARES'):
        rate, estimado = _tipo_cambio_usd(conn, (row['fecha_vale'] or row['fecha'])[:10])
        return subtotal * rate, rate, estimado
    return subtotal, 1.0, False


def _sincronizar_bloques_dashboard(conn, grupo):
    bloque_id = 1 if grupo == 'produccion' else 2
    conn.execute("""
        INSERT OR IGNORE INTO dashboard_consumo_productos (producto_id, grupo)
        SELECT producto_id, ? FROM bloque_productos
        WHERE bloque_id=?
    """, (grupo, bloque_id))
    conn.commit()


@dashboard_bp.route('/dashboard')
@login_required
def index():
    conn = get_db()
    hoy = date.today()
    total_productos = conn.execute(
        "SELECT COUNT(*) FROM productos WHERE activo=1").fetchone()[0]
    stock_bajo = conn.execute(
        "SELECT COUNT(*) FROM productos WHERE activo=1 AND stock_actual <= stock_minimo AND stock_minimo > 0"
    ).fetchone()[0]
    entradas_hoy = conn.execute(
        "SELECT COUNT(*) FROM entradas WHERE DATE(fecha)=?", (hoy.isoformat(),)
    ).fetchone()[0]
    salidas_hoy = conn.execute(
        "SELECT COUNT(*) FROM salidas WHERE DATE(fecha)=?", (hoy.isoformat(),)
    ).fetchone()[0]

    ultimas_entradas = conn.execute("""
        SELECT e.folio, p.codigo, p.descripcion, e.cantidad, e.fecha
        FROM entradas e JOIN productos p ON e.producto_id=p.id
        ORDER BY e.fecha DESC LIMIT 5
    """).fetchall()

    ultimas_salidas = conn.execute("""
        SELECT s.folio, p.codigo, p.descripcion, s.cantidad, s.responsable, s.fecha
        FROM salidas s JOIN productos p ON s.producto_id=p.id
        ORDER BY s.fecha DESC LIMIT 5
    """).fetchall()

    alertas = conn.execute("""
        SELECT codigo, descripcion, stock_actual, stock_minimo
        FROM productos WHERE activo=1 AND stock_actual <= stock_minimo AND stock_minimo > 0
        ORDER BY (stock_actual - stock_minimo) ASC LIMIT 10
    """).fetchall()

    # Últimos 7 días — entradas y salidas por día
    labels = [(hoy - timedelta(days=n)).isoformat() for n in range(6, -1, -1)]
    desde = labels[0]

    ent_por_dia = {r['dia']: r['total'] for r in conn.execute("""
        SELECT DATE(fecha) as dia, COUNT(*) as total
        FROM entradas WHERE DATE(fecha) >= ?
        GROUP BY DATE(fecha)
    """, (desde,)).fetchall()}
    sal_por_dia = {r['dia']: r['total'] for r in conn.execute("""
        SELECT DATE(fecha) as dia, COUNT(*) as total
        FROM salidas WHERE DATE(fecha) >= ?
        GROUP BY DATE(fecha)
    """, (desde,)).fetchall()}
    data_entradas = [ent_por_dia.get(d, 0) for d in labels]
    data_salidas  = [sal_por_dia.get(d, 0) for d in labels]

    # Top 5 productos más movidos este mes
    inicio_mes = hoy.replace(day=1)
    siguiente_mes = (inicio_mes.replace(day=28) + timedelta(days=4)).replace(day=1)
    top_productos = conn.execute("""
        SELECT p.codigo, p.descripcion,
               COALESCE(e.total,0) as entradas,
               COALESCE(s.total,0) as salidas
        FROM productos p
        LEFT JOIN (
            SELECT producto_id, SUM(cantidad) as total FROM entradas
            WHERE fecha >= ? AND fecha < ? GROUP BY producto_id
        ) e ON e.producto_id = p.id
        LEFT JOIN (
            SELECT producto_id, SUM(cantidad) as total FROM salidas
            WHERE fecha >= ? AND fecha < ? GROUP BY producto_id
        ) s ON s.producto_id = p.id
        WHERE p.activo=1 AND (COALESCE(e.total,0) + COALESCE(s.total,0)) > 0
        ORDER BY (COALESCE(e.total,0) + COALESCE(s.total,0)) DESC LIMIT 30
    """, (inicio_mes.isoformat(), siguiente_mes.isoformat(),
          inicio_mes.isoformat(), siguiente_mes.isoformat())).fetchall()

    conn.close()

    return render_template('dashboard.html',
        total_productos=total_productos,
        stock_bajo=stock_bajo,
        entradas_hoy=entradas_hoy,
        salidas_hoy=salidas_hoy,
        ultimas_entradas=ultimas_entradas,
        ultimas_salidas=ultimas_salidas,
        alertas=alertas,
        chart_labels=labels,
        chart_entradas=data_entradas,
        chart_salidas=data_salidas,
        top_productos=top_productos,
    )


@dashboard_bp.route('/dashboard/consumo', methods=['GET', 'POST'])
@login_required
def consumo():
    conn = get_db()
    if request.method == 'POST':
        accion = request.form.get('accion')
        grupo = request.form.get('grupo', 'produccion')
        if grupo not in ('produccion', 'caldera'):
            grupo = 'produccion'
        if accion == 'sincronizar':
            _sincronizar_bloques_dashboard(conn, grupo)
            flash('Productos de los bloques del Balance agregados al historial.', 'success')
        elif accion == 'agregar':
            pid = request.form.get('producto_id', type=int)
            if pid:
                conn.execute("INSERT OR IGNORE INTO dashboard_consumo_productos (producto_id, grupo) VALUES (?, ?)", (pid, grupo))
                conn.commit()
                flash('Producto agregado al historial de consumo.', 'success')
        elif accion == 'quitar':
            rid = request.form.get('registro_id', type=int)
            if rid:
                conn.execute("UPDATE dashboard_consumo_productos SET activo=0 WHERE id=?", (rid,))
                conn.commit()
        return redirect(url_for('dashboard.consumo', grupo=grupo, anio=request.form.get('anio', date.today().year)))

    grupo = request.args.get('grupo', 'produccion')
    if grupo not in ('produccion', 'caldera'):
        grupo = 'produccion'
    _sincronizar_bloques_dashboard(conn, grupo)
    anio = request.args.get('anio', date.today().year, type=int)
    q = request.args.get('q', '').strip()
    seleccionados = conn.execute("""
        SELECT d.id, p.id AS producto_id, p.codigo, p.descripcion
        FROM dashboard_consumo_productos d JOIN productos p ON p.id=d.producto_id
        WHERE d.grupo=? AND d.activo=1 ORDER BY p.codigo
    """, (grupo,)).fetchall()
    resultados = []
    if q:
        like = f'%{q}%'
        resultados = conn.execute("""
            SELECT id, codigo, descripcion FROM productos
            WHERE activo=1 AND (codigo LIKE ? OR descripcion LIKE ?)
            ORDER BY codigo LIMIT 30
        """, (like, like)).fetchall()
    meses = [f'{anio}-{m:02d}' for m in range(1, 13)]
    ids = [r['producto_id'] for r in seleccionados]
    inicios_anio = {}
    if ids:
        marks = ','.join('?' for _ in ids)
        inicios_anio = {
            r['producto_id']: r['cantidad'] for r in conn.execute(
                f"SELECT producto_id, cantidad FROM dashboard_consumo_inicio WHERE grupo=? AND anio=? AND producto_id IN ({marks})",
                [grupo, anio] + ids
            ).fetchall()
        }
    mensual = {m: {'entradas': 0, 'salidas': 0, 'costo': 0} for m in meses}
    producto_mensual = [
        {'producto_id': r['producto_id'], 'codigo': r['codigo'], 'descripcion': r['descripcion'],
         'entradas': {m: 0 for m in meses}, 'salidas': {m: 0 for m in meses}}
        for r in seleccionados
    ]
    producto_por_id = {p['producto_id']: p for p in producto_mensual}
    if ids:
        marks = ','.join('?' for _ in ids)
        for table, key in (('entradas', 'entradas'), ('salidas', 'salidas')):
            fecha_expr = 'COALESCE(fecha_vale, fecha)'
            if table == 'entradas':
                sql = f"""
                    SELECT producto_id, strftime('%Y-%m', {fecha_expr}) AS mes,
                           SUM(COALESCE(cantidad,0)) AS cantidad,
                           SUM(CASE WHEN COALESCE(precio_unitario,0) != 0 THEN cantidad*precio_unitario ELSE importe END) AS subtotal,
                           moneda, MAX(fecha_vale) AS fecha_vale, MAX(fecha) AS fecha
                    FROM entradas WHERE producto_id IN ({marks}) AND strftime('%Y', {fecha_expr})=?
                    GROUP BY producto_id, mes, moneda, fecha_vale, fecha, id
                """
            else:
                sql = f"""
                    SELECT producto_id, strftime('%Y-%m', {fecha_expr}) AS mes,
                           SUM(COALESCE(cantidad,0)) AS cantidad,
                           'MXN' AS moneda, MAX(fecha_vale) AS fecha_vale, MAX(fecha) AS fecha
                    FROM salidas WHERE producto_id IN ({marks}) AND strftime('%Y', {fecha_expr})=?
                    GROUP BY producto_id, mes, fecha_vale, fecha, id
                """
            rows = conn.execute(sql, ids + [str(anio)]).fetchall()
            for row in rows:
                if row['mes'] not in mensual: continue
                mensual[row['mes']][key] += float(row['cantidad'] or 0)
                if row['producto_id'] in producto_por_id:
                    producto_por_id[row['producto_id']][key][row['mes']] += float(row['cantidad'] or 0)
                if table == 'entradas':
                    mxn, _, _ = _importe_mxn(conn, row)
                    mensual[row['mes']]['costo'] += mxn
    existencias_mensuales = {}
    for producto in producto_mensual:
        existencia = float(inicios_anio.get(producto['producto_id'], 0) or 0)
        existencias_mensuales[producto['producto_id']] = {}
        for mes in meses:
            existencia += producto['entradas'][mes] - producto['salidas'][mes]
            existencias_mensuales[producto['producto_id']][mes] = existencia
    conn.close()
    return render_template('dashboard_consumo.html', grupo=grupo, anio=anio,
                           seleccionados=seleccionados, resultados=resultados,
                           meses=meses, mensual=mensual, producto_mensual=producto_mensual,
                           inicios_anio=inicios_anio,
                           existencias_mensuales=existencias_mensuales,
                           nombres_meses=['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'])


@dashboard_bp.route('/dashboard/departamentos')
@login_required
def departamentos():
    conn = get_db()
    hoy = date.today()
    fecha_ini = request.args.get('fecha_ini', f'{hoy.year}-01-01')
    fecha_fin = request.args.get('fecha_fin', hoy.isoformat())
    rows = conn.execute("""
        SELECT COALESCE(NULLIF(TRIM(e.departamento),''), NULLIF(TRIM(p.departamento),''), 'SIN DEPARTAMENTO') AS departamento,
               e.cantidad,
               CASE WHEN COALESCE(e.precio_unitario,0) != 0 THEN e.cantidad*e.precio_unitario ELSE e.importe END AS subtotal,
               e.moneda, e.fecha_vale, e.fecha
        FROM entradas e LEFT JOIN productos p ON p.id=e.producto_id
        WHERE DATE(COALESCE(e.fecha_vale,e.fecha)) BETWEEN ? AND ?
        ORDER BY departamento
    """, (fecha_ini, fecha_fin)).fetchall()
    totales = {}
    for row in rows:
        item = totales.setdefault(row['departamento'], {'movimientos': 0, 'cantidad': 0, 'costo_mxn': 0})
        item['movimientos'] += 1
        item['cantidad'] += float(row['cantidad'] or 0)
        mxn, _, _ = _importe_mxn(conn, row)
        item['costo_mxn'] += mxn
    ranking = [{'departamento': k, **v} for k, v in totales.items()]
    ranking.sort(key=lambda x: x['costo_mxn'], reverse=True)
    conn.close()
    return render_template('dashboard_departamentos.html', fecha_ini=fecha_ini,
                           fecha_fin=fecha_fin, ranking=ranking)
