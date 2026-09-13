import base64
import os
import subprocess
import tempfile
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from database import get_db, log_actividad
from routes.auth import login_required
from routes.entradas import TSC_PRINTER_NAME, _lineas_tsc, _texto_tsc


etiquetas_produccion_bp = Blueprint(
    'etiquetas_produccion', __name__, url_prefix='/etiquetas-produccion'
)


PICTOGRAMAS = {
    'ghs01': 'GHS01 - Explosivo',
    'ghs02': 'GHS02 - Inflamable',
    'ghs03': 'GHS03 - Oxidante',
    'ghs04': 'GHS04 - Gas presurizado',
    'ghs05': 'GHS05 - Corrosivo',
    'ghs06': 'GHS06 - Tóxico',
    'ghs07': 'GHS07 - Tóxico / irritante',
    'ghs08': 'GHS08 - Peligroso para la salud',
    'ghs09': 'GHS09 - Medio ambiente',
}

PICTOGRAMA_SIGLAS = {
    'ghs01': '✹',
    'ghs02': '♨',
    'ghs03': '◉',
    'ghs04': '▰',
    'ghs05': '⌁',
    'ghs06': '☠',
    'ghs07': '!',
    'ghs08': '♟',
    'ghs09': '♣',
}

PICTOGRAMA_TEXTO_CORTO = {
    'ghs01': ('GHS01', 'EXPLOSIVO'),
    'ghs02': ('GHS02', 'INFLAMABLE'),
    'ghs03': ('GHS03', 'OXIDANTE'),
    'ghs04': ('GHS04', 'GAS', 'PRESURIZADO'),
    'ghs05': ('GHS05', 'CORROSIVO'),
    'ghs06': ('GHS06', 'TOXICO'),
    'ghs07': ('GHS07', 'TOXICO', 'IRRITANTE'),
    'ghs08': ('GHS08', 'PELIGROSO', 'SALUD'),
    'ghs09': ('GHS09', 'MEDIO', 'AMBIENTE'),
}

PICTOGRAMA_ALIASES = {
    'salud': 'ghs08',
    'inflamable': 'ghs02',
    'reactividad': 'ghs03',
    'especial': 'ghs05',
    'advertencia': 'ghs07',
}


def _normalizar_pictogramas(valores):
    seleccionados = []
    for valor in valores:
        for parte in str(valor or '').split(','):
            clave = PICTOGRAMA_ALIASES.get(parte.strip(), parte.strip())
            if clave in PICTOGRAMAS and clave not in seleccionados:
                seleccionados.append(clave)
            if len(seleccionados) == 4:
                break
        if len(seleccionados) == 4:
            break
    return ','.join(seleccionados) if seleccionados else 'ninguno'


def _lista_pictogramas(valor):
    pictos = []
    for parte in str(valor or '').split(','):
        clave = PICTOGRAMA_ALIASES.get(parte.strip(), parte.strip())
        if clave in PICTOGRAMAS and clave not in pictos:
            pictos.append(clave)
    return pictos[:4]


def _texto_pictogramas(valor):
    pictos = _lista_pictogramas(valor)
    if not pictos:
        return 'Sin pictograma'
    return ', '.join(PICTOGRAMAS[p] for p in pictos)


def _cantidad_lineas_necesarias(texto, ancho):
    palabras = _texto_tsc(texto).split()
    if not palabras:
        return 1
    total = 0
    actual = ''
    for palabra in palabras:
        candidato = f"{actual} {palabra}".strip()
        if len(candidato) <= ancho:
            actual = candidato
        else:
            if actual:
                total += 1
            actual = palabra[:ancho]
    if actual:
        total += 1
    return total


def _crear_ejemplos_si_vacio(conn):
    total = conn.execute("SELECT COUNT(*) FROM etiquetas_produccion").fetchone()[0]
    if total:
        return
    conn.executemany(
        """
        INSERT INTO etiquetas_produccion (producto, uso, pictograma, observaciones)
        VALUES (?, ?, 'advertencia', ?)
        """,
        [
            ('TRESYPLUS FRIO', 'DESENGRASANTE GENERAL', 'Ejemplo tomado del formato de producción.'),
            ('LANDYS', 'LIMPIADOR DESINFECTANTE', 'Ejemplo tomado del formato de producción.'),
        ],
    )
    conn.commit()


