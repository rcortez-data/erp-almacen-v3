from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, Response
from routes.auth import login_required, rol_required
from database import get_db, log_actividad, generar_codigo_producto, generar_codigo_barras_producto, obtener_nombres_unidades
from constantes import CATEGORIAS_CON_MAQUINA, MAQUINAS
from datetime import datetime, date
from collections import defaultdict
import re
import unicodedata
import sqlite3
from barcode_utils import code128_svg

inventario_bp = Blueprint('inventario', __name__, url_prefix='/inventario')


@inventario_bp.route('/stock-caldera-2026', methods=['GET', 'POST'])
@login_required
@rol_required('admin')
def stock_caldera_2026():
    anio = date.today().year
    conn = get_db()
    filas = conn.execute("""
        SELECT p.id, p.codigo, p.descripcion, p.unidad_medida, p.stock_actual,
               COALESCE((SELECT cantidad FROM dashboard_consumo_inicio d
                         WHERE d.producto_id=p.id AND d.grupo='caldera' AND d.anio=?),0) AS inicio_anio,
               COALESCE((SELECT SUM(COALESCE(e.cantidad_piezas,e.cantidad)) FROM entradas e
                         WHERE e.producto_id=p.id AND strftime('%Y',COALESCE(e.fecha_vale,e.fecha))=?),0) AS entradas_anio,
               COALESCE((SELECT SUM(s.cantidad) FROM salidas s
                         WHERE s.producto_id=p.id AND strftime('%Y',COALESCE(s.fecha_vale,s.fecha))=?),0) AS salidas_anio
        FROM productos p JOIN bloque_productos bp ON bp.producto_id=p.id
        WHERE bp.bloque_id=2 AND p.activo=1 ORDER BY bp.orden, p.codigo
    """, (anio, str(anio), str(anio))).fetchall()
    filas = [dict(r) for r in filas]
    for fila in filas:
        fila['existencia_calculada'] = round(float(fila['inicio_anio']) + float(fila['entradas_anio']) - float(fila['salidas_anio']), 4)
        fila['diferencia'] = round(fila['existencia_calculada'] - float(fila['stock_actual'] or 0), 4)
    if request.method == 'POST':
        for fila in filas:
            conn.execute("UPDATE productos SET stock_actual=? WHERE id=?", (fila['existencia_calculada'], fila['id']))
        conn.commit()
        log_actividad(session['user_id'], 'RECALCULAR_STOCK_CALDERA', f'Año: {anio} | Productos: {len(filas)}')
        conn.close()
        flash(f'Se actualizaron {len(filas)} stocks de Caldera con el cálculo de {anio}.', 'success')
        return redirect(url_for('inventario.stock_caldera_2026'))
    conn.close()
    return render_template('inventario/stock_caldera_2026.html', filas=filas, anio=anio)


def normalizar_descripcion_duplicado(texto):
    """Firma comparable que ignora acentos, signos y espacios accidentales."""
    texto = unicodedata.normalize('NFKD', texto or '')
    texto = ''.join(c for c in texto if not unicodedata.combining(c)).lower()
    texto = texto.replace('×', 'x')
    return ' '.join(re.findall(r'[a-z0-9]+', texto))


def normalizar_codigo_barras(texto):
    """Normaliza códigos internos para evitar diferencias por espacios o formato."""
    return re.sub(r'\s+', '', str(texto or '')).strip().upper()


def construir_busqueda_dinamica(texto, campos):
    """
    Divide el texto en palabras y exige que TODAS aparezcan (en cualquier
    orden, en cualquiera de los campos indicados). Así 'tornillo 1/4'
    encuentra 'TORNILLO ALLEN 1/4 X 2' aunque no sea coincidencia exacta.
    """
    palabras = [p for p in texto.strip().split() if p]
    condiciones = []
    params = []
    for palabra in palabras:
        sub_cond = " OR ".join([f"{c} LIKE ?" for c in campos])
        condiciones.append(f"({sub_cond})")
        params += [f"%{palabra}%"] * len(campos)
    return " AND ".join(condiciones), params


