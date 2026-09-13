import os
import re
import base64
import subprocess
import tempfile
from datetime import datetime

from flask import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from barcode_utils import code128_svg
from database import get_db, log_actividad
from routes.auth import login_required
from routes.entradas import TSC_PRINTER_NAME, _lineas_tsc, _texto_tsc


prestamos_mantenimiento_bp = Blueprint(
    'prestamos_mantenimiento', __name__, url_prefix='/prestamos-mantenimiento'
)


ESTADOS_MATERIAL = {
    'disponible': ('Disponible', 'success'),
    'prestado': ('Prestado', 'warning'),
    'danado': ('Dañado', 'danger'),
    'perdido': ('Perdido', 'dark'),
    'mantenimiento': ('Mantenimiento', 'info'),
    'baja': ('Baja', 'secondary'),
}


def _limpiar_codigo(valor):
    texto = str(valor or '').strip().upper()
    texto = re.sub(r'[^A-Z0-9_-]+', '-', texto)
    texto = re.sub(r'-+', '-', texto).strip('-')
    return texto


def _codigo_barras_personal(codigo):
    return f'MANT-{_limpiar_codigo(codigo)}'


def _codigo_barras_material(codigo):
    return f'PRES-{_limpiar_codigo(codigo)}'


def _siguiente_codigo(tipo, prefijo):
    conn = get_db()
    try:
        conn.execute("INSERT OR IGNORE INTO folios VALUES (?, 0)", (tipo,))
        conn.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo=?", (tipo,))
        num = conn.execute("SELECT ultimo FROM folios WHERE tipo=?", (tipo,)).fetchone()[0]
        conn.commit()
        return f'{prefijo}-{num:06d}'
    finally:
        conn.close()


def _guardar_foto_material(archivo, codigo, sufijo='ITEM'):
    if not archivo or not archivo.filename:
        return None
    extension = os.path.splitext(archivo.filename)[1].lower()
    if extension not in {'.jpg', '.jpeg', '.png', '.webp'}:
        raise ValueError('La foto debe ser JPG, PNG o WEBP.')
    carpeta = os.path.join(current_app.root_path, 'static', 'uploads', 'material_prestamo')
    os.makedirs(carpeta, exist_ok=True)
    nombre_archivo = f'{_codigo_barras_material(codigo)}-{_limpiar_codigo(sufijo)}{extension}'
    archivo.save(os.path.join(carpeta, nombre_archivo))
    return f'uploads/material_prestamo/{nombre_archivo}'


def _material_prestado_activo(conn, material_id):
    return conn.execute(
        "SELECT id FROM prestamos_mantenimiento WHERE material_id=? AND estado='prestado'",
        (material_id,)
    ).fetchone()


@prestamos_mantenimiento_bp.route('/')
@login_required
def index():
    conn = get_db()
    stats = {
        'disponibles': conn.execute("SELECT COUNT(*) FROM material_prestamo WHERE activo=1 AND estado='disponible'").fetchone()[0],
        'prestados': conn.execute("SELECT COUNT(*) FROM material_prestamo WHERE activo=1 AND estado='prestado'").fetchone()[0],
        'danados': conn.execute("SELECT COUNT(*) FROM material_prestamo WHERE activo=1 AND estado='danado'").fetchone()[0],
        'perdidos': conn.execute("SELECT COUNT(*) FROM material_prestamo WHERE activo=1 AND estado='perdido'").fetchone()[0],
        'total': conn.execute("SELECT COUNT(*) FROM material_prestamo WHERE activo=1").fetchone()[0],
    }
    prestamos = conn.execute("""
        SELECT pm.*, mp.codigo AS material_codigo, mp.nombre AS material_nombre,
               COALESCE(pm.recibe_codigo_historico, pr.codigo) AS recibe_codigo,
               COALESCE(pm.recibe_nombre_historico, pr.nombre) AS recibe_nombre,
               COALESCE(pm.recibe_area_historico, pr.area) AS recibe_area
        FROM prestamos_mantenimiento pm
        JOIN material_prestamo mp ON mp.id = pm.material_id
        JOIN personal_mantenimiento pr ON pr.id = pm.trabajador_recibe_id
        WHERE pm.estado='prestado'
        ORDER BY pm.fecha_prestamo DESC
        LIMIT 25
    """).fetchall()
    conn.close()
    return render_template(
        'prestamos_mantenimiento/index.html',
        stats=stats,
        prestamos=prestamos,
        estados_material=ESTADOS_MATERIAL,
    )


