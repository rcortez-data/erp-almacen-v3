from flask import Blueprint, render_template, request, send_file, session
from routes.auth import login_required
from database import get_db
import io
import csv
from datetime import datetime

reportes_bp = Blueprint('reportes', __name__, url_prefix='/reportes')


def get_movimientos(fecha_ini, fecha_fin, tipo=None, producto_q=''):
    conn = get_db()
    rows = []
    if tipo in (None, 'entrada'):
        q = """
            SELECT 'Entrada' as tipo, e.folio, p.codigo, p.descripcion, e.cantidad,
                   p.unidad_medida, e.fecha, u.nombre as usuario, e.no_factura,
                   e.no_requisicion, e.orden_compra, COALESCE(pr.nombre, e.proveedor_nombre_historico) as proveedor, '' as responsable
            FROM entradas e
            JOIN productos p ON e.producto_id=p.id
            LEFT JOIN usuarios u ON e.usuario_id=u.id
            LEFT JOIN proveedores pr ON e.proveedor_id=pr.id
            WHERE 1=1
        """
        params = []
        if fecha_ini: q += " AND DATE(e.fecha)>=?"; params.append(fecha_ini)
        if fecha_fin: q += " AND DATE(e.fecha)<=?"; params.append(fecha_fin)
        if producto_q:
            q += " AND (p.codigo LIKE ? OR p.descripcion LIKE ?)"
            params += [f'%{producto_q}%', f'%{producto_q}%']
        rows += conn.execute(q, params).fetchall()

    if tipo in (None, 'salida'):
        q = """
            SELECT 'Salida' as tipo, s.folio, p.codigo, p.descripcion, s.cantidad,
                   p.unidad_medida, s.fecha, u.nombre as usuario, '' as no_factura,
                   '' as no_requisicion, '' as orden_compra, '' as proveedor, s.responsable
            FROM salidas s
            JOIN productos p ON s.producto_id=p.id
            LEFT JOIN usuarios u ON s.usuario_id=u.id
            WHERE 1=1
        """
        params = []
        if fecha_ini: q += " AND DATE(s.fecha)>=?"; params.append(fecha_ini)
        if fecha_fin: q += " AND DATE(s.fecha)<=?"; params.append(fecha_fin)
        if producto_q:
            q += " AND (p.codigo LIKE ? OR p.descripcion LIKE ?)"
            params += [f'%{producto_q}%', f'%{producto_q}%']
        rows += conn.execute(q, params).fetchall()

    conn.close()
    return sorted(rows, key=lambda r: r['fecha'] or '', reverse=True)


@reportes_bp.route('/')
@login_required
def index():
    fecha_ini = request.args.get('fecha_ini', '')
    fecha_fin = request.args.get('fecha_fin', '')
    tipo = request.args.get('tipo', '')
    producto_q = request.args.get('producto_q', '').strip()
    movimientos = get_movimientos(fecha_ini, fecha_fin, tipo or None, producto_q)
    return render_template('reportes/index.html',
                           movimientos=movimientos, fecha_ini=fecha_ini,
                           fecha_fin=fecha_fin, tipo=tipo, producto_q=producto_q)


@reportes_bp.route('/exportar/csv')
@login_required
def exportar_csv():
    fecha_ini = request.args.get('fecha_ini', '')
    fecha_fin = request.args.get('fecha_fin', '')
    tipo = request.args.get('tipo', '')
    producto_q = request.args.get('producto_q', '').strip()
    movimientos = get_movimientos(fecha_ini, fecha_fin, tipo or None, producto_q)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Tipo', 'Folio', 'Código', 'Descripción', 'Cantidad',
                     'Unidad', 'Fecha', 'Usuario', 'Factura', 'Requisición',
                     'OC', 'Proveedor', 'Responsable'])
    for m in movimientos:
        writer.writerow([m['tipo'], m['folio'], m['codigo'], m['descripcion'],
                         m['cantidad'], m['unidad_medida'], m['fecha'],
                         m['usuario'], m['no_factura'], m['no_requisicion'],
                         m['orden_compra'], m['proveedor'], m['responsable']])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'movimientos_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    )


@reportes_bp.route('/exportar/pdf')
@login_required
def exportar_pdf():
    fecha_ini = request.args.get('fecha_ini', '')
    fecha_fin = request.args.get('fecha_fin', '')
    tipo = request.args.get('tipo', '')
    producto_q = request.args.get('producto_q', '').strip()
    movimientos = get_movimientos(fecha_ini, fecha_fin, tipo or None, producto_q)
    return render_template('reportes/pdf.html',
                           movimientos=movimientos, fecha_ini=fecha_ini,
                           fecha_fin=fecha_fin, tipo=tipo,
                           now=datetime.now().strftime('%d/%m/%Y %H:%M'))


@reportes_bp.route('/inventario')
@login_required
def reporte_inventario():
    conn = get_db()
    productos = conn.execute("""
        SELECT p.*, c.nombre as categoria
        FROM productos p LEFT JOIN categorias c ON p.categoria_id=c.id
        WHERE p.activo=1 ORDER BY p.codigo
    """).fetchall()
    conn.close()
    return render_template('reportes/inventario.html', productos=productos,
                           now=datetime.now().strftime('%d/%m/%Y %H:%M'))


@reportes_bp.route('/inventario/pdf')
@login_required
def inventario_pdf():
    conn = get_db()
    productos = conn.execute("""
        SELECT p.*, c.nombre as categoria
        FROM productos p LEFT JOIN categorias c ON p.categoria_id=c.id
        WHERE p.activo=1 ORDER BY p.codigo
    """).fetchall()
    conn.close()
    bajos = [p for p in productos if p['stock_actual'] <= p['stock_minimo'] and p['stock_minimo'] > 0]
    return render_template('reportes/inventario_pdf.html', productos=productos,
                           bajos=bajos, now=datetime.now().strftime('%d/%m/%Y %H:%M'))


@reportes_bp.route('/inventario/csv')
@login_required
def inventario_csv():
    conn = get_db()
    productos = conn.execute("""
        SELECT p.*, c.nombre as categoria
        FROM productos p LEFT JOIN categorias c ON p.categoria_id=c.id
        WHERE p.activo=1 ORDER BY p.codigo
    """).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Código', 'Descripción', 'Categoría', 'Unidad', 'Ubicación',
                     'Stock Actual', 'Stock Mínimo', 'Alerta'])
    for p in productos:
        alerta = 'SÍ' if p['stock_actual'] <= p['stock_minimo'] and p['stock_minimo'] > 0 else ''
        writer.writerow([p['codigo'], p['descripcion'], p['categoria'],
                         p['unidad_medida'], p['ubicacion'], p['stock_actual'],
                         p['stock_minimo'], alerta])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'inventario_{datetime.now().strftime("%Y%m%d")}.csv'
    )
