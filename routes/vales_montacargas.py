from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from routes.auth import login_required
from database import get_db, log_actividad
from routes.inventario import construir_busqueda_dinamica
from datetime import datetime, date
import calendar

vales_montacargas_bp = Blueprint('vales_montacargas', __name__, url_prefix='/vales-montacargas')

DOC_KEY = 'vale_mc_doc'


def _rango_mes_actual():
    hoy = date.today()
    ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
    return hoy.replace(day=1).isoformat(), hoy.replace(day=ultimo_dia).isoformat()


@vales_montacargas_bp.route('/')
@login_required
def index():
    # Por defecto se muestra el mes actual (para el resumen mensual). Si el
    # usuario pulsa "Ver todos" llegan como cadena vacía y se respeta (sin filtro).
    default_ini, default_fin = _rango_mes_actual()
    fecha_ini = request.args.get('fecha_ini', default_ini)
    fecha_fin = request.args.get('fecha_fin', default_fin)
    q_resp = request.args.get('q_resp', '').strip()
    q_area = request.args.get('q_area', '').strip()
    q_vale = request.args.get('q_vale', '').strip()
    montacargas_id = request.args.get('montacargas_id', '')
    pagina = request.args.get('pagina', 1, type=int)
    registros_por_pagina = 50

    conn = get_db()

    def aplicar_filtros(base_query, base_params):
        query, params = base_query, list(base_params)
        if fecha_ini:
            query += " AND DATE(COALESCE(v.fecha_vale, v.fecha)) >= ?"; params.append(fecha_ini)
        if fecha_fin:
            query += " AND DATE(COALESCE(v.fecha_vale, v.fecha)) <= ?"; params.append(fecha_fin)
        if q_resp:
            cond, cond_params = construir_busqueda_dinamica(q_resp, ["v.responsable"])
            if cond:
                query += f" AND {cond}"; params += cond_params
        if q_area:
            cond, cond_params = construir_busqueda_dinamica(
                q_area, ["COALESCE(a.nombre, v.area_nombre_historico, v.area)"])
            if cond:
                query += f" AND {cond}"; params += cond_params
        if q_vale:
            cond, cond_params = construir_busqueda_dinamica(q_vale, ["v.no_vale", "v.folio"])
            if cond:
                query += f" AND {cond}"; params += cond_params
        if montacargas_id:
            query += " AND v.montacargas_id = ?"; params.append(montacargas_id)
        return query, params

    base_query = """
        SELECT v.*, COALESCE(m.nombre, v.montacargas_nombre_historico) as montacargas_nombre,
               COALESCE(a.nombre, v.area_nombre_historico, v.area) as area_nombre,
               u.nombre as usuario_nombre
        FROM vales_montacargas v
        LEFT JOIN montacargas m ON v.montacargas_id = m.id
        LEFT JOIN areas a ON v.area_id = a.id
        LEFT JOIN usuarios u ON v.usuario_id = u.id
        WHERE 1=1
    """
    query, params = aplicar_filtros(base_query, [])
    query += " ORDER BY v.fecha DESC"

    vales_completo = conn.execute(query, params).fetchall()
    total_registros = len(vales_completo)
    total_paginas = (total_registros + registros_por_pagina - 1) // registros_por_pagina

    if pagina < 1:
        pagina = 1
    elif pagina > total_paginas and total_paginas > 0:
        pagina = total_paginas

    offset = (pagina - 1) * registros_por_pagina
    vales = vales_completo[offset:offset + registros_por_pagina]

    # ====== RESUMEN: piezas por montacarguista (responsable) y por montacargas,
    # respetando el mismo rango de fechas y filtros que el listado ======
    resumen_query, resumen_params = aplicar_filtros("""
        SELECT v.responsable, COALESCE(m.nombre, v.montacargas_nombre_historico) as montacargas_nombre,
               SUM(v.cantidad) as total_piezas, COUNT(*) as total_vales
        FROM vales_montacargas v
        LEFT JOIN montacargas m ON v.montacargas_id = m.id
        LEFT JOIN areas a ON v.area_id = a.id
        WHERE 1=1
    """, [])
    resumen_query += " GROUP BY v.responsable, montacargas_nombre ORDER BY total_piezas DESC"
    resumen = conn.execute(resumen_query, resumen_params).fetchall()

    total_piezas_periodo = sum(r['total_piezas'] for r in resumen) if resumen else 0
    resumen_por_responsable = {}
    for r in resumen:
        responsable = r['responsable'] or 'Sin nombre'
        grupo = resumen_por_responsable.setdefault(responsable, {
            'responsable': responsable,
            'total_piezas': 0,
            'total_vales': 0,
            'detalles': [],
        })
        grupo['total_piezas'] += r['total_piezas'] or 0
        grupo['total_vales'] += r['total_vales'] or 0
        grupo['detalles'].append(r)
    resumen_responsables = sorted(
        resumen_por_responsable.values(),
        key=lambda grupo: grupo['total_piezas'],
        reverse=True
    )

    montacargas_lista = conn.execute(
        "SELECT * FROM montacargas WHERE activo=1 ORDER BY nombre").fetchall()
    areas_lista = conn.execute(
        "SELECT * FROM areas WHERE activo=1 ORDER BY nombre").fetchall()
    responsables_lista = conn.execute("""
        SELECT DISTINCT responsable
        FROM vales_montacargas
        WHERE responsable IS NOT NULL AND TRIM(responsable) != ''
        ORDER BY responsable
    """).fetchall()

    conn.close()
    return render_template('vales_montacargas/index.html', vales=vales,
                           fecha_ini=fecha_ini, fecha_fin=fecha_fin, q_resp=q_resp,
                           q_area=q_area, q_vale=q_vale, montacargas_id=montacargas_id,
                           pagina_actual=pagina, total_paginas=total_paginas,
                           total_registros=total_registros, registros_pagina=len(vales),
                           resumen=resumen, total_piezas_periodo=total_piezas_periodo,
                           resumen_responsables=resumen_responsables,
                           montacargas_lista=montacargas_lista, areas_lista=areas_lista,
                           responsables_lista=responsables_lista)