@prestamos_mantenimiento_bp.route('/personal')
@login_required
def personal():
    q = (request.args.get('q') or '').strip()
    ver = request.args.get('ver', 'activos')
    params = []
    query = "SELECT * FROM personal_mantenimiento WHERE 1=1"
    query += " AND COALESCE(tipo_responsable, 'mantenimiento')='mantenimiento'"
    if ver == 'activos':
        query += " AND activo=1"
    elif ver == 'inactivos':
        query += " AND activo=0"
    if q:
        query += " AND (codigo LIKE ? OR codigo_barras LIKE ? OR nombre LIKE ? OR area LIKE ?)"
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%'])
    query += " ORDER BY activo DESC, nombre"
    conn = get_db()
    registros = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('prestamos_mantenimiento/personal.html', registros=registros, q=q, ver=ver)


@prestamos_mantenimiento_bp.route('/personal/catalogo')
@login_required
def personal_catalogo():
    q = (request.args.get('q') or '').strip()
    params = []
    query = """
        SELECT *
        FROM personal_mantenimiento
        WHERE activo=1
          AND COALESCE(tipo_responsable, 'mantenimiento')='mantenimiento'
    """
    if q:
        query += " AND (codigo LIKE ? OR codigo_barras LIKE ? OR nombre LIKE ? OR area LIKE ?)"
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%'])
    query += " ORDER BY area, nombre, codigo"
    conn = get_db()
    registros = conn.execute(query, params).fetchall()
    conn.close()
    return render_template(
        'prestamos_mantenimiento/personal_catalogo.html',
        registros=registros,
        q=q,
        now=datetime.now().strftime('%d/%m/%Y %H:%M'),
    )


