from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file, jsonify
from routes.auth import login_required
from routes.inventario import construir_busqueda_dinamica
from database import get_db, log_actividad, next_folio_requisicion, set_folio_counter, obtener_nombres_unidades
from datetime import date, datetime, timedelta
import json
import os
import platform
import re
import openpyxl

requisiciones_bp = Blueprint('requisiciones', __name__, url_prefix='/requisiciones')

MAX_ITEMS = 10

UNIDAD_SINGULAR = {
    'piezas': 'Pieza',
    'pieza': 'Pieza',
    'kilos': 'Kilo',
    'kilo': 'Kilo',
    'kilogramos': 'Kilo',
    'kilogramo': 'Kilo',
    'kg': 'Kilo',
    'litros': 'Litro',
    'litro': 'Litro',
    'metros': 'Metro',
    'metro': 'Metro',
    'cajas': 'Caja',
    'caja': 'Caja',
    'paquetes': 'Paquete',
    'paquete': 'Paquete',
    'bolsas': 'Bolsa',
    'bolsa': 'Bolsa',
    'botes': 'Bote',
    'bote': 'Bote',
    'cubetas': 'Cubeta',
    'cubeta': 'Cubeta',
    'galones': 'Galon',
    'galon': 'Galon',
    'galón': 'Galon',
    'garrafas': 'Garrafa',
    'garrafa': 'Garrafa',
    'bidones': 'Bidon',
    'bidon': 'Bidon',
    'bidón': 'Bidon',
    'rollos': 'Rollo',
    'rollo': 'Rollo',
    'pares': 'Par',
    'par': 'Par',
    'juegos': 'Juego',
    'juego': 'Juego',
    'millares': 'Millar',
    'millar': 'Millar',
    'lotes': 'Lote',
    'lote': 'Lote',
    'servicios': 'Servicio',
    'servicio': 'Servicio',
}

UNIDAD_PLURAL = {
    'Pieza': 'Piezas',
    'Kilo': 'Kilos',
    'Litro': 'Litros',
    'Metro': 'Metros',
    'Caja': 'Cajas',
    'Paquete': 'Paquetes',
    'Bolsa': 'Bolsas',
    'Bote': 'Botes',
    'Cubeta': 'Cubetas',
    'Galon': 'Galones',
    'Garrafa': 'Garrafas',
    'Bidon': 'Bidones',
    'Rollo': 'Rollos',
    'Par': 'Pares',
    'Juego': 'Juegos',
    'Millar': 'Millares',
    'Lote': 'Lotes',
    'Servicio': 'Servicios',
}

# Plantilla real del formato (queda en el proyecto como respaldo/base).
PLANTILLA_XLSM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              'plantillas', 'REQUISICIONES.xlsm')
# Ruta local en la PC de Ricardo: ahí se sobreescribe el archivo con los datos de cada
# requisición y se abre directo en Excel. Solo funciona cuando la app corre en esa misma
# PC (un servidor web no puede abrir archivos en la computadora de quien lo visita).
RUTA_LOCAL_XLSM = r"C:\Users\Almacen\Desktop\ERP\REQUISICIONES.xlsm"


def _fecha_impresion(valor):
    if not valor:
        return ''
    try:
        fecha = datetime.strptime(str(valor)[:10], '%Y-%m-%d')
        meses = [
            'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
        ]
        return f"{fecha.day}/{meses[fecha.month - 1]}/{fecha.year}"
    except (ValueError, TypeError):
        return valor


def _sumar_dias_fecha(valor, dias):
    if not valor:
        return ''
    try:
        return (datetime.strptime(str(valor)[:10], '%Y-%m-%d') + timedelta(days=dias)).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return ''


def _dias_desde_fecha(valor):
    if not valor:
        return 0
    try:
        fecha = datetime.strptime(str(valor)[:10], '%Y-%m-%d').date()
        return max(0, (date.today() - fecha).days)
    except (ValueError, TypeError):
        return 0


def _leer_items_formulario(f):
    items = []
    for i in range(1, MAX_ITEMS + 1):
        cantidad = (f.get(f'cantidad_{i}') or '').strip()
        descripcion = (f.get(f'descripcion_{i}') or '').strip()
        unidad = _unidad_singular(f.get(f'unidad_{i}') or '')
        producto_id = f.get(f'producto_id_{i}') or None
        material_pedir_id = f.get(f'material_pedir_id_{i}') or None
        actualizar_unidad_catalogo = f.get(f'actualizar_unidad_catalogo_{i}') in ('1', 'on', 'true', 'si')
        try:
            material_pedir_id = int(material_pedir_id) if material_pedir_id else None
        except (TypeError, ValueError):
            material_pedir_id = None
        if descripcion and not cantidad and not producto_id:
            items.append({
                'cantidad': 0, 'unidad': '', 'descripcion': descripcion,
                'producto_id': None, 'material_pedir_id': material_pedir_id,
                'actualizar_unidad_catalogo': False,
            })
        elif cantidad and descripcion:
            items.append({
                'cantidad': float(cantidad), 'unidad': unidad, 'descripcion': descripcion,
                'producto_id': int(producto_id) if producto_id else None,
                'material_pedir_id': material_pedir_id,
                'actualizar_unidad_catalogo': actualizar_unidad_catalogo,
            })
    return items


def _normalizar_codigo_producto(texto):
    return re.sub(r'\s+', '', str(texto or '')).strip().upper()


def _unidad_singular(unidad):
    texto = (unidad or '').strip()
    if not texto:
        return ''
    return UNIDAD_SINGULAR.get(texto.lower(), texto[:1].upper() + texto[1:])


def _unidad_para_cantidad(unidad, cantidad):
    singular = _unidad_singular(unidad)
    try:
        cantidad_num = float(cantidad or 0)
    except (TypeError, ValueError):
        cantidad_num = 0
    if cantidad_num >= 2:
        return UNIDAD_PLURAL.get(singular, singular)
    return singular


def _unidades_activas():
    return [_unidad_singular(u) for u in obtener_nombres_unidades()]


def _material_pendiente_para_producto(conn, producto_id):
    producto = conn.execute(
        "SELECT id, codigo, unidad_medida FROM productos WHERE id=? AND activo=1",
        (producto_id,)
    ).fetchone()
    if not producto:
        return None

    codigo_norm = _normalizar_codigo_producto(producto['codigo'])
    condiciones = ["m.producto_id=?"]
    params = [producto_id]
    if codigo_norm:
        condiciones.append("UPPER(REPLACE(COALESCE(m.codigo,''),' ',''))=?")
        params.append(codigo_norm)

    filas = conn.execute(f"""
        SELECT m.id, m.cantidad, m.unidad, m.prioridad, m.motivo, m.fecha
        FROM material_por_pedir m
        WHERE COALESCE(m.solicitado,0)=0
          AND ({' OR '.join(condiciones)})
        ORDER BY CASE m.prioridad
                   WHEN 'urgente' THEN 0
                   WHEN 'alta' THEN 1
                   WHEN 'normal' THEN 2
                   ELSE 3
                 END,
                 m.fecha ASC,
                 m.id ASC
    """, params).fetchall()
    if not filas:
        return None

    grupos = {}
    for fila in filas:
        unidad = _unidad_singular(fila['unidad'] or producto['unidad_medida'] or '')
        grupos.setdefault(unidad, {'cantidad': 0, 'ids': [], 'motivos': []})
        grupos[unidad]['cantidad'] += float(fila['cantidad'] or 0)
        grupos[unidad]['ids'].append(fila['id'])
        if fila['motivo']:
            grupos[unidad]['motivos'].append(fila['motivo'])

    unidad_elegida, datos = max(grupos.items(), key=lambda par: (len(par[1]['ids']), par[1]['cantidad']))
    return {
        'cantidad': datos['cantidad'],
        'unidad': unidad_elegida,
        'ids': datos['ids'],
        'total_pendientes': len(filas),
        'pendientes_misma_unidad': len(datos['ids']),
        'unidades_distintas': len(grupos),
        'motivos': datos['motivos'][:3],
    }