@vales_montacargas_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    """Captura un vale a la vez (quién recibió, área, montacargas, cantidad de
    piezas y folio de vale). No afecta el inventario: es solo un registro de
    control para saber cuántas piezas saca cada montacarguista y en cuál
    montacargas. La fecha se comporta igual que en Salidas: se puede editar y
    se recuerda para el siguiente vale."""
    conn = get_db()
    montacargas_lista = conn.execute(
        "SELECT * FROM montacargas WHERE activo=1 ORDER BY nombre").fetchall()
    areas_lista = conn.execute(
        "SELECT * FROM areas WHERE activo=1 ORDER BY nombre").fetchall()

    if request.method == 'POST':
        f = request.form
        responsable = (f.get('responsable') or '').strip()
        area_id = f.get('area_id') or None
        no_vale = (f.get('no_vale') or '').strip()
        montacargas_id = f.get('montacargas_id')
        cantidad = f.get('cantidad')
        observaciones = (f.get('observaciones') or '').strip() or None
        fecha_vale = f.get('fecha_vale') or session.get(DOC_KEY, {}).get('fecha_vale', date.today().isoformat())

        errores = []
        if not responsable:
            errores.append('El nombre de quien recibió es obligatorio.')
        if not no_vale:
            errores.append('El folio de vale es obligatorio.')
        if not montacargas_id:
            errores.append('Selecciona el montacargas de la lista.')
        try:
            cantidad = float(cantidad)
            if cantidad <= 0:
                errores.append('La cantidad debe ser mayor a 0.')
        except (TypeError, ValueError):
            errores.append('Captura una cantidad válida.')

        if errores:
            for e in errores:
                flash(e, 'danger')
            conn.close()
            doc = {'responsable': responsable, 'area_id': area_id, 'no_vale': no_vale,
                   'montacargas_id': montacargas_id, 'cantidad': f.get('cantidad', ''),
                   'observaciones': observaciones or '', 'fecha_vale': fecha_vale}
            ahora = datetime.now().strftime('%Y-%m-%dT%H:%M')
            return render_template('vales_montacargas/form.html', doc=doc,
                                   montacargas_lista=montacargas_lista,
                                   areas_lista=areas_lista, ahora=ahora)

        montacargas_item = conn.execute(
            "SELECT * FROM montacargas WHERE id=?", (montacargas_id,)).fetchone()
        area_item = conn.execute(
            "SELECT * FROM areas WHERE id=?", (area_id,)).fetchone() if area_id else None

        try:
            conn.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo = 'vale_montacargas'")
            num = conn.execute("SELECT ultimo FROM folios WHERE tipo = 'vale_montacargas'").fetchone()[0]
            folio = f"VMC-{str(num).zfill(6)}"
            fecha_sql = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute("""
                INSERT INTO vales_montacargas
                (folio, no_vale, responsable, area_id, area_nombre_historico,
                 montacargas_id, montacargas_nombre_historico,
                 cantidad, unidad, observaciones, usuario_id, fecha, fecha_vale)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (folio, no_vale, responsable, area_id,
                  area_item['nombre'] if area_item else None,
                  montacargas_id, montacargas_item['nombre'] if montacargas_item else None,
                  cantidad, 'piezas', observaciones, session['user_id'], fecha_sql, fecha_vale))
            conn.commit()
            log_actividad(session['user_id'], 'NUEVO_VALE_MONTACARGAS',
                          f"Folio: {folio} | Vale: {no_vale} | Montacargas: {montacargas_item['nombre'] if montacargas_item else '-'} | "
                          f"Recibió: {responsable} | Cantidad: {cantidad}")
            flash(f"Vale de montacargas registrado correctamente (folio {folio}, vale {no_vale}).", 'success')
            # Se limpia el formulario para el siguiente vale, igual que en Salidas,
            # pero se conserva la fecha si el usuario la cambió a mano.
            session[DOC_KEY] = {
                'responsable': '',
                'area_id': '',
                'montacargas_id': '',
                'no_vale': '',
                'cantidad': '',
                'observaciones': '',
                'fecha_vale': fecha_vale,
            }
            conn.close()
            return redirect(url_for('vales_montacargas.nuevo'))
        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('vales_montacargas.nuevo'))

    doc = session.get(DOC_KEY, {})
    conn.close()
    ahora = datetime.now().strftime('%Y-%m-%dT%H:%M')
    return render_template('vales_montacargas/form.html', doc=doc,
                           montacargas_lista=montacargas_lista,
                           areas_lista=areas_lista, ahora=ahora)


@vales_montacargas_bp.route('/editar/<int:vid>', methods=['GET', 'POST'])
@login_required
def editar(vid):
    conn = get_db()
    vale = conn.execute("""
        SELECT v.*, COALESCE(m.nombre, v.montacargas_nombre_historico) as montacargas_nombre,
               COALESCE(a.nombre, v.area_nombre_historico, v.area) as area_nombre
        FROM vales_montacargas v
        LEFT JOIN montacargas m ON v.montacargas_id = m.id
        LEFT JOIN areas a ON v.area_id = a.id
        WHERE v.id=?
    """, (vid,)).fetchone()
    montacargas_lista = conn.execute(
        "SELECT * FROM montacargas WHERE activo=1 ORDER BY nombre").fetchall()
    areas_lista = conn.execute(
        "SELECT * FROM areas WHERE activo=1 ORDER BY nombre").fetchall()
    if not vale:
        flash('Registro no encontrado.', 'danger')
        conn.close()
        return redirect(url_for('vales_montacargas.index'))

    if request.method == 'POST':
        f = request.form
        responsable = (f.get('responsable') or '').strip()
        area_id = f.get('area_id') or None
        no_vale = (f.get('no_vale') or '').strip()
        montacargas_id = f.get('montacargas_id')
        observaciones = (f.get('observaciones') or '').strip() or None
        fecha_vale = f.get('fecha_vale') or vale['fecha_vale'] or vale['fecha'][:10]

        errores = []
        if not responsable:
            errores.append('El nombre de quien recibió es obligatorio.')
        if not no_vale:
            errores.append('El folio de vale es obligatorio.')
        if not montacargas_id:
            errores.append('Selecciona el montacargas de la lista.')
        try:
            cantidad = float(f.get('cantidad'))
            if cantidad <= 0:
                errores.append('La cantidad debe ser mayor a 0.')
        except (TypeError, ValueError):
            errores.append('Captura una cantidad válida.')

        if errores:
            for e in errores:
                flash(e, 'danger')
            conn.close()
            return render_template('vales_montacargas/form.html', doc=None, vale=vale,
                                   montacargas_lista=montacargas_lista,
                                   areas_lista=areas_lista, editar=True)

        montacargas_item = conn.execute(
            "SELECT * FROM montacargas WHERE id=?", (montacargas_id,)).fetchone()
        area_item = conn.execute(
            "SELECT * FROM areas WHERE id=?", (area_id,)).fetchone() if area_id else None
        try:
            conn.execute("""
                UPDATE vales_montacargas SET
                    responsable=?, area_id=?, area_nombre_historico=?, no_vale=?,
                    montacargas_id=?, montacargas_nombre_historico=?,
                    cantidad=?, observaciones=?, fecha_vale=?
                WHERE id=?
            """, (responsable, area_id, area_item['nombre'] if area_item else None, no_vale,
                  montacargas_id, montacargas_item['nombre'] if montacargas_item else None,
                  cantidad, observaciones, fecha_vale, vid))
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_VALE_MONTACARGAS', f"ID: {vid} | Folio: {vale['folio']}")
            flash('Vale de montacargas actualizado correctamente.', 'success')
            conn.close()
            return redirect(url_for('vales_montacargas.index'))
        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('vales_montacargas.editar', vid=vid))

    conn.close()
    return render_template('vales_montacargas/form.html', doc=None, vale=vale,
                           montacargas_lista=montacargas_lista,
                           areas_lista=areas_lista, editar=True)


@vales_montacargas_bp.route('/eliminar/<int:vid>', methods=['POST'])
@login_required
def eliminar(vid):
    conn = get_db()
    vale = conn.execute("SELECT * FROM vales_montacargas WHERE id=?", (vid,)).fetchone()
    if not vale:
        flash('Registro no encontrado.', 'danger')
        conn.close()
        return redirect(url_for('vales_montacargas.index'))
    try:
        conn.execute("DELETE FROM vales_montacargas WHERE id=?", (vid,))
        conn.commit()
        log_actividad(session['user_id'], 'ELIMINAR_VALE_MONTACARGAS', f"ID: {vid} | Folio: {vale['folio']}")
        flash(f"Vale (folio {vale['folio']}) eliminado.", 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    conn.close()
    return redirect(url_for('vales_montacargas.index'))
