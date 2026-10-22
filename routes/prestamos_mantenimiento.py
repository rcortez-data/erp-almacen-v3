import os
import re
import base64
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from barcode_utils import code128_svg
from database import get_db, log_actividad
from routes.auth import login_required
from routes.entradas import TSC_PRINTER_NAME, _lineas_tsc, _texto_tsc


prestamos_mantenimiento_bp = Blueprint(
    'prestamos_mantenimiento', __name__, url_prefix='/prestamos-mantenimiento'
)


def _fecha_hora_local(valor):
    """Convierte un timestamp UTC de la base a hora de Ciudad de México."""
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).strip().replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo('America/Mexico_City')).strftime('%d/%m/%Y %H:%M')
    except (TypeError, ValueError):
        return str(valor)


def _prestamo_con_dos_dias_atraso(valor, ahora=None):
    """Indica si un préstamo activo ya cumplió 48 horas sin devolución."""
    if not valor:
        return False
    try:
        fecha = datetime.fromisoformat(str(valor).strip().replace('Z', '+00:00'))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        ahora = ahora or datetime.now(timezone.utc)
        if ahora.tzinfo is None:
            ahora = ahora.replace(tzinfo=timezone.utc)
        return ahora - fecha.astimezone(timezone.utc) >= timedelta(days=2)
    except (TypeError, ValueError):
        return False


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


def _siguiente_codigo(tipo, prefijo, conn=None):
    """Obtiene el siguiente código y evita colisiones con códigos existentes."""
    conn_propia = conn is None
    conn = conn or get_db()
    try:
        conn.execute("INSERT OR IGNORE INTO folios VALUES (?, 0)", (tipo,))
        while True:
            conn.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo=?", (tipo,))
            num = conn.execute("SELECT ultimo FROM folios WHERE tipo=?", (tipo,)).fetchone()[0]
            codigo = f'{prefijo}-{num:06d}'
            if not conn.execute(
                    "SELECT 1 FROM material_prestamo WHERE codigo=? LIMIT 1",
                    (codigo,)).fetchone():
                if conn_propia:
                    conn.commit()
                return codigo
    finally:
        if conn_propia:
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
    ahora = datetime.now(timezone.utc)
    prestamos = [
        dict(prestamo, es_atrasado=_prestamo_con_dos_dias_atraso(prestamo['fecha_prestamo'], ahora))
        for prestamo in prestamos
    ]
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
    # La nómina se guarda como texto para conservar ceros y códigos manuales,
    # pero el listado debe ordenarla numéricamente (2 antes que 10).
    query += """ ORDER BY activo DESC,
        CASE WHEN codigo <> '' AND codigo NOT GLOB '*[^0-9]*' THEN 0 ELSE 1 END,
        CASE WHEN codigo <> '' AND codigo NOT GLOB '*[^0-9]*' THEN CAST(codigo AS INTEGER) END,
        codigo COLLATE NOCASE, nombre COLLATE NOCASE"""
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
    query += """ ORDER BY
        CASE WHEN codigo <> '' AND codigo NOT GLOB '*[^0-9]*' THEN 0 ELSE 1 END,
        CASE WHEN codigo <> '' AND codigo NOT GLOB '*[^0-9]*' THEN CAST(codigo AS INTEGER) END,
        codigo COLLATE NOCASE, nombre COLLATE NOCASE"""
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
        codigo_manual = _limpiar_codigo(request.form.get('codigo'))
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
            # Si el material ya trae un código propio se respeta; si no,
            # se genera uno automático dentro de la misma conexión del INSERT.
            codigo = codigo_manual or _siguiente_codigo('material_prestamo', 'PRES', conn=conn)
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


def _estado_material_desde_movimiento(prestamo):
    if not prestamo:
        return 'disponible'
    if prestamo['estado'] == 'prestado':
        return 'prestado'
    if prestamo['estado'] == 'perdido':
        return 'perdido'
    return {
        'danado': 'danado',
        'mantenimiento': 'mantenimiento',
        'perdido': 'perdido',
    }.get(prestamo['estado_devolucion'], 'disponible')


