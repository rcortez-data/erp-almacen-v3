import calendar
import csv
import io
import base64
import os
import subprocess
import tempfile
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, Response, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from routes.auth import login_required, rol_required
from database import get_db, log_actividad
from routes.inventario import construir_busqueda_dinamica
from routes.entradas import TSC_PRINTER_NAME, _texto_tsc, _lineas_tsc

balance_bp = Blueprint('balance', __name__, url_prefix='/balance')

SEL_KEY = 'balance_ids'          # productos seleccionados para el balance mensual
TITLE_KEY = 'balance_tipo_reporte'
BALANCE_LOGO_TSC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'static', 'img', 'grupo-tensa-logo-tsc-420x164.bin')
BALANCE_LOGO_TSC_WIDTH_DOTS = 420
BALANCE_LOGO_TSC_HEIGHT_DOTS = 163
BALANCE_LOGO_TSC_BYTES_PER_ROW = 53

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


def _tipo_conversion(producto):
    try:
        tipo = producto['tipo_conversion']
    except (KeyError, IndexError):
        tipo = None
    return tipo if tipo in ('uso_a_compra', 'compra_a_uso') else 'uso_a_compra'


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
    En productos como PAPEL: unidad_compra=CAJA, unidad_medida=PIEZA,
    factor_conversion=12 significa 1 caja = 12 piezas.
    """
    factor = _factor_conversion(producto)
    if not factor:
        return None
    if _tipo_conversion(producto) == 'compra_a_uso':
        return _redondear_unidad_stock(float(valor_compra) * factor, producto)
    return _redondear_unidad_stock(float(valor_compra) / factor, producto)


def _a_unidad_compra(valor_stock, producto, redondear_pieza=True):
    factor = _factor_conversion(producto)
    if not factor or valor_stock is None:
        return None
    if _tipo_conversion(producto) == 'compra_a_uso':
        valor = float(valor_stock) / factor
    else:
        valor = float(valor_stock) * factor
    if redondear_pieza and _unidad_es_pieza(producto):
        return round(valor)
    return round(valor, 2)


def _cantidad_salida_stock(cantidad_db, producto):
    """Lee salidas.cantidad y la devuelve en unidad de inventario."""
    factor = _factor_conversion(producto)
    if not factor:
        return float(cantidad_db or 0)
    return _a_unidad_stock(float(cantidad_db or 0), producto)


def _cantidad_salida_db_desde_stock(cantidad_stock, producto):
    """Convierte unidad de inventario al valor que se guarda en salidas.cantidad."""
    factor = _factor_conversion(producto)
    if not factor:
        return float(cantidad_stock or 0)
    return _a_unidad_compra(float(cantidad_stock or 0), producto, redondear_pieza=False)


def _sumar_salidas_en_stock(conn, producto, fecha_inicio=None, fecha_fin=None):
    """Suma salidas en la unidad de inventario del producto.

    Las salidas nuevas guardan ``cantidad_stock`` como snapshot de la
    cantidad descontada del inventario. Las salidas históricas pueden no
    tener ese campo; para ellas se usa la conversión de ``cantidad`` como
    respaldo. Esto evita interpretar una salida histórica de 50 PIEZAS como
    50 KILOS cuando el producto tiene conversión.
    """
    where = ["producto_id=?"]
    params = [producto['id']]
    if fecha_inicio is not None:
        where.append("DATE(COALESCE(fecha_vale, fecha)) >= ?")
        params.append(fecha_inicio)
    if fecha_fin is not None:
        where.append("DATE(COALESCE(fecha_vale, fecha)) <= ?")
        params.append(fecha_fin)

    rows = conn.execute(
        f"SELECT cantidad, cantidad_stock, unidad_compra_movimiento, "
        f"factor_conversion_movimiento FROM salidas WHERE {' AND '.join(where)}",
        params,
    ).fetchall()
    total = 0.0
    for row in rows:
        if (row['cantidad_stock'] is not None and
                row['unidad_compra_movimiento'] and
                row['factor_conversion_movimiento']):
            total += float(row['cantidad_stock'] or 0)
        else:
            total += float(_cantidad_salida_stock(row['cantidad'], producto) or 0)
    return total


def _es_producto_caldera(conn, producto_id):
    row = conn.execute(
        "SELECT 1 FROM bloque_productos WHERE bloque_id=2 AND producto_id=? LIMIT 1",
        (producto_id,),
    ).fetchone()
    return bool(row)


def _sincronizar_salida_caldera_desde_balance(conn, producto, anio, mes, consumo_stock, usuario_id):
    """Crea/actualiza la salida automática de Caldera a partir del balance mensual.

    Solo se usa desde agosto 2026 en adelante para no tocar los meses históricos
    que ya se capturaron manualmente como base.
    """
    if (anio, mes) < (2026, 8) or not _es_producto_caldera(conn, producto['id']):
        return False

    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1]).isoformat()
    periodo = f'{anio}-{mes:02d}'
    no_vale = f'CONSUMO-CALDERA-{periodo}'
    consumo_stock = round(float(consumo_stock or 0), 4)
    if consumo_stock < 0:
        raise ValueError(f'El consumo de Caldera de {producto["codigo"]} no puede ser negativo.')

    existente = conn.execute("""
        SELECT id, cantidad
        FROM salidas
        WHERE producto_id=?
          AND tipo_movimiento='consumo_fisico'
          AND area='CALDERA'
          AND fecha_vale=?
    """, (producto['id'], ultimo_dia)).fetchone()
    cantidad_db = _cantidad_salida_db_desde_stock(consumo_stock, producto)

    if existente:
        consumo_anterior_stock = _cantidad_salida_stock(existente['cantidad'], producto)
        diferencia_stock = consumo_stock - consumo_anterior_stock
        conn.execute("""
            UPDATE salidas
            SET cantidad=?, usuario_id=?, observaciones=?, fecha=?
            WHERE id=?
        """, (
            cantidad_db, usuario_id,
            'Consumo fisico mensual actualizado desde Balance Mensual',
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'), existente['id'],
        ))
        if abs(diferencia_stock) > 0.0001:
            conn.execute(
                "UPDATE productos SET stock_actual=stock_actual-? WHERE id=?",
                (diferencia_stock, producto['id']),
            )
        return True

    if consumo_stock <= 0:
        return False

    conn.execute("INSERT OR IGNORE INTO folios (tipo, ultimo) VALUES ('salida', 0)")
    conn.execute("UPDATE folios SET ultimo=ultimo+1 WHERE tipo='salida'")
    numero = conn.execute("SELECT ultimo FROM folios WHERE tipo='salida'").fetchone()[0]
    folio = f'SAL-{str(numero).zfill(6)}'
    conn.execute("""
        INSERT INTO salidas
        (folio, producto_id, cantidad, responsable, area, no_vale, tipo_vale,
         tipo_movimiento, usuario_id, observaciones, fecha, fecha_vale)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        folio, producto['id'], cantidad_db, 'CONSUMO FISICO', 'CALDERA', no_vale,
        'caldera', 'consumo_fisico', usuario_id,
        'Consumo fisico mensual generado desde Balance Mensual',
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ultimo_dia,
    ))
    conn.execute("UPDATE productos SET stock_actual=stock_actual-? WHERE id=?", (consumo_stock, producto['id']))
    return True


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
    total = conn.execute("""
        SELECT COUNT(DISTINCT p.id)
        FROM productos p
        JOIN bloque_productos bp ON bp.producto_id=p.id
        WHERE p.activo=1 AND bp.bloque_id IN (1, 2)
    """).fetchone()[0]
    cerrados = conn.execute("""
        SELECT COUNT(DISTINCT cf.producto_id)
        FROM conteos_fisicos cf
        JOIN productos p ON p.id=cf.producto_id
        JOIN bloque_productos bp ON bp.producto_id=p.id
        WHERE p.activo=1
          AND bp.bloque_id IN (1, 2)
          AND cf.anio=?
          AND cf.mes=?
          AND cf.salidas_manual IS NOT NULL
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


def _agrupar_filas_reporte_balance(conn, filas, ids):
    """Agrupa filas como el reporte mensual impreso: Producción, Caldera y otros."""
    filas_por_id = {fila['producto_id']: fila for fila in filas}
    grupos_reporte = []
    ids_en_grupos = set()
    if ids:
        relaciones = conn.execute(
            """
            SELECT bp.producto_id, bp.bloque_id, COALESCE(bp.orden, 999999) AS orden
            FROM bloque_productos bp
            WHERE bp.producto_id IN ({}) AND bp.bloque_id IN (1, 2)
            ORDER BY bp.bloque_id, orden, bp.producto_id
            """.format(','.join('?' * len(ids))),
            ids,
        ).fetchall()
        nombres_bloque = {
            1: 'REPORTE MENSUAL DE PRODUCCIÓN',
            2: 'REPORTE MENSUAL DE CALDERA',
        }
        for bloque_id in (1, 2):
            filas_bloque = []
            for relacion in relaciones:
                if relacion['bloque_id'] == bloque_id and relacion['producto_id'] in filas_por_id:
                    filas_bloque.append(filas_por_id[relacion['producto_id']])
                    ids_en_grupos.add(relacion['producto_id'])
            if filas_bloque:
                grupos_reporte.append({
                    'titulo': nombres_bloque[bloque_id],
                    'subtitulo': 'INSUMOS DE PRODUCCIÓN' if bloque_id == 1 else 'INSUMOS DE CALDERA',
                    'clase': 'grupo-produccion' if bloque_id == 1 else 'grupo-caldera',
                    'filas': filas_bloque,
                })
        filas_otros = [fila for fila in filas if fila['producto_id'] not in ids_en_grupos]
        if filas_otros:
            grupos_reporte.append({
                'titulo': 'REPORTE MENSUAL DE INVENTARIO',
                'subtitulo': 'OTROS PRODUCTOS SELECCIONADOS',
                'clase': 'grupo-inventario',
                'filas': filas_otros,
            })
    return grupos_reporte


def _cantidad_etiqueta_balance(valor):
    if valor is None:
        return '0'
    valor = round(float(valor), 4)
    if abs(valor - round(valor)) < 0.0001:
        return f"{int(round(valor)):,}"
    return f"{valor:,.2f}".rstrip('0').rstrip('.')


def _unidad_etiqueta_balance(cantidad, unidad):
    """Devuelve la unidad en singular/plural para etiquetas de balance."""
    try:
        numero = abs(float(cantidad or 0))
    except (TypeError, ValueError):
        numero = 0
    texto = str(unidad or '').strip()
    base = texto.lower().replace('.', '')
    unidades = {
        'pieza': ('PIEZA', 'PIEZAS'), 'piezas': ('PIEZA', 'PIEZAS'),
        'pza': ('PIEZA', 'PIEZAS'), 'pzas': ('PIEZA', 'PIEZAS'),
        'kilo': ('KILO', 'KILOS'), 'kilos': ('KILO', 'KILOS'),
        'kg': ('KILO', 'KILOS'), 'kgs': ('KILO', 'KILOS'),
        'kilogramo': ('KILOGRAMO', 'KILOGRAMOS'), 'kilogramos': ('KILOGRAMO', 'KILOGRAMOS'),
        'litro': ('LITRO', 'LITROS'), 'litros': ('LITRO', 'LITROS'),
        'lt': ('LITRO', 'LITROS'), 'lts': ('LITRO', 'LITROS'),
        'l': ('LITRO', 'LITROS'),
        'metro': ('METRO', 'METROS'), 'metros': ('METRO', 'METROS'),
        'caja': ('CAJA', 'CAJAS'), 'cajas': ('CAJA', 'CAJAS'),
        'rollo': ('ROLLO', 'ROLLOS'), 'rollos': ('ROLLO', 'ROLLOS'),
        'juego': ('JUEGO', 'JUEGOS'), 'juegos': ('JUEGO', 'JUEGOS'),
        'unidad': ('UNIDAD', 'UNIDADES'), 'unidades': ('UNIDAD', 'UNIDADES'),
    }
    singular, plural = unidades.get(base, (texto.upper(), f"{texto.upper()}S" if texto and not texto.upper().endswith('S') else texto.upper()))
    return plural if numero > 1 else singular


def _cantidad_unidad_etiqueta_balance(cantidad, unidad):
    return f"{_cantidad_etiqueta_balance(cantidad)} {_unidad_etiqueta_balance(cantidad, unidad)}".strip()


def _ids_balance_desde_request(args):
    ids = []
    productos = args.get('productos', '')
    if productos:
        for raw in productos.split(','):
            try:
                ids.append(int(raw))
            except (TypeError, ValueError):
                continue
    for raw in args.getlist('ids'):
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        if pid not in ids:
            ids.append(pid)
    if not ids:
        ids = [int(pid) for pid in session.get(SEL_KEY, []) if str(pid).isdigit()]
    return ids


def _obtener_etiquetas_balance(args):
    hoy = date.today()
    anio = int(args.get('anio', hoy.year))
    mes = int(args.get('mes', hoy.month))
    ids = _ids_balance_desde_request(args)
    conn = get_db()
    etiquetas = []
    if ids:
        for producto in _productos_por_ids_en_orden(conn, ids):
            fila = _calcular_fila(conn, producto, anio, mes)
            etiquetas.append({
                'grupo': 'GRUPO TENSA',
                'codigo': fila['codigo'],
                'producto': fila['descripcion'],
                'cantidad': _cantidad_etiqueta_balance(fila['existencia_final']),
                'unidad': fila['unidad_medida'],
                'cantidad_texto': _cantidad_unidad_etiqueta_balance(fila['existencia_final'], fila['unidad_medida']),
                'cantidad_compra': _cantidad_etiqueta_balance(fila['existencia_final_compra'])
                    if fila['existencia_final_compra'] is not None else None,
                'unidad_compra': fila['unidad_compra'],
                'cantidad_compra_texto': _cantidad_unidad_etiqueta_balance(fila['existencia_final_compra'], fila['unidad_compra'])
                    if fila['existencia_final_compra'] is not None and fila['unidad_compra'] else None,
                'periodo': f"{MESES[mes]} {anio}",
            })
    conn.close()
    return etiquetas, anio, mes


def _tspl_etiqueta_balance(e):
    ancho_etiqueta = 812  # 101mm aprox. a 203 dpi
    salida = bytearray()

    def comando(valor):
        salida.extend((valor + '\r\n').encode('ascii', errors='ignore'))

    for linea in [
        'SIZE 101 mm,76 mm',
        'GAP 3 mm,0 mm',
        'DENSITY 8',
        'SPEED 4',
        'DIRECTION 1',
        'REFERENCE 0,0',
        'CLS',
    ]:
        comando(linea)

    def texto(x, y, valor, xmul=1, ymul=1, fuente="2"):
        comando(f'TEXT {x},{y},"{fuente}",0,{xmul},{ymul},"{_texto_tsc(valor)}"')

    def ancho_aprox(valor, fuente="2", xmul=1):
        base = {"1": 8, "2": 12, "3": 16, "4": 24}.get(str(fuente), 12)
        return len(_texto_tsc(valor)) * base * xmul

    def texto_centrado(y, valor, xmul=1, ymul=1, fuente="2"):
        ancho = ancho_aprox(valor, fuente, xmul)
        x = max(20, int((ancho_etiqueta - ancho) / 2))
        texto(x, y, valor, xmul, ymul, fuente)

    if os.path.exists(BALANCE_LOGO_TSC):
        x_logo = int((ancho_etiqueta - BALANCE_LOGO_TSC_WIDTH_DOTS) / 2)
        comando(f'BITMAP {x_logo},0,{BALANCE_LOGO_TSC_BYTES_PER_ROW},{BALANCE_LOGO_TSC_HEIGHT_DOTS},0,')
        with open(BALANCE_LOGO_TSC, 'rb') as logo:
            salida.extend(logo.read())
        salida.extend(b'\r\n')
    else:
        texto_centrado(18, e.get('grupo') or 'GRUPO TENSA', 2, 2, "4")
    comando('BAR 55,170,702,5')
    texto_centrado(195, 'PRODUCTO', 1, 1, "3")
    y = 230
    for linea in _lineas_tsc(e.get('producto') or '---', 21, 4):
        texto_centrado(y, linea, 2, 1, "3")
        y += 43
    texto_centrado(340, 'CANTIDAD', 1, 1, "3")
    comando('BAR 210,370,392,4')
    texto_centrado(400, e.get('cantidad_texto') or f"{e.get('cantidad')} {e.get('unidad')}", 2, 1, "3")
    if e.get('cantidad_compra_texto'):
        texto_centrado(450, e.get('cantidad_compra_texto'), 2, 1, "3")
        texto_centrado(500, e.get('periodo') or '', 1, 1, "3")
    else:
        texto_centrado(470, e.get('periodo') or '', 1, 1, "3")
    comando('PRINT 1,1')
    return bytes(salida)


def _imprimir_tsc_balance(etiquetas):
    data = b''.join(_tspl_etiqueta_balance(e) for e in etiquetas)
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
  $doc.pDocName = "ERP Etiquetas Balance"
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


def _calcular_fila(conn, producto, anio, mes):
    """Calcula inicio + entradas - salidas manuales = existencia final."""
    inicio_mes, fin_mes = _rango_mes(anio, mes)
    pid = producto['id']
    # Septiembre de 2026 es el primer periodo que contiene vales mixtos:
    # históricos capturados en piezas y nuevos capturados en kilos con
    # cantidad_stock. Los cierres anteriores se conservan como históricos.
    usar_snapshot_salidas = (anio, mes) >= (2026, 9)

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
    if conteo_ant:
        existencia_inicio = conteo_ant['existencia_fisica']
        inicio_es_estimado = False
    else:
        if referencia_caldera:
            factor = _factor_conversion(producto)
            entradas_anteriores = conn.execute(
                "SELECT COALESCE(SUM(COALESCE(cantidad_piezas, cantidad)),0) FROM entradas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) >= ? AND DATE(COALESCE(fecha_vale, fecha)) < ?",
                (pid, f'{anio}-01-01', inicio_mes)).fetchone()[0]
            if usar_snapshot_salidas:
                salidas_anteriores = _sumar_salidas_en_stock(
                    conn, producto, f'{anio}-01-01', inicio_mes)
            else:
                salidas_anteriores = conn.execute(
                    "SELECT COALESCE(SUM(cantidad),0) FROM salidas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) >= ? AND DATE(COALESCE(fecha_vale, fecha)) < ?",
                    (pid, f'{anio}-01-01', inicio_mes)).fetchone()[0]
                if factor:
                    salidas_anteriores = _a_unidad_stock(salidas_anteriores or 0, producto)
            existencia_inicio = float(referencia_caldera['cantidad'] or 0) + float(entradas_anteriores or 0) - float(salidas_anteriores or 0)
            inicio_es_estimado = False
        else:
        # Estimación: retrocede desde el stock actual usando movimientos registrados desde el inicio del mes.
        # Ojo: el stock siempre se mueve en piezas (unidad_medida), por eso usamos cantidad_piezas
        # (que es igual a "cantidad" para productos sin conversión de unidad).
            factor = _factor_conversion(producto)
            if factor:
                entradas_post_compra = conn.execute(
                    "SELECT COALESCE(SUM(cantidad),0) FROM entradas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) >= ?",
                    (pid, inicio_mes)).fetchone()[0]
                entradas_post = _a_unidad_stock(entradas_post_compra, producto)
            else:
                entradas_post = conn.execute(
                    "SELECT COALESCE(SUM(COALESCE(cantidad_piezas, cantidad)),0) FROM entradas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) >= ?",
                    (pid, inicio_mes)).fetchone()[0]
            if usar_snapshot_salidas:
                salidas_post = _sumar_salidas_en_stock(conn, producto, inicio_mes)
            else:
                salidas_post = conn.execute(
                    "SELECT COALESCE(SUM(cantidad),0) FROM salidas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) >= ?",
                    (pid, inicio_mes)).fetchone()[0]
                if factor:
                    salidas_post = _a_unidad_stock(salidas_post or 0, producto)
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
            entradas_mes = _a_unidad_stock(entradas_mes_compra, producto)

    # 3) Salidas registradas en el ERP, en unidad de inventario.
    factor = _factor_conversion(producto)
    if factor and usar_snapshot_salidas:
        salidas_registradas = _sumar_salidas_en_stock(
            conn, producto, inicio_mes, fin_mes)
        salidas_registradas_compra = _a_unidad_compra(
            salidas_registradas, producto, redondear_pieza=False)
    elif factor:
        salidas_registradas_compra = conn.execute(
            "SELECT COALESCE(SUM(cantidad),0) FROM salidas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) BETWEEN ? AND ?",
            (pid, inicio_mes, fin_mes)).fetchone()[0]
        salidas_registradas = _a_unidad_stock(salidas_registradas_compra or 0, producto)
    else:
        salidas_registradas = conn.execute(
            "SELECT COALESCE(SUM(cantidad),0) FROM salidas WHERE producto_id=? AND DATE(COALESCE(fecha_vale, fecha)) BETWEEN ? AND ?",
            (pid, inicio_mes, fin_mes)).fetchone()[0]
        salidas_registradas_compra = None

    # 4) Físico capturado de ESTE mes (si ya se guardó)
    conteo_actual = conn.execute(
        """SELECT existencia_fisica, salidas_manual, existencia_inicio, entradas_mes
           FROM conteos_fisicos WHERE producto_id=? AND anio=? AND mes=?""",
        (pid, anio, mes)).fetchone()
    inicio_guardado = bool(conteo_actual and conteo_actual['existencia_inicio'] is not None)
    if inicio_guardado:
        existencia_inicio = conteo_actual['existencia_inicio']
        inicio_es_estimado = False
    if conteo_actual and conteo_actual['entradas_mes'] is not None:
        entradas_mes = conteo_actual['entradas_mes']
        entradas_mes_compra = _a_unidad_compra(entradas_mes, producto, redondear_pieza=False)
    salidas_manual = conteo_actual['salidas_manual'] if conteo_actual else None
    if conteo_actual and conteo_actual['existencia_fisica'] is not None:
        # La salida mostrada siempre se deriva de los datos visibles del mes.
        # Esto corrige registros antiguos que conservaron una entrada o salida
        # previa aunque el usuario haya capturado nuevos valores.
        salidas_manual = existencia_inicio + entradas_mes - conteo_actual['existencia_fisica']
    # Productos.stock_actual es la existencia oficial; el cierre físico queda
    # solo como referencia histórica/auditable.
    existencia_esperada = existencia_inicio + entradas_mes - salidas_registradas
    # Si existe un conteo físico guardado, ese dato es el cierre fijo del mes.
    # La existencia esperada se conserva aparte para comparar diferencias.
    existencia_final = conteo_actual['existencia_fisica'] if conteo_actual else existencia_esperada
    diferencia_salidas = None
    if salidas_manual is not None:
        diferencia_salidas = round(salidas_manual - salidas_registradas, 2)
    salidas_reporte = salidas_manual if salidas_manual is not None else salidas_registradas

    return {
        'producto_id': pid, 'codigo': producto['codigo'], 'descripcion': producto['descripcion'],
        'unidad_medida': producto['unidad_medida'],
        'unidad_compra': producto['unidad_compra'], 'factor_conversion': producto['factor_conversion'],
        'tipo_conversion': _tipo_conversion(producto),
        'entradas_mes_compra': round(entradas_mes_compra, 2) if entradas_mes_compra is not None else None,
        'existencia_inicio_compra': _a_unidad_compra(existencia_inicio, producto),
        'existencia_inicio': round(existencia_inicio, 2), 'inicio_es_estimado': inicio_es_estimado,
        'inicio_guardado': inicio_guardado,
        'entradas_mes': round(entradas_mes, 2),
        'entradas_capturadas': conteo_actual['entradas_mes'] if conteo_actual else None,
        'salidas_registradas': round(salidas_registradas, 2),
        'salidas_registradas_compra': round(salidas_registradas_compra, 2) if salidas_registradas_compra is not None else None,
        'salidas_manual': salidas_manual, 'existencia_fisica': conteo_actual['existencia_fisica'] if conteo_actual else None,
        'salidas_reporte': round(salidas_reporte, 2) if salidas_reporte is not None else None,
        'salidas_reporte_compra': _a_unidad_compra(salidas_reporte, producto, redondear_pieza=False),
        'existencia_final': existencia_final,
        'existencia_esperada': round(existencia_esperada, 2),
        'diferencia_stock': round(float(existencia_final or 0) - float(existencia_esperada or 0), 2),
        'salidas_manual_compra': _a_unidad_compra(salidas_manual, producto),
        'existencia_final_compra': _a_unidad_compra(existencia_final, producto, redondear_pieza=False),
        'diferencia_salidas': diferencia_salidas,
    }


def _guardar_cierre_producto(conn, producto, anio, mes, inicio, salidas, usuario_id, entradas_mes=None):
    """Guarda un cierre mensual ya validado y devuelve su existencia final."""
    fila = _calcular_fila(conn, producto, anio, mes)
    entradas_para_guardar = fila['entradas_mes'] if entradas_mes is None else entradas_mes
    existencia_final = inicio + entradas_para_guardar - salidas
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
          inicio, entradas_para_guardar, usuario_id))
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
        f['salidas_manual_compra']
        for f in filas
        if f['salidas_manual_compra'] is not None
    )
    todos_capturados = bool(filas) and all(f['salidas_manual'] is not None for f in filas)
    periodo = _estado_periodo(conn, anio, mes)
    resumen_periodo = _resumen_periodo(conn, anio, mes)
    conteos_bloques = {
        row['bloque_id']: row['total']
        for row in conn.execute("""
            SELECT bp.bloque_id, COUNT(p.id) AS total
            FROM bloque_productos bp
            JOIN productos p ON p.id=bp.producto_id
            WHERE bp.bloque_id IN (1, 2) AND p.activo=1
            GROUP BY bp.bloque_id
        """).fetchall()
    }
    conn.close()
    return render_template('balance/index.html', filas=filas, anio=anio, mes=mes,
                           meses=MESES, total_consumo=total_consumo,
                           total_existencia_final=total_existencia_final,
                           total_consumo_compra=total_consumo_compra,
                           todos_capturados=todos_capturados,
                           tipo_reporte=session.get(TITLE_KEY, 'inventario'),
                           anio_actual=hoy.year, periodo=periodo,
                           resumen_periodo=resumen_periodo,
                           conteos_bloques=conteos_bloques)


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
        if _periodo_cerrado(conn, anio, mes):
            conn.close()
            flash('Este periodo esta cerrado. Un administrador debe reabrirlo antes de modificarlo.', 'danger')
            return redirect(url_for('balance.todos_productos', anio=anio, mes=mes, pagina=pagina, q=q))
        guardados = 0
        salidas_caldera = 0
        errores = []
        for pid_raw in request.form.getlist('producto_ids'):
            try:
                pid = int(pid_raw)
                producto = conn.execute('SELECT * FROM productos WHERE id=? AND activo=1', (pid,)).fetchone()
                if not producto:
                    continue
                inicio = _valor_manual_balance(request.form, producto, 'inicio')
                existencia_final = _valor_manual_balance(request.form, producto, 'final')
                if inicio is None or existencia_final is None:
                    continue
                if inicio < 0 or existencia_final < 0:
                    raise ValueError('Inicio, entradas y existencia final deben ser positivos.')
                entradas_capturadas = _valor_manual_balance(request.form, producto, 'entradas') if anio == 2026 and mes <= 7 else None
                if entradas_capturadas is not None and entradas_capturadas < 0:
                    raise ValueError('Inicio, entradas y existencia final deben ser positivos.')
                entradas_mes = entradas_capturadas if entradas_capturadas is not None else _calcular_fila(conn, producto, anio, mes)['entradas_mes']
                salidas = inicio + entradas_mes - existencia_final
                if salidas < 0:
                    raise ValueError(f'La existencia final de {producto["codigo"]} supera inicio + entradas.')
                _guardar_cierre_producto(conn, producto, anio, mes, inicio, salidas, session['user_id'], entradas_mes)
                if _sincronizar_salida_caldera_desde_balance(conn, producto, anio, mes, salidas, session['user_id']):
                    salidas_caldera += 1
                guardados += 1
            except (TypeError, ValueError) as error:
                errores.append(str(error))
        conn.commit()
        conn.close()
        if guardados:
            flash(f'Se guardaron {guardados} cierres de esta pagina.', 'success')
        if salidas_caldera:
            flash(f'Se generaron/actualizaron {salidas_caldera} salida(s) automáticas de Caldera desde Balance.', 'success')
        if errores:
            flash(errores[0], 'danger')
        return redirect(url_for('balance.todos_productos', anio=anio, mes=mes, pagina=pagina, q=q))

    ids_seleccionados = [int(pid) for pid in session.get(SEL_KEY, []) if str(pid).isdigit()]
    if ids_seleccionados:
        placeholders = ','.join('?' * len(ids_seleccionados))
        filtro = f"WHERE activo=1 AND id IN ({placeholders})"
        params = ids_seleccionados[:]
    else:
        filtro = "WHERE 1=0"
        params = []
    if q:
        filtro += " AND (codigo LIKE ? OR descripcion LIKE ?)"
        params.extend([f'%{q}%', f'%{q}%'])
    total = conn.execute(f'SELECT COUNT(*) FROM productos {filtro}', params).fetchone()[0]
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = min(pagina, total_paginas)
    orden_bloque = ''
    if ids_seleccionados:
        orden_bloque = ' ORDER BY CASE id ' + ' '.join(
            f'WHEN {pid} THEN {posicion}' for posicion, pid in enumerate(ids_seleccionados)
        ) + ' END'
    productos = conn.execute(
        f'SELECT * FROM productos {filtro}{orden_bloque} LIMIT ? OFFSET ?',
        (*params, por_pagina, (pagina - 1) * por_pagina),
    ).fetchall()
    filas = [_calcular_fila(conn, producto, anio, mes) for producto in productos]
    if ids_seleccionados:
        relaciones = conn.execute(
            'SELECT producto_id, bloque_id FROM bloque_productos WHERE producto_id IN (' +
            ','.join('?' * len(ids_seleccionados)) + ')', ids_seleccionados
        ).fetchall()
        bloques_por_producto = {}
        nombres_bloque = {1: 'Insumos de Producción', 2: 'Insumos de Caldera'}
        for relacion in relaciones:
            nombre = nombres_bloque.get(relacion['bloque_id'])
            if nombre:
                bloques_por_producto.setdefault(relacion['producto_id'], []).append(nombre)
        for fila in filas:
            nombres = bloques_por_producto.get(fila['producto_id'], [])
            fila['bloque_nombre'] = ' / '.join(nombres) if nombres else 'Otros seleccionados'
    hay_caldera_auto = bool(
        (anio, mes) >= (2026, 8)
        and any('Caldera' in (fila.get('bloque_nombre') or '') for fila in filas)
    )
    periodo = _estado_periodo(conn, anio, mes)
    resumen_periodo = _resumen_periodo(conn, anio, mes)
    conn.close()
    return render_template(
        'balance/todos.html', filas=filas, anio=anio, mes=mes, meses=MESES,
        anio_actual=hoy.year, pagina=pagina, total_paginas=total_paginas,
        total=total, q=q, periodo=periodo, resumen_periodo=resumen_periodo,
        hay_caldera_auto=hay_caldera_auto,
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


def _valor_excel_reporte(fila, campo_base, campo_compra=None):
    if campo_compra and fila['unidad_compra'] and fila['factor_conversion'] and fila.get(campo_compra) is not None:
        return fila.get(campo_compra)
    return fila.get(campo_base)


def _unidad_excel_reporte(fila):
    if fila['unidad_compra'] and fila['factor_conversion']:
        return str(fila['unidad_compra'] or '').upper()
    return str(fila['unidad_medida'] or '').upper()


def _conversion_excel_reporte(fila):
    if fila['unidad_compra'] and fila['factor_conversion']:
        if fila.get('tipo_conversion') == 'compra_a_uso':
            return f"1 {str(fila['unidad_compra'] or '').upper()} = {fila['factor_conversion']} {str(fila['unidad_medida'] or '').upper()}"
        return f"1 {str(fila['unidad_medida'] or '').upper()} = {fila['factor_conversion']} {str(fila['unidad_compra'] or '').upper()}"
    return '—'


def _nombre_hoja_excel(titulo):
    texto = (titulo or 'Balance').replace('REPORTE MENSUAL DE ', '').replace('/', '-').strip()
    texto = ''.join(ch for ch in texto if ch not in r'[]:*?/\\')
    return (texto or 'Balance')[:31]


def _agregar_hoja_balance_excel(wb, titulo, subtitulo, filas, anio, mes, index=0):
    ws = wb.active if index == 0 else wb.create_sheet()
    ws.title = _nombre_hoja_excel(titulo)
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.page_margins.top = 0.35
    ws.page_margins.bottom = 0.35

    borde_negro = Side(style='medium', color='000000')
    borde_gris = Side(style='thin', color='8DA1B5')
    fill_header = PatternFill('solid', fgColor='FFFFFF')
    fill_sub = PatternFill('solid', fgColor='F8FAFC')

    ws.merge_cells('A1:G1')
    ws['A1'] = titulo
    ws['A1'].font = Font(size=18, bold=True, color='123B68')
    ws['A1'].alignment = Alignment(horizontal='center')
    ws.merge_cells('A2:G2')
    ws['A2'] = f'Periodo: {MESES[mes]} {anio}'
    ws['A2'].font = Font(size=11, bold=True, color='64748B')
    ws['A2'].alignment = Alignment(horizontal='center')
    ws.merge_cells('A4:G4')
    ws['A4'] = subtitulo or titulo
    ws['A4'].font = Font(size=12, bold=True, color='000000')
    ws['A4'].alignment = Alignment(horizontal='center')
    ws['A4'].border = Border(top=borde_negro, bottom=borde_negro, left=borde_negro, right=borde_negro)
    ws['A4'].fill = fill_sub

    encabezados = ['Descripcion', 'Unidad', 'Conversion', 'Cierre anterior', 'Entradas mes', 'Salidas mes', 'Existencia final']
    for col, encabezado in enumerate(encabezados, start=1):
        celda = ws.cell(row=6, column=col, value=encabezado)
        celda.font = Font(size=11, bold=True, color='000000')
        celda.fill = fill_header
        celda.border = Border(top=borde_negro, bottom=borde_negro, left=borde_negro, right=borde_negro)
        celda.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    fila_excel = 7
    for fila in filas:
        valores = [
            fila['descripcion'],
            _unidad_excel_reporte(fila),
            _conversion_excel_reporte(fila),
            _valor_excel_reporte(fila, 'existencia_inicio', 'existencia_inicio_compra'),
            _valor_excel_reporte(fila, 'entradas_mes', 'entradas_mes_compra'),
            _valor_excel_reporte(fila, 'salidas_reporte', 'salidas_reporte_compra'),
            _valor_excel_reporte(fila, 'existencia_final', 'existencia_final_compra'),
        ]
        for col, valor in enumerate(valores, start=1):
            celda = ws.cell(row=fila_excel, column=col, value=valor)
            celda.border = Border(top=borde_gris, bottom=borde_gris, left=borde_gris, right=borde_gris)
            celda.alignment = Alignment(
                horizontal='right' if col >= 4 else 'left',
                vertical='center',
                wrap_text=col <= 3,
            )
            if col >= 4 and isinstance(valor, (int, float)):
                celda.number_format = '#,##0.00'
        fila_excel += 1

    ancho_cols = {
        'A': 34, 'B': 12, 'C': 24, 'D': 17, 'E': 17, 'F': 17, 'G': 17,
    }
    for col, ancho in ancho_cols.items():
        ws.column_dimensions[col].width = ancho
    ws.freeze_panes = 'A7'
    ws.print_title_rows = '1:6'
    return ws


@balance_bp.route('/todos/exportar.xlsx')
@login_required
def exportar_todos_excel():
    """Genera Excel con el mismo formato del reporte mensual impreso y guarda copia en Escritorio."""
    hoy = date.today()
    anio = int(request.args.get('anio', hoy.year))
    mes = int(request.args.get('mes', hoy.month))
    q = request.args.get('q', '').strip()
    conn = get_db()

    ids = [int(pid) for pid in session.get(SEL_KEY, []) if str(pid).isdigit()]
    if not ids:
        ids = [
            row['producto_id'] for row in conn.execute("""
                SELECT bp.producto_id
                FROM bloque_productos bp
                JOIN productos p ON p.id=bp.producto_id
                WHERE bp.bloque_id IN (1, 2) AND p.activo=1
                ORDER BY bp.bloque_id, bp.orden, p.codigo
            """).fetchall()
        ]

    filas = []
    for producto in _productos_por_ids_en_orden(conn, ids):
        if q and q.lower() not in f"{producto['codigo']} {producto['descripcion']}".lower():
            continue
        filas.append(_calcular_fila(conn, producto, anio, mes))
    grupos_reporte = _agrupar_filas_reporte_balance(conn, filas, [fila['producto_id'] for fila in filas])
    if not grupos_reporte:
        grupos_reporte = [{
            'titulo': 'REPORTE MENSUAL DE INVENTARIO',
            'subtitulo': 'PRODUCTOS SELECCIONADOS',
            'filas': filas,
        }]
    conn.close()

    wb = Workbook()
    for idx, grupo in enumerate(grupos_reporte):
        _agregar_hoja_balance_excel(
            wb, grupo['titulo'], grupo.get('subtitulo'), grupo['filas'], anio, mes, idx,
        )

    nombre_archivo = f"Balance_Mensual_{anio}_{mes:02d}.xlsx"
    escritorio = os.path.join(os.environ.get('USERPROFILE', r'C:\Users\Almacen'), 'Desktop')
    os.makedirs(escritorio, exist_ok=True)
    ruta = os.path.join(escritorio, nombre_archivo)
    wb.save(ruta)
    return send_file(
        ruta,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
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
    grupos_reporte = _agrupar_filas_reporte_balance(conn, filas, ids)
    total_consumo = sum(f['salidas_manual'] for f in filas if f['salidas_manual'] is not None)
    total_existencia_final = sum(
        f['existencia_final'] for f in filas if f['existencia_final'] is not None
    )
    total_consumo_compra = sum(
        f['salidas_manual_compra']
        for f in filas
        if f['salidas_manual_compra'] is not None
    )
    conn.close()
    from datetime import datetime as dt
    return render_template('balance/imprimir.html', filas=filas, anio=anio, mes=mes,
                           meses=MESES, total_consumo=total_consumo,
                           total_existencia_final=total_existencia_final,
                           total_consumo_compra=total_consumo_compra,
                           grupos_reporte=grupos_reporte,
                           tipo_reporte=tipo_reporte,
                           titulo_reporte=titulo_reporte,
                           now=dt.now().strftime('%d/%m/%Y %H:%M'))


@balance_bp.route('/etiquetas')
@login_required
def etiquetas():
    etiquetas, anio, mes = _obtener_etiquetas_balance(request.args)
    return render_template('balance/etiquetas.html', etiquetas=etiquetas, anio=anio, mes=mes,
                           meses=MESES, printer_name=TSC_PRINTER_NAME)


@balance_bp.route('/etiquetas/tsc', methods=['POST'])
@login_required
def imprimir_etiquetas_tsc():
    etiquetas, _anio, _mes = _obtener_etiquetas_balance(request.form)
    volver = request.form.get('volver') or url_for('balance.index')
    if not etiquetas:
        flash('No hay productos seleccionados para imprimir etiquetas.', 'warning')
        return redirect(volver)
    try:
        _imprimir_tsc_balance(etiquetas)
        flash(f'{len(etiquetas)} etiqueta(s) de balance enviadas a {TSC_PRINTER_NAME}.', 'success')
    except Exception as exc:
        flash(f'No se pudo imprimir en {TSC_PRINTER_NAME}: {exc}', 'danger')
    return redirect(volver)


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
