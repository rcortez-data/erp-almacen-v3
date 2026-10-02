import json
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from database import get_db, log_actividad, obtener_nombres_unidades
from routes.auth import login_required
from routes.inventario import construir_busqueda_dinamica
from routes.requisiciones import MAX_ITEMS, _asegurar_tabla_borradores


material_por_pedir_bp = Blueprint('material_por_pedir', __name__, url_prefix='/material-por-pedir')


def _normalizar_estado_pedido(valor):
    return valor if valor in ('pendiente', 'pedido', 'urgente', 'normal') else 'todos'


def _normalizar_prioridad(valor):
    return 'urgente' if valor == 'urgente' else 'normal'


def _producto(conn, producto_id):
    if not producto_id:
        return None
    return conn.execute(
        "SELECT id, codigo, descripcion, unidad_medida, stock_actual FROM productos WHERE id=?",
        (producto_id,)
    ).fetchone()


@material_por_pedir_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    conn = get_db()
    unidades = obtener_nombres_unidades(conn)

    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'agregar':
            producto_id = request.form.get('producto_id') or None
            producto = _producto(conn, producto_id)
            descripcion = (request.form.get('descripcion') or '').strip()
            codigo = (request.form.get('codigo') or '').strip() or None
            unidad = (request.form.get('unidad') or '').strip() or None
            if producto:
                descripcion = descripcion or producto['descripcion']
                codigo = producto['codigo']
                unidad = unidad or producto['unidad_medida']
            cantidad = float(request.form.get('cantidad') or 0)
            prioridad = _normalizar_prioridad(request.form.get('prioridad'))
            motivo = (request.form.get('motivo') or '').strip() or None
            if not descripcion:
                flash('Captura un producto o una descripción del material.', 'danger')
            else:
                conn.execute("""
                    INSERT INTO material_por_pedir
                    (producto_id, codigo, descripcion, cantidad, unidad, prioridad, motivo, usuario_id, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (
                    int(producto_id) if producto_id else None,
                    codigo, descripcion, cantidad, unidad, prioridad, motivo,
                    session.get('user_id'), datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ))
                conn.commit()
                log_actividad(session.get('user_id'), 'MATERIAL_POR_PEDIR',
                              f"Agregado: {codigo or '-'} {descripcion} | Cantidad: {cantidad} {unidad or ''}")
                flash('Material agregado a pendientes por pedir.', 'success')
                conn.close()
                return redirect(url_for('material_por_pedir.index'))

        elif accion == 'marcar_pedido':
            item_id = request.form.get('id')
            orden_compra = (request.form.get('orden_compra') or '').strip() or None
            notas_pedido = (request.form.get('notas_pedido') or '').strip() or None
            conn.execute("""
                UPDATE material_por_pedir
                SET solicitado=1, fecha_solicitado=?, orden_compra=?, notas_pedido=?,
                    pedido_por_usuario_id=?, updated_at=?
                WHERE id=?
            """, (
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), orden_compra, notas_pedido,
                session.get('user_id'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), item_id
            ))
            conn.commit()
            log_actividad(session.get('user_id'), 'MATERIAL_PEDIDO', f"Pendiente ID: {item_id} | OC: {orden_compra or '-'}")
            flash('Material marcado como pedido.', 'success')
            conn.close()
            return redirect(url_for('material_por_pedir.index', estado=request.args.get('estado', 'todos')))

        elif accion == 'reabrir':
            item_id = request.form.get('id')
            conn.execute("""
                UPDATE material_por_pedir
                SET solicitado=0, fecha_solicitado=NULL, orden_compra=NULL, notas_pedido=NULL,
                    pedido_por_usuario_id=NULL, requisicion_id=NULL, requisicion_folio=NULL, updated_at=?
                WHERE id=?
            """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), item_id))
            conn.commit()
            log_actividad(session.get('user_id'), 'MATERIAL_PEDIDO_REABIERTO', f"Pendiente ID: {item_id}")
            flash('Material regresado a pendientes.', 'warning')
            conn.close()
            return redirect(url_for('material_por_pedir.index', estado=request.args.get('estado', 'todos')))

        elif accion == 'eliminar':
            item_id = request.form.get('id')
            conn.execute("DELETE FROM material_por_pedir WHERE id=?", (item_id,))
            conn.commit()
            log_actividad(session.get('user_id'), 'ELIMINAR_MATERIAL_POR_PEDIR', f"Pendiente ID: {item_id}")
            flash('Registro eliminado.', 'success')
            conn.close()
            return redirect(url_for('material_por_pedir.index'))

        elif accion == 'crear_requisicion':
            ids = []
            for raw in request.form.getlist('seleccionados'):
                try:
                    ids.append(int(raw))
                except (TypeError, ValueError):
                    continue
            ids = list(dict.fromkeys(ids))
            if not ids:
                flash('Selecciona al menos un material pendiente.', 'warning')
                conn.close()
                return redirect(url_for('material_por_pedir.index', estado=request.args.get('estado', 'pendiente')))
            if len(ids) > MAX_ITEMS:
                flash(f'Sólo puedes mandar máximo {MAX_ITEMS} materiales a una requisición.', 'danger')
                conn.close()
                return redirect(url_for('material_por_pedir.index', estado=request.args.get('estado', 'pendiente')))

            placeholders = ','.join('?' for _ in ids)
            filas = conn.execute(f"""
                SELECT m.*, p.codigo AS producto_codigo, p.descripcion AS producto_descripcion,
                       p.unidad_medida AS unidad_producto
                FROM material_por_pedir m
                LEFT JOIN productos p ON p.id=m.producto_id
                WHERE m.id IN ({placeholders}) AND COALESCE(m.solicitado,0)=0
            """, ids).fetchall()
            por_id = {fila['id']: fila for fila in filas}
            seleccionados = [por_id[item_id] for item_id in ids if item_id in por_id]
            if not seleccionados:
                flash('Los materiales seleccionados ya están marcados como pedidos o no existen.', 'warning')
                conn.close()
                return redirect(url_for('material_por_pedir.index', estado=request.args.get('estado', 'pendiente')))

            hoy = date.today()
            datos = {
                'fecha_requisicion': hoy.isoformat(),
                'fecha_necesita': (hoy + timedelta(days=3)).isoformat(),
                'solicitante': '',
                'asunto': '',
                'observaciones': '',
                '_origen': 'material_por_pedir',
                '_guardado': datetime.now().isoformat(),
            }
            for idx, fila in enumerate(seleccionados, start=1):
                datos[f'cantidad_{idx}'] = str(fila['cantidad'] or '')
                datos[f'unidad_{idx}'] = fila['unidad'] or fila['unidad_producto'] or ''
                datos[f'descripcion_{idx}'] = fila['descripcion'] or ''
                datos[f'producto_id_{idx}'] = str(fila['producto_id'] or '')
                datos[f'material_pedir_id_{idx}'] = str(fila['id'])
                if fila['producto_id']:
                    codigo = fila['producto_codigo'] or fila['codigo'] or ''
                    descripcion = fila['producto_descripcion'] or fila['descripcion'] or ''
                    datos[f'buscador_cat_{idx}'] = f"{codigo} — {descripcion}".strip(' —')
                elif fila['codigo']:
                    datos[f'buscador_cat_{idx}'] = fila['codigo']

            _asegurar_tabla_borradores(conn)
            conn.execute("""
                INSERT INTO requisicion_borradores (usuario_id, datos_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(usuario_id) DO UPDATE SET
                    datos_json=excluded.datos_json,
                    updated_at=CURRENT_TIMESTAMP
            """, (session['user_id'], json.dumps(datos, ensure_ascii=False)))
            conn.commit()
            log_actividad(session.get('user_id'), 'MATERIAL_A_REQUISICION',
                          f"Pendientes: {', '.join(str(f['id']) for f in seleccionados)}")
            conn.close()
            flash(f'Se preparó una requisición con {len(seleccionados)} material(es). Revísala y guarda.', 'success')
            return redirect(url_for('requisiciones.nuevo', desde_material=1))

    q = request.args.get('q', '').strip()
    estado = _normalizar_estado_pedido(request.args.get('estado', 'todos'))
    prioridad = request.args.get('prioridad', '').strip()

    query = """
        SELECT m.*, p.stock_actual, p.unidad_medida AS unidad_producto,
               u.nombre AS usuario_nombre, up.nombre AS pedido_por_nombre,
               (
                 SELECT COALESCE(NULLIF(pr2.nombre_comercial, ''), pr2.nombre, e2.proveedor_nombre_historico)
                 FROM entradas e2
                 LEFT JOIN proveedores pr2 ON pr2.id = e2.proveedor_id
                 WHERE e2.producto_id = p.id
                   AND COALESCE(e2.es_servicio, 0) = 0
                 ORDER BY DATE(COALESCE(e2.fecha_vale, e2.fecha)) DESC, e2.id DESC
                 LIMIT 1
               ) AS ultimo_proveedor,
               (
                 SELECT COALESCE(e3.fecha_vale, e3.fecha)
                 FROM entradas e3
                 WHERE e3.producto_id = p.id
                   AND COALESCE(e3.es_servicio, 0) = 0
                 ORDER BY DATE(COALESCE(e3.fecha_vale, e3.fecha)) DESC, e3.id DESC
                 LIMIT 1
               ) AS ultima_entrada_fecha
        FROM material_por_pedir m
        LEFT JOIN productos p ON p.id=m.producto_id
        LEFT JOIN usuarios u ON u.id=m.usuario_id
        LEFT JOIN usuarios up ON up.id=m.pedido_por_usuario_id
        WHERE 1=1
    """
    params = []
    if estado == 'pendiente':
        query += " AND COALESCE(m.solicitado,0)=0"
    elif estado == 'pedido':
        query += " AND COALESCE(m.solicitado,0)=1"
    elif estado == 'urgente':
        query += " AND COALESCE(m.solicitado,0)=0 AND m.prioridad='urgente'"
    elif estado == 'normal':
        query += " AND COALESCE(m.solicitado,0)=0 AND COALESCE(m.prioridad,'normal')='normal'"
    if prioridad:
        prioridad = _normalizar_prioridad(prioridad)
        query += " AND m.prioridad=?"
        params.append(prioridad)
    if q:
        cond, cond_params = construir_busqueda_dinamica(
            q, ["m.codigo", "m.descripcion", "m.motivo", "m.orden_compra", "m.requisicion_folio"]
        )
        if cond:
            query += f" AND {cond}"
            params.extend(cond_params)
    query += """
        ORDER BY DATETIME(COALESCE(m.fecha, m.updated_at)) DESC,
                 m.id DESC
    """
    registros = conn.execute(query, params).fetchall()
    resumen = conn.execute("""
        SELECT
          SUM(CASE WHEN COALESCE(solicitado,0)=0 THEN 1 ELSE 0 END) AS pendientes,
          SUM(CASE WHEN COALESCE(solicitado,0)=1 THEN 1 ELSE 0 END) AS pedidos,
          SUM(CASE WHEN prioridad='urgente' AND COALESCE(solicitado,0)=0 THEN 1 ELSE 0 END) AS urgentes,
          SUM(CASE WHEN COALESCE(prioridad,'normal')='normal' AND COALESCE(solicitado,0)=0 THEN 1 ELSE 0 END) AS normales,
          COUNT(*) AS total
        FROM material_por_pedir
    """).fetchone()
    conn.close()
    return render_template('material_por_pedir/index.html', registros=registros, unidades=unidades,
                           q=q, estado=estado, prioridad=prioridad, resumen=resumen)


@material_por_pedir_bp.route('/editar/<int:item_id>', methods=['GET', 'POST'])
@login_required
def editar(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM material_por_pedir WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        flash('Registro no encontrado.', 'danger')
        return redirect(url_for('material_por_pedir.index'))
    unidades = obtener_nombres_unidades(conn)
    if request.method == 'POST':
        f = request.form
        producto_id = f.get('producto_id') or None
        producto = _producto(conn, producto_id)
        descripcion = (f.get('descripcion') or '').strip()
        codigo = (f.get('codigo') or '').strip() or None
        unidad = (f.get('unidad') or '').strip() or None
        if producto:
            codigo = producto['codigo']
            descripcion = descripcion or producto['descripcion']
            unidad = unidad or producto['unidad_medida']
        if not descripcion:
            flash('Captura la descripción del material.', 'danger')
        else:
            conn.execute("""
                UPDATE material_por_pedir
                SET producto_id=?, codigo=?, descripcion=?, cantidad=?, unidad=?,
                    prioridad=?, motivo=?, updated_at=?
                WHERE id=?
            """, (
                int(producto_id) if producto_id else None,
                codigo, descripcion, float(f.get('cantidad') or 0), unidad,
                _normalizar_prioridad(f.get('prioridad')), (f.get('motivo') or '').strip() or None,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), item_id
            ))
            conn.commit()
            log_actividad(session.get('user_id'), 'EDITAR_MATERIAL_POR_PEDIR', f"Pendiente ID: {item_id}")
            conn.close()
            flash('Registro actualizado.', 'success')
            return redirect(url_for('material_por_pedir.index'))
    conn.close()
    return render_template('material_por_pedir/form.html', item=item, unidades=unidades)