def _ids_desde_request(req):
    ids = []
    for valor in req.form.getlist('ids') + req.args.getlist('ids'):
        for parte in str(valor or '').split(','):
            parte = parte.strip()
            if parte.isdigit():
                ids.append(int(parte))
    return list(dict.fromkeys(ids))


def _obtener_etiquetas(conn, ids=None, incluir_inactivas=False):
    params = []
    where = []
    if ids:
        marcas = ','.join('?' for _ in ids)
        where.append(f'id IN ({marcas})')
        params.extend(ids)
    if not incluir_inactivas:
        where.append('activo=1')
    sql = "SELECT * FROM etiquetas_produccion"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY producto COLLATE NOCASE"
    filas = conn.execute(sql, params).fetchall()
    if not ids:
        return filas
    orden = {item_id: i for i, item_id in enumerate(ids)}
    return sorted(filas, key=lambda row: orden.get(row['id'], 999999))


@etiquetas_produccion_bp.route('/')
@login_required
def index():
    q = (request.args.get('q') or '').strip()
    estado = request.args.get('estado', 'activos')
    conn = get_db()
    _crear_ejemplos_si_vacio(conn)
    params = []
    where = []
    if estado == 'inactivos':
        where.append('activo=0')
    elif estado != 'todos':
        where.append('activo=1')
    if q:
        where.append('(producto LIKE ? OR uso LIKE ?)')
        params.extend([f'%{q}%', f'%{q}%'])
    sql = "SELECT * FROM etiquetas_produccion"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY producto COLLATE NOCASE"
    etiquetas = conn.execute(sql, params).fetchall()
    stats = {
        'activas': conn.execute("SELECT COUNT(*) FROM etiquetas_produccion WHERE activo=1").fetchone()[0],
        'inactivas': conn.execute("SELECT COUNT(*) FROM etiquetas_produccion WHERE activo=0").fetchone()[0],
    }
    conn.close()
    return render_template(
        'etiquetas_produccion/index.html',
        etiquetas=etiquetas,
        stats=stats,
        q=q,
        estado=estado,
        pictogramas=PICTOGRAMAS,
        texto_pictogramas=_texto_pictogramas,
    )


@etiquetas_produccion_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        producto = (request.form.get('producto') or '').strip().upper()
        uso = (request.form.get('uso') or '').strip().upper()
        pictograma = _normalizar_pictogramas(request.form.getlist('pictogramas'))
        observaciones = (request.form.get('observaciones') or '').strip()
        if not producto or not uso:
            flash('Producto y uso son obligatorios.', 'danger')
        else:
            conn = get_db()
            conn.execute(
                """
                INSERT INTO etiquetas_produccion (producto, uso, pictograma, activo, observaciones)
                VALUES (?, ?, ?, 1, ?)
                """,
                (producto, uso, pictograma, observaciones),
            )
            conn.commit()
            log_actividad(session.get('user_id'), 'NUEVA_ETIQUETA_PRODUCCION', producto)
            conn.close()
            flash('Etiqueta de producción guardada.', 'success')
            return redirect(url_for('etiquetas_produccion.index'))
    return render_template(
        'etiquetas_produccion/form.html',
        etiqueta=None,
        pictogramas=PICTOGRAMAS,
        lista_pictogramas=_lista_pictogramas,
    )


@etiquetas_produccion_bp.route('/editar/<int:item_id>', methods=['GET', 'POST'])
@login_required
def editar(item_id):
    conn = get_db()
    etiqueta = conn.execute("SELECT * FROM etiquetas_produccion WHERE id=?", (item_id,)).fetchone()
    if not etiqueta:
        conn.close()
        flash('Etiqueta no encontrada.', 'warning')
        return redirect(url_for('etiquetas_produccion.index'))

    if request.method == 'POST':
        producto = (request.form.get('producto') or '').strip().upper()
        uso = (request.form.get('uso') or '').strip().upper()
        pictograma = _normalizar_pictogramas(request.form.getlist('pictogramas'))
        observaciones = (request.form.get('observaciones') or '').strip()
        activo = 1 if request.form.get('activo') == '1' else 0
        if not producto or not uso:
            flash('Producto y uso son obligatorios.', 'danger')
        else:
            conn.execute(
                """
                UPDATE etiquetas_produccion
                SET producto=?, uso=?, pictograma=?, activo=?, observaciones=?, fecha_actualizacion=?
                WHERE id=?
                """,
                (producto, uso, pictograma, activo, observaciones, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), item_id),
            )
            conn.commit()
            log_actividad(session.get('user_id'), 'EDITAR_ETIQUETA_PRODUCCION', producto)
            conn.close()
            flash('Etiqueta de producción actualizada.', 'success')
            return redirect(url_for('etiquetas_produccion.index'))

    conn.close()
    return render_template(
        'etiquetas_produccion/form.html',
        etiqueta=etiqueta,
        pictogramas=PICTOGRAMAS,
        lista_pictogramas=_lista_pictogramas,
    )


