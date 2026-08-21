from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from routes.auth import login_required, rol_required
from database import get_db, log_actividad

areas_bp = Blueprint('areas', __name__, url_prefix='/areas')


@areas_bp.route('/')
@login_required
def index():
    q = request.args.get('q', '').strip()
    ver = request.args.get('ver', 'activos')
    conn = get_db()
    query = "SELECT * FROM areas WHERE 1=1"
    params = []
    if ver == 'activos':
        query += " AND activo = 1"
    elif ver == 'archivados':
        query += " AND activo = 0"
    if q:
        query += " AND nombre LIKE ?"
        params.append(f'%{q}%')
    query += " ORDER BY activo DESC, nombre"
    areas = conn.execute(query, params).fetchall()

    total_activos = conn.execute("SELECT COUNT(*) FROM areas WHERE activo=1").fetchone()[0]
    total_archivados = conn.execute("SELECT COUNT(*) FROM areas WHERE activo=0").fetchone()[0]

    conn.close()
    return render_template('areas/index.html', areas=areas, q=q, ver=ver,
                           total_activos=total_activos, total_archivados=total_archivados)


@areas_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        if not nombre:
            flash('El nombre del área es obligatorio.', 'danger')
            return render_template('areas/form.html', area_item=None)
        conn = get_db()
        try:
            conn.execute("INSERT INTO areas (nombre) VALUES (?)", (nombre,))
            conn.commit()
            log_actividad(session['user_id'], 'NUEVA_AREA', f"Nombre: {nombre}")
            flash('Área registrada correctamente.', 'success')
            return redirect(url_for('areas.index'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
        finally:
            conn.close()
    return render_template('areas/form.html', area_item=None)


@areas_bp.route('/editar/<int:aid>', methods=['GET', 'POST'])
@login_required
def editar(aid):
    conn = get_db()
    item = conn.execute("SELECT * FROM areas WHERE id=?", (aid,)).fetchone()
    conn.close()
    if not item:
        flash('Área no encontrada.', 'danger')
        return redirect(url_for('areas.index'))
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        activo = int(request.form.get('activo', 1))
        if not nombre:
            flash('El nombre del área es obligatorio.', 'danger')
            return render_template('areas/form.html', area_item=item)
        conn = get_db()
        try:
            conn.execute("UPDATE areas SET nombre=?, activo=? WHERE id=?", (nombre, activo, aid))
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_AREA', f"ID: {aid} | Nombre: {nombre}")
            flash('Área actualizada.', 'success')
            return redirect(url_for('areas.index'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
        finally:
            conn.close()
    return render_template('areas/form.html', area_item=item)


@areas_bp.route('/eliminar/<int:aid>', methods=['POST'])
@login_required
@rol_required('admin')
def eliminar(aid):
    conn = get_db()
    item = conn.execute("SELECT * FROM areas WHERE id=?", (aid,)).fetchone()
    if not item:
        flash('Área no encontrada.', 'danger')
        conn.close()
        return redirect(url_for('areas.index'))
    try:
        # Los vales que ya la referencian no se borran: se guarda el nombre tal
        # como estaba (area_nombre_historico) para no perder el dato histórico.
        conn.execute("""
            UPDATE vales_montacargas SET area_nombre_historico = COALESCE(area_nombre_historico, ?),
                                          area_id = NULL
            WHERE area_id=?
        """, (item['nombre'], aid))
        conn.execute("DELETE FROM areas WHERE id=?", (aid,))
        conn.commit()
        log_actividad(session['user_id'], 'ELIMINAR_AREA', f"ID: {aid} | Nombre: {item['nombre']}")
        flash(f"Área \"{item['nombre']}\" eliminada permanentemente.", 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    conn.close()
    return redirect(url_for('areas.index'))


@areas_bp.route('/api/crear', methods=['POST'])
@login_required
def api_crear():
    """Alta rápida de área por AJAX, usada desde el formulario de Vales de
    montacargas cuando el área que se necesita no está en la lista."""
    nombre = (request.form.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'error': 'El nombre del área es obligatorio.'}), 400

    conn = get_db()
    try:
        existente = conn.execute("SELECT id, nombre, activo FROM areas WHERE nombre=?", (nombre,)).fetchone()
        if existente:
            if not existente['activo']:
                conn.execute("UPDATE areas SET activo=1 WHERE id=?", (existente['id'],))
                conn.commit()
            return jsonify({'id': existente['id'], 'nombre': existente['nombre']})
        cur = conn.execute("INSERT INTO areas (nombre) VALUES (?)", (nombre,))
        conn.commit()
        nuevo_id = cur.lastrowid
        log_actividad(session['user_id'], 'NUEVA_AREA',
                       f"Nombre: {nombre} (alta rápida desde Vales de montacargas)")
        return jsonify({'id': nuevo_id, 'nombre': nombre})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