@inventario_bp.route('/')
@login_required
def index():
    q = request.args.get('q', '').strip()
    q_ubi = request.args.get('q_ubi', '').strip()
    cat = request.args.get('cat', '')
    estado = request.args.get('estado', '')
    tipo_inventario = request.args.get('tipo', 'todos')  # catalogo, maquinados, todos
    pagina = request.args.get('pagina', 1, type=int)
    registros_por_pagina = 50
    
    conn = get_db()
    query = """
        SELECT p.*, COALESCE(c.nombre, p.categoria_nombre_historico) as categoria, 'catálogo' as tipo_inventario
        FROM productos p
        LEFT JOIN categorias c ON p.categoria_id=c.id
        WHERE p.activo=1
    """
    params = []
    
    # Filtrar por tipo si lo especifica
    # En la BD, diferenciamos por código o categoría si es necesario
    # Por ahora traemos todos
    
    if q:
        cond, cond_params = construir_busqueda_dinamica(
            q, ["p.codigo", "p.codigo_barras", "p.descripcion", "c.nombre"])
        if cond:
            query += f" AND {cond}"
            params += cond_params
    if q_ubi:
        cond, cond_params = construir_busqueda_dinamica(q_ubi, ["p.ubicacion", "p.departamento"])
        if cond:
            query += f" AND {cond}"
            params += cond_params
    if cat:
        query += " AND p.categoria_id=?"
        params.append(cat)
    if estado == 'contado':
        query += " AND p.estado_fisico='contado'"
    elif estado == 'faltante':
        query += " AND p.estado_fisico='faltante'"
    elif estado == 'sin_revisar':
        query += " AND (p.estado_fisico IS NULL OR p.estado_fisico='')"
    query += " ORDER BY p.codigo"
    
    productos_completo = conn.execute(query, params).fetchall()
    total_registros = len(productos_completo)
    total_paginas = (total_registros + registros_por_pagina - 1) // registros_por_pagina
    
    if pagina < 1:
        pagina = 1
    elif pagina > total_paginas and total_paginas > 0:
        pagina = total_paginas
    
    offset = (pagina - 1) * registros_por_pagina
    productos = productos_completo[offset:offset + registros_por_pagina]
    
    categorias = conn.execute("SELECT * FROM categorias ORDER BY LOWER(nombre)").fetchall()
    total_faltantes = conn.execute(
        "SELECT COUNT(*) FROM productos WHERE activo=1 AND estado_fisico='faltante'").fetchone()[0]
    total_stock_bajo = conn.execute(
        "SELECT COUNT(*) FROM productos WHERE activo=1 AND stock_actual <= stock_minimo AND stock_minimo > 0"
    ).fetchone()[0]
    total_contados = conn.execute(
        "SELECT COUNT(*) FROM productos WHERE activo=1 AND estado_fisico='contado'").fetchone()[0]
    total_sin_revisar = conn.execute("""
        SELECT COUNT(*) FROM productos
        WHERE activo=1 AND (estado_fisico IS NULL OR estado_fisico='')
    """).fetchone()[0]
    conn.close()
    return render_template('inventario/index.html', productos=productos,
                           categorias=categorias, q=q, q_ubi=q_ubi, cat=cat,
                           estado=estado, total_faltantes=total_faltantes,
                           total_stock_bajo=total_stock_bajo,
                           total_contados=total_contados,
                           total_sin_revisar=total_sin_revisar,
                           pagina_actual=pagina, total_paginas=total_paginas,
                           total_registros=total_registros, registros_pagina=len(productos),
                           tipo_inventario=tipo_inventario)