@etiquetas_produccion_bp.route('/desactivar/<int:item_id>', methods=['POST'])
@login_required
def desactivar(item_id):
    conn = get_db()
    conn.execute(
        "UPDATE etiquetas_produccion SET activo=0, fecha_actualizacion=? WHERE id=?",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), item_id),
    )
    conn.commit()
    conn.close()
    flash('Etiqueta desactivada. No se borró el historial.', 'success')
    return redirect(url_for('etiquetas_produccion.index'))


@etiquetas_produccion_bp.route('/vista')
@login_required
def vista():
    ids = _ids_desde_request(request)
    conn = get_db()
    etiquetas = _obtener_etiquetas(conn, ids or None)
    conn.close()
    return render_template(
        'etiquetas_produccion/vista.html',
        etiquetas=etiquetas,
        ids=','.join(str(e['id']) for e in etiquetas),
        printer_name=TSC_PRINTER_NAME,
        pictogramas=PICTOGRAMAS,
        pictograma_siglas=PICTOGRAMA_SIGLAS,
        pictograma_texto_corto=PICTOGRAMA_TEXTO_CORTO,
        lista_pictogramas=_lista_pictogramas,
    )


@etiquetas_produccion_bp.route('/imprimir-tsc', methods=['POST'])
@login_required
def imprimir_tsc():
    ids = _ids_desde_request(request)
    if not ids:
        flash('Selecciona al menos una etiqueta para imprimir.', 'warning')
        return redirect(url_for('etiquetas_produccion.index'))
    copias = request.form.get('copias', '1')
    try:
        copias = max(1, min(50, int(copias)))
    except ValueError:
        copias = 1
    conn = get_db()
    etiquetas = _obtener_etiquetas(conn, ids)
    conn.close()
    if not etiquetas:
        flash('No se encontraron etiquetas activas para imprimir.', 'warning')
        return redirect(url_for('etiquetas_produccion.index'))
    try:
        _imprimir_tsc_produccion(etiquetas, copias=copias)
        flash(f'{len(etiquetas)} etiqueta(s) enviadas a {TSC_PRINTER_NAME}.', 'success')
    except Exception as exc:
        flash(f'No se pudo imprimir en {TSC_PRINTER_NAME}: {exc}', 'danger')
    return redirect(url_for('etiquetas_produccion.index'))


