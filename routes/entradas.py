from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file, abort
from routes.auth import login_required
from database import get_db, next_folio, log_actividad, get_folio_diario, set_folio_diario
from routes.inventario import construir_busqueda_dinamica
from constantes import CATEGORIAS_CON_MAQUINA, MAQUINAS
from datetime import date, datetime
import base64
import re
import os
import subprocess
import tempfile
import unicodedata

entradas_bp = Blueprint('entradas', __name__, url_prefix='/entradas')

CART_KEY = 'entrada_cart'
DOC_KEY = 'entrada_doc'
OC_PDF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ORDENES DE COMPRA')
TSC_PRINTER_NAME = os.environ.get('ERP_TSC_PRINTER', 'TSC TE200')


def _normalizar_oc_pdf(oc):
    digitos = ''.join(re.findall(r'\d+', str(oc or '')))
    if not digitos:
        return None
    return f"OC{digitos[-10:].zfill(10)}.pdf"


def _ruta_oc_pdf(oc):
    nombre = _normalizar_oc_pdf(oc)
    if not nombre:
        return None
    return os.path.join(OC_PDF_DIR, nombre)


def _oc_pdf_url(oc):
    ruta = _ruta_oc_pdf(oc)
    if not ruta or not os.path.isfile(ruta):
        return None
    nombre = os.path.splitext(os.path.basename(ruta))[0]
    return url_for('entradas.abrir_oc_pdf_local', oc=nombre)


def _areas_activas(conn=None):
    cerrar = conn is None
    if conn is None:
        conn = get_db()
    filas = conn.execute("SELECT nombre FROM areas WHERE activo=1 ORDER BY LOWER(nombre)").fetchall()
    if cerrar:
        conn.close()
    return [fila['nombre'] for fila in filas]


def _subtotal_real(entrada_row):
    """Calcula el subtotal (sin IVA) confiable de una entrada.

    Algunas entradas vienen de la importación masiva del Excel War Machine,
    donde la columna 'Importe' del Excel a veces ya traía el IVA incluido
    (el importe de la factura, no el subtotal). Si confiamos ciegamente en
    el campo `importe` guardado y le volvemos a sumar 16% de IVA, el total
    sale duplicado.

    cantidad * precio_unitario SÍ es confiable como subtotal (precio_unitario
    es el precio unitario antes de IVA), así que se usa como fuente principal.
    Solo si no hay precio_unitario capturado (0 o nulo) se usa el `importe`
    guardado como respaldo, para no perder el dato en esos casos.
    """
    cantidad = entrada_row['cantidad'] or 0
    precio_unitario = entrada_row['precio_unitario'] or 0
    if precio_unitario:
        return round(cantidad * precio_unitario, 2)
    return round(entrada_row['importe'] or 0, 2)


def _es_dolar(moneda):
    """True si el valor de moneda (columna 'moneda' de entradas, o lo que
    venga del formulario) representa dólares estadounidenses. Cualquier otra
    cosa (incluido NULL/vacío/'PESOS', que es lo que trae toda la historia
    capturada antes de este cambio) se trata como pesos mexicanos (MXN)."""
    return (moneda or '').strip().upper() in ('USD', 'DOLAR', 'DOLARES', 'DÓLAR', 'DÓLARES', 'US')


def _iva_de(subtotal, moneda, aplica_iva=None):
    """16% de IVA, o 0 si no aplica.

    `aplica_iva` es el valor explícito capturado (1/0/True/False) para ese
    renglón: por default los pesos sí llevan IVA y los dólares no, pero es
    editable por si llega una factura en dólares que sí trae IVA desglosado
    (o, al revés, una en pesos que no).

    Si `aplica_iva` es None (registros capturados antes de que existiera esta
    opción, donde la columna quedó en NULL), se usa el comportamiento viejo:
    se infiere nada más de la moneda.
    """
    if aplica_iva is not None:
        aplica = bool(aplica_iva)
    else:
        aplica = not _es_dolar(moneda)
    if not aplica:
        return 0.0
    return round((subtotal or 0) * 0.16, 2)


def _normalizar_unidad(unidad):
    """Normaliza nombres de unidades para que sean consistentes.
    
    Convierte:
      - 'kilogramo', 'KILOGRAMO', 'kg', 'KG' → 'KILO'
      - Mantiene otros valores sin cambios
    """
    if not unidad:
        return unidad
    
    unidad_upper = str(unidad).upper().strip()
    
    # Mapeo de variaciones a estándar
    normalizacion = {
        'KILOGRAMO': 'KILO',
        'KG': 'KILO',
        'KILOGRAMOS': 'KILO',
    }
    
    return normalizacion.get(unidad_upper, unidad)


def _cantidad_etiqueta(entrada_row):
    cantidad = entrada_row['cantidad_piezas'] if entrada_row['cantidad_piezas'] is not None else entrada_row['cantidad']
    if cantidad is None:
        return ''
    try:
        cantidad_num = float(cantidad)
        if cantidad_num.is_integer():
            return str(int(cantidad_num))
        return f"{cantidad_num:.4f}".rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return str(cantidad)


def _maquina_categoria_etiqueta(row):
    maquina = (row['maquina'] or '').strip() if 'maquina' in row.keys() else ''
    maquina_otro = (row['maquina_otro'] or '').strip() if 'maquina_otro' in row.keys() else ''
    if maquina.lower() == 'otros' and maquina_otro:
        return maquina_otro
    if maquina or maquina_otro:
        return maquina or maquina_otro
    categoria = (row['categoria'] or '').strip() if 'categoria' in row.keys() else ''
    return categoria or '---'


def _aplicar_filtros_entradas(query, params, fecha_ini, fecha_fin, q, q_doc, q_doc_campo, q_prov, q_prov_archivados):
    if fecha_ini:
        query += " AND DATE(COALESCE(e.fecha_vale, e.fecha)) >= ?"; params.append(fecha_ini)
    if fecha_fin:
        query += " AND DATE(COALESCE(e.fecha_vale, e.fecha)) <= ?"; params.append(fecha_fin)
    if q:
        cond, cond_params = construir_busqueda_dinamica(q, ["p.codigo", "p.codigo_barras", "p.descripcion"])
        if cond:
            query += f" AND {cond}"
            params += cond_params
    if q_doc:
        campos_doc = {
            'factura': 'e.no_factura',
            'remision': 'e.no_remision',
            'requisicion': 'e.no_requisicion',
            'oc': 'e.orden_compra',
            'folio': 'e.folio',
        }
        if q_doc_campo in campos_doc:
            columna = campos_doc[q_doc_campo]
            query += f" AND TRIM(UPPER({columna})) LIKE TRIM(UPPER(?))"
            params.append(f"%{q_doc}%")
        else:
            columnas_doc = ["e.no_factura", "e.no_remision", "e.no_requisicion", "e.orden_compra", "e.folio"]
            cond, cond_params = construir_busqueda_dinamica(q_doc, columnas_doc)
            if cond:
                query += f" AND {cond}"
                params += cond_params
    if q_prov:
        cond, cond_params = construir_busqueda_dinamica(
            q_prov, ["pr.nombre", "pr.nombre_comercial", "e.proveedor_nombre_historico"])
        if cond:
            query += f" AND {cond}"
            params += cond_params
        if not q_prov_archivados:
            query += " AND COALESCE(pr.activo, 0)=1"
    return query, params