@inventario_bp.route('/duplicados')
@login_required
def duplicados():
    """Lista coincidencias de alta confianza sin modificar productos."""
    q = request.args.get('q', '').strip()
    pagina = max(request.args.get('pagina', 1, type=int), 1)
    grupos_por_pagina = 40
    conn = get_db()
    query = """
        SELECT p.id, p.codigo, p.descripcion, p.stock_actual, p.unidad_medida,
               p.ubicacion, p.departamento,
               COALESCE(c.nombre, p.categoria_nombre_historico) AS categoria
        FROM productos p
        LEFT JOIN categorias c ON p.categoria_id=c.id
        WHERE p.activo=1
    """
    params = []
    if q:
        query += " AND (LOWER(p.descripcion) LIKE LOWER(?) OR LOWER(p.codigo) LIKE LOWER(?) OR LOWER(p.codigo_barras) LIKE LOWER(?))"
        params.extend((f'%{q}%', f'%{q}%', f'%{q}%'))
    query += " ORDER BY LOWER(p.descripcion), p.codigo"
    productos = conn.execute(query, params).fetchall()
    conn.close()

    candidatos = defaultdict(list)
    for producto in productos:
        firma = normalizar_descripcion_duplicado(producto['descripcion'])
        if firma:
            candidatos[firma].append(producto)
    grupos = [
        {'firma': firma, 'productos': items, 'stock_total': sum(float(p['stock_actual'] or 0) for p in items)}
        for firma, items in candidatos.items() if len(items) > 1
    ]
    grupos.sort(key=lambda grupo: (-len(grupo['productos']), grupo['firma']))
    total_grupos = len(grupos)
    total_productos = sum(len(grupo['productos']) for grupo in grupos)
    total_paginas = max((total_grupos + grupos_por_pagina - 1) // grupos_por_pagina, 1)
    pagina = min(pagina, total_paginas)
    inicio = (pagina - 1) * grupos_por_pagina
    grupos = grupos[inicio:inicio + grupos_por_pagina]
    return render_template(
        'inventario/duplicados.html', grupos=grupos, q=q,
        total_grupos=total_grupos, total_productos=total_productos,
        pagina_actual=pagina, total_paginas=total_paginas,
    )


@inventario_bp.route('/api/buscar')
@login_required
def api_buscar():
    """Búsqueda dinámica de productos para autocompletado (usada en Entradas/Salidas)."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    conn = get_db()
    cond, params = construir_busqueda_dinamica(
        q, ["p.codigo", "p.codigo_barras", "p.descripcion", "p.departamento"])
    query = f"""
        SELECT p.id, p.codigo, p.codigo_barras, p.descripcion, p.categoria_id,
               COALESCE(c.nombre, p.categoria_nombre_historico) AS categoria,
               p.unidad_medida,
               p.stock_actual, p.precio_unitario, p.departamento, p.ubicacion,
               p.maquina, p.maquina_otro,
               p.unidad_compra, p.factor_conversion
        FROM productos p
        LEFT JOIN categorias c ON p.categoria_id=c.id
        WHERE p.activo=1 AND {cond}
        ORDER BY p.codigo
        LIMIT 25
    """
    productos = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(p) for p in productos])


@inventario_bp.route('/api/producto/<int:pid>')
@login_required
def api_producto(pid):
    """Devuelve los datos de un producto puntual (usado para preseleccionar tras registrar uno nuevo)."""
    conn = get_db()
    p = conn.execute("""
        SELECT p.id, p.codigo, p.codigo_barras, p.descripcion, p.categoria_id,
               COALESCE(c.nombre, p.categoria_nombre_historico) AS categoria,
               p.unidad_medida, p.stock_actual, p.precio_unitario, p.departamento, p.ubicacion,
               p.maquina, p.maquina_otro,
               unidad_compra, factor_conversion
        FROM productos p
        LEFT JOIN categorias c ON p.categoria_id=c.id
        WHERE p.id=?
    """, (pid,)).fetchone()
    conn.close()
    if not p:
        return jsonify({}), 404
    return jsonify(dict(p))


@inventario_bp.route('/codigo-barras/<int:pid>.svg')
@login_required
def codigo_barras_svg(pid):
    conn = get_db()
    producto = conn.execute(
        "SELECT codigo, codigo_barras FROM productos WHERE id=? AND activo=1",
        (pid,),
    ).fetchone()
    conn.close()
    if not producto:
        return Response("Producto no encontrado", status=404)
    codigo_barras = producto['codigo_barras'] or generar_codigo_barras_producto(producto['codigo'])
    incluir_texto = request.args.get('texto', '1') != '0'
    alto = request.args.get('alto', 58, type=int)
    return Response(code128_svg(codigo_barras, alto=alto, margen=2, incluir_texto=incluir_texto), mimetype='image/svg+xml')


@inventario_bp.route('/etiquetas')
@login_required
def etiquetas():
    ids = []
    for raw in request.args.getlist('ids'):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    q = request.args.get('q', '').strip()
    conn = get_db()
    params = []
    query = """
        SELECT id, codigo, codigo_barras, descripcion, ubicacion, unidad_medida
        FROM productos
        WHERE activo=1
    """
    if ids:
        placeholders = ",".join("?" for _ in ids)
        query += f" AND id IN ({placeholders})"
        params.extend(ids)
    elif q:
        cond, cond_params = construir_busqueda_dinamica(q, ["codigo", "codigo_barras", "descripcion", "ubicacion"])
        if cond:
            query += f" AND {cond}"
            params.extend(cond_params)
    else:
        query += " AND 1=0"
    query += " ORDER BY codigo"
    productos = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('inventario/etiquetas.html', productos=productos, q=q, ids=ids)


@inventario_bp.route('/etiquetas-tsc')
@login_required
def etiquetas_tsc():
    ids = []
    for raw in request.args.getlist('ids'):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    q = request.args.get('q', '').strip()
    conn = get_db()
    params = []
    query = """
        SELECT p.id, p.codigo, p.descripcion, p.ubicacion, p.unidad_medida,
               p.maquina, p.maquina_otro,
               le.cantidad, le.no_remision,
               COALESCE(NULLIF(pr.nombre_comercial, ''), pr.nombre, le.proveedor_nombre_historico) AS proveedor
        FROM productos p
        LEFT JOIN (
            SELECT e.*
            FROM entradas e
            INNER JOIN (
                SELECT producto_id, MAX(fecha) AS fecha_max
                FROM entradas
                WHERE producto_id IS NOT NULL
                GROUP BY producto_id
            ) ult ON ult.producto_id = e.producto_id AND ult.fecha_max = e.fecha
        ) le ON le.producto_id = p.id
        LEFT JOIN proveedores pr ON pr.id = le.proveedor_id
        WHERE p.activo=1
    """
    if ids:
        placeholders = ",".join("?" for _ in ids)
        query += f" AND p.id IN ({placeholders})"
        params.extend(ids)
    elif q:
        cond, cond_params = construir_busqueda_dinamica(
            q, ["p.codigo", "p.codigo_barras", "p.descripcion", "p.ubicacion", "le.no_remision"])
        if cond:
            query += f" AND {cond}"
            params.extend(cond_params)
    else:
        query += " AND 1=0"
    query += " ORDER BY p.codigo"
    productos = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('inventario/etiquetas_tsc.html', productos=productos, q=q, ids=ids)


@inventario_bp.route('/movil')
@login_required
def movil():
    conn = get_db()
    areas_lista = conn.execute("SELECT nombre FROM areas WHERE activo=1 ORDER BY LOWER(nombre)").fetchall()
    conn.close()
    return render_template('inventario/movil.html', areas_lista=areas_lista, maquinas=MAQUINAS)


@inventario_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@rol_required('admin')
def nuevo():
    conn = get_db()
    categorias = conn.execute("SELECT * FROM categorias ORDER BY LOWER(nombre)").fetchall()
    unidades = obtener_nombres_unidades(conn)
    departamentos = [a['nombre'] for a in conn.execute("SELECT nombre FROM areas WHERE activo=1 ORDER BY LOWER(nombre)").fetchall()]
    origen = request.args.get('origen') or request.form.get('origen', '')
    if request.method == 'POST':
        f = request.form
        ubicacion = (f.get('ubicacion') or '').strip()
        if len(ubicacion) < 6:
            flash('La ubicación es obligatoria y debe tener al menos 6 caracteres.', 'danger')
            conn.close()
            return render_template('inventario/form.html', categorias=categorias, producto=None,
                                   origen=origen, maquinas=MAQUINAS, departamentos=departamentos,
                                   unidades=unidades,
                                   categorias_con_maquina=CATEGORIAS_CON_MAQUINA)
        usa_conversion = f.get('usa_conversion') == 'on'
        unidad_compra = f.get('unidad_compra') if usa_conversion else None
        factor_conversion = float(f['factor_conversion']) if usa_conversion and f.get('factor_conversion') else None
        try:
            codigo = generar_codigo_producto()
            codigo_barras = normalizar_codigo_barras(generar_codigo_barras_producto(codigo))

            # Validación amigable antes del INSERT. La restricción UNIQUE se
            # conserva como última protección ante altas simultáneas.
            existente = conn.execute(
                """SELECT codigo, descripcion FROM productos
                   WHERE UPPER(REPLACE(codigo_barras, ' ', ''))=?""",
                (codigo_barras,)
            ).fetchone()
            if existente:
                flash(
                    f'El código de barras {codigo_barras} ya está registrado '
                    f'en el producto {existente["codigo"]}: {existente["descripcion"]}.',
                    'warning'
                )
                conn.close()
                return render_template('inventario/form.html', categorias=categorias, producto=None,
                                       origen=origen, maquinas=MAQUINAS, departamentos=departamentos,
                                       unidades=unidades,
                                       categorias_con_maquina=CATEGORIAS_CON_MAQUINA)
            conn.execute("""
                INSERT INTO productos (codigo, codigo_barras, descripcion, categoria_id, unidad_medida, ubicacion, departamento,
                                        maquina, maquina_otro, unidad_compra, factor_conversion, stock_minimo, precio_unitario)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (codigo, codigo_barras, f['descripcion'], f.get('categoria_id') or None,
                  f['unidad_medida'], ubicacion, f.get('departamento') or None,
                  f.get('maquina') or None, f.get('maquina_otro') or None,
                  unidad_compra, factor_conversion,
                  float(f.get('stock_minimo') or 0),
                  float(f.get('precio_unitario') or 0)))
            conn.commit()
            fila = conn.execute("SELECT id FROM productos WHERE codigo=?", (codigo,)).fetchone()
            nuevo_id = fila['id']
            log_actividad(session['user_id'], 'NUEVO_PRODUCTO', f"Código: {codigo}")
            if origen == 'entradas':
                flash(f'Producto {codigo} registrado. Ahora captura la cantidad para agregarlo a la entrada.', 'success')
                return redirect(url_for('entradas.nuevo', agregar=nuevo_id))
            if f.get('accion') == 'otro':
                flash(f'Producto {codigo} registrado. Puedes registrar el siguiente.', 'success')
                return redirect(url_for('inventario.nuevo'))
            flash(f'Producto {codigo} registrado correctamente.', 'success')
            return redirect(url_for('inventario.index'))
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if 'codigo_barras' in str(e).lower():
                flash(
                    f'El código de barras {codigo_barras} ya fue registrado por '
                    'otro usuario. Verifique el producto existente.',
                    'warning'
                )
            else:
                flash('No fue posible registrar el producto porque existe un dato duplicado.', 'danger')
        except Exception:
            conn.rollback()
            flash('No fue posible registrar el producto. Verifique los datos e inténtelo nuevamente.', 'danger')
    conn.close()
    return render_template('inventario/form.html', categorias=categorias, producto=None, origen=origen,
                           maquinas=MAQUINAS, departamentos=departamentos, unidades=unidades,
                           categorias_con_maquina=CATEGORIAS_CON_MAQUINA)