def _tspl_etiqueta_produccion(item, copias=1):
    producto = _texto_tsc(item['producto'])
    uso = _texto_tsc(item['uso'])
    pictos = _lista_pictogramas(item['pictograma'])
    partes = []

    def cmd(valor):
        partes.append((valor + '\r\n').encode('ascii', errors='ignore'))

    for comando in [
        'SIZE 101 mm,76 mm',
        'GAP 3 mm,0 mm',
        'DENSITY 8',
        'SPEED 4',
        'DIRECTION 1',
        'REFERENCE 0,0',
        'CLS',
    ]:
        cmd(comando)

    def text(x, y, font, rot, xm, ym, value):
        cmd(f'TEXT {x},{y},"{font}",{rot},{xm},{ym},"{_texto_tsc(value)}"')

    def texto_adaptable(valor, opciones):
        for ancho, max_lineas, font, xm, ym, paso_y in opciones:
            if _cantidad_lineas_necesarias(valor, ancho) <= max_lineas:
                return _lineas_tsc(valor, ancho, max_lineas), font, xm, ym, paso_y
        ancho, max_lineas, font, xm, ym, paso_y = opciones[-1]
        return _lineas_tsc(valor, ancho, max_lineas), font, xm, ym, paso_y

    producto_opts = [
        (10, 1, '5', 2, 2, 78),
        (16, 1, '5', 1, 2, 64),
        (24, 1, '4', 1, 2, 50),
        (34, 1, '3', 1, 2, 42),
    ]
    uso_opts = [
        (16, 1, '5', 1, 2, 64),
        (24, 1, '4', 1, 2, 50),
        (34, 1, '3', 1, 2, 42),
        (44, 1, '2', 1, 2, 34),
    ]

    x_texto = 100

    text(x_texto, 7, '3', 0, 1, 1, 'PRODUCTO:')
    y_producto = 50
    producto_lineas, producto_font, producto_xm, producto_ym, producto_paso = texto_adaptable(producto, producto_opts)
    for linea in producto_lineas:
        text(x_texto, y_producto, producto_font, 0, producto_xm, producto_ym, linea)
        y_producto += producto_paso

    text(x_texto, 197, '3', 0, 1, 1, 'USO:')
    y_uso = 240
    uso_lineas, uso_font, uso_xm, uso_ym, uso_paso = texto_adaptable(uso, uso_opts)
    for linea in uso_lineas:
        text(x_texto, y_uso, uso_font, 0, uso_xm, uso_ym, linea)
        y_uso += uso_paso

    posiciones = {
        1: [(405, 464)],
        2: [(315, 464), (535, 464)],
        3: [(230, 464), (445, 464), (660, 464)],
        4: [(155, 464), (345, 464), (535, 464), (725, 464)],
    }

    def rombo(cx, cy, clave):
        partes.append(_tspl_bitmap_pictograma(cx, cy - 48, clave, size=156, grosor=5))
        textos = PICTOGRAMA_TEXTO_CORTO.get(clave, (clave.upper(),))
        y_texto = cy + 66
        for linea in textos[:3]:
            texto_limpio = _texto_tsc(linea)[:12]
            x_linea = cx - max(24, len(texto_limpio) * 4)
            text(x_linea, y_texto, '1', 0, 1, 1, texto_limpio)
            y_texto += 17

    for clave, (cx, cy) in zip(pictos, posiciones.get(len(pictos), [])):
        rombo(cx, cy, clave)

    cmd(f'PRINT 1,{copias}')
    return b''.join(partes)