def _sincronizar_estado_material_desde_historial(conn, material_id):
    prestamo = conn.execute("""
        SELECT estado, estado_devolucion
        FROM prestamos_mantenimiento
        WHERE material_id=?
        ORDER BY fecha_prestamo DESC, id DESC
        LIMIT 1
    """, (material_id,)).fetchone()
    conn.execute(
        "UPDATE material_prestamo SET estado=? WHERE id=?",
        (_estado_material_desde_movimiento(prestamo), material_id)
    )


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


@prestamos_mantenimiento_bp.route('/historial/editar/<int:prestamo_id>', methods=['GET', 'POST'])
@login_required
def historial_editar(prestamo_id):
    conn = get_db()
    prestamo = conn.execute("""
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
        WHERE pm.id=?
    """, (prestamo_id,)).fetchone()
    if not prestamo:
        conn.close()
        flash('Movimiento no encontrado.', 'danger')
        return redirect(url_for('prestamos_mantenimiento.historial'))

    if request.method == 'POST':
        estado = request.form.get('estado') or 'prestado'
        if estado not in {'prestado', 'devuelto', 'perdido'}:
            estado = 'prestado'
        estado_devolucion = request.form.get('estado_devolucion') or None
        if estado == 'prestado':
            estado_devolucion = None

        fecha_prestamo = (request.form.get('fecha_prestamo') or '').strip() or prestamo['fecha_prestamo']
        fecha_devolucion = (request.form.get('fecha_devolucion') or '').strip() or None
        if estado == 'prestado':
            fecha_devolucion = None

        recibe_codigo = (request.form.get('recibe_codigo') or '').strip() or None
        recibe_nombre = (request.form.get('recibe_nombre') or '').strip()
        recibe_area = (request.form.get('recibe_area') or '').strip() or None
        devuelve_codigo = (request.form.get('devuelve_codigo') or '').strip() or None
        devuelve_nombre = (request.form.get('devuelve_nombre') or '').strip() or None
        devuelve_area = (request.form.get('devuelve_area') or '').strip() or None
        observaciones_prestamo = (request.form.get('observaciones_prestamo') or '').strip() or None
        observaciones_devolucion = (request.form.get('observaciones_devolucion') or '').strip() or None

        if not recibe_nombre:
            flash('El nombre de quien recibió es obligatorio.', 'danger')
            conn.close()
            return render_template('prestamos_mantenimiento/historial_form.html', item=prestamo)

        try:
            conn.execute("""
                UPDATE prestamos_mantenimiento
                SET estado=?, estado_devolucion=?, fecha_prestamo=?, fecha_devolucion=?,
                    recibe_codigo_historico=?, recibe_nombre_historico=?, recibe_area_historico=?,
                    devuelve_codigo_historico=?, devuelve_nombre_historico=?, devuelve_area_historico=?,
                    observaciones_prestamo=?, observaciones_devolucion=?
                WHERE id=?
            """, (
                estado, estado_devolucion, fecha_prestamo, fecha_devolucion,
                recibe_codigo, recibe_nombre, recibe_area,
                devuelve_codigo, devuelve_nombre, devuelve_area,
                observaciones_prestamo, observaciones_devolucion, prestamo_id
            ))
            _sincronizar_estado_material_desde_historial(conn, prestamo['material_id'])
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_HISTORIAL_PRESTAMO', f'{prestamo["material_codigo"]} | movimiento {prestamo_id}')
            flash('Movimiento actualizado.', 'success')
            return redirect(url_for('prestamos_mantenimiento.historial'))
        except Exception as e:
            conn.rollback()
            flash(f'No se pudo actualizar el movimiento: {e}', 'danger')

    conn.close()
    return render_template('prestamos_mantenimiento/historial_form.html', item=prestamo)