@inventario_bp.route('/editar/<int:pid>', methods=['GET', 'POST'])
@login_required
@rol_required('admin')
def editar(pid):
    conn = get_db()
    producto = conn.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()
    categorias = conn.execute("SELECT * FROM categorias ORDER BY LOWER(nombre)").fetchall()
    unidades = obtener_nombres_unidades(conn)
    departamentos = [a['nombre'] for a in conn.execute("SELECT nombre FROM areas WHERE activo=1 ORDER BY LOWER(nombre)").fetchall()]
    if not producto:
        flash('Producto no encontrado.', 'danger')
        return redirect(url_for('inventario.index'))
    if request.method == 'POST':
        f = request.form
        ubicacion = (f.get('ubicacion') or '').strip()
        if len(ubicacion) < 6:
            flash('La ubicación es obligatoria y debe tener al menos 6 caracteres.', 'danger')
            conn.close()
            return render_template('inventario/form.html', categorias=categorias, producto=producto,
                                   origen='', maquinas=MAQUINAS, departamentos=departamentos,
                                   unidades=unidades,
                                   categorias_con_maquina=CATEGORIAS_CON_MAQUINA)
        usa_conversion = f.get('usa_conversion') == 'on'
        unidad_compra = f.get('unidad_compra') if usa_conversion else None
        factor_conversion = float(f['factor_conversion']) if usa_conversion and f.get('factor_conversion') else None
        try:
            conn.execute("""
                UPDATE productos SET descripcion=?, categoria_id=?, unidad_medida=?,
                ubicacion=?, departamento=?, maquina=?, maquina_otro=?, unidad_compra=?, factor_conversion=?,
                stock_minimo=?, precio_unitario=? WHERE id=?
            """, (f['descripcion'], f.get('categoria_id') or None, f['unidad_medida'],
                  ubicacion, f.get('departamento') or None,
                  f.get('maquina') or None, f.get('maquina_otro') or None,
                  unidad_compra, factor_conversion,
                  float(f.get('stock_minimo') or 0),
                  float(f.get('precio_unitario') or 0), pid))
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_PRODUCTO', f"ID: {pid}")
            flash('Producto actualizado.', 'success')
            return redirect(url_for('inventario.index'))
        except Exception as e:
            conn.rollback()
            flash(f'Error: {str(e)}', 'danger')
    conn.close()
    return render_template('inventario/form.html', categorias=categorias, producto=producto, origen='',
                           maquinas=MAQUINAS, departamentos=departamentos, unidades=unidades,
                           categorias_con_maquina=CATEGORIAS_CON_MAQUINA)