@prestamos_mantenimiento_bp.route('/personal/nuevo', methods=['GET', 'POST'])
@login_required
def personal_nuevo():
    if request.method == 'POST':
        codigo = _limpiar_codigo(request.form.get('codigo'))
        nombre = (request.form.get('nombre') or '').strip()
        area = (request.form.get('area') or '').strip() or None
        observaciones = (request.form.get('observaciones') or '').strip() or None
        if not codigo or not nombre:
            flash('El número de nómina y el nombre del personal son obligatorios.', 'danger')
            return render_template('prestamos_mantenimiento/personal_form.html', item=None)
        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO personal_mantenimiento
                (codigo, codigo_barras, nombre, area, tipo_responsable, observaciones)
                VALUES (?,?,?,?,?,?)
            """, (codigo, _codigo_barras_personal(codigo), nombre, area, 'mantenimiento', observaciones))
            conn.commit()
            log_actividad(session['user_id'], 'NUEVO_PERSONAL_MANTENIMIENTO', f'Nómina: {codigo} | {nombre}')
            flash('Personal de mantenimiento registrado.', 'success')
            return redirect(url_for('prestamos_mantenimiento.personal'))
        except Exception as e:
            conn.rollback()
            flash(f'No se pudo guardar. Revisa que el código no esté repetido. Detalle: {e}', 'danger')
        finally:
            conn.close()
    return render_template('prestamos_mantenimiento/personal_form.html', item=None)


@prestamos_mantenimiento_bp.route('/personal/editar/<int:item_id>', methods=['GET', 'POST'])
@login_required
def personal_editar(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM personal_mantenimiento WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        flash('Personal no encontrado.', 'danger')
        return redirect(url_for('prestamos_mantenimiento.personal'))
    if request.method == 'POST':
        codigo = _limpiar_codigo(request.form.get('codigo'))
        nombre = (request.form.get('nombre') or '').strip()
        area = (request.form.get('area') or '').strip() or None
        activo = 1 if request.form.get('activo') == '1' else 0
        observaciones = (request.form.get('observaciones') or '').strip() or None
        if not codigo or not nombre:
            flash('Número de nómina y nombre son obligatorios.', 'danger')
            conn.close()
            return render_template('prestamos_mantenimiento/personal_form.html', item=item)
        try:
            conn.execute("""
                UPDATE personal_mantenimiento
                SET codigo=?, codigo_barras=?, nombre=?, area=?, activo=?, observaciones=?
                WHERE id=?
            """, (codigo, _codigo_barras_personal(codigo), nombre, area, activo, observaciones, item_id))
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_PERSONAL_MANTENIMIENTO', f'Nómina: {codigo} | {nombre}')
            flash('Personal actualizado.', 'success')
            return redirect(url_for('prestamos_mantenimiento.personal'))
        except Exception as e:
            conn.rollback()
            flash(f'No se pudo actualizar: {e}', 'danger')
    conn.close()
    return render_template('prestamos_mantenimiento/personal_form.html', item=item)


@prestamos_mantenimiento_bp.route('/material')
@login_required
def material():
    q = (request.args.get('q') or '').strip()
    estado = request.args.get('estado', 'activos')
    params = []
    query = "SELECT * FROM material_prestamo WHERE 1=1"
    if estado == 'activos':
        query += " AND activo=1"
    elif estado in ESTADOS_MATERIAL:
        query += " AND estado=? AND activo=1"
        params.append(estado)
    elif estado == 'inactivos':
        query += " AND activo=0"
    if q:
        query += " AND (codigo LIKE ? OR codigo_barras LIKE ? OR nombre LIKE ? OR descripcion LIKE ? OR categoria LIKE ?)"
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%'])
    query += " ORDER BY activo DESC, estado='prestado' DESC, nombre, codigo"
    conn = get_db()
    registros = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('prestamos_mantenimiento/material.html', registros=registros, q=q, estado=estado, estados_material=ESTADOS_MATERIAL)


@prestamos_mantenimiento_bp.route('/material/nuevo', methods=['GET', 'POST'])
@login_required
def material_nuevo():
    if request.method == 'POST':
        codigo = _limpiar_codigo(request.form.get('codigo')) or _siguiente_codigo('material_prestamo', 'PRES')
        nombre = (request.form.get('nombre') or '').strip()
        descripcion = (request.form.get('descripcion') or '').strip() or None
        categoria = (request.form.get('categoria') or '').strip() or None
        ubicacion = (request.form.get('ubicacion') or '').strip() or None
        estado = request.form.get('estado') or 'disponible'
        observaciones = (request.form.get('observaciones') or '').strip() or None
        if not nombre:
            flash('El nombre del material es obligatorio.', 'danger')
            return render_template('prestamos_mantenimiento/material_form.html', item=None, estados_material=ESTADOS_MATERIAL)
        conn = get_db()
        try:
            foto = _guardar_foto_material(request.files.get('foto'), codigo, 'ITEM')
            foto_ubicacion = _guardar_foto_material(request.files.get('foto_ubicacion'), codigo, 'UBICACION')
            conn.execute("""
                INSERT INTO material_prestamo
                (codigo, codigo_barras, nombre, descripcion, categoria, ubicacion, foto_ruta, foto_ubicacion_ruta, estado, observaciones)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (codigo, _codigo_barras_material(codigo), nombre, descripcion, categoria, ubicacion, foto, foto_ubicacion, estado, observaciones))
            conn.commit()
            log_actividad(session['user_id'], 'NUEVO_MATERIAL_PRESTAMO', f'{codigo} | {nombre}')
            flash('Material a préstamo registrado.', 'success')
            return redirect(url_for('prestamos_mantenimiento.material'))
        except Exception as e:
            conn.rollback()
            flash(f'No se pudo guardar. Revisa que el código no esté repetido. Detalle: {e}', 'danger')
        finally:
            conn.close()
    return render_template('prestamos_mantenimiento/material_form.html', item=None, estados_material=ESTADOS_MATERIAL)