def _obtener_etiquetas_entradas(args):
    ids = []
    for raw in args.getlist('ids'):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue

    fecha_ini = args.get('fecha_ini', '')
    fecha_fin = args.get('fecha_fin', '')
    q = args.get('q', '').strip()
    q_doc = args.get('q_doc', '').strip()
    q_doc_campo = args.get('q_doc_campo', '').strip()
    q_prov = args.get('q_prov', '').strip()
    q_prov_archivados = args.get('q_prov_archivados') == '1'

    conn = get_db()
    params = []
    query = """
        SELECT e.id, e.folio, e.cantidad, e.cantidad_piezas, e.no_factura, e.no_remision,
               e.orden_compra, e.departamento, e.observaciones, e.fecha, e.fecha_vale,
               p.codigo, p.descripcion, COALESCE(e.ubicacion, p.ubicacion) AS ubicacion,
               p.unidad_medida, p.maquina, p.maquina_otro,
               COALESCE(c.nombre, p.categoria_nombre_historico) AS categoria,
               COALESCE(NULLIF(pr.nombre_comercial, ''), pr.nombre, e.proveedor_nombre_historico) AS proveedor_nombre
        FROM entradas e
        LEFT JOIN productos p ON e.producto_id=p.id
        LEFT JOIN categorias c ON p.categoria_id=c.id
        LEFT JOIN proveedores pr ON e.proveedor_id=pr.id
        WHERE e.producto_id IS NOT NULL
    """

    if ids:
        placeholders = ",".join("?" for _ in ids)
        query += f" AND e.id IN ({placeholders})"
        params.extend(ids)
    elif any([fecha_ini, fecha_fin, q, q_doc, q_prov, q_prov_archivados]):
        query, params = _aplicar_filtros_entradas(
            query, params, fecha_ini, fecha_fin, q, q_doc, q_doc_campo, q_prov, q_prov_archivados)
    else:
        query += " AND 1=0"

    query += " ORDER BY COALESCE(e.no_factura, ''), COALESCE(e.no_remision, ''), e.id"
    filas = conn.execute(query, params).fetchall()
    conn.close()

    etiquetas = []
    for fila in filas:
        etiqueta = dict(fila)
        etiqueta['cantidad_label'] = _cantidad_etiqueta(fila)
        etiqueta['unidad_label'] = _normalizar_unidad(fila['unidad_medida'])
        etiqueta['maquina_categoria_label'] = _maquina_categoria_etiqueta(fila)
        documentos = []
        if fila['no_factura']:
            documentos.append(f"FAC: {fila['no_factura']}")
        if fila['no_remision']:
            documentos.append(f"REM: {fila['no_remision']}")
        if not documentos and fila['orden_compra']:
            documentos.append(f"OC: {fila['orden_compra']}")
        etiqueta['documentos_label'] = documentos or [fila['folio']]
        etiquetas.append(etiqueta)
    return etiquetas


def _texto_tsc(texto):
    texto = unicodedata.normalize('NFKD', str(texto or ''))
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return texto.replace('"', "'").upper().strip()


def _lineas_tsc(texto, ancho, max_lineas):
    palabras = _texto_tsc(texto).split()
    lineas = []
    actual = ''
    for palabra in palabras:
        candidato = f"{actual} {palabra}".strip()
        if len(candidato) <= ancho:
            actual = candidato
        else:
            if actual:
                lineas.append(actual)
            actual = palabra[:ancho]
        if len(lineas) >= max_lineas:
            break
    if actual and len(lineas) < max_lineas:
        lineas.append(actual)
    return lineas or ['---']


def _tspl_etiqueta(e):
    lineas = [
        'SIZE 101 mm,76 mm',
        'GAP 3 mm,0 mm',
        'DENSITY 8',
        'SPEED 4',
        'DIRECTION 1',
        'REFERENCE 0,0',
        'CLS',
    ]

    def titulo(x, y, texto, w):
        lineas.append(f'TEXT {x},{y},"2",0,1,1,"{_texto_tsc(texto)}"')
        lineas.append(f'BAR {x},{y + 22},{w},3')

    def texto(x, y, valor, xmul=1, ymul=1, fuente="2"):
        lineas.append(f'TEXT {x},{y},"{fuente}",0,{xmul},{ymul},"{_texto_tsc(valor)}"')

    titulo(40, 45, 'Codigo sistema', 205)
    texto(40, 88, e.get('codigo') or '---', 1, 1, "4")
    titulo(40, 190, 'Cantidad', 135)
    texto(40, 233, f"{e.get('cantidad_label', '')} {e.get('unidad_label', '')}", 1, 1, "4")
    titulo(40, 330, 'Factura/Remision', 230)
    y_doc = 372
    for doc in e.get('documentos_label') or ['---']:
        texto(40, y_doc, doc, 1, 1, "2")
        y_doc += 28
    titulo(40, 535, 'Proveedor', 120)
    for i, prov in enumerate(_lineas_tsc(e.get('proveedor_nombre') or '---', 26, 2)):
        texto(40, 570 + (i * 24), prov, 1, 1, "2")

    titulo(420, 45, 'Producto', 130)
    y_prod = 90
    for prod in _lineas_tsc(e.get('descripcion') or '---', 18, 9):
        texto(420, y_prod, prod, 1, 1, "4")
        y_prod += 42
    titulo(420, 410, 'Ubicacion', 145)
    for i, ubicacion in enumerate(_lineas_tsc(e.get('ubicacion') or '---', 19, 2)):
        texto(420, 452 + (i * 32), ubicacion, 1, 1, "3")
    titulo(420, 535, 'Categoria o maquina', 230)
    for i, maq in enumerate(_lineas_tsc(e.get('maquina_categoria_label') or '---', 19, 2)):
        texto(420, 578 + (i * 30), maq, 1, 1, "3")

    lineas.append('PRINT 1,1')
    return '\r\n'.join(lineas) + '\r\n'


def _imprimir_tsc(etiquetas):
    data = ''.join(_tspl_etiqueta(e) for e in etiquetas)
    printer_b64 = base64.b64encode(TSC_PRINTER_NAME.encode('utf-16le')).decode('ascii')
    ps = r'''
$printer = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($env:ERP_TSC_PRINTER_B64))
$bytes = [IO.File]::ReadAllBytes($env:ERP_TSC_FILE)
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class RawPrinterHelper {
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Ansi)]
  public class DOCINFOA {
    [MarshalAs(UnmanagedType.LPStr)] public string pDocName;
    [MarshalAs(UnmanagedType.LPStr)] public string pOutputFile;
    [MarshalAs(UnmanagedType.LPStr)] public string pDataType;
  }
  [DllImport("winspool.Drv", EntryPoint="OpenPrinterA", SetLastError=true, CharSet=CharSet.Ansi)]
  public static extern bool OpenPrinter(string szPrinter, out IntPtr hPrinter, IntPtr pd);
  [DllImport("winspool.Drv", SetLastError=true)] public static extern bool ClosePrinter(IntPtr hPrinter);
  [DllImport("winspool.Drv", EntryPoint="StartDocPrinterA", SetLastError=true, CharSet=CharSet.Ansi)]
  public static extern bool StartDocPrinter(IntPtr hPrinter, int level, [In] DOCINFOA di);
  [DllImport("winspool.Drv", SetLastError=true)] public static extern bool EndDocPrinter(IntPtr hPrinter);
  [DllImport("winspool.Drv", SetLastError=true)] public static extern bool StartPagePrinter(IntPtr hPrinter);
  [DllImport("winspool.Drv", SetLastError=true)] public static extern bool EndPagePrinter(IntPtr hPrinter);
  [DllImport("winspool.Drv", SetLastError=true)] public static extern bool WritePrinter(IntPtr hPrinter, IntPtr pBytes, int dwCount, out int dwWritten);
}
"@
$h = [IntPtr]::Zero
if (-not [RawPrinterHelper]::OpenPrinter($printer, [ref]$h, [IntPtr]::Zero)) { throw "No se pudo abrir impresora $printer" }
try {
  $doc = New-Object RawPrinterHelper+DOCINFOA
  $doc.pDocName = "ERP Etiquetas Entradas"
  $doc.pDataType = "RAW"
  [RawPrinterHelper]::StartDocPrinter($h, 1, $doc) | Out-Null
  [RawPrinterHelper]::StartPagePrinter($h) | Out-Null
  $ptr = [Runtime.InteropServices.Marshal]::AllocHGlobal($bytes.Length)
  try {
    [Runtime.InteropServices.Marshal]::Copy($bytes, 0, $ptr, $bytes.Length)
    $written = 0
    [RawPrinterHelper]::WritePrinter($h, $ptr, $bytes.Length, [ref]$written) | Out-Null
  } finally {
    [Runtime.InteropServices.Marshal]::FreeHGlobal($ptr)
  }
  [RawPrinterHelper]::EndPagePrinter($h) | Out-Null
  [RawPrinterHelper]::EndDocPrinter($h) | Out-Null
} finally {
  [RawPrinterHelper]::ClosePrinter($h) | Out-Null
}
'''
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile('wb', suffix='.tspl', delete=False) as tmp:
            tmp.write(data.encode('ascii', errors='ignore'))
            tmp_name = tmp.name
        env = os.environ.copy()
        env['ERP_TSC_PRINTER_B64'] = printer_b64
        env['ERP_TSC_FILE'] = tmp_name
        resultado = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
            env=env, capture_output=True, text=True, timeout=30)
        if resultado.returncode != 0:
            raise RuntimeError((resultado.stderr or resultado.stdout or 'No se pudo imprimir en TSC.').strip())
    finally:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