def _dar_baja_producto(conn, pid, motivo='BAJA DIRECTA'):
    producto = conn.execute(
        "SELECT id, codigo, descripcion, activo FROM productos WHERE id=?", (pid,)
    ).fetchone()
    if not producto:
        return None
    if producto['activo']:
        quien = session.get('nombre') or session.get('username') or 'Sistema'
        ahora = datetime.now().strftime('%Y-%m-%d %H:%M')
        conn.execute("""
            UPDATE productos
            SET activo=0, baja_por=?, baja_folio=?, baja_fecha=?, estado_fisico=NULL
            WHERE id=?
        """, (quien, motivo, ahora, pid))
    return producto


@inventario_bp.route('/baja/<int:pid>', methods=['POST'])
@login_required
@rol_required('admin')
def baja(pid):
    conn = get_db()
    producto = _dar_baja_producto(conn, pid)
    if not producto:
        conn.close()
        flash('Producto no encontrado.', 'danger')
        return redirect(url_for('inventario.index'))
    conn.commit()
    conn.close()
    log_actividad(session['user_id'], 'BAJA_PRODUCTO',
                  f"Código: {producto['codigo']} | Descripción: {producto['descripcion']}")
    flash(f"Producto {producto['codigo']} dado de baja. Se guardaron usuario y fecha.", 'warning')
    return redirect(request.referrer or url_for('inventario.index'))