def _areas_activas(conn=None):
    cerrar = conn is None
    if conn is None:
        conn = get_db()
    filas = conn.execute("SELECT nombre FROM areas WHERE activo=1 ORDER BY LOWER(nombre)").fetchall()
    if cerrar:
        conn.close()
    return [fila['nombre'] for fila in filas]


def _normalizar_folio_requisicion(texto):
    if not texto:
        return ""
    return str(texto).strip().upper().replace("-", "").replace(" ", "")


def _folios_desde_texto_requisicion(texto):
    if not texto:
        return []
    folios = []
    vistos = set()
    for match in re.finditer(r'(?:AL\s*-?\s*)?(\d+)', str(texto), flags=re.IGNORECASE):
        folio = int(match.group(1))
        if folio not in vistos:
            vistos.add(folio)
            folios.append(folio)
    return folios


def _generar_codigo_producto_conn(conn):
    conn.execute("INSERT OR IGNORE INTO folios VALUES ('producto', 0)")
    conn.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo = 'producto'")
    num = conn.execute("SELECT ultimo FROM folios WHERE tipo = 'producto'").fetchone()[0]
    return f"PRD-{str(num).zfill(6)}"


def _crear_productos_para_items_libres(conn, items):
    """Convierte partidas libres en productos nuevos con stock cero."""
    creados = []
    for item in items:
        if item.get('producto_id'):
            continue
        if float(item.get('cantidad') or 0) <= 0:
            continue

        descripcion = (item.get('descripcion') or '').strip()
        if not descripcion:
            continue

        codigo = _generar_codigo_producto_conn(conn)
        unidad = (item.get('unidad') or '').strip() or 'PIEZA'
        cur = conn.execute("""
            INSERT INTO productos
            (codigo, descripcion, unidad_medida, ubicacion, departamento,
             stock_actual, stock_minimo, precio_unitario, activo)
            VALUES (?,?,?,?,?,0,0,0,1)
        """, (codigo, descripcion, unidad, 'PENDIENTE', 'ALMACEN GENERAL'))
        item['producto_id'] = cur.lastrowid
        creados.append(codigo)
    return creados


def _sincronizar_productos_desde_items(conn, items):
    """
    Actualiza el catálogo desde partidas ligadas.

    La unidad capturada en una requisición es la unidad en que se está solicitando
    el material y puede ser distinta a la unidad base del inventario. Por ejemplo,
    Playo puede estar en inventario como Pieza, pero pedirse en Kilos. Por eso la
    unidad sólo se copia al catálogo cuando el usuario marca explícitamente
    "Actualizar catálogo" en ese renglón.
    """
    for item in items:
        producto_id = item.get('producto_id')
        unidad = (item.get('unidad') or '').strip()
        descripcion = (item.get('descripcion') or '').strip()
        actualizar_unidad = bool(item.get('actualizar_unidad_catalogo'))
        if not producto_id:
            continue

        producto = conn.execute(
            "SELECT descripcion, unidad_medida FROM productos WHERE id=?", (producto_id,)
        ).fetchone()
        if not producto:
            continue

        cambios = {}
        if actualizar_unidad and unidad and producto['unidad_medida'] != unidad:
            cambios['unidad_medida'] = unidad
        if descripcion and producto['descripcion'] != descripcion:
            cambios['descripcion'] = descripcion

        if cambios:
            set_clause = ", ".join(f"{campo}=?" for campo in cambios)
            conn.execute(
                f"UPDATE productos SET {set_clause} WHERE id=?",
                (*cambios.values(), producto_id)
            )


def _sincronizar_material_por_pedir(conn, requisicion_id, folio, items, usuario_id, orden_compra=None):
    """
    Marca como "pedido" el material pendiente cuando una requisición contiene
    el mismo producto. Se compara primero por producto_id y también por código
    normalizado para cubrir registros capturados manualmente.
    """
    if not items:
        return 0

    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    folio_txt = f"AL-{folio}"
    referencia = (orden_compra or '').strip() or folio_txt
    actualizados = 0
    vistos = set()

    for item in items:
        material_pedir_id = item.get('material_pedir_id')
        if material_pedir_id and material_pedir_id not in vistos:
            pendiente = conn.execute("""
                SELECT id, notas_pedido
                FROM material_por_pedir
                WHERE id=? AND COALESCE(solicitado,0)=0
            """, (material_pedir_id,)).fetchone()
            if pendiente:
                vistos.add(material_pedir_id)
                nota_auto = f"Vinculado automáticamente con requisición {folio_txt}"
                notas_previas = (pendiente['notas_pedido'] or '').strip()
                notas = nota_auto if not notas_previas else f"{notas_previas} | {nota_auto}"
                conn.execute("""
                    UPDATE material_por_pedir
                    SET solicitado=1,
                        fecha_solicitado=COALESCE(fecha_solicitado, ?),
                        orden_compra=COALESCE(NULLIF(orden_compra,''), ?),
                        notas_pedido=?,
                        pedido_por_usuario_id=COALESCE(pedido_por_usuario_id, ?),
                        requisicion_id=?,
                        requisicion_folio=?,
                        updated_at=?
                    WHERE id=?
                """, (
                    ahora, referencia, notas, usuario_id, requisicion_id, folio_txt,
                    ahora, material_pedir_id
                ))
                actualizados += 1

        if float(item.get('cantidad') or 0) <= 0:
            continue
        producto_id = item.get('producto_id')
        codigo = ''
        if producto_id:
            producto = conn.execute(
                "SELECT codigo FROM productos WHERE id=?", (producto_id,)
            ).fetchone()
            if producto:
                codigo = _normalizar_codigo_producto(producto['codigo'])

        condiciones = []
        params = []
        if producto_id:
            condiciones.append("m.producto_id=?")
            params.append(producto_id)
        if codigo:
            condiciones.append("UPPER(REPLACE(COALESCE(m.codigo,''),' ',''))=?")
            params.append(codigo)
        if not condiciones:
            continue

        pendientes = conn.execute(f"""
            SELECT m.id, m.notas_pedido
            FROM material_por_pedir m
            WHERE COALESCE(m.solicitado,0)=0
              AND ({' OR '.join(condiciones)})
        """, params).fetchall()

        for pendiente in pendientes:
            pendiente_id = pendiente['id']
            if pendiente_id in vistos:
                continue
            vistos.add(pendiente_id)

            nota_auto = f"Vinculado automáticamente con requisición {folio_txt}"
            notas_previas = (pendiente['notas_pedido'] or '').strip()
            notas = nota_auto if not notas_previas else f"{notas_previas} | {nota_auto}"
            conn.execute("""
                UPDATE material_por_pedir
                SET solicitado=1,
                    fecha_solicitado=COALESCE(fecha_solicitado, ?),
                    orden_compra=COALESCE(NULLIF(orden_compra,''), ?),
                    notas_pedido=?,
                    pedido_por_usuario_id=COALESCE(pedido_por_usuario_id, ?),
                    requisicion_id=?,
                    requisicion_folio=?,
                    updated_at=?
                WHERE id=?
            """, (
                ahora, referencia, notas, usuario_id, requisicion_id, folio_txt,
                ahora, pendiente_id
            ))
            actualizados += 1

    return actualizados