def _vincular_con_requisicion(conn, doc):
    """Si el documento de la entrada trae un número de requisición (ej. '12' o 'AL-12'),
    busca la requisición con ese folio y completa (sin sobreescribir lo ya capturado) sus
    campos de seguimiento con la orden de compra / factura / remisión de esta entrada, para
    que el estatus de la requisición se pueda rastrear desde ahí. También cambia su estado a
    'revision' de inmediato (antes esto solo pasaba al abrir la requisición manualmente)."""
    texto = (doc.get('no_requisicion') or '').strip()
    if not texto:
        return
    m = re.search(r'(\d+)', texto)
    if not m:
        return
    folio_num = int(m.group(1))
    req = conn.execute("SELECT * FROM requisiciones WHERE folio=?", (folio_num,)).fetchone()
    if not req:
        return
    cambios = {}
    if not req['orden_compra'] and doc.get('orden_compra'):
        cambios['orden_compra'] = doc.get('orden_compra')
    if not req['no_factura'] and doc.get('no_factura'):
        cambios['no_factura'] = doc.get('no_factura')
    if not req['no_remision'] and doc.get('no_remision'):
        cambios['no_remision'] = doc.get('no_remision')
    if cambios:
        set_clause = ", ".join(f"{k}=?" for k in cambios)
        conn.execute(f"UPDATE requisiciones SET {set_clause} WHERE id=?",
                     (*cambios.values(), req['id']))
    if req['estado'] not in ('revision', 'parcial', 'completa'):
        conn.execute("UPDATE requisiciones SET estado='revision' WHERE id=?", (req['id'],))
    flash(f'Esta entrada se vinculó con la requisición AL-{folio_num}.', 'info')


def _normalizar_requisicion(texto):
    if not texto:
        return ""
    return str(texto).strip().upper().replace("-", "").replace(" ", "")


def _coincide_requisicion(texto, folio_num):
    valor = _normalizar_requisicion(texto)
    folio = str(folio_num)
    return valor in (folio, f"AL{folio}")


def _folio_requisicion_desde_texto(texto):
    texto = (texto or '').strip()
    if not texto:
        return None
    m = re.search(r'(\d+)', texto)
    return int(m.group(1)) if m else None


def _recalcular_estado_requisicion_por_texto(conn, texto_requisicion):
    folio_num = _folio_requisicion_desde_texto(texto_requisicion)
    if not folio_num:
        return

    req = conn.execute("SELECT * FROM requisiciones WHERE folio=?", (folio_num,)).fetchone()
    if not req:
        return

    entradas = conn.execute("""
        SELECT producto_id, cantidad, cantidad_piezas, no_requisicion
        FROM entradas
        WHERE no_requisicion IS NOT NULL AND TRIM(no_requisicion) != ''
    """).fetchall()
    entradas_rel = [
        e for e in entradas
        if _coincide_requisicion(e['no_requisicion'], folio_num)
    ]

    if not entradas_rel:
        conn.execute("""
            UPDATE requisiciones
            SET estado='pendiente',
                orden_compra=NULL,
                no_factura=NULL,
                no_remision=NULL
            WHERE id=?
        """, (req['id'],))
        return

    items = conn.execute(
        "SELECT producto_id, cantidad, cantidad_recibida FROM requisicion_items WHERE requisicion_id=? ORDER BY orden",
        (req['id'],)
    ).fetchall()
    if not items:
        conn.execute("UPDATE requisiciones SET estado='revision' WHERE id=?", (req['id'],))
        return

    recibido_por_producto = {}
    for entrada in entradas_rel:
        if not entrada['producto_id']:
            continue
        cantidad = entrada['cantidad_piezas'] if entrada['cantidad_piezas'] is not None else entrada['cantidad']
        recibido_por_producto[entrada['producto_id']] = recibido_por_producto.get(entrada['producto_id'], 0) + (cantidad or 0)

    completos = 0
    con_algo = 0
    for item in items:
        if item['producto_id']:
            recibido = recibido_por_producto.get(item['producto_id'], 0)
        else:
            recibido = item['cantidad_recibida'] or 0
        if recibido >= item['cantidad']:
            completos += 1
        if recibido > 0:
            con_algo += 1

    if completos == len(items):
        estado = 'completa'
    elif con_algo > 0:
        estado = 'parcial'
    else:
        estado = 'revision'

    conn.execute("UPDATE requisiciones SET estado=? WHERE id=?", (estado, req['id']))


@entradas_bp.route('/orden-compra/<path:oc>')
@login_required
def abrir_oc_pdf(oc):
    ruta = _ruta_oc_pdf(oc)
    if not ruta or not os.path.isfile(ruta):
        abort(404)
    return send_file(ruta, mimetype='application/pdf', as_attachment=False)


@entradas_bp.route('/orden-compra-local/<path:oc>')
@login_required
def abrir_oc_pdf_local(oc):
    ruta = _ruta_oc_pdf(oc)
    if not ruta or not os.path.isfile(ruta):
        abort(404)
    try:
        os.startfile(ruta)
    except Exception as exc:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'error': f'No se pudo abrir en Acrobat: {exc}'}), 500
        flash(f'No se pudo abrir en Acrobat: {exc}. Se abrirá en el navegador.', 'warning')
        return send_file(ruta, mimetype='application/pdf', as_attachment=False)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True})
    flash('Orden de compra abierta en el visor de PDF predeterminado.', 'success')
    volver = request.referrer or url_for('entradas.index')
    return redirect(volver)