def _tspl_bitmap_pictograma(cx, cy, clave, size=66, grosor=3):
    """Dibuja un pictograma GHS simplificado como bitmap monocromático."""
    width = int(size)
    height = int(size)
    radio = (size - 1) / 2
    centro = radio
    bytes_por_fila = (width + 7) // 8
    matriz = [[False for _ in range(width)] for _ in range(height)]

    def punto(x, y):
        ix = int(round(x))
        iy = int(round(y))
        if 0 <= ix < width and 0 <= iy < height:
            matriz[iy][ix] = True

    def linea(x1, y1, x2, y2, t=1):
        pasos = max(abs(x2 - x1), abs(y2 - y1), 1)
        for i in range(int(pasos) + 1):
            x = x1 + (x2 - x1) * i / pasos
            y = y1 + (y2 - y1) * i / pasos
            for dx in range(-t, t + 1):
                for dy in range(-t, t + 1):
                    if dx * dx + dy * dy <= t * t:
                        punto(x + dx, y + dy)

    def rect(x1, y1, x2, y2):
        for y in range(int(y1), int(y2) + 1):
            for x in range(int(x1), int(x2) + 1):
                punto(x, y)

    def circulo(cx0, cy0, r, fill=False, t=1):
        for y in range(int(cy0 - r - t), int(cy0 + r + t) + 1):
            for x in range(int(cx0 - r - t), int(cx0 + r + t) + 1):
                d = ((x - cx0) ** 2 + (y - cy0) ** 2) ** 0.5
                if (fill and d <= r) or (not fill and abs(d - r) <= t):
                    punto(x, y)

    def poligono(puntos, t=1):
        for a, b in zip(puntos, puntos[1:] + puntos[:1]):
            linea(a[0], a[1], b[0], b[1], t)

    def texto_simple_exclamacion():
        rect(centro - 5, centro - 24, centro + 5, centro + 10)
        circulo(centro, centro + 27, 5, fill=True)

    # Rombo exterior.
    for y in range(height):
        for x in range(width):
            distancia_manhattan = abs(x - centro) + abs(y - centro)
            if abs(distancia_manhattan - radio) <= grosor:
                matriz[y][x] = True

    if clave == 'ghs07':
        texto_simple_exclamacion()
    elif clave == 'ghs09':
        # Árbol seco + pez, simplificado para TSC.
        linea(centro - 18, centro + 26, centro + 26, centro + 26, 2)
        linea(centro - 2, centro + 25, centro - 2, centro - 10, 2)
        linea(centro - 2, centro - 4, centro - 22, centro - 20, 2)
        linea(centro - 2, centro + 3, centro + 18, centro - 14, 2)
        linea(centro - 2, centro + 10, centro - 24, centro + 2, 2)
        circulo(centro + 20, centro + 10, 7, False, 2)
        linea(centro + 27, centro + 10, centro + 40, centro + 2, 2)
        linea(centro + 27, centro + 10, centro + 40, centro + 18, 2)
    elif clave == 'ghs02':
        poligono([
            (centro, centro - 35), (centro + 16, centro - 10),
            (centro + 7, centro - 2), (centro + 20, centro + 25),
            (centro, centro + 34), (centro - 18, centro + 22),
            (centro - 10, centro), (centro - 22, centro - 8),
        ], 3)
        circulo(centro, centro + 18, 12, False, 3)
    elif clave == 'ghs03':
        circulo(centro, centro + 15, 16, False, 3)
        for ang in range(-70, 80, 30):
            x1 = centro + 10 * __import__('math').sin(__import__('math').radians(ang))
            y1 = centro - 8 - 10 * __import__('math').cos(__import__('math').radians(ang))
            x2 = centro + 25 * __import__('math').sin(__import__('math').radians(ang))
            y2 = centro - 8 - 28 * __import__('math').cos(__import__('math').radians(ang))
            linea(x1, y1, x2, y2, 2)
    elif clave == 'ghs04':
        rect(centro - 25, centro - 9, centro + 25, centro + 9)
        circulo(centro - 25, centro, 9, False, 2)
        circulo(centro + 25, centro, 9, False, 2)
    elif clave == 'ghs05':
        linea(centro - 35, centro + 28, centro + 35, centro + 28, 2)
        linea(centro - 25, centro - 12, centro - 5, centro - 4, 3)
        linea(centro + 8, centro - 16, centro + 28, centro - 8, 3)
        linea(centro - 18, centro, centro - 30, centro + 18, 2)
        linea(centro + 20, centro - 3, centro + 8, centro + 18, 2)
        rect(centro - 34, centro + 21, centro - 15, centro + 25)
    elif clave == 'ghs06':
        circulo(centro, centro - 10, 16, False, 3)
        linea(centro - 24, centro + 15, centro + 24, centro + 43, 3)
        linea(centro + 24, centro + 15, centro - 24, centro + 43, 3)
        circulo(centro - 6, centro - 12, 2, fill=True)
        circulo(centro + 6, centro - 12, 2, fill=True)
    elif clave == 'ghs08':
        circulo(centro, centro - 24, 11, fill=True)
        poligono([(centro - 22, centro + 35), (centro, centro - 5), (centro + 22, centro + 35)], 3)
        linea(centro - 11, centro + 5, centro + 11, centro + 25, 2)
        linea(centro + 11, centro + 5, centro - 11, centro + 25, 2)
    elif clave == 'ghs01':
        for ang in range(0, 360, 45):
            import math
            linea(
                centro, centro,
                centro + 34 * math.cos(math.radians(ang)),
                centro + 34 * math.sin(math.radians(ang)),
                2,
            )
        circulo(centro, centro, 8, fill=True)
    else:
        texto_simple_exclamacion()

    datos = bytearray()

    for y in range(height):
        fila = [0xFF] * bytes_por_fila
        for x in range(width):
            if matriz[y][x]:
                fila[x // 8] &= ~(1 << (7 - (x % 8)))
        datos.extend(fila)

    x0 = int(cx - width / 2)
    y0 = int(cy - height / 2)
    encabezado = f'BITMAP {x0},{y0},{bytes_por_fila},{height},0,'.encode('ascii')
    return encabezado + bytes(datos) + b'\r\n'


def _imprimir_tsc_produccion(etiquetas, copias=1):
    data = b''.join(_tspl_etiqueta_produccion(item, copias=copias) for item in etiquetas)
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
  $doc.pDocName = "ERP Etiquetas Produccion"
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
            tmp.write(data)
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