def _asegurar_tabla_borradores(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS requisicion_borradores (
            usuario_id INTEGER PRIMARY KEY,
            datos_json TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _entradas_relacionadas(conn, requisicion):
    """
    Busca entradas vinculadas SOLO por Nº de requisición/folio.
    
    El folio se puede escribir de cualquier forma:
    - "51" coincide con AL-51
    - "AL-51" coincide con 51
    - "AL 51" coincide con "AL51"
    - etc.
    
    NO busca por OC, factura o remisión. Solo por folio.
    
    IMPORTANTE: Busca TODAS las entradas con no_requisicion rellenado,
    incluso las que no tienen producto_id vinculado.
    """
    
    folio_num = int(requisicion['folio'])
    
    # Buscar TODAS las entradas con no_requisicion, sin importar producto
    entradas = conn.execute("""
        SELECT e.*, 
               COALESCE(p.codigo, 'SIN_PRODUCTO') as codigo, 
               COALESCE(p.descripcion, e.concepto_servicio) as descripcion, 
               COALESCE(p.unidad_medida, 'UNIDAD') as unidad_medida
        FROM entradas e
        LEFT JOIN productos p ON e.producto_id = p.id
        WHERE e.no_requisicion IS NOT NULL AND TRIM(e.no_requisicion) != ''
        ORDER BY e.fecha DESC
    """).fetchall()
    
    # Filtrar en Python normalizando
    resultado = []
    for entrada in entradas:
        if folio_num in _folios_desde_texto_requisicion(entrada['no_requisicion']):
            resultado.append(entrada)
    
    return resultado


def _items_por_requisicion(conn, requisicion_ids):
    if not requisicion_ids:
        return {}
    placeholders = ",".join("?" for _ in requisicion_ids)
    filas = conn.execute(
        f"SELECT * FROM requisicion_items WHERE requisicion_id IN ({placeholders}) ORDER BY requisicion_id, orden",
        requisicion_ids
    ).fetchall()
    resultado = {rid: [] for rid in requisicion_ids}
    for fila in filas:
        resultado.setdefault(fila['requisicion_id'], []).append(fila)
    return resultado


def _entradas_por_folio_requisicion(conn):
    filas = conn.execute("""
        SELECT e.*,
               COALESCE(p.codigo, 'SIN_PRODUCTO') as codigo,
               COALESCE(p.descripcion, e.concepto_servicio) as descripcion,
               COALESCE(p.unidad_medida, 'UNIDAD') as unidad_medida
        FROM entradas e
        LEFT JOIN productos p ON e.producto_id = p.id
        WHERE e.no_requisicion IS NOT NULL AND TRIM(e.no_requisicion) != ''
        ORDER BY e.fecha DESC
    """).fetchall()
    resultado = {}
    for entrada in filas:
        for folio in _folios_desde_texto_requisicion(entrada['no_requisicion']):
            clave = _normalizar_folio_requisicion(folio)
            resultado.setdefault(clave, []).append(entrada)
    return resultado


def _enriquecer_items(items, entradas_relacionadas):
    """Para partidas ligadas a un producto del catálogo, calcula lo recibido SUMANDO las
    entradas vinculadas de ese mismo producto (automático, no se captura a mano). Para
    partidas de texto libre (sin producto_id), se usa lo que se haya capturado a mano en
    'cantidad_recibida'."""
    recibido_por_producto = {}
    for e in entradas_relacionadas:
        cant = e['cantidad_piezas'] if e['cantidad_piezas'] is not None else e['cantidad']
        recibido_por_producto[e['producto_id']] = recibido_por_producto.get(e['producto_id'], 0) + cant

    resultado = []
    for it in items:
        d = dict(it)
        d['informativo'] = float(d.get('cantidad') or 0) <= 0
        if d.get('recepcion_manual'):
            d['recibido_calc'] = d.get('cantidad_recibida') or 0
            d['auto'] = False
            d['manual'] = True
        elif d.get('producto_id'):
            d['recibido_calc'] = recibido_por_producto.get(d['producto_id'], 0)
            d['auto'] = True
            d['manual'] = False
        else:
            d['recibido_calc'] = d.get('cantidad_recibida') or 0
            d['auto'] = False
            d['manual'] = False
        resultado.append(d)
    return resultado


def _calcular_estado(items_enriquecidos):
    items_pendientes = [it for it in items_enriquecidos if not it.get('informativo')]
    if not items_pendientes:
        return 'pendiente'
    completos = sum(1 for it in items_pendientes if it['recibido_calc'] >= it['cantidad'])
    con_algo = sum(1 for it in items_pendientes if it['recibido_calc'] > 0)
    if completos == len(items_pendientes):
        return 'completa'
    if con_algo > 0:
        return 'parcial'
    return 'pendiente'


def _sincronizar_estado(conn, requisicion_id, estado_calculado, entradas_relacionadas):
    """
    Mantiene la columna 'estado' de la requisición en línea con la realidad:
      - Si ya está todo recibido (completa) o algo recibido (parcial), SIEMPRE
        se actualiza a ese valor (es un hecho objetivo, no depende de que
        alguien lo marque a mano).
      - Si no hay nada recibido todavía pero ya llegaron entradas ligadas por
        folio, se marca 'revision' para poder revisarlas.
    No hace nada si el estado ya coincide (evita commits de más).
    """
    req = conn.execute("SELECT estado FROM requisiciones WHERE id=?", (requisicion_id,)).fetchone()
    if not req:
        return
    estado_actual = req['estado']
    nuevo_estado = None
    if estado_calculado in ('completa', 'parcial'):
        nuevo_estado = estado_calculado
    elif not entradas_relacionadas and estado_calculado == 'pendiente':
        nuevo_estado = 'pendiente'
    elif entradas_relacionadas and estado_actual not in ('revision', 'parcial', 'completa'):
        nuevo_estado = 'revision'
    if nuevo_estado and nuevo_estado != estado_actual:
        if nuevo_estado == 'pendiente' and not entradas_relacionadas:
            conn.execute("""
                UPDATE requisiciones
                SET estado=?,
                    orden_compra=NULL,
                    no_factura=NULL,
                    no_remision=NULL
                WHERE id=?
            """, (nuevo_estado, requisicion_id))
        else:
            conn.execute("UPDATE requisiciones SET estado=? WHERE id=?", (nuevo_estado, requisicion_id))
        conn.commit()


def _registrar_recepcion(conn, item_id, cantidad, usuario_id):
    """
    Registra una entrega parcial (o total) de una partida de texto libre, con
    la fecha/hora del momento (automática, no se captura a mano). Guarda cada
    entrega como un renglón separado en requisicion_item_recepciones para
    conservar el historial completo (ej. 1000 kg hoy, 500 kg después), y
    recalcula cantidad_recibida como la SUMA de todas las entregas.
    """
    if cantidad <= 0:
        return
    conn.execute("""
        INSERT INTO requisicion_item_recepciones (requisicion_item_id, cantidad, usuario_id)
        VALUES (?, ?, ?)
    """, (item_id, cantidad, usuario_id))
    total = conn.execute("""
        SELECT COALESCE(SUM(cantidad), 0) total FROM requisicion_item_recepciones
        WHERE requisicion_item_id=?
    """, (item_id,)).fetchone()['total']
    conn.execute("UPDATE requisicion_items SET cantidad_recibida=? WHERE id=?", (total, item_id))


@requisiciones_bp.route('/')
@login_required
def index():
    q = request.args.get('q', '').strip()
    q_folio = request.args.get('folio', '').strip()
    q_descripcion = request.args.get('descripcion', '').strip()
    q_partida = request.args.get('partida', '').strip()
    q_oc = request.args.get('oc', '').strip()
    q_factura = request.args.get('factura', '').strip()
    estado_f = request.args.get('estado', '')
    pagina = request.args.get('pagina', 1, type=int)
    registros_por_pagina = 50
    
    conn = get_db()
    query = "SELECT r.* FROM requisiciones r WHERE 1=1"
    params = []
    if q:
        cond, cond_params = construir_busqueda_dinamica(
            q, ["r.asunto", "r.solicitante", "r.departamento", "r.orden_compra", "r.no_factura", "CAST(r.folio AS TEXT)"])
        if cond:
            query += f" AND {cond}"
            params += cond_params
    if q_folio:
        query += " AND CAST(r.folio AS TEXT) LIKE ?"
        folio_busqueda = ''.join(ch for ch in q_folio if ch.isdigit()) or q_folio
        params.append(f"%{folio_busqueda}%")
    if q_descripcion:
        cond, cond_params = construir_busqueda_dinamica(q_descripcion, ["r.asunto"])
        if cond:
            query += f" AND {cond}"
            params += cond_params
    if q_partida:
        cond, cond_params = construir_busqueda_dinamica(q_partida, ["ri.descripcion"])
        if cond:
            query += f" AND EXISTS (SELECT 1 FROM requisicion_items ri WHERE ri.requisicion_id = r.id AND {cond})"
            params += cond_params
    if q_oc:
        cond, cond_params = construir_busqueda_dinamica(q_oc, ["r.orden_compra"])
        if cond:
            query += f" AND {cond}"
            params += cond_params
    if q_factura:
        cond, cond_params = construir_busqueda_dinamica(q_factura, ["r.no_factura"])
        if cond:
            query += f" AND {cond}"
            params += cond_params
    query += " ORDER BY r.folio DESC"
    filas = conn.execute(query, params).fetchall()
    requisicion_ids = [r['id'] for r in filas]
    items_map = _items_por_requisicion(conn, requisicion_ids)
    entradas_map = _entradas_por_folio_requisicion(conn)

    resultado = []
    for r in filas:
        items = items_map.get(r['id'], [])
        folio_normalizado = _normalizar_folio_requisicion(r['folio'])
        folio_al_normalizado = _normalizar_folio_requisicion(f"AL-{r['folio']}")
        entradas_rel = entradas_map.get(folio_normalizado, []) + entradas_map.get(folio_al_normalizado, [])
        items_enriquecidos = _enriquecer_items(items, entradas_rel)
        estado = _calcular_estado(items_enriquecidos)
        estado_visible = r['estado'] if r['estado'] in ('revision', 'completa') else estado
        dias_abierta = _dias_desde_fecha(r['fecha_requisicion'] or r['fecha'])
        atrasada = estado_visible != 'completa' and dias_abierta > 7
        if estado_f == 'atrasada':
            if not atrasada:
                continue
        elif estado_f and estado_visible != estado_f:
            continue
        partidas_preview = [
            (
                it['descripcion']
                if float(it['cantidad'] or 0) <= 0
                else f"{'%g' % it['cantidad']} {it['unidad'] or ''} - {it['descripcion']}"
            )
            for it in items[:10]
        ]
        resultado.append({**dict(r), 'estado_calc': estado, 'estado_visible': estado_visible,
                          'num_items': len(items), 'partidas_preview': partidas_preview,
                          'dias_abierta': dias_abierta, 'atrasada': atrasada})

    resumen_estados = {'pendiente': 0, 'revision': 0, 'parcial': 0, 'completa': 0}
    requisiciones_atrasadas = 0
    for r in resultado:
        estado_resumen = r['estado_visible']
        if estado_resumen in resumen_estados:
            resumen_estados[estado_resumen] += 1
        if r.get('atrasada'):
            requisiciones_atrasadas += 1
    
    total_registros = len(resultado)
    total_paginas = (total_registros + registros_por_pagina - 1) // registros_por_pagina
    
    if pagina < 1:
        pagina = 1
    elif pagina > total_paginas and total_paginas > 0:
        pagina = total_paginas
    
    offset = (pagina - 1) * registros_por_pagina
    requisiciones = resultado[offset:offset + registros_por_pagina]
    
    conn.close()
    filtros_activos = any([q, q_folio, q_descripcion, q_partida, q_oc, q_factura, estado_f])

    return render_template('requisiciones/index.html', requisiciones=requisiciones, q=q,
                           q_folio=q_folio, q_descripcion=q_descripcion, q_partida=q_partida,
                           q_oc=q_oc, q_factura=q_factura, filtros_activos=filtros_activos,
                           estado_f=estado_f,
                           resumen_estados=resumen_estados,
                           requisiciones_atrasadas=requisiciones_atrasadas,
                           pagina_actual=pagina, total_paginas=total_paginas,
                           total_registros=total_registros, registros_pagina=len(requisiciones))


@requisiciones_bp.route('/borrador', methods=['GET', 'POST', 'DELETE'])
@login_required
def borrador():
    conn = get_db()
    _asegurar_tabla_borradores(conn)
    usuario_id = session['user_id']

    if request.method == 'GET':
        fila = conn.execute(
            "SELECT datos_json, updated_at FROM requisicion_borradores WHERE usuario_id=?",
            (usuario_id,)
        ).fetchone()
        conn.close()
        if not fila:
            return {'ok': True, 'datos': None}
        try:
            datos = json.loads(fila['datos_json'])
        except (TypeError, json.JSONDecodeError):
            datos = None
        return {'ok': True, 'datos': datos, 'updated_at': fila['updated_at']}

    if request.method == 'DELETE':
        conn.execute("DELETE FROM requisicion_borradores WHERE usuario_id=?", (usuario_id,))
        conn.commit()
        conn.close()
        return {'ok': True}

    datos = request.get_json(silent=True) or {}
    conn.execute("""
        INSERT INTO requisicion_borradores (usuario_id, datos_json, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(usuario_id) DO UPDATE SET
            datos_json=excluded.datos_json,
            updated_at=CURRENT_TIMESTAMP
    """, (usuario_id, json.dumps(datos, ensure_ascii=False)))
    conn.commit()
    conn.close()
    return {'ok': True}


@requisiciones_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        f = request.form
        items = _leer_items_formulario(f)
        if not items:
            flash('Agrega al menos una partida o un renglón informativo.', 'danger')
            return render_template('requisiciones/form.html', requisicion=None,
                                   departamentos=_areas_activas(), unidades=_unidades_activas(), hoy=date.today().isoformat(),
                                   max_items=MAX_ITEMS, unidad_singular=_unidad_singular)
        conn = get_db()
        try:
            folio = next_folio_requisicion()
            existe = conn.execute("SELECT id FROM requisiciones WHERE folio=?", (folio,)).fetchone()
            if existe:
                flash(f'El folio AL-{folio} ya existe (requisición #{existe["id"]}). '
                      f'Usa un número distinto o deja el campo vacío para generarlo automáticamente.', 'danger')
                conn.close()
                return render_template('requisiciones/form.html', requisicion=None,
                                       departamentos=_areas_activas(), unidades=_unidades_activas(), hoy=date.today().isoformat(),
                                       max_items=MAX_ITEMS, unidad_singular=_unidad_singular)
            productos_creados = _crear_productos_para_items_libres(conn, items)
            cur = conn.execute("""
                INSERT INTO requisiciones
                (folio, fecha_requisicion, fecha_necesita, departamento, solicitante, asunto,
                 visto_bueno, autorizo, observaciones, usuario_id)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (folio, f.get('fecha_requisicion') or date.today().isoformat(),
                  f.get('fecha_necesita') or None, 'ALMACEN GENERAL',
                  f.get('solicitante') or None, f.get('asunto') or None,
                  f.get('visto_bueno') or None, f.get('autorizo') or None,
                  f.get('observaciones') or None, session['user_id']))
            rid = cur.lastrowid
            for idx, item in enumerate(items, start=1):
                conn.execute("""
                    INSERT INTO requisicion_items (requisicion_id, orden, cantidad, unidad, descripcion, producto_id)
                    VALUES (?,?,?,?,?,?)
                """, (rid, idx, item['cantidad'], item['unidad'], item['descripcion'], item['producto_id']))
            _sincronizar_productos_desde_items(conn, items)
            pendientes_vinculados = _sincronizar_material_por_pedir(
                conn, rid, folio, items, session['user_id']
            )
            _asegurar_tabla_borradores(conn)
            conn.execute("DELETE FROM requisicion_borradores WHERE usuario_id=?", (session['user_id'],))
            conn.commit()
            log_actividad(session['user_id'], 'NUEVA_REQUISICION', f"Folio: AL-{folio}")
            extra = f" Se crearon {len(productos_creados)} productos nuevos." if productos_creados else ""
            if pendientes_vinculados:
                extra += f" Se marcaron {pendientes_vinculados} material(es) pendiente(s) como pedido."
            flash(f'Requisición AL-{folio} registrada correctamente.{extra}', 'success')
            conn.close()
            return redirect(url_for('requisiciones.nuevo', limpio=1))
        except Exception as e:
            conn.rollback()
            conn.close()
            if 'UNIQUE' in str(e) and 'folio' in str(e):
                flash(f'El folio AL-{folio} ya existe. Usa un número distinto o deja el campo vacío.', 'danger')
            else:
                flash(f'Error: {str(e)}', 'danger')
            return render_template('requisiciones/form.html', requisicion=None,
                                   departamentos=_areas_activas(), unidades=_unidades_activas(), hoy=date.today().isoformat(),
                                   max_items=MAX_ITEMS, unidad_singular=_unidad_singular)

    if request.args.get('limpio') == '1':
        conn = get_db()
        _asegurar_tabla_borradores(conn)
        conn.execute("DELETE FROM requisicion_borradores WHERE usuario_id=?", (session['user_id'],))
        conn.commit()
        conn.close()

    return render_template('requisiciones/form.html', requisicion=None,
                           departamentos=_areas_activas(), unidades=_unidades_activas(), hoy=date.today().isoformat(),
                           max_items=MAX_ITEMS, unidad_singular=_unidad_singular)


@requisiciones_bp.route('/editar/<int:rid>', methods=['GET', 'POST'])
@login_required
def editar(rid):
    conn = get_db()
    requisicion = conn.execute("SELECT * FROM requisiciones WHERE id=?", (rid,)).fetchone()
    if not requisicion:
        flash('Requisición no encontrada.', 'danger')
        conn.close()
        return redirect(url_for('requisiciones.index'))

    if request.method == 'POST':
        f = request.form
        items = _leer_items_formulario(f)
        if not items:
            flash('Agrega al menos una partida o un renglón informativo.', 'danger')
            conn.close()
            return redirect(url_for('requisiciones.editar', rid=rid))
        try:
            productos_creados = _crear_productos_para_items_libres(conn, items)
            conn.execute("""
                UPDATE requisiciones SET
                    fecha_requisicion=?, fecha_necesita=?, departamento=?, solicitante=?,
                    asunto=?, visto_bueno=?, autorizo=?, observaciones=?
                WHERE id=?
            """, (f.get('fecha_requisicion') or requisicion['fecha_requisicion'],
                  f.get('fecha_necesita') or None, 'ALMACEN GENERAL',
                  f.get('solicitante') or None, f.get('asunto') or None,
                  f.get('visto_bueno') or None, f.get('autorizo') or None,
                  f.get('observaciones') or None, rid))
            # Reemplaza las partidas (se pierde la recepción manual de partidas de texto
            # libre capturada antes; las ligadas a catálogo se vuelven a calcular solas)
            conn.execute("DELETE FROM requisicion_items WHERE requisicion_id=?", (rid,))
            for idx, item in enumerate(items, start=1):
                conn.execute("""
                    INSERT INTO requisicion_items (requisicion_id, orden, cantidad, unidad, descripcion, producto_id)
                    VALUES (?,?,?,?,?,?)
                """, (rid, idx, item['cantidad'], item['unidad'], item['descripcion'], item['producto_id']))
            _sincronizar_productos_desde_items(conn, items)
            pendientes_vinculados = _sincronizar_material_por_pedir(
                conn, rid, requisicion['folio'], items, session['user_id'], requisicion['orden_compra']
            )
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_REQUISICION', f"ID: {rid} | Folio: AL-{requisicion['folio']}")
            extra = f" Se crearon {len(productos_creados)} productos nuevos." if productos_creados else ""
            if pendientes_vinculados:
                extra += f" Se marcaron {pendientes_vinculados} material(es) pendiente(s) como pedido."
            flash(f'Requisición actualizada.{extra}', 'success')
            conn.close()
            return redirect(url_for('requisiciones.detalle', rid=rid))
        except Exception as e:
            conn.rollback()
            flash(f'Error: {str(e)}', 'danger')

    items = conn.execute(
        "SELECT ri.*, p.codigo, p.descripcion as producto_descripcion FROM requisicion_items ri "
        "LEFT JOIN productos p ON ri.producto_id = p.id "
        "WHERE ri.requisicion_id=? ORDER BY ri.orden", (rid,)).fetchall()
    conn.close()
    return render_template('requisiciones/form.html', requisicion=requisicion, items=items,
                           departamentos=_areas_activas(), unidades=_unidades_activas(), hoy=date.today().isoformat(),
                           max_items=MAX_ITEMS, unidad_singular=_unidad_singular)


@requisiciones_bp.route('/eliminar/<int:rid>', methods=['POST'])
@login_required
def eliminar(rid):
    conn = get_db()
    requisicion = conn.execute("SELECT * FROM requisiciones WHERE id=?", (rid,)).fetchone()
    if not requisicion:
        flash('Requisición no encontrada.', 'danger')
        conn.close()
        return redirect(url_for('requisiciones.index'))
    try:
        materiales_ligados = conn.execute(
            "SELECT COUNT(*) AS total FROM material_por_pedir WHERE requisicion_id=?",
            (rid,)
        ).fetchone()['total']
        conn.execute("""
            UPDATE material_por_pedir
            SET solicitado=0,
                fecha_solicitado=NULL,
                orden_compra=NULL,
                notas_pedido=NULL,
                pedido_por_usuario_id=NULL,
                requisicion_id=NULL,
                requisicion_folio=NULL,
                updated_at=?
            WHERE requisicion_id=?
        """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), rid))
        conn.execute("""
            DELETE FROM requisicion_item_recepciones
            WHERE requisicion_item_id IN (
                SELECT id FROM requisicion_items WHERE requisicion_id=?
            )
        """, (rid,))
        conn.execute("DELETE FROM requisicion_items WHERE requisicion_id=?", (rid,))
        conn.execute("DELETE FROM requisiciones WHERE id=?", (rid,))
        conn.commit()
        log_actividad(session['user_id'], 'ELIMINAR_REQUISICION', f"ID: {rid} | Folio: AL-{requisicion['folio']}")
        extra = f" {materiales_ligados} material(es) regresaron a pendientes por pedir." if materiales_ligados else ""
        flash(f"Requisición AL-{requisicion['folio']} eliminada permanentemente.{extra}", 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    conn.close()
    return redirect(url_for('requisiciones.index'))


@requisiciones_bp.route('/marcar_completa/<int:rid>', methods=['POST'])
@login_required
def marcar_completa(rid):
    conn = get_db()
    requisicion = conn.execute("SELECT folio FROM requisiciones WHERE id=?", (rid,)).fetchone()
    if not requisicion:
        conn.close()
        flash('Requisición no encontrada.', 'danger')
        return redirect(url_for('requisiciones.index'))

    conn.execute("UPDATE requisiciones SET estado='completa' WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    log_actividad(session['user_id'], 'MARCAR_REQUISICION_COMPLETA',
                  f"ID: {rid} | Folio: AL-{requisicion['folio']}")
    flash(f"Requisición AL-{requisicion['folio']} marcada como completa.", 'success')
    return redirect(request.referrer or url_for('requisiciones.index'))


@requisiciones_bp.route('/marcar_completas', methods=['POST'])
@login_required
def marcar_completas():
    ids = []
    for valor in request.form.getlist('requisicion_ids'):
        try:
            ids.append(int(valor))
        except (TypeError, ValueError):
            continue

    if not ids:
        flash('Selecciona al menos una requisición.', 'warning')
        return redirect(request.referrer or url_for('requisiciones.index'))

    conn = get_db()
    placeholders = ','.join('?' for _ in ids)
    folios = conn.execute(
        f"SELECT folio FROM requisiciones WHERE id IN ({placeholders}) ORDER BY folio",
        ids
    ).fetchall()
    conn.execute(
        f"UPDATE requisiciones SET estado='completa' WHERE id IN ({placeholders})",
        ids
    )
    conn.commit()
    conn.close()

    folios_txt = ', '.join(f"AL-{f['folio']}" for f in folios)
    log_actividad(session['user_id'], 'MARCAR_REQUISICIONES_COMPLETAS',
                  f"Folios: {folios_txt}")
    flash(f"{len(folios)} requisición(es) marcada(s) como completas.", 'success')
    return redirect(request.referrer or url_for('requisiciones.index'))


@requisiciones_bp.route('/detalle/<int:rid>', methods=['GET', 'POST'])
@login_required
def detalle(rid):
    conn = get_db()
    if request.method == 'POST':
        f = request.form
        accion = f.get('accion')
        if accion == 'actualizar_seguimiento':
            orden_compra = (f.get('orden_compra') or '').strip() or None
            conn.execute("""
                UPDATE requisiciones SET orden_compra=?, no_factura=?, no_remision=?
                WHERE id=?
            """, (orden_compra, f.get('no_factura') or None, f.get('no_remision') or None, rid))
            if orden_compra:
                conn.execute("""
                    UPDATE material_por_pedir
                    SET orden_compra=?, updated_at=?
                    WHERE requisicion_id=?
                      AND COALESCE(solicitado,0)=1
                      AND (orden_compra IS NULL OR orden_compra='' OR orden_compra=requisicion_folio)
                """, (orden_compra, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), rid))
            conn.commit()
            log_actividad(session['user_id'], 'SEGUIMIENTO_REQUISICION', f"ID: {rid}")
            flash('Datos de seguimiento actualizados.', 'success')
        elif accion == 'actualizar_recepcion':
            items = conn.execute(
                "SELECT id, producto_id FROM requisicion_items WHERE requisicion_id=? ORDER BY orden",
                (rid,)).fetchall()
            for it in items:
                item_id = it['id']
                if f.get(f"quitar_manual_{item_id}"):
                    conn.execute("""
                        UPDATE requisicion_items
                        SET recepcion_manual=0, recepcion_manual_at=NULL,
                            recepcion_manual_usuario_id=NULL,
                            cantidad_recibida=CASE WHEN producto_id IS NULL THEN cantidad_recibida ELSE 0 END
                        WHERE id=?
                    """, (item_id,))
                    continue

                manual_val = f.get(f"recibido_manual_{item_id}")
                if manual_val is not None and manual_val.strip() != '':
                    try:
                        cantidad_manual = float(manual_val)
                    except ValueError:
                        continue
                    conn.execute("""
                        UPDATE requisicion_items
                        SET cantidad_recibida=?, recepcion_manual=1,
                            recepcion_manual_at=?, recepcion_manual_usuario_id=?
                        WHERE id=?
                    """, (
                        cantidad_manual, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        session['user_id'], item_id
                    ))
                    continue

                if it['producto_id'] is None:
                    val = f.get(f"recibido_{item_id}")
                    if val is not None and val.strip() != '':
                        try:
                            cantidad = float(val)
                        except ValueError:
                            continue
                        _registrar_recepcion(conn, item_id, cantidad, session['user_id'])
            conn.commit()
            log_actividad(session['user_id'], 'RECEPCION_REQUISICION', f"ID: {rid}")
            flash('Recepción actualizada.', 'success')
            requisicion_actual = conn.execute("SELECT * FROM requisiciones WHERE id=?", (rid,)).fetchone()
            items_actuales = conn.execute(
                "SELECT * FROM requisicion_items WHERE requisicion_id=? ORDER BY orden", (rid,)).fetchall()
            entradas_rel = _entradas_relacionadas(conn, requisicion_actual)
            estado_calc = _calcular_estado(_enriquecer_items(items_actuales, entradas_rel))
            _sincronizar_estado(conn, rid, estado_calc, entradas_rel)
        elif accion == 'recibir_todo':
            # Solo aplica a partidas de texto libre; registra como entrega el
            # remanente pendiente de cada una (con fecha del momento), en vez de
            # solo poner cantidad_recibida=cantidad (para no perder el historial).
            items = conn.execute("""
                SELECT id, cantidad, cantidad_recibida FROM requisicion_items
                WHERE requisicion_id=? AND producto_id IS NULL
            """, (rid,)).fetchall()
            for it in items:
                pendiente = (it['cantidad'] or 0) - (it['cantidad_recibida'] or 0)
                if pendiente > 0:
                    _registrar_recepcion(conn, it['id'], pendiente, session['user_id'])
            conn.commit()
            log_actividad(session['user_id'], 'RECEPCION_TOTAL_REQUISICION', f"ID: {rid}")
            flash('Se marcaron como recibidas las partidas de texto libre. Las ligadas a un producto del catálogo se calculan automáticamente según las entradas registradas.', 'success')
            requisicion_actual = conn.execute("SELECT * FROM requisiciones WHERE id=?", (rid,)).fetchone()
            items_actuales = conn.execute(
                "SELECT * FROM requisicion_items WHERE requisicion_id=? ORDER BY orden", (rid,)).fetchall()
            entradas_rel = _entradas_relacionadas(conn, requisicion_actual)
            estado_calc = _calcular_estado(_enriquecer_items(items_actuales, entradas_rel))
            _sincronizar_estado(conn, rid, estado_calc, entradas_rel)
        elif accion == 'cambiar_estado':
            # Nueva acción: cambiar estado a pendiente, revision, parcial o completa
            nuevo_estado = f.get('nuevo_estado', '').lower()
            if nuevo_estado in ['pendiente', 'revision', 'parcial', 'completa']:
                conn.execute("UPDATE requisiciones SET estado=? WHERE id=?", (nuevo_estado, rid))
                conn.commit()
                estado_label = {'pendiente': '⏳ Pendiente', 'revision': '⚡ Revisión', 
                              'parcial': 'Parcial', 'completa': 'Completa'}.get(nuevo_estado, nuevo_estado)
                log_actividad(session['user_id'], 'CAMBIAR_ESTADO_REQUISICION', f"ID: {rid} | Estado: {nuevo_estado}")
                flash(f'Estado actualizado a: {estado_label}', 'success')
            else:
                flash(f'Estado inválido: {nuevo_estado}', 'danger')
        conn.close()
        return redirect(url_for('requisiciones.detalle', rid=rid))

    requisicion = conn.execute("SELECT * FROM requisiciones WHERE id=?", (rid,)).fetchone()
    if not requisicion:
        flash('Requisición no encontrada.', 'danger')
        conn.close()
        return redirect(url_for('requisiciones.index'))
    items = conn.execute(
        "SELECT ri.*, p.codigo, p.descripcion as producto_descripcion FROM requisicion_items ri "
        "LEFT JOIN productos p ON ri.producto_id = p.id "
        "WHERE ri.requisicion_id=? ORDER BY ri.orden", (rid,)).fetchall()

    # Historial de entregas parciales (con fecha automática) de las partidas de texto libre
    recepciones_por_item = {}
    for it in items:
        if it['producto_id'] is None:
            recs = conn.execute("""
                SELECT cantidad, fecha FROM requisicion_item_recepciones
                WHERE requisicion_item_id=? ORDER BY fecha
            """, (it['id'],)).fetchall()
            if recs:
                recepciones_por_item[it['id']] = recs

    entradas_relacionadas = _entradas_relacionadas(conn, requisicion)
    items_enriquecidos = _enriquecer_items(items, entradas_relacionadas)
    estado = _calcular_estado(items_enriquecidos)

    # Mantener sincronizada la columna 'estado' con lo que realmente se ha recibido
    _sincronizar_estado(conn, rid, estado, entradas_relacionadas)
    requisicion = conn.execute("SELECT * FROM requisiciones WHERE id=?", (rid,)).fetchone()

    conn.close()
    return render_template('requisiciones/detalle.html', requisicion=requisicion,
                           items=items_enriquecidos, estado=estado,
                           entradas_relacionadas=entradas_relacionadas,
                           recepciones_por_item=recepciones_por_item,
                           unidad_para_cantidad=_unidad_para_cantidad)


@requisiciones_bp.route('/imprimir/<int:rid>')
@login_required
def imprimir(rid):
    """Llena el formato real (REQUISICIONES.xlsm, hoja FORM-REQUISICION) con los datos de
    esta requisición y lo abre directo en Excel en la PC de Ricardo (ruta fija en el
    escritorio). No se toca ninguna dimensión, combinación de celdas ni el diseño del
    formato — solo se escriben los valores en las celdas de captura:
    Q3=fecha requisición, Q4=fecha en que se necesita, P6:P15=cantidad, Q6:Q15=unidad,
    R6:R15=descripción, Q20=folio, R20=detalle/motivo, Q21=solicitante.
    (Q3:R3, Q4:R4 y Q21:R21 están combinadas, por eso se escribe en la celda ancla Q.)
    Compras y Autorizó ya vienen fijos en el formato de Excel, no se tocan desde aquí."""
    conn = get_db()
    requisicion = conn.execute("SELECT * FROM requisiciones WHERE id=?", (rid,)).fetchone()
    if not requisicion:
        conn.close()
        flash('Requisición no encontrada.', 'danger')
        return redirect(url_for('requisiciones.index'))
    items = conn.execute(
        "SELECT * FROM requisicion_items WHERE requisicion_id=? ORDER BY orden", (rid,)).fetchall()
    conn.close()

    origen = RUTA_LOCAL_XLSM if os.path.exists(RUTA_LOCAL_XLSM) else PLANTILLA_XLSM
    if not os.path.exists(origen):
        flash('No se encontró el formato REQUISICIONES.xlsm ni en la ruta local ni en el servidor.', 'danger')
        return redirect(url_for('requisiciones.detalle', rid=rid))

    wb = openpyxl.load_workbook(origen, keep_vba=True)
    ws = wb['FORM-REQUISICION']

    def _fecha(valor):
        if not valor:
            return None
        try:
            return datetime.strptime(valor[:10], '%Y-%m-%d')
        except (ValueError, TypeError):
            return valor

    ws['Q3'] = _fecha(requisicion['fecha_requisicion'])
    ws['Q4'] = _fecha(requisicion['fecha_necesita'])
    ws['Q20'] = requisicion['folio']
    ws['R20'] = requisicion['asunto'] or ''
    ws['Q21'] = requisicion['solicitante'] or ''

    fila_inicial = 6
    for i in range(MAX_ITEMS):
        fila = fila_inicial + i
        if i < len(items):
            it = items[i]
            es_informativo = float(it['cantidad'] or 0) <= 0
            ws[f'P{fila}'] = None if es_informativo else it['cantidad']
            ws[f'Q{fila}'] = None if es_informativo else _unidad_para_cantidad(it['unidad'], it['cantidad'])
            ws[f'R{fila}'] = it['descripcion']
        else:
            ws[f'P{fila}'] = None
            ws[f'Q{fila}'] = None
            ws[f'R{fila}'] = None

    log_actividad(session['user_id'], 'IMPRIMIR_REQUISICION', f"ID: {rid} | Folio: AL-{requisicion['folio']}")

    carpeta_local = os.path.dirname(RUTA_LOCAL_XLSM)
    if platform.system() == 'Windows' and os.path.isdir(carpeta_local):
        # Corriendo en la PC de Ricardo: sobreescribe el archivo de esa ruta y lo abre en Excel.
        try:
            wb.save(RUTA_LOCAL_XLSM)
            os.startfile(RUTA_LOCAL_XLSM)
            flash(f'Se abrió {RUTA_LOCAL_XLSM} en Excel con los datos de la requisición AL-{requisicion["folio"]}.', 'success')
            return redirect(url_for('requisiciones.detalle', rid=rid))
        except PermissionError:
            flash('No se pudo guardar el formato: parece que el archivo REQUISICIONES.xlsm ya está abierto en Excel. Ciérralo e intenta de nuevo.', 'danger')
            return redirect(url_for('requisiciones.detalle', rid=rid))
        except Exception:
            pass  # cae al fallback de descarga

    # Si no se pudo abrir localmente (ej. accediendo desde otra PC o por internet),
    # se descarga el archivo en su lugar.
    import io
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True,
                     download_name=f"Requisicion_AL-{requisicion['folio']}.xlsm",
                     mimetype='application/vnd.ms-excel.sheet.macroEnabled.12')


@requisiciones_bp.route('/imprimir_hoja/<int:rid>')
@login_required
def imprimir_hoja(rid):
    """Muestra una hoja imprimible en navegador para imprimir sobre formato fisico."""
    conn = get_db()
    requisicion = conn.execute("SELECT * FROM requisiciones WHERE id=?", (rid,)).fetchone()
    if not requisicion:
        conn.close()
        flash('Requisición no encontrada.', 'danger')
        return redirect(url_for('requisiciones.index'))

    items = conn.execute(
        "SELECT * FROM requisicion_items WHERE requisicion_id=? ORDER BY orden", (rid,)
    ).fetchall()
    conn.close()

    log_actividad(session['user_id'], 'IMPRIMIR_HOJA_REQUISICION',
                  f"ID: {rid} | Folio: AL-{requisicion['folio']}")

    return render_template(
        'requisiciones/imprimir_hoja.html',
        requisicion=requisicion,
        items=items,
        max_items=MAX_ITEMS,
        unidad_para_cantidad=_unidad_para_cantidad,
        fecha_requisicion=_fecha_impresion(requisicion['fecha_requisicion']),
        fecha_necesita=_fecha_impresion(requisicion['fecha_necesita'] or _sumar_dias_fecha(requisicion['fecha_requisicion'], 3)),
        auto_print=request.args.get('auto') == '1'
    )


@requisiciones_bp.route('/api/por_folio/<int:folio>')
@login_required
def api_por_folio(folio):
    """Para el menú que aparece en la captura de Entradas al escribir un Nº de requisición:
    regresa las partidas de esa requisición con lo solicitado, lo ya recibido y lo pendiente,
    más información de ENTRADAS RELACIONADAS, para poder elegir cuál se está recibiendo en esta factura."""
    conn = get_db()
    requisicion = conn.execute("SELECT * FROM requisiciones WHERE folio=?", (folio,)).fetchone()
    if not requisicion:
        conn.close()
        return {"encontrada": False}
    items = conn.execute(
        "SELECT ri.*, p.codigo, p.descripcion as producto_descripcion, p.unidad_medida as producto_unidad "
        "FROM requisicion_items ri LEFT JOIN productos p ON ri.producto_id = p.id "
        "WHERE ri.requisicion_id=? ORDER BY ri.orden", (requisicion['id'],)).fetchall()
    
    # Obtener entradas relacionadas
    entradas_rel = _entradas_relacionadas(conn, requisicion)
    
    # Enriquecer items con cantidades recibidas
    items_enriquecidos = _enriquecer_items(items, entradas_rel)
    
    # Calcular estado general de la requisición
    estado_general = _calcular_estado(items_enriquecidos)
    
    conn.close()

    resultado = []
    for it in items_enriquecidos:
        es_informativo = bool(it.get('informativo'))
        pendiente = max(0, it['cantidad'] - it['recibido_calc'])
        resultado.append({
            'producto_id': it['producto_id'],
            'codigo': it['codigo'],
            'descripcion': it['descripcion'],
            'unidad': _unidad_para_cantidad(it['unidad'], it['cantidad']),
            'cantidad': it['cantidad'],
            'recibido': it['recibido_calc'],
            'pendiente': pendiente,
            'completa': (not es_informativo) and it['recibido_calc'] >= it['cantidad'],
            'ligada_catalogo': bool(it['producto_id']),
            'informativo': es_informativo,
        })
    
    # Resumen de entradas relacionadas
    entradas_resumen = []
    for e in entradas_rel[:5]:  # Máximo 5 últimas entradas
        entradas_resumen.append({
            'fecha': e['fecha'][:10],
            'factura': e['no_factura'] or '—',
            'cantidad_total': e['cantidad'],
            'codigo_producto': e['codigo'],
        })
    
    return {
        "encontrada": True,
        "folio": requisicion['folio'],
        "asunto": requisicion['asunto'],
        "solicitante": requisicion['solicitante'],
        "departamento": requisicion['departamento'],
        "estado_general": estado_general,  # 'completa', 'parcial', 'pendiente'
        "items": resultado,
        "entradas_relacionadas": entradas_resumen,
    }


@requisiciones_bp.route('/api/material-pendiente/<int:producto_id>')
@login_required
def api_material_pendiente(producto_id):
    conn = get_db()
    pendiente = _material_pendiente_para_producto(conn, producto_id)
    conn.close()
    if not pendiente:
        return jsonify({'encontrado': False})
    return jsonify({'encontrado': True, **pendiente})


@requisiciones_bp.route('/folio', methods=['POST'])
@login_required
def editar_folio():
    """Corrige el contador global de folios de requisición (ej. al empezar a usar el
    sistema, para que el siguiente folio generado siga desde el número real en papel)."""
    folio_nuevo = request.form.get('folio_nuevo')
    if not folio_nuevo or not folio_nuevo.isdigit():
        flash('El folio debe ser un número.', 'danger')
        return redirect(url_for('requisiciones.index'))
    set_folio_counter('requisicion', int(folio_nuevo))
    log_actividad(session['user_id'], 'EDITAR_FOLIO_REQUISICION', f"Nuevo consecutivo: {folio_nuevo}")
    flash(f'El próximo folio de requisición será AL-{int(folio_nuevo)+1}.', 'success')
    return redirect(url_for('requisiciones.index'))