@entradas_bp.route('/')
@login_required
def index():
    fecha_ini = request.args.get('fecha_ini', '')
    fecha_fin = request.args.get('fecha_fin', '')
    q = request.args.get('q', '').strip()
    q_doc = request.args.get('q_doc', '').strip()
    q_doc_campo = request.args.get('q_doc_campo', '').strip()
    q_prov = request.args.get('q_prov', '').strip()
    q_prov_archivados = request.args.get('q_prov_archivados') == '1'
    pagina = request.args.get('pagina', 1, type=int)
    registros_por_pagina = 50
    
    conn = get_db()
    select_sql = """
        SELECT e.*, COALESCE(p.codigo, 'SERVICIO') as codigo,
               COALESCE(p.descripcion, e.concepto_servicio) as descripcion,
               COALESCE(p.unidad_medida, 'SERVICIO') as unidad_medida,
               p.unidad_compra, p.factor_conversion, COALESCE(e.ubicacion, p.ubicacion) as ubicacion_actual,
               u.nombre as usuario_nombre, COALESCE(pr.nombre, e.proveedor_nombre_historico) as proveedor_nombre,
               pr.nombre_comercial as proveedor_nombre_comercial
    """
    from_sql = """
        FROM entradas e
        LEFT JOIN productos p ON e.producto_id=p.id
        LEFT JOIN usuarios u ON e.usuario_id=u.id
        LEFT JOIN proveedores pr ON e.proveedor_id=pr.id
        WHERE 1=1
    """
    where_sql = ""
    params = []
    if fecha_ini:
        where_sql += " AND DATE(COALESCE(e.fecha_vale, e.fecha)) >= ?"; params.append(fecha_ini)
    if fecha_fin:
        where_sql += " AND DATE(COALESCE(e.fecha_vale, e.fecha)) <= ?"; params.append(fecha_fin)
    if q:
        cond, cond_params = construir_busqueda_dinamica(q, ["p.codigo", "p.codigo_barras", "p.descripcion"])
        if cond:
            where_sql += f" AND {cond}"
            params += cond_params
    if q_doc:
        campos_doc = {
            'factura': 'e.no_factura',
            'remision': 'e.no_remision',
            'requisicion': 'e.no_requisicion',
            'oc': 'e.orden_compra',
            'folio': 'e.folio',
        }
        if q_doc_campo in campos_doc:
            # Campo específico elegido: búsqueda PARCIAL (LIKE)
            # Permite encontrar "41" dentro de "OC-4140-B"
            columna = campos_doc[q_doc_campo]
            where_sql += f" AND TRIM(UPPER({columna})) LIKE TRIM(UPPER(?))"
            params.append(f"%{q_doc}%")
        else:
            # 'Todos': búsqueda flexible parcial en cualquiera de los campos
            columnas_doc = ["e.no_factura", "e.no_remision", "e.no_requisicion", "e.orden_compra", "e.folio"]
            cond, cond_params = construir_busqueda_dinamica(q_doc, columnas_doc)
            if cond:
                where_sql += f" AND {cond}"
                params += cond_params
    if q_prov:
        cond, cond_params = construir_busqueda_dinamica(
            q_prov, ["pr.nombre", "pr.nombre_comercial", "e.proveedor_nombre_historico"])
        if cond:
            where_sql += f" AND {cond}"
            params += cond_params
        if not q_prov_archivados:
            where_sql += " AND COALESCE(pr.activo, 0)=1"

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
    entradas_pagina = conn.execute(
        f"{select_sql} {from_sql} {where_sql} ORDER BY e.fecha DESC LIMIT ? OFFSET ?",
        params + [registros_por_pagina, offset]
    ).fetchall()

    entradas = []
    for e in entradas_pagina:
        fila = dict(e)
        fila['subtotal_real'] = _subtotal_real(e)
        fila['es_dolar'] = _es_dolar(e['moneda'])
        fila['iva_real'] = _iva_de(fila['subtotal_real'], e['moneda'], e['aplica_iva'])
        fila['importe_con_iva'] = round(fila['subtotal_real'] + fila['iva_real'], 2)
        fila['unidad_medida'] = _normalizar_unidad(fila.get('unidad_medida'))
        fila['ubicacion'] = fila.get('ubicacion_actual') or fila.get('ubicacion')
        fila['oc_pdf_url'] = _oc_pdf_url(fila.get('orden_compra'))
        entradas.append(fila)

    subtotal_sql = "CASE WHEN COALESCE(e.precio_unitario, 0) != 0 THEN COALESCE(e.cantidad, 0) * COALESCE(e.precio_unitario, 0) ELSE COALESCE(e.importe, 0) END"
    iva_sql = f"""CASE
        WHEN e.aplica_iva IS NOT NULL THEN CASE WHEN e.aplica_iva THEN ({subtotal_sql}) * 0.16 ELSE 0 END
        WHEN UPPER(COALESCE(e.moneda, '')) IN ('USD','DOLAR','DOLARES','DÓLAR','DÓLARES','US') THEN 0
        ELSE ({subtotal_sql}) * 0.16
    END"""
    totales = conn.execute(f"""
        SELECT COALESCE(SUM({subtotal_sql}), 0) AS total_importe,
               COALESCE(SUM({iva_sql}), 0) AS total_iva,
               COALESCE(SUM(CASE WHEN UPPER(COALESCE(e.moneda, '')) IN ('USD','DOLAR','DOLARES','DÓLAR','DÓLARES','US') THEN {subtotal_sql} ELSE 0 END), 0) AS total_importe_usd
        {from_sql} {where_sql}
    """, params).fetchone()
    total_importe = round(totales['total_importe'] or 0, 2)
    total_iva = round(totales['total_iva'] or 0, 2)
    total_general = round(total_importe + total_iva, 2)
    total_importe_usd = round(totales['total_importe_usd'] or 0, 2)
    total_importe_mxn = round(total_importe - total_importe_usd, 2)
    total_general_mxn = round(total_importe_mxn + total_iva, 2)
    filtro_activo = bool(fecha_ini or fecha_fin or q or q_doc or q_prov or q_prov_archivados)
    conn.close()
    return render_template('entradas/index.html', entradas=entradas,
                           fecha_ini=fecha_ini, fecha_fin=fecha_fin,
                           q=q, q_doc=q_doc, q_doc_campo=q_doc_campo, q_prov=q_prov,
                           q_prov_archivados=q_prov_archivados,
                           total_importe=total_importe, total_iva=total_iva,
                           total_general=total_general, filtro_activo=filtro_activo,
                           total_importe_mxn=total_importe_mxn, total_importe_usd=total_importe_usd,
                           total_general_mxn=total_general_mxn,
                           pagina_actual=pagina, total_paginas=total_paginas,
                           total_registros=total_registros, registros_pagina=len(entradas))


@entradas_bp.route('/etiquetas')
@login_required
def etiquetas():
    etiquetas = _obtener_etiquetas_entradas(request.args)
    return render_template('entradas/etiquetas.html', etiquetas=etiquetas, printer_name=TSC_PRINTER_NAME)


@entradas_bp.route('/etiquetas/tsc', methods=['POST'])
@login_required
def imprimir_etiquetas_tsc():
    etiquetas = _obtener_etiquetas_entradas(request.form)
    volver = request.form.get('volver') or url_for('entradas.index')
    if not etiquetas:
        flash('No hay etiquetas para imprimir.', 'warning')
        return redirect(volver)
    try:
        _imprimir_tsc(etiquetas)
        flash(f'{len(etiquetas)} etiqueta(s) enviadas a {TSC_PRINTER_NAME}.', 'success')
    except Exception as exc:
        flash(f'No se pudo imprimir en {TSC_PRINTER_NAME}: {exc}', 'danger')
    return redirect(volver)


@entradas_bp.route('/api/buscar_documento')
@login_required
def api_buscar_documento():
    """Autocompletado para el buscador de Factura/Remisión/Requisición/OC/Folio.
    Devuelve valores EXACTOS que existen en la BD y contienen el texto escrito,
    para que el usuario pueda escribir solo una parte y elegir el valor completo
    con un clic (así el filtro sigue siendo una coincidencia exacta y no arrastra
    documentos distintos que solo comparten dígitos)."""
    campo = request.args.get('campo', '').strip()
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    campos_doc = {
        'factura': ('no_factura', 'Factura'),
        'remision': ('no_remision', 'Remisión'),
        'requisicion': ('no_requisicion', 'Requisición'),
        'oc': ('orden_compra', 'OC'),
        'folio': ('folio', 'Folio'),
    }
    columnas = [campos_doc[campo]] if campo in campos_doc else list(campos_doc.values())

    conn = get_db()
    resultados = []
    for columna, etiqueta in columnas:
        filas = conn.execute(f"""
            SELECT {columna} AS valor, MAX(e.fecha) AS fecha, COUNT(*) AS num_renglones
            FROM entradas e
            WHERE {columna} IS NOT NULL AND TRIM({columna}) != '' AND {columna} LIKE ?
            GROUP BY {columna}
            ORDER BY fecha DESC
            LIMIT 10
        """, (f'%{q}%',)).fetchall()
        for f in filas:
            resultados.append({
                'valor': f['valor'],
                'campo_label': etiqueta,
                'campo_key': [k for k, v in campos_doc.items() if v[1] == etiqueta][0],
                'fecha': (f['fecha'] or '')[:10],
                'num_renglones': f['num_renglones'],
            })
    conn.close()

    resultados = resultados[:15]
    return jsonify(resultados)


