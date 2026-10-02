from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from routes.auth import login_required, rol_required
from database import get_db, log_actividad

listados_bp = Blueprint('listados', __name__, url_prefix='/listados')


@listados_bp.route('/unidades')
@login_required
def unidades():
    q = request.args.get('q', '').strip()
    ver = request.args.get('ver', 'activos')
    conn = get_db()
    query = "SELECT * FROM unidades WHERE 1=1"
    params = []
    if ver == 'activos':
        query += " AND activo=1"
    elif ver == 'archivados':
        query += " AND activo=0"
    if q:
        query += " AND nombre LIKE ?"
        params.append(f"%{q}%")
    query += " ORDER BY activo DESC, LOWER(nombre)"
    unidades_lista = conn.execute(query, params).fetchall()
    total_activos = conn.execute("SELECT COUNT(*) FROM unidades WHERE activo=1").fetchone()[0]
    total_archivados = conn.execute("SELECT COUNT(*) FROM unidades WHERE activo=0").fetchone()[0]
    conn.close()
    return render_template(
        'listados/unidades.html',
        unidades=unidades_lista,
        q=q,
        ver=ver,
        total_activos=total_activos,
        total_archivados=total_archivados,
    )


@listados_bp.route('/unidades/nueva', methods=['POST'])
@login_required
def unidad_nueva():
    nombre = (request.form.get('nombre') or '').strip()
    if not nombre:
        flash('El nombre de la unidad es obligatorio.', 'danger')
        return redirect(url_for('listados.unidades'))

    conn = get_db()
    try:
        existente = conn.execute("SELECT id, activo FROM unidades WHERE nombre=?", (nombre,)).fetchone()
        if existente:
            if not existente['activo']:
                conn.execute("UPDATE unidades SET activo=1 WHERE id=?", (existente['id'],))
                conn.commit()
                flash('Unidad reactivada.', 'success')
            else:
                flash('Esa unidad ya existe.', 'warning')
            return redirect(url_for('listados.unidades'))

        conn.execute("INSERT INTO unidades (nombre) VALUES (?)", (nombre,))
        conn.commit()
        log_actividad(session['user_id'], 'NUEVA_UNIDAD', f"Nombre: {nombre}")
        flash('Unidad registrada correctamente.', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('listados.unidades'))


@listados_bp.route('/unidades/editar/<int:uid>', methods=['POST'])
@login_required
def unidad_editar(uid):
    nombre = (request.form.get('nombre') or '').strip()
    activo = int(request.form.get('activo', 1))
    if not nombre:
        flash('El nombre de la unidad es obligatorio.', 'danger')
        return redirect(url_for('listados.unidades'))

    conn = get_db()
    try:
        conn.execute("UPDATE unidades SET nombre=?, activo=? WHERE id=?", (nombre, activo, uid))
        conn.commit()
        log_actividad(session['user_id'], 'EDITAR_UNIDAD', f"ID: {uid} | Nombre: {nombre}")
        flash('Unidad actualizada.', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('listados.unidades'))


@listados_bp.route('/unidades/eliminar/<int:uid>', methods=['POST'])
@login_required
@rol_required('admin')
def unidad_eliminar(uid):
    conn = get_db()
    unidad = conn.execute("SELECT * FROM unidades WHERE id=?", (uid,)).fetchone()
    if not unidad:
        conn.close()
        flash('Unidad no encontrada.', 'danger')
        return redirect(url_for('listados.unidades'))
    try:
        conn.execute("UPDATE unidades SET activo=0 WHERE id=?", (uid,))
        conn.commit()
        log_actividad(session['user_id'], 'DESACTIVAR_UNIDAD', f"ID: {uid} | Nombre: {unidad['nombre']}")
        flash(f"Unidad \"{unidad['nombre']}\" desactivada.", 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('listados.unidades'))