@inventario_bp.route('/baja-multiple', methods=['POST'])
@login_required
@rol_required('admin')
def baja_multiple():
    ids = request.form.getlist('ids')
    conn = get_db()
    bajas = []
    for pid_str in ids:
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        producto = _dar_baja_producto(conn, pid, 'BAJA MÚLTIPLE')
        if producto:
            bajas.append(producto['codigo'])
    conn.commit()
    conn.close()
    if bajas:
        log_actividad(session['user_id'], 'BAJA_PRODUCTOS_LOTE',
                      f"{len(bajas)} productos: {', '.join(bajas[:20])}")
        flash(f'{len(bajas)} producto(s) dados de baja. Se guardaron usuario y fecha.', 'success')
    if not ids:
        flash('No seleccionaste ningún producto.', 'warning')
    return redirect(request.referrer or url_for('inventario.index'))


@inventario_bp.route('/marcar/<int:pid>', methods=['POST'])
@login_required
def marcar_estado(pid):
    """
    Marca un producto como 'contado' (verde) o 'faltante' (rojo) durante el
    conteo físico, o lo regresa a 'sin revisar' si se manda 'limpiar'. Pensado
    para ir clic por clic mientras se cuenta el almacén, sin recargar la página.
    """
    estado = request.form.get('estado')
    if estado not in ('contado', 'faltante', 'limpiar'):
        return jsonify({'ok': False, 'error': 'estado inválido'}), 400
    valor = None if estado == 'limpiar' else estado
    conn = get_db()
    conn.execute("UPDATE productos SET estado_fisico=? WHERE id=?", (valor, pid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'estado': valor})