@prestamos_mantenimiento_bp.route('/historial/eliminar/<int:prestamo_id>', methods=['POST'])
@login_required
def historial_eliminar(prestamo_id):
    conn = get_db()
    prestamo = conn.execute("""
        SELECT pm.*, mp.codigo AS material_codigo
        FROM prestamos_mantenimiento pm
        JOIN material_prestamo mp ON mp.id = pm.material_id
        WHERE pm.id=?
    """, (prestamo_id,)).fetchone()
    if not prestamo:
        conn.close()
        flash('Movimiento no encontrado.', 'danger')
        return redirect(url_for('prestamos_mantenimiento.historial'))
    try:
        material_id = prestamo['material_id']
        conn.execute("DELETE FROM prestamos_mantenimiento WHERE id=?", (prestamo_id,))
        _sincronizar_estado_material_desde_historial(conn, material_id)
        conn.commit()
        log_actividad(session['user_id'], 'ELIMINAR_HISTORIAL_PRESTAMO', f'{prestamo["material_codigo"]} | movimiento {prestamo_id}')
        flash('Movimiento eliminado y estado del material recalculado.', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'No se pudo eliminar el movimiento: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('prestamos_mantenimiento.historial'))


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
    if prestamo:
        data['prestamo'] = dict(prestamo)
        data['prestamo']['fecha_prestamo'] = _fecha_hora_local(prestamo['fecha_prestamo'])
    else:
        data['prestamo'] = None
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
    # Se desplaza 5 mm (aprox. 40 dots) la división central hacia la derecha:
    # la columna izquierda queda un poco más ancha y se compensa el margen
    # desigual que deja la impresora.
    ancho_izquierdo = 446
    ancho_derecho = 366
    tarjetas = [
        (0, 0),
        (ancho_izquierdo, 0),
        (0, 304),
        (ancho_izquierdo, 304),
    ]

    def texto(x, y, valor, fuente='2', xmul=1, ymul=1):
        lineas.append(f'TEXT {x},{y},"{fuente}",0,{xmul},{ymul},"{_texto_tsc(valor)}"')

    def barcode(x, y, valor, altura=58, texto_visible=1, modulo=1, proporcion=2):
        valor = _texto_tsc(valor)
        lineas.append(f'BARCODE {x},{y},"128",{altura},{texto_visible},0,{modulo},{proporcion},"{valor}"')

    for idx, item in enumerate(bloque):
        if item is None:
            continue
        base_x, base_y = tarjetas[idx]
        if idx >= 2:
            base_y -= 16
        # La TSC está tomando el origen un poco cargado hacia la izquierda.
        # El material se centra usando el ancho real de cada columna para que
        # el código derecho no quede recortado por la división central.
        ajuste_columna = 12 if idx % 2 == 0 else 24
        x_texto = base_x + 74 + ajuste_columna
        x_titulo = base_x + 104 + ajuste_columna
        x_barcode = base_x + 112 + ajuste_columna
        y = base_y + 24
        es_personal = tipo == 'personal'
        titulo = 'PERSONAL MANTENIMIENTO' if es_personal else 'MATERIAL A PRESTAMO'
        nombre = item['nombre']
        codigo_barras = item['codigo_barras']
        if not es_personal:
            # Material: etiqueta limpia, únicamente el código de barras y
            # mucho más grande dentro de su cuarto de hoja.
            ancho_tarjeta = ancho_izquierdo if idx % 2 == 0 else ancho_derecho
            # La columna derecha es más angosta. Usa un módulo compacto para
            # conservar zonas blancas a ambos lados y evitar que el lector
            # encuentre el código recortado por el borde de la etiqueta.
            es_columna_derecha = idx % 2 == 1
            ancho_barra_estimado = 180 if es_columna_derecha else min(ancho_tarjeta - 20, 328)
            ajuste_derecha = 12 if es_columna_derecha else 0
            x_barcode = base_x + max(10, int((ancho_tarjeta - ancho_barra_estimado) / 2)) + ajuste_derecha
            modulo_barra = 1 if es_columna_derecha else 2
            proporcion_barra = 2 if es_columna_derecha else 4
            barcode(x_barcode, base_y + 76, codigo_barras, altura=150,
                    texto_visible=0, modulo=modulo_barra, proporcion=proporcion_barra)
            nombre_ref = _lineas_tsc(nombre, 34, 1)[0]
            ancho_nombre = min(ancho_tarjeta - 16, len(nombre_ref) * 8)
            x_nombre = base_x + max(8, int((ancho_tarjeta - ancho_nombre) / 2))
            texto(x_nombre, base_y + 276, nombre_ref, '1', 1, 1)
            continue
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
    return Response(code128_svg(item['codigo_barras'], alto=52, modulo=2, margen=8, incluir_texto=False), mimetype='image/svg+xml')


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