@entradas_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    conn = get_db()
    proveedores = conn.execute(
        "SELECT * FROM proveedores WHERE activo=1 ORDER BY nombre").fetchall()
    departamentos = _areas_activas(conn)
    categorias = conn.execute("SELECT * FROM categorias ORDER BY LOWER(nombre)").fetchall()

    if request.method == 'POST':
        accion = request.form.get('accion')

        # Los datos del documento se guardan en sesión cada vez que se envía el formulario
        session[DOC_KEY] = {
            'no_requisicion': request.form.get('no_requisicion', ''),
            'no_factura': request.form.get('no_factura', ''),
            'orden_compra': request.form.get('orden_compra', ''),
            'no_remision': request.form.get('no_remision', ''),
            'solo_remision': bool(request.form.get('solo_remision')),
            'sin_oc': bool(request.form.get('sin_oc')),
            'compra_gas': bool(request.form.get('compra_gas')),
            'proveedor_id': request.form.get('proveedor_id', ''),
            'proveedor_texto': request.form.get('buscador_proveedor_valor') or session.get(DOC_KEY, {}).get('proveedor_texto', ''),
            'observaciones': request.form.get('observaciones', ''),
            'tipo_movimiento': request.form.get('tipo_movimiento', 'normal'),
            'fecha_vale': request.form.get('fecha_vale') or session.get(DOC_KEY, {}).get('fecha_vale', date.today().isoformat()),
        }
        session.modified = True

        if accion == 'ir_nuevo_producto':
            conn.close()
            return redirect(url_for('inventario.nuevo', origen='entradas'))

        elif accion == 'agregar_item':
            pid = request.form.get('producto_id')
            cantidad = request.form.get('cantidad')
            precio = request.form.get('precio_unitario') or 0
            categoria_item = request.form.get('categoria_item') or None
            maquina_item = (request.form.get('maquina_item') or '').strip()
            maquina_otro_item = (request.form.get('maquina_otro_item') or '').strip()
            departamento_item = request.form.get('departamento_item') or None
            ubicacion_item = (request.form.get('ubicacion_item') or '').strip()
            uso_item = (request.form.get('uso_item') or '').strip()
            moneda = (request.form.get('moneda') or 'MXN').strip().upper()
            aplica_iva = request.form.get('aplica_iva') == 'on'
            if not pid or not cantidad:
                flash('Selecciona un producto de la lista y captura la cantidad.', 'danger')
            elif not ubicacion_item:
                flash('La ubicación es obligatoria para agregar el producto a la entrada.', 'danger')
            elif len(ubicacion_item) < 2:
                flash('La ubicación debe tener mínimo 2 caracteres.', 'danger')
            elif not uso_item:
                flash('El uso es obligatorio para agregar el producto a la entrada.', 'danger')
            else:
                prod = conn.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()
                if not prod:
                    flash('El producto seleccionado no existe.', 'danger')
                else:
                    cantidad = float(cantidad)
                    precio = float(precio)
                    tiene_conversion = bool(prod['unidad_compra'] and prod['factor_conversion'])
                    cantidad_piezas = round(cantidad / prod['factor_conversion'], 4) if tiene_conversion else cantidad
                    categoria_con_maquina = False
                    if categoria_item:
                        cat_row = conn.execute("SELECT nombre FROM categorias WHERE id=?", (categoria_item,)).fetchone()
                        categoria_nombre = cat_row['nombre'] if cat_row else ''
                        categoria_con_maquina = categoria_nombre in CATEGORIAS_CON_MAQUINA
                        categoria_actual = str(prod['categoria_id'] or '')
                        if categoria_item != categoria_actual:
                            conn.execute(
                                "UPDATE productos SET categoria_id=? WHERE id=?",
                                (categoria_item, prod['id'])
                            )
                        if categoria_con_maquina:
                            conn.execute(
                                "UPDATE productos SET maquina=?, maquina_otro=? WHERE id=?",
                                (maquina_item or None, maquina_otro_item if maquina_item == 'Otros' else None, prod['id'])
                            )
                        else:
                            conn.execute(
                                "UPDATE productos SET maquina=NULL, maquina_otro=NULL WHERE id=?",
                                (prod['id'],)
                            )
                    if departamento_item and departamento_item != (prod['departamento'] or ''):
                        conn.execute(
                            "UPDATE productos SET departamento=? WHERE id=?",
                            (departamento_item, prod['id'])
                        )
                    if ubicacion_item and ubicacion_item != (prod['ubicacion'] or ''):
                        conn.execute(
                            "UPDATE productos SET ubicacion=? WHERE id=?",
                            (ubicacion_item, prod['id'])
                        )
                    if ((categoria_item and categoria_item != str(prod['categoria_id'] or '')) or
                        (categoria_item and (
                            (maquina_item or '') != (prod['maquina'] or '') or
                            ((maquina_otro_item if maquina_item == 'Otros' else '') != (prod['maquina_otro'] or ''))
                        )) or
                        (departamento_item and departamento_item != (prod['departamento'] or '')) or
                        (ubicacion_item and ubicacion_item != (prod['ubicacion'] or ''))):
                        conn.commit()
                    cart = session.get(CART_KEY, [])
                    cart.append({
                        'producto_id': prod['id'], 'codigo': prod['codigo'],
                        'codigo_barras': prod['codigo_barras'],
                        'descripcion': prod['descripcion'],
                        'unidad_medida': prod['unidad_compra'] if tiene_conversion else prod['unidad_medida'],
                        'cantidad': cantidad, 'precio_unitario': precio,
                        'importe': round(cantidad * precio, 4),
                        'departamento': departamento_item or prod['departamento'],
                        'ubicacion': ubicacion_item or prod['ubicacion'],
                        'uso': uso_item,
                        'tiene_conversion': tiene_conversion,
                        'cantidad_piezas': cantidad_piezas,
                        'unidad_piezas': prod['unidad_medida'],
                        'es_servicio': False,
                        'moneda': moneda,
                        'aplica_iva': aplica_iva,
                    })
                    session[CART_KEY] = cart
                    session['entrada_ultima_moneda'] = moneda
                    session['entrada_ultimo_aplica_iva'] = aplica_iva
                    session.modified = True
                    if tiene_conversion:
                        flash(f"{prod['codigo']} agregado a la lista ({cantidad} {prod['unidad_compra']} = {cantidad_piezas} {prod['unidad_medida']}).", 'success')
                    else:
                        flash(f"{prod['codigo']} agregado a la lista.", 'success')
            conn.close()
            return redirect(url_for('entradas.nuevo'))

        elif accion == 'agregar_servicio':
            # Cargos de la factura que NO son un producto de inventario
            # (servicios, flete, instalación, etc.) — no afectan stock ni
            # requieren dar de alta nada en el catálogo.
            concepto = (request.form.get('concepto_servicio') or '').strip()
            cantidad_raw = request.form.get('cantidad_servicio') or '1'
            precio_raw = request.form.get('precio_servicio') or '0'
            departamento_item = request.form.get('departamento_item_servicio') or None
            moneda = (request.form.get('moneda_servicio') or 'MXN').strip().upper()
            aplica_iva = request.form.get('aplica_iva_servicio') == 'on'
            if not concepto:
                flash('Escribe una descripción para el servicio o cargo (ej. "Flete", "Servicio de instalación").', 'danger')
            else:
                try:
                    cantidad = float(cantidad_raw)
                    precio = float(precio_raw)
                except ValueError:
                    cantidad, precio = 1.0, 0.0
                cart = session.get(CART_KEY, [])
                cart.append({
                    'producto_id': None, 'codigo': 'SERVICIO',
                    'descripcion': concepto,
                    'unidad_medida': 'SERVICIO',
                    'cantidad': cantidad, 'precio_unitario': precio,
                    'importe': round(cantidad * precio, 4),
                    'departamento': departamento_item,
                    'tiene_conversion': False,
                    'cantidad_piezas': cantidad,
                    'unidad_piezas': 'SERVICIO',
                    'es_servicio': True,
                    'concepto_servicio': concepto,
                    'moneda': moneda,
                    'aplica_iva': aplica_iva,
                })
                session[CART_KEY] = cart
                session['entrada_ultima_moneda'] = moneda
                session['entrada_ultimo_aplica_iva'] = aplica_iva
                session.modified = True
                flash(f'"{concepto}" agregado a la lista como servicio/cargo (sin afectar stock).', 'success')
            conn.close()
            return redirect(url_for('entradas.nuevo'))

        elif accion == 'quitar_item':
            idx = int(request.form.get('idx', -1))
            cart = session.get(CART_KEY, [])
            if 0 <= idx < len(cart):
                cart.pop(idx)
                session[CART_KEY] = cart
                session.modified = True
            conn.close()
            return redirect(url_for('entradas.nuevo'))

        elif accion in ('guardar_todo', 'guardar_y_nueva'):
            cart = session.get(CART_KEY, [])
            doc = session.get(DOC_KEY, {})
            if not cart:
                flash('Agrega al menos un producto a la lista antes de guardar.', 'danger')
                conn.close()
                return redirect(url_for('entradas.nuevo'))
            if not doc.get('solo_remision') and not doc.get('sin_oc') and not doc.get('compra_gas') and not (doc.get('orden_compra') or '').strip():
                flash('La orden de compra es obligatoria. Si esta factura no tiene OC porque fue pagada en efectivo, '
                      'marca la casilla "Factura sin OC". Si es una compra de gas marca "Compra de gas". '
                      'Si es solo una remisión (sin OC, factura ni requisición), marca "Solo remisión".', 'danger')
                conn.close()
                return redirect(url_for('entradas.nuevo'))
            if not doc.get('solo_remision') and not (doc.get('no_factura') or '').strip():
                flash('El número de factura es obligatorio. Si esta entrada es solo una remisión '
                      '(sin OC, factura ni requisición), marca la casilla "Solo remisión".', 'danger')
                conn.close()
                return redirect(url_for('entradas.nuevo'))
            if not doc.get('solo_remision') and not (doc.get('proveedor_id') or '').strip():
                flash('Debes elegir el proveedor de la lista de resultados (o darlo de alta con el botón '
                      '"¿No lo encuentras?") antes de guardar. Si escribiste el nombre pero no le diste clic a un '
                      'resultado, el proveedor no quedó seleccionado. Si esta entrada es solo una remisión '
                      '(sin OC, factura ni requisición), marca la casilla "Solo remisión".', 'danger')
                conn.close()
                return redirect(url_for('entradas.nuevo'))
            try:
                prov_id = doc.get('proveedor_id') or None
                tipo_mov = doc.get('tipo_movimiento') or 'normal'
                fecha_sql = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                fecha_vale = doc.get('fecha_vale') or date.today().isoformat()
                folios_generados = []
                for item in cart:
                    conn.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo = 'entrada'")
                    num = conn.execute("SELECT ultimo FROM folios WHERE tipo = 'entrada'").fetchone()[0]
                    folio = f"ENT-{str(num).zfill(6)}"
                    conn.execute("""
                        INSERT INTO entradas
                        (folio, producto_id, es_servicio, concepto_servicio,
                         cantidad, cantidad_piezas, precio_unitario, importe,
                         no_requisicion, no_factura, orden_compra, no_remision, sin_oc,
                         proveedor_id, departamento, ubicacion, uso, tipo_movimiento, usuario_id, observaciones, fecha, fecha_vale, moneda, aplica_iva, compra_gas)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (folio, item.get('producto_id'), int(item.get('es_servicio', False)),
                          item.get('concepto_servicio'),
                          item['cantidad'], item.get('cantidad_piezas', item['cantidad']),
                          item['precio_unitario'],
                          item['importe'], doc.get('no_requisicion'), doc.get('no_factura'),
                          doc.get('orden_compra'), doc.get('no_remision'), int(doc.get('sin_oc', False)), prov_id,
                          item.get('departamento'), item.get('ubicacion'), item.get('uso'), tipo_mov,
                          session['user_id'], doc.get('observaciones'), fecha_sql, fecha_vale,
                          item.get('moneda') or 'MXN', int(bool(item.get('aplica_iva'))),
                          int(doc.get('compra_gas', False))))
                    if not item.get('es_servicio') and item.get('producto_id'):
                        conn.execute(
                            "UPDATE productos SET stock_actual = stock_actual + ? WHERE id=?",
                            (item.get('cantidad_piezas', item['cantidad']), item['producto_id']))
                    folios_generados.append(folio)
                conn.commit()
                log_actividad(session['user_id'], 'ENTRADA',
                              f"Folios: {', '.join(folios_generados)} | Factura: {doc.get('no_factura') or '-'} | Tipo: {tipo_mov}")
                session.pop(CART_KEY, None)
                session.pop(DOC_KEY, None)

                # Vínculo automático con Requisiciones: si se capturó no_requisicion,
                # se busca la requisición con ese folio y se completan (sin pisar) sus
                # datos de seguimiento (OC/factura/remisión) con los de esta entrada,
                # y se cambia su estado a "revisión" de inmediato.
                _vincular_con_requisicion(conn, doc)
                conn.commit()

                flash(f"{len(folios_generados)} entrada(s) registradas correctamente.", 'success')
                conn.close()
                if accion == 'guardar_y_nueva':
                    return redirect(url_for('entradas.nuevo'))
                return redirect(url_for('entradas.index'))
            except Exception as e:
                conn.rollback()
                flash(f'Error: {str(e)}', 'danger')
                conn.close()
                return redirect(url_for('entradas.nuevo'))

    doc = session.get(DOC_KEY, {})
    cart = session.get(CART_KEY, [])
    conn.close()
    preseleccion_id = request.args.get('agregar')
    ahora = datetime.now().strftime('%Y-%m-%dT%H:%M')
    return render_template('entradas/form.html', proveedores=proveedores,
                           doc=doc, cart=cart, preseleccion_id=preseleccion_id,
                           departamentos=departamentos, categorias=categorias, ahora=ahora,
                           categorias_con_maquina=CATEGORIAS_CON_MAQUINA, maquinas=MAQUINAS)


@entradas_bp.route('/cancelar_captura')
@login_required
def cancelar_captura():
    session.pop(CART_KEY, None)
    session.pop(DOC_KEY, None)
    flash('Captura cancelada.', 'warning')
    return redirect(url_for('entradas.index'))


@entradas_bp.route('/detalle/<int:eid>')
@login_required
def detalle(eid):
    conn = get_db()
    entrada = conn.execute("""
        SELECT e.*, COALESCE(p.codigo, 'SERVICIO') as codigo,
               COALESCE(p.descripcion, e.concepto_servicio) as descripcion,
               COALESCE(p.unidad_compra, p.unidad_medida, 'SERVICIO') as unidad_medida,
               p.unidad_compra, p.factor_conversion, COALESCE(e.ubicacion, p.ubicacion) as ubicacion_actual,
               u.nombre as usuario_nombre, COALESCE(pr.nombre, e.proveedor_nombre_historico) as proveedor_nombre
        FROM entradas e
        LEFT JOIN productos p ON e.producto_id=p.id
        LEFT JOIN usuarios u ON e.usuario_id=u.id
        LEFT JOIN proveedores pr ON e.proveedor_id=pr.id
        WHERE e.id=?
    """, (eid,)).fetchone()
    requisicion_vinculada = None
    if entrada:
        m = re.search(r'(\d+)', entrada['no_requisicion'] or '')
        if m:
            requisicion_vinculada = conn.execute(
                "SELECT id, folio FROM requisiciones WHERE folio=?", (int(m.group(1)),)).fetchone()
    conn.close()
    if not entrada:
        flash('Registro no encontrado.', 'danger')
        return redirect(url_for('entradas.index'))
    entrada = dict(entrada)
    entrada['ubicacion'] = entrada.get('ubicacion_actual') or entrada.get('ubicacion')
    subtotal = _subtotal_real(entrada)
    iva = _iva_de(subtotal, entrada['moneda'], entrada['aplica_iva'])
    total_con_iva = round(subtotal + iva, 2)
    es_dolar = _es_dolar(entrada['moneda'])
    oc_pdf_url = _oc_pdf_url(entrada['orden_compra'])
    volver = request.args.get('volver', '')
    return render_template('entradas/detalle.html', entrada=entrada, requisicion_vinculada=requisicion_vinculada,
                           subtotal=subtotal, iva=iva, total_con_iva=total_con_iva, es_dolar=es_dolar,
                           oc_pdf_url=oc_pdf_url, volver=volver)


@entradas_bp.route('/eliminar/<int:eid>', methods=['POST'])
@login_required
def eliminar(eid):
    """Elimina una entrada capturada por error. Revierte su efecto en el stock del
    producto (resta lo que esa entrada había sumado) y borra el registro."""
    volver = request.values.get('volver', '')
    conn = get_db()
    entrada = conn.execute("SELECT * FROM entradas WHERE id=?", (eid,)).fetchone()
    if not entrada:
        flash('Registro no encontrado.', 'danger')
        conn.close()
        return redirect(f"{url_for('entradas.index')}?{volver}" if volver else url_for('entradas.index'))
    try:
        cantidad_piezas = entrada['cantidad_piezas'] if entrada['cantidad_piezas'] is not None else entrada['cantidad']
        conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?",
                    (cantidad_piezas, entrada['producto_id']))
        conn.execute("DELETE FROM entradas WHERE id=?", (eid,))
        _recalcular_estado_requisicion_por_texto(conn, entrada['no_requisicion'])
        conn.commit()
        log_actividad(
            session['user_id'], 'ELIMINAR_ENTRADA',
            f"ID: {eid} | Folio: {entrada['folio']} | Producto ID: {entrada['producto_id']} | Cantidad: {cantidad_piezas}",
        )
        flash(f"Entrada (folio {entrada['folio']}) eliminada y stock revertido.", 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    conn.close()
    return redirect(f"{url_for('entradas.index')}?{volver}" if volver else url_for('entradas.index'))


@entradas_bp.route('/editar/<int:eid>', methods=['GET', 'POST'])
@login_required
def editar(eid):
    """
    Completar datos de una entrada capturada solo con remisión (sin factura todavía).
    Aquí se puede agregar factura, OC, requisición, proveedor, departamento y corregir
    la fecha para que la entrada aparezca en el reporte diario del día correcto.
    """
    conn = get_db()
    entrada = conn.execute("""
        SELECT e.*, COALESCE(p.codigo, 'SERVICIO') as codigo,
               COALESCE(p.descripcion, e.concepto_servicio) as descripcion,
               COALESCE(p.unidad_compra, p.unidad_medida, 'SERVICIO') as unidad_medida,
               COALESCE(e.ubicacion, p.ubicacion) as ubicacion_actual,
               COALESCE(pr.nombre, e.proveedor_nombre_historico) as proveedor_nombre
        FROM entradas e
        LEFT JOIN productos p ON e.producto_id=p.id
        LEFT JOIN proveedores pr ON e.proveedor_id=pr.id
        WHERE e.id=?
    """, (eid,)).fetchone()
    if not entrada:
        flash('Registro no encontrado.', 'danger')
        conn.close()
        return redirect(url_for('entradas.index'))
    departamentos = _areas_activas(conn)

    entrada = dict(entrada)
    entrada['ubicacion'] = entrada.get('ubicacion_actual') or entrada.get('ubicacion')
    entrada['moneda'] = (entrada.get('moneda') or 'MXN').strip().upper()
    if entrada.get('aplica_iva') is None:
        entrada['aplica_iva'] = int(not _es_dolar(entrada['moneda']))

    volver = request.values.get('volver', '')

    if request.method == 'POST':
        f = request.form
        try:
            es_servicio = bool(entrada['es_servicio'])

            if es_servicio:
                # ---- Editar un servicio/cargo (sin producto, sin stock) ----
                concepto = (f.get('concepto_servicio') or '').strip()
                cantidad_raw = f.get('cantidad')
                precio_raw = f.get('precio_unitario') or 0
                if not concepto or not cantidad_raw:
                    flash('Escribe una descripción del servicio y la cantidad.', 'danger')
                    conn.close()
                    return render_template('entradas/editar.html', entrada=entrada, departamentos=departamentos, volver=volver)

                cantidad = float(cantidad_raw)
                precio = float(precio_raw)
                importe = round(cantidad * precio, 4)
                pid = None
                cantidad_piezas_nueva = cantidad
            else:
                # ---- Editar una entrada normal (producto de inventario) ----
                pid = f.get('producto_id')
                cantidad_raw = f.get('cantidad')
                precio_raw = f.get('precio_unitario') or 0
                if not pid or not cantidad_raw:
                    flash('Selecciona un producto de la lista y captura la cantidad.', 'danger')
                    conn.close()
                    return render_template('entradas/editar.html', entrada=entrada, departamentos=departamentos, volver=volver)

                pid = int(pid)
                cantidad = float(cantidad_raw)
                precio = float(precio_raw)

                prod_nuevo = conn.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()
                if not prod_nuevo:
                    flash('El producto seleccionado no existe.', 'danger')
                    conn.close()
                    return render_template('entradas/editar.html', entrada=entrada, departamentos=departamentos, volver=volver)

                tiene_conversion = bool(prod_nuevo['unidad_compra'] and prod_nuevo['factor_conversion'])
                cantidad_piezas_nueva = round(cantidad / prod_nuevo['factor_conversion'], 4) if tiene_conversion else cantidad
                importe = round(cantidad * precio, 4)
                concepto = None

                # Revertir el efecto en stock del producto/cantidad ORIGINAL de esta entrada
                cantidad_piezas_original = entrada['cantidad_piezas'] if entrada['cantidad_piezas'] is not None else entrada['cantidad']
                conn.execute("UPDATE productos SET stock_actual = stock_actual - ? WHERE id=?",
                            (cantidad_piezas_original, entrada['producto_id']))

                # Aplicar el efecto en stock del producto/cantidad NUEVO
                conn.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE id=?",
                            (cantidad_piezas_nueva, pid))

            fecha_vale = f.get('fecha_vale') or entrada.get('fecha_vale') or entrada['fecha'][:10]
            proveedor_id = f.get('proveedor_id') or None
            ubicacion = (f.get('ubicacion') or '').strip() or None
            moneda = (f.get('moneda') or entrada.get('moneda') or 'MXN').strip().upper()
            if 'aplica_iva_present' in f:
                aplica_iva = int(f.get('aplica_iva') == 'on')
            else:
                aplica_iva = int(bool(entrada.get('aplica_iva')))
            if ubicacion and not es_servicio and pid:
                conn.execute("UPDATE productos SET ubicacion=? WHERE id=?", (ubicacion, pid))
            conn.execute("""
                UPDATE entradas SET
                    producto_id=?, concepto_servicio=?, cantidad=?, cantidad_piezas=?, precio_unitario=?, importe=?,
                    no_requisicion=?, no_factura=?, orden_compra=?, no_remision=?,
                    proveedor_id=?, departamento=?, ubicacion=?, uso=?, observaciones=?, fecha_vale=?, moneda=?, aplica_iva=?
                WHERE id=?
            """, (pid, concepto, cantidad, cantidad_piezas_nueva, precio, importe,
                  f.get('no_requisicion') or None, f.get('no_factura') or None,
                  f.get('orden_compra') or None, f.get('no_remision') or None,
                  proveedor_id, f.get('departamento') or None, ubicacion, f.get('uso') or None,
                  f.get('observaciones') or None,
                  fecha_vale, moneda, aplica_iva, eid))

            doc_requisicion_nueva = {
                'no_requisicion': f.get('no_requisicion') or None,
                'orden_compra': f.get('orden_compra') or None,
                'no_factura': f.get('no_factura') or None,
                'no_remision': f.get('no_remision') or None,
            }
            _recalcular_estado_requisicion_por_texto(conn, entrada.get('no_requisicion'))
            _vincular_con_requisicion(conn, doc_requisicion_nueva)
            _recalcular_estado_requisicion_por_texto(conn, doc_requisicion_nueva['no_requisicion'])
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_ENTRADA', f"ID: {eid} | Folio: {entrada['folio']}")
            flash('Entrada actualizada correctamente.', 'success')
            conn.close()
            if volver:
                return redirect(f"{url_for('entradas.index')}?{volver}")
            return redirect(url_for('entradas.detalle', eid=eid))
        except Exception as e:
            conn.rollback()
            flash(f'Error: {str(e)}', 'danger')

    conn.close()
    return render_template('entradas/editar.html', entrada=entrada, departamentos=departamentos, volver=volver)


@entradas_bp.route('/carga_inicial', methods=['GET', 'POST'])
@login_required
def carga_inicial():
    """
    Alta rápida de material que YA está físicamente en el almacén (para completar
    el catálogo/stock inicial), sin factura, proveedor, orden de compra ni precio.
    No afecta reportes de costos ni el reporte diario de entradas con factura.
    """
    conn = get_db()
    departamentos = _areas_activas(conn)
    if request.method == 'POST':
        f = request.form
        pid = f.get('producto_id')
        cantidad_raw = f.get('cantidad')
        if not pid or not cantidad_raw:
            flash('Selecciona un producto de la lista y captura la cantidad.', 'danger')
            conn.close()
            return render_template('entradas/carga_inicial.html',
                                   ahora=datetime.now().strftime('%Y-%m-%dT%H:%M'),
                                   departamentos=departamentos)
        pid = int(pid)
        cantidad = float(cantidad_raw)
        fecha_captura = f.get('fecha_captura') or datetime.now().strftime('%Y-%m-%dT%H:%M')
        fecha_sql = fecha_captura.replace('T', ' ') + (':00' if fecha_captura.count(':') == 1 else '')
        prod = conn.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()
        if not prod:
            flash('El producto seleccionado no existe.', 'danger')
        else:
            try:
                conn.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo = 'entrada'")
                num = conn.execute("SELECT ultimo FROM folios WHERE tipo = 'entrada'").fetchone()[0]
                folio = f"ENT-{str(num).zfill(6)}"
                # Cantidad se captura directo en la unidad de stock (piezas), sin conversión de kg.
                conn.execute("""
                    INSERT INTO entradas
                    (folio, producto_id, cantidad, cantidad_piezas, precio_unitario, importe,
                     tipo_movimiento, departamento, usuario_id, observaciones, fecha)
                    VALUES (?,?,?,?,0,0,'carga_inicial',?,?,?,?)
                """, (folio, pid, cantidad, cantidad, f.get('departamento') or None,
                      session['user_id'], f.get('observaciones'), fecha_sql))
                conn.execute("UPDATE productos SET stock_actual = stock_actual + ? WHERE id=?",
                            (cantidad, pid))
                conn.commit()
                log_actividad(session['user_id'], 'CARGA_INICIAL',
                              f"Folio: {folio} | {prod['codigo']} | Cantidad: {cantidad}")
                flash(f'Material existente registrado ({folio}). No afecta costos ni reportes con factura.', 'success')
                conn.close()
                return redirect(url_for('entradas.carga_inicial'))
            except Exception as e:
                conn.rollback()
                flash(f'Error: {str(e)}', 'danger')
    conn.close()
    return render_template('entradas/carga_inicial.html',
                           ahora=datetime.now().strftime('%Y-%m-%dT%H:%M'),
                           departamentos=departamentos)


@entradas_bp.route('/reporte_diario/folio', methods=['POST'])
@login_required
def editar_folio_diario():
    """Corrige a mano el folio del reporte diario de una fecha (ej. para hacerlo coincidir
    con el consecutivo real en papel cuando se empieza a usar el sistema)."""
    fecha = request.form.get('fecha') or date.today().isoformat()
    folio_nuevo = request.form.get('folio_nuevo')
    if not folio_nuevo or not folio_nuevo.isdigit():
        flash('El folio debe ser un número.', 'danger')
        return redirect(url_for('entradas.reporte_diario', fecha=fecha))
    set_folio_diario(fecha, int(folio_nuevo))
    log_actividad(session['user_id'], 'EDITAR_FOLIO_DIARIO', f"Fecha: {fecha} | Folio: {folio_nuevo}")
    flash(f'Folio del reporte de {fecha} actualizado a {folio_nuevo}.', 'success')
    return redirect(url_for('entradas.reporte_diario', fecha=fecha))


@entradas_bp.route('/reporte_diario')
@login_required
def reporte_diario():
    fecha = request.args.get('fecha') or date.today().isoformat()
    pagina = request.args.get('pagina', 1, type=int)
    modo_impresion = request.args.get('imprimir') == '1'
    registros_por_pagina = 50
    
    conn = get_db()
    filas = conn.execute("""
        SELECT e.*, COALESCE(p.codigo, 'SERVICIO') as codigo,
               COALESCE(p.descripcion, e.concepto_servicio) as descripcion,
               COALESCE(p.unidad_compra, p.unidad_medida, 'SERVICIO') as unidad_medida,
               p.departamento as depto_producto,
               COALESCE(pr.nombre, e.proveedor_nombre_historico) as proveedor_nombre
        FROM entradas e
        LEFT JOIN productos p ON e.producto_id=p.id
        LEFT JOIN proveedores pr ON e.proveedor_id=pr.id
        WHERE DATE(COALESCE(e.fecha_vale, e.fecha)) = ?
          AND e.no_factura IS NOT NULL AND TRIM(e.no_factura) != ''
        ORDER BY
          UPPER(TRIM(COALESCE(e.no_factura, ''))),
          UPPER(TRIM(COALESCE(e.orden_compra, ''))),
          e.id
    """, (fecha,)).fetchall()

    total_importe = 0
    total_iva = 0
    total_general = 0
    total_importe_usd = 0
    total_importe_mxn = 0
    total_iva_usd = 0
    total_iva_mxn = 0
    total_general_usd = 0
    total_general_mxn = 0
    resumen_completo = []
    
    for e in filas:
        importe = _subtotal_real(e)
        iva = _iva_de(importe, e['moneda'], e['aplica_iva'])
        total = round(importe + iva, 2)
        total_importe += importe
        total_iva += iva
        total_general += total
        if _es_dolar(e['moneda']):
            total_importe_usd += importe
            total_iva_usd += iva
            total_general_usd += total
        else:
            total_importe_mxn += importe
            total_iva_mxn += iva
            total_general_mxn += total
        resumen_completo.append({
            'descripcion': e['descripcion'],
            'es_servicio': bool(e['es_servicio']),
            'cantidad': e['cantidad'],
            'unidad_medida': _normalizar_unidad(e['unidad_medida']),
            'precio_unitario': e['precio_unitario'] or 0,
            'subtotal': importe,
            'iva': iva,
            'importe_total': total,
            'orden_compra': e['orden_compra'] or '—',
            'oc_pdf_url': _oc_pdf_url(e['orden_compra']),
            'no_factura': e['no_factura'] or '—',
            'proveedor_nombre': e['proveedor_nombre'] or '—',
            'departamento': e['departamento'] or e['depto_producto'] or '—',
            'es_dolar': _es_dolar(e['moneda']),
        })

    total_registros = len(resumen_completo)
    total_paginas = (total_registros + registros_por_pagina - 1) // registros_por_pagina
    
    if pagina < 1:
        pagina = 1
    elif pagina > total_paginas and total_paginas > 0:
        pagina = total_paginas
    
    if modo_impresion:
        pagina = 1
        total_paginas = 1
        resumen = resumen_completo
        es_ultima_pagina = True
    else:
        offset = (pagina - 1) * registros_por_pagina
        resumen = resumen_completo[offset:offset + registros_por_pagina]
        es_ultima_pagina = pagina == total_paginas

    folio = get_folio_diario(fecha)
    conn.close()

    fecha_dt = datetime.strptime(fecha, '%Y-%m-%d')
    meses_largo = ['', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
                   'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    dias_largo = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
    fecha_larga = f"{dias_largo[fecha_dt.weekday()]} {fecha_dt.day} de {meses_largo[fecha_dt.month]} de {fecha_dt.year}"

    return render_template('entradas/reporte_diario.html',
                           filas=resumen,
                           fecha=fecha,
                           fecha_larga=fecha_larga,
                           folio=folio,
                           total_importe=round(total_importe, 2),
                           total_iva=round(total_iva, 2),
                           total_general=round(total_general, 2),
                           total_importe_usd=round(total_importe_usd, 2),
                           total_importe_mxn=round(total_importe_mxn, 2),
                           total_iva_usd=round(total_iva_usd, 2),
                           total_iva_mxn=round(total_iva_mxn, 2),
                           total_general_usd=round(total_general_usd, 2),
                           total_general_mxn=round(total_general_mxn, 2),
                           pagina_actual=pagina,
                           total_paginas=total_paginas,
                           total_registros=total_registros,
                           registros_pagina=len(resumen),
                           es_ultima_pagina=es_ultima_pagina,
                           modo_impresion=modo_impresion)