@inventario_bp.route('/stock-real/<int:pid>', methods=['POST'])
@login_required
def stock_real(pid):
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    stock_raw = (request.form.get('stock_real') or '').strip()
    motivo = (request.form.get('motivo') or '').strip()
    try:
        stock_nuevo = float(stock_raw)
    except ValueError:
        if es_ajax:
            return jsonify({'ok': False, 'error': 'Captura un stock real valido.'}), 400
        flash('Captura un stock real valido.', 'danger')
        return redirect(request.referrer or url_for('inventario.index'))
    if stock_nuevo < 0:
        if es_ajax:
            return jsonify({'ok': False, 'error': 'El stock real no puede ser negativo.'}), 400
        flash('El stock real no puede ser negativo.', 'danger')
        return redirect(request.referrer or url_for('inventario.index'))

    conn = get_db()
    producto = conn.execute(
        "SELECT id, codigo, descripcion, stock_actual, unidad_medida FROM productos WHERE id=? AND activo=1",
        (pid,),
    ).fetchone()
    if not producto:
        conn.close()
        if es_ajax:
            return jsonify({'ok': False, 'error': 'Producto no encontrado.'}), 404
        flash('Producto no encontrado.', 'danger')
        return redirect(request.referrer or url_for('inventario.index'))

    stock_anterior = float(producto['stock_actual'] or 0)
    diferencia = stock_nuevo - stock_anterior
    conn.execute(
        "UPDATE productos SET stock_actual=?, estado_fisico='contado' WHERE id=?",
        (stock_nuevo, pid),
    )
    conn.commit()
    conn.close()

    detalle = (
        f"Producto: {producto['codigo']} | Stock anterior: {stock_anterior:g} | "
        f"Stock real: {stock_nuevo:g} | Diferencia: {diferencia:g}"
    )
    if motivo:
        detalle += f" | Nota: {motivo}"
    log_actividad(session['user_id'], 'FIJAR_STOCK_REAL', detalle)
    if es_ajax:
        return jsonify({
            'ok': True,
            'stock': stock_nuevo,
            'stock_label': f'{stock_nuevo:g}',
            'unidad': producto['unidad_medida'],
            'estado': 'contado',
            'mensaje': f"Stock real de {producto['codigo']} actualizado a {stock_nuevo:g} {producto['unidad_medida']}.",
        })
    flash(
        f"Stock real de {producto['codigo']} actualizado a {stock_nuevo:g} {producto['unidad_medida']}.",
        'success',
    )
    return redirect(request.referrer or url_for('inventario.index'))