@prestamos_mantenimiento_bp.route('/material/editar/<int:item_id>', methods=['GET', 'POST'])
@login_required
def material_editar(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM material_prestamo WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        flash('Material no encontrado.', 'danger')
        return redirect(url_for('prestamos_mantenimiento.material'))
    if request.method == 'POST':
        codigo = _limpiar_codigo(request.form.get('codigo'))
        nombre = (request.form.get('nombre') or '').strip()
        descripcion = (request.form.get('descripcion') or '').strip() or None
        categoria = (request.form.get('categoria') or '').strip() or None
        ubicacion = (request.form.get('ubicacion') or '').strip() or None
        estado = request.form.get('estado') or item['estado']
        activo = 1 if request.form.get('activo') == '1' else 0
        observaciones = (request.form.get('observaciones') or '').strip() or None
        if not codigo or not nombre:
            flash('Código y nombre son obligatorios.', 'danger')
            conn.close()
            return render_template('prestamos_mantenimiento/material_form.html', item=item, estados_material=ESTADOS_MATERIAL)
        if item['estado'] == 'prestado' and estado != 'prestado' and _material_prestado_activo(conn, item_id):
            flash('Este material está prestado. Registra la devolución antes de cambiar su estado.', 'danger')
            conn.close()
            return render_template('prestamos_mantenimiento/material_form.html', item=item, estados_material=ESTADOS_MATERIAL)
        try:
            foto = item['foto_ruta']
            foto_ubicacion = item['foto_ubicacion_ruta']
            nueva_foto = _guardar_foto_material(request.files.get('foto'), codigo, 'ITEM')
            nueva_foto_ubicacion = _guardar_foto_material(request.files.get('foto_ubicacion'), codigo, 'UBICACION')
            if nueva_foto:
                foto = nueva_foto
            if nueva_foto_ubicacion:
                foto_ubicacion = nueva_foto_ubicacion
            conn.execute("""
                UPDATE material_prestamo
                SET codigo=?, codigo_barras=?, nombre=?, descripcion=?, categoria=?,
                    ubicacion=?, foto_ruta=?, foto_ubicacion_ruta=?, estado=?, activo=?, observaciones=?
                WHERE id=?
            """, (codigo, _codigo_barras_material(codigo), nombre, descripcion, categoria, ubicacion, foto, foto_ubicacion, estado, activo, observaciones, item_id))
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_MATERIAL_PRESTAMO', f'{codigo} | {nombre}')
            flash('Material actualizado.', 'success')
            return redirect(url_for('prestamos_mantenimiento.material'))
        except Exception as e:
            conn.rollback()
            flash(f'No se pudo actualizar: {e}', 'danger')
    conn.close()
    return render_template('prestamos_mantenimiento/material_form.html', item=item, estados_material=ESTADOS_MATERIAL)


@prestamos_mantenimiento_bp.route('/prestar', methods=['GET', 'POST'])
@login_required
def prestar():
    if request.method == 'POST':
        responsable_modo = request.form.get('responsable_modo') or 'catalogo'
        trabajador_codigo = (request.form.get('trabajador_codigo') or '').strip()
        manual_nomina = _limpiar_codigo(request.form.get('manual_nomina'))
        manual_nombre = (request.form.get('manual_nombre') or '').strip()
        manual_area = (request.form.get('manual_area') or '').strip()
        material_codigos = [c.strip() for c in (request.form.get('material_codigos') or '').splitlines() if c.strip()]
        observaciones = (request.form.get('observaciones') or '').strip() or None
        if not material_codigos:
            flash('Escanea al menos un material.', 'danger')
            return redirect(url_for('prestamos_mantenimiento.prestar'))
        conn = get_db()
        try:
            trabajador = _resolver_responsable(
                conn,
                modo=responsable_modo,
                codigo_catalogo=trabajador_codigo,
                manual_nomina=manual_nomina,
                manual_nombre=manual_nombre,
                manual_area=manual_area,
            )
            if not trabajador:
                flash('Indica quién se lleva el material. Puede ser por escáner o captura manual con nómina, nombre y área.', 'danger')
                return redirect(url_for('prestamos_mantenimiento.prestar'))
            registrados = 0
            errores = []
            for codigo in material_codigos:
                material_item = _buscar_material_por_codigo(conn, codigo)
                if not material_item:
                    errores.append(f'{codigo}: no existe o está inactivo')
                    continue
                if material_item['estado'] != 'disponible':
                    errores.append(f"{material_item['codigo']}: no está disponible ({material_item['estado']})")
                    continue
                conn.execute("""
                    INSERT INTO prestamos_mantenimiento
                    (material_id, trabajador_recibe_id, usuario_prestamo_id,
                     recibe_codigo_historico, recibe_nombre_historico, recibe_area_historico,
                     observaciones_prestamo)
                    VALUES (?,?,?,?,?,?,?)
                """, (material_item['id'], trabajador['id'], session.get('user_id'),
                      trabajador['codigo_visible'], trabajador['nombre'], trabajador['area'], observaciones))
                conn.execute("UPDATE material_prestamo SET estado='prestado' WHERE id=?", (material_item['id'],))
                registrados += 1
            conn.commit()
            if registrados:
                log_actividad(session['user_id'], 'PRESTAMO_MANTENIMIENTO', f'{trabajador["codigo"]} | {registrados} materiales')
                flash(f'Se registraron {registrados} préstamo(s).', 'success')
            for error in errores:
                flash(error, 'warning')
        except Exception as e:
            conn.rollback()
            flash(f'No se pudo registrar el préstamo: {e}', 'danger')
        finally:
            conn.close()
        return redirect(url_for('prestamos_mantenimiento.index'))
    return render_template('prestamos_mantenimiento/prestar.html')


@prestamos_mantenimiento_bp.route('/devolver', methods=['GET', 'POST'])
@login_required
def devolver():
    if request.method == 'POST':
        material_codigo = (request.form.get('material_codigo') or '').strip()
        devuelve_modo = request.form.get('devuelve_modo') or 'catalogo'
        devuelve_codigo = (request.form.get('devuelve_codigo') or '').strip()
        devuelve_manual_nomina = _limpiar_codigo(request.form.get('devuelve_manual_nomina'))
        devuelve_manual_nombre = (request.form.get('devuelve_manual_nombre') or '').strip()
        devuelve_manual_area = (request.form.get('devuelve_manual_area') or '').strip()
        estado_devolucion = request.form.get('estado_devolucion') or 'bueno'
        observaciones = (request.form.get('observaciones') or '').strip() or None
        conn = get_db()
        try:
            material_item = _buscar_material_por_codigo(conn, material_codigo, solo_activo=False)
            devuelve = _resolver_responsable(
                conn,
                modo=devuelve_modo,
                codigo_catalogo=devuelve_codigo,
                manual_nomina=devuelve_manual_nomina,
                manual_nombre=devuelve_manual_nombre,
                manual_area=devuelve_manual_area,
            )
            if not devuelve:
                flash('Indica quién devuelve el material. Puede ser por escáner o captura manual con nómina, nombre y área.', 'danger')
                return redirect(url_for('prestamos_mantenimiento.devolver'))
            if not material_item:
                flash('No encontré el material con ese código.', 'danger')
                return redirect(url_for('prestamos_mantenimiento.devolver'))
            prestamo = conn.execute("""
                SELECT * FROM prestamos_mantenimiento
                WHERE material_id=? AND estado='prestado'
                ORDER BY fecha_prestamo DESC LIMIT 1
            """, (material_item['id'],)).fetchone()
            if not prestamo:
                flash('Ese material no aparece como prestado.', 'warning')
                return redirect(url_for('prestamos_mantenimiento.devolver'))
            nuevo_estado = {
                'bueno': 'disponible',
                'danado': 'danado',
                'mantenimiento': 'mantenimiento',
                'perdido': 'perdido',
            }.get(estado_devolucion, 'disponible')
            conn.execute("""
                UPDATE prestamos_mantenimiento
                SET trabajador_devuelve_id=?, fecha_devolucion=CURRENT_TIMESTAMP,
                    usuario_devolucion_id=?, estado=?,
                    estado_devolucion=?,
                    devuelve_codigo_historico=?, devuelve_nombre_historico=?, devuelve_area_historico=?,
                    observaciones_devolucion=?
                WHERE id=?
            """, (devuelve['id'] if devuelve else None, session.get('user_id'),
                  'perdido' if nuevo_estado == 'perdido' else 'devuelto',
                  estado_devolucion, devuelve['codigo_visible'], devuelve['nombre'], devuelve['area'],
                  observaciones, prestamo['id']))
            conn.execute("UPDATE material_prestamo SET estado=? WHERE id=?", (nuevo_estado, material_item['id']))
            conn.commit()
            log_actividad(session['user_id'], 'DEVOLUCION_MANTENIMIENTO', material_item['codigo'])
            flash('Devolución registrada.', 'success')
            return redirect(url_for('prestamos_mantenimiento.index'))
        except Exception as e:
            conn.rollback()
            flash(f'No se pudo registrar la devolución: {e}', 'danger')
        finally:
            conn.close()
    return render_template('prestamos_mantenimiento/devolver.html')


@prestamos_mantenimiento_bp.route('/historial')
@login_required
def historial():
    q = (request.args.get('q') or '').strip()
    estado = request.args.get('estado', 'todos')
    params = []
    query = """
        SELECT pm.*, mp.codigo AS material_codigo, mp.nombre AS material_nombre,
               COALESCE(pm.recibe_codigo_historico, pr.codigo) AS recibe_codigo,
               COALESCE(pm.recibe_nombre_historico, pr.nombre) AS recibe_nombre,
               COALESCE(pm.recibe_area_historico, pr.area) AS recibe_area,
               COALESCE(pm.devuelve_codigo_historico, pd.codigo) AS devuelve_codigo,
               COALESCE(pm.devuelve_nombre_historico, pd.nombre) AS devuelve_nombre,
               COALESCE(pm.devuelve_area_historico, pd.area) AS devuelve_area
        FROM prestamos_mantenimiento pm
        JOIN material_prestamo mp ON mp.id = pm.material_id
        JOIN personal_mantenimiento pr ON pr.id = pm.trabajador_recibe_id
        LEFT JOIN personal_mantenimiento pd ON pd.id = pm.trabajador_devuelve_id
        WHERE 1=1
    """
    if estado in {'prestado', 'devuelto', 'perdido'}:
        query += " AND pm.estado=?"
        params.append(estado)
    if q:
        query += """
            AND (mp.codigo LIKE ? OR mp.nombre LIKE ?
                 OR COALESCE(pm.recibe_codigo_historico, pr.codigo) LIKE ?
                 OR COALESCE(pm.recibe_nombre_historico, pr.nombre) LIKE ?
                 OR COALESCE(pm.devuelve_codigo_historico, pd.codigo) LIKE ?
                 OR COALESCE(pm.devuelve_nombre_historico, pd.nombre) LIKE ?)
        """
        params.extend([f'%{q}%'] * 6)
    query += " ORDER BY pm.fecha_prestamo DESC LIMIT 500"
    conn = get_db()
    registros = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('prestamos_mantenimiento/historial.html', registros=registros, q=q, estado=estado)


@prestamos_mantenimiento_bp.route('/api/personal/<codigo>')
@login_required
def api_personal(codigo):
    conn = get_db()
    item = _buscar_personal_por_codigo(conn, codigo)
    conn.close()
    return jsonify(dict(item) if item else {'error': 'No encontrado'}), 200 if item else 404


@prestamos_mantenimiento_bp.route('/api/material/<codigo>')
@login_required
def api_material(codigo):
    conn = get_db()
    item = _buscar_material_por_codigo(conn, codigo, solo_activo=False)
    prestamo = None
    if item:
        prestamo = conn.execute("""
            SELECT pm.*,
                   COALESCE(pm.recibe_codigo_historico, pr.codigo) AS recibe_codigo,
                   COALESCE(pm.recibe_nombre_historico, pr.nombre) AS recibe_nombre,
                   COALESCE(pm.recibe_area_historico, pr.area) AS recibe_area
            FROM prestamos_mantenimiento pm
            JOIN personal_mantenimiento pr ON pr.id = pm.trabajador_recibe_id
            WHERE pm.material_id=? AND pm.estado='prestado'
            ORDER BY pm.fecha_prestamo DESC LIMIT 1
        """, (item['id'],)).fetchone()
    conn.close()
    if not item:
        return jsonify({'error': 'No encontrado'}), 404
    data = dict(item)
    data['prestamo'] = dict(prestamo) if prestamo else None
    return jsonify(data)


@prestamos_mantenimiento_bp.route('/api/responsables')
@login_required
def api_responsables():
    q = (request.args.get('q') or '').strip()
    if len(q) < 1:
        return jsonify([])
    conn = get_db()
    filas = conn.execute("""
        SELECT codigo, nombre, area, COALESCE(tipo_responsable, 'mantenimiento') AS tipo
        FROM personal_mantenimiento
        WHERE activo=1 AND (
            codigo LIKE ? OR codigo_barras LIKE ? OR nombre LIKE ? OR area LIKE ?
        )
        ORDER BY
            CASE COALESCE(tipo_responsable, 'mantenimiento') WHEN 'mantenimiento' THEN 0 ELSE 1 END,
            nombre
        LIMIT 12
    """, (f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%')).fetchall()
    conn.close()
    return jsonify([
        {
            'codigo': _codigo_visible_responsable(fila),
            'nombre': fila['nombre'],
            'area': fila['area'],
            'tipo': fila['tipo'],
            'label': f"{_codigo_visible_responsable(fila)} · {fila['nombre']} · {fila['area'] or '-'}",
        }
        for fila in filas
    ])


@prestamos_mantenimiento_bp.route('/etiquetas')
@login_required
def etiquetas():
    tipo, registros = _obtener_registros_etiquetas(request.args)
    return render_template(
        'prestamos_mantenimiento/etiquetas.html',
        tipo=tipo,
        registros=registros,
        printer_name=TSC_PRINTER_NAME,
    )


@prestamos_mantenimiento_bp.route('/etiquetas/tsc', methods=['POST'])
@login_required
def etiquetas_tsc():
    tipo, registros = _obtener_registros_etiquetas(request.form)
    volver = request.form.get('volver') or url_for(
        'prestamos_mantenimiento.personal' if tipo == 'personal' else 'prestamos_mantenimiento.material'
    )
    if not registros:
        flash('Selecciona al menos una etiqueta para imprimir.', 'warning')
        return redirect(volver)
    try:
        _imprimir_tsc_prestamos(tipo, registros)
        flash(f'{len(registros)} etiqueta(s) enviadas a {TSC_PRINTER_NAME}.', 'success')
    except Exception as exc:
        flash(f'No se pudo imprimir en {TSC_PRINTER_NAME}: {exc}', 'danger')
    return redirect(volver)


def _obtener_registros_etiquetas(args):
    tipo = args.get('tipo', 'material')
    ids = _ids_desde_request(args)
    registros = []
    conn = get_db()
    if ids and tipo == 'personal':
        placeholders = ','.join('?' for _ in ids)
        filas = conn.execute(f"""
            SELECT id, codigo, codigo_barras, nombre, area
            FROM personal_mantenimiento
            WHERE id IN ({placeholders})
              AND COALESCE(tipo_responsable, 'mantenimiento')='mantenimiento'
            ORDER BY nombre
        """, ids).fetchall()
        por_id = {fila['id']: fila for fila in filas}
        registros = [por_id[item_id] for item_id in ids if item_id in por_id]
    elif ids:
        placeholders = ','.join('?' for _ in ids)
        filas = conn.execute(f"""
            SELECT id, codigo, codigo_barras, nombre, descripcion, categoria, ubicacion
            FROM material_prestamo
            WHERE id IN ({placeholders})
            ORDER BY nombre, codigo
        """, ids).fetchall()
        por_id = {fila['id']: fila for fila in filas}
        registros = [por_id[item_id] for item_id in ids if item_id in por_id]
    conn.close()
    return tipo, registros


def _tspl_prestamos_bloque(tipo, bloque):
    lineas = [
        'SIZE 101 mm,76 mm',
        'GAP 3 mm,0 mm',
        'DENSITY 8',
        'SPEED 4',
        'DIRECTION 1',
        'REFERENCE 0,0',
        'CLS',
    ]

    # 101x76 mm a 203 dpi = aprox. 812 x 608 dots. Cada sub-etiqueta mide
    # ~406 x 304 dots para sacar hasta 4 piezas recortables por etiqueta TSC.
    tarjetas = [
        (0, 0),
        (406, 0),
        (0, 304),
        (406, 304),
    ]

    def texto(x, y, valor, fuente='2', xmul=1, ymul=1):
        lineas.append(f'TEXT {x},{y},"{fuente}",0,{xmul},{ymul},"{_texto_tsc(valor)}"')

    def barcode(x, y, valor):
        valor = _texto_tsc(valor)
        lineas.append(f'BARCODE {x},{y},"128",58,1,0,1,2,"{valor}"')

    # Líneas de corte.
    lineas.append('BAR 405,0,2,608')
    lineas.append('BAR 0,303,812,2')

    for idx, item in enumerate(bloque):
        if item is None:
            continue
        base_x, base_y = tarjetas[idx]
        if idx >= 2:
            base_y -= 16
        # La TSC está tomando el origen un poco cargado hacia la izquierda.
        # Se centra cada sub-etiqueta dentro de su cuarto y se usa código de
        # barras más angosto para que no se salga del área recortable.
        ajuste_columna = 12 if idx % 2 == 0 else 24
        x_texto = base_x + 74 + ajuste_columna
        x_titulo = base_x + 104 + ajuste_columna
        x_barcode = base_x + 112 + ajuste_columna
        y = base_y + 24
        es_personal = tipo == 'personal'
        titulo = 'PERSONAL MANTENIMIENTO' if es_personal else 'MATERIAL A PRESTAMO'
        nombre = item['nombre']
        codigo_barras = item['codigo_barras']
        meta = (
            f"NOMINA: {item['codigo']}  {item['area'] or ''}"
            if es_personal
            else f"{item['categoria'] or 'HERRAMIENTA'}  {item['ubicacion'] or ''}"
        )

        texto(x_titulo, y, 'GRUPO TENSA', '2', 1, 1)
        texto(x_texto, y + 25, titulo, '1', 1, 1)
        y_nombre = y + 50
        for linea in _lineas_tsc(nombre, 22, 2):
            texto(x_texto, y_nombre, linea, '2', 1, 1)
            y_nombre += 24
        texto(x_texto, base_y + 134, meta, '1', 1, 1)
        barcode(x_barcode, base_y + 162, codigo_barras)

    lineas.append('PRINT 1,1')
    return '\r\n'.join(lineas) + '\r\n'


def _imprimir_tsc_prestamos(tipo, registros):
    bloques = []
    actual = []
    for item in registros:
        actual.append(item)
        if len(actual) == 4:
            bloques.append(actual)
            actual = []
    if actual:
        while len(actual) < 4:
            actual.append(None)
        bloques.append(actual)

    data = ''.join(_tspl_prestamos_bloque(tipo, bloque) for bloque in bloques)
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
  $doc.pDocName = "ERP Etiquetas Prestamos Mantenimiento"
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


@prestamos_mantenimiento_bp.route('/personal/codigo-barras/<int:item_id>.svg')
@login_required
def personal_codigo_barras(item_id):
    conn = get_db()
    item = conn.execute("SELECT codigo_barras FROM personal_mantenimiento WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not item:
        return Response('No encontrado', status=404)
    return Response(code128_svg(item['codigo_barras'], alto=52, modulo=2, margen=8, incluir_texto=True), mimetype='image/svg+xml')


@prestamos_mantenimiento_bp.route('/material/codigo-barras/<int:item_id>.svg')
@login_required
def material_codigo_barras(item_id):
    conn = get_db()
    item = conn.execute("SELECT codigo_barras FROM material_prestamo WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not item:
        return Response('No encontrado', status=404)
    return Response(code128_svg(item['codigo_barras'], alto=52, modulo=2, margen=8, incluir_texto=True), mimetype='image/svg+xml')


def _ids_desde_request(args):
    valores = []
    for valor in args.getlist('ids'):
        valores.extend(str(valor).split(','))
    ids = []
    for valor in valores:
        try:
            item_id = int(str(valor).strip())
        except (TypeError, ValueError):
            continue
        if item_id not in ids:
            ids.append(item_id)
    return ids


def _buscar_personal_por_codigo(conn, codigo):
    valor = str(codigo or '').strip()
    limpio = _limpiar_codigo(valor)
    codigo_barras = _codigo_barras_personal(limpio)
    return conn.execute("""
        SELECT * FROM personal_mantenimiento
        WHERE activo=1
          AND COALESCE(tipo_responsable, 'mantenimiento')='mantenimiento'
          AND (codigo=? OR codigo_barras=? OR codigo_barras=?)
        LIMIT 1
    """, (limpio, valor, codigo_barras)).fetchone()


def _codigo_visible_responsable(fila):
    codigo = fila['codigo']
    if str(codigo or '').startswith('MANUAL-'):
        return str(codigo)[7:]
    return codigo


def _row_responsable(fila):
    return {
        'id': fila['id'],
        'codigo': fila['codigo'],
        'codigo_visible': _codigo_visible_responsable(fila),
        'nombre': fila['nombre'],
        'area': fila['area'],
    }


def _obtener_o_crear_responsable_manual(conn, nomina, nombre, area):
    if not nomina or not nombre or not area:
        return None
    codigo = f'MANUAL-{_limpiar_codigo(nomina)}'
    existente = conn.execute(
        "SELECT * FROM personal_mantenimiento WHERE codigo=? LIMIT 1", (codigo,)
    ).fetchone()
    if existente:
        conn.execute("""
            UPDATE personal_mantenimiento
            SET nombre=?, area=?, activo=1, tipo_responsable='manual'
            WHERE id=?
        """, (nombre, area, existente['id']))
        fila = conn.execute("SELECT * FROM personal_mantenimiento WHERE id=?", (existente['id'],)).fetchone()
        return _row_responsable(fila)
    cur = conn.execute("""
        INSERT INTO personal_mantenimiento
        (codigo, codigo_barras, nombre, area, tipo_responsable, activo, observaciones)
        VALUES (?, NULL, ?, ?, 'manual', 1, ?)
    """, (codigo, nombre, area, 'Alta automática desde préstamo/devolución manual.'))
    fila = conn.execute("SELECT * FROM personal_mantenimiento WHERE id=?", (cur.lastrowid,)).fetchone()
    return _row_responsable(fila)


def _resolver_responsable(conn, modo, codigo_catalogo, manual_nomina, manual_nombre, manual_area):
    if modo == 'manual':
        return _obtener_o_crear_responsable_manual(conn, manual_nomina, manual_nombre, manual_area)
    fila = _buscar_personal_por_codigo(conn, codigo_catalogo)
    return _row_responsable(fila) if fila else None


def _buscar_material_por_codigo(conn, codigo, solo_activo=True):
    valor = str(codigo or '').strip()
    limpio = _limpiar_codigo(valor)
    codigo_barras = _codigo_barras_material(limpio)
    query = "SELECT * FROM material_prestamo WHERE (codigo=? OR codigo_barras=? OR codigo_barras=?)"
    params = [limpio, valor, codigo_barras]
    if solo_activo:
        query += " AND activo=1"
    query += " LIMIT 1"
    return conn.execute(query, params).fetchone()