@inventario_bp.route('/bajas')
@login_required
def bajas():
    """
    Historial de productos dados de baja (activo=0): quién, cuándo y con qué
    folio/motivo. Incluye tanto las bajas manuales (con folio/motivo capturado)
    como las bajas masivas del conteo físico (folio 'CONTEO FISICO').
    """
    conn = get_db()
    productos = conn.execute("""
        SELECT * FROM productos WHERE activo=0 ORDER BY baja_fecha DESC
    """).fetchall()
    conn.close()
    return render_template('inventario/bajas.html', productos=productos)


@inventario_bp.route('/eliminar-faltantes', methods=['POST'])
@login_required
@rol_required('admin')
def eliminar_faltantes():
    """
    Da de baja de un solo golpe TODOS los productos marcados como 'faltante'
    durante el conteo físico. Es el paso final de la depuración: cuentas
    físicamente, marcas lo que no encontraste con la X, y al terminar le das
    aquí para darlos de baja.

    A diferencia del borrado físico, esto SIEMPRE funciona (tengan o no
    movimientos registrados) porque no borra nada: solo desactiva el producto
    (activo=0) y registra quién y cuándo, igual que 'Dar de baja' individual,
    pero sin pedir folio ni motivo (un solo clic).
    """
    conn = get_db()
    ids = [r['id'] for r in conn.execute(
        "SELECT id FROM productos WHERE estado_fisico='faltante'").fetchall()]
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M')
    quien = session.get('nombre') or session.get('username') or 'Sistema'
    for pid in ids:
        conn.execute("""
            UPDATE productos
            SET activo=0, baja_por=?, baja_folio=?, baja_fecha=?, estado_fisico=NULL
            WHERE id=?
        """, (quien, 'CONTEO FISICO', ahora, pid))
    conn.commit()
    if ids:
        log_actividad(session['user_id'], 'BAJA_FALTANTES',
                      f"{len(ids)} productos dados de baja por conteo físico")
        flash(f'{len(ids)} producto(s) marcados con X dados de baja.', 'success')
    else:
        flash('No hay productos marcados con X.', 'warning')
    conn.close()
    return redirect(request.referrer or url_for('inventario.index'))


@inventario_bp.route('/movimientos/<int:pid>')
@login_required
def movimientos(pid):
    conn = get_db()
    producto = conn.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()
    entradas = conn.execute("""
        SELECT 'Entrada' as tipo, e.folio, e.cantidad, e.fecha, u.nombre as usuario,
               e.no_factura, e.no_requisicion, e.orden_compra, e.no_remision
        FROM entradas e LEFT JOIN usuarios u ON e.usuario_id=u.id
        WHERE e.producto_id=? ORDER BY e.fecha DESC
    """, (pid,)).fetchall()
    salidas = conn.execute("""
        SELECT 'Salida' as tipo, s.folio, s.cantidad, s.fecha, u.nombre as usuario,
               s.responsable, s.observaciones
        FROM salidas s LEFT JOIN usuarios u ON s.usuario_id=u.id
        WHERE s.producto_id=? ORDER BY s.fecha DESC
    """, (pid,)).fetchall()
    conn.close()
    return render_template('inventario/movimientos.html',
                           producto=producto, entradas=entradas, salidas=salidas)
