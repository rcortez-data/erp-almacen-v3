from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from routes.auth import login_required, rol_required
from database import get_db, log_actividad

proveedores_bp = Blueprint('proveedores', __name__, url_prefix='/proveedores')


@proveedores_bp.route('/')
@login_required
def index():
    q = request.args.get('q', '').strip()
    # Por defecto solo se muestran proveedores ACTIVOS (lista limpia).
    # ?ver=todos o ?ver=archivados permite consultar el histórico cuando se necesite.
    ver = request.args.get('ver', 'activos')
    conn = get_db()
    query = "SELECT * FROM proveedores WHERE 1=1"
    params = []
    if ver == 'activos':
        query += " AND activo = 1"
    elif ver == 'archivados':
        query += " AND activo = 0"
    # ver == 'todos' -> sin filtro de activo
    if q:
        query += " AND (nombre LIKE ? OR nombre_comercial LIKE ?)"
        params += [f'%{q}%', f'%{q}%']
    query += " ORDER BY activo DESC, nombre"
    proveedores = conn.execute(query, params).fetchall()

    total_activos = conn.execute("SELECT COUNT(*) FROM proveedores WHERE activo=1").fetchone()[0]
    total_archivados = conn.execute("SELECT COUNT(*) FROM proveedores WHERE activo=0").fetchone()[0]

    conn.close()
    return render_template('proveedores/index.html', proveedores=proveedores, q=q, ver=ver,
                           total_activos=total_activos, total_archivados=total_archivados)


@proveedores_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@rol_required('admin')
def nuevo():
    if request.method == 'POST':
        f = request.form
        nombre = f.get('nombre', '').strip()
        nombre_comercial = f.get('nombre_comercial', '').strip()
        if not nombre:
            flash('El nombre fiscal del proveedor es obligatorio.', 'danger')
            return render_template('proveedores/form.html', proveedor=None)
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO proveedores (nombre, nombre_comercial) VALUES (?, ?)",
                (nombre, nombre_comercial or None)
            )
            conn.commit()
            log_actividad(session['user_id'], 'NUEVO_PROVEEDOR', f"Nombre fiscal: {nombre}")
            flash('Proveedor registrado correctamente.', 'success')
            return redirect(url_for('proveedores.index'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
        finally:
            conn.close()
    return render_template('proveedores/form.html', proveedor=None)


@proveedores_bp.route('/editar/<int:pid>', methods=['GET', 'POST'])
@login_required
@rol_required('admin')
def editar(pid):
    conn = get_db()
    proveedor = conn.execute("SELECT * FROM proveedores WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not proveedor:
        flash('Proveedor no encontrado.', 'danger')
        return redirect(url_for('proveedores.index'))
    if request.method == 'POST':
        f = request.form
        nombre = f.get('nombre', '').strip()
        nombre_comercial = f.get('nombre_comercial', '').strip()
        activo = int(f.get('activo', 1))
        if not nombre:
            flash('El nombre fiscal del proveedor es obligatorio.', 'danger')
            return render_template('proveedores/form.html', proveedor=proveedor)
        conn = get_db()
        try:
            conn.execute(
                "UPDATE proveedores SET nombre=?, nombre_comercial=?, activo=? WHERE id=?",
                (nombre, nombre_comercial or None, activo, pid)
            )
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_PROVEEDOR', f"ID: {pid} | Nombre fiscal: {nombre}")
            flash('Proveedor actualizado.', 'success')
            return redirect(url_for('proveedores.index'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
        finally:
            conn.close()
    return render_template('proveedores/form.html', proveedor=proveedor)


@proveedores_bp.route('/eliminar/<int:pid>', methods=['POST'])
@login_required
@rol_required('admin')
def eliminar(pid):
    conn = get_db()
    proveedor = conn.execute("SELECT * FROM proveedores WHERE id=?", (pid,)).fetchone()
    if not proveedor:
        flash('Proveedor no encontrado.', 'danger')
        conn.close()
        return redirect(url_for('proveedores.index'))
    try:
        # Las entradas que lo referencian no se borran: se guarda el nombre tal como
        # estaba (proveedor_nombre_historico) para no perder ese dato, y se quita
        # el enlace al proveedor que se está borrando.
        conn.execute("""
            UPDATE entradas SET proveedor_nombre_historico = COALESCE(proveedor_nombre_historico, ?),
                                proveedor_id = NULL
            WHERE proveedor_id=?
        """, (proveedor['nombre'], pid))
        conn.execute("DELETE FROM proveedores WHERE id=?", (pid,))
        conn.commit()
        log_actividad(session['user_id'], 'ELIMINAR_PROVEEDOR', f"ID: {pid} | Nombre: {proveedor['nombre']}")
        flash(f"Proveedor \"{proveedor['nombre']}\" eliminado permanentemente.", 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    conn.close()
    return redirect(url_for('proveedores.index'))


@proveedores_bp.route('/eliminar-varios', methods=['POST'])
@login_required
@rol_required('admin')
def eliminar_varios():
    ids = request.form.getlist('ids')
    ids = [int(i) for i in ids if i.isdigit()]
    if not ids:
        flash('No seleccionaste ningún proveedor.', 'warning')
        return redirect(url_for('proveedores.index'))
    conn = get_db()
    try:
        placeholders = ','.join('?' * len(ids))
        nombres = [r['nombre'] for r in conn.execute(
            f"SELECT nombre FROM proveedores WHERE id IN ({placeholders})", ids).fetchall()]
        # Guarda el nombre de CADA proveedor (subconsulta correlacionada, antes de
        # borrar proveedores) para no perder el dato en las entradas históricas.
        conn.execute(f"""
            UPDATE entradas SET
                proveedor_nombre_historico = COALESCE(proveedor_nombre_historico,
                    (SELECT nombre FROM proveedores WHERE proveedores.id = entradas.proveedor_id)),
                proveedor_id = NULL
            WHERE proveedor_id IN ({placeholders})
        """, ids)
        conn.execute(f"DELETE FROM proveedores WHERE id IN ({placeholders})", ids)
        conn.commit()
        log_actividad(session['user_id'], 'ELIMINAR_PROVEEDORES_VARIOS', f"{len(ids)} proveedores: {', '.join(nombres)}")
        flash(f'{len(ids)} proveedor(es) eliminado(s) permanentemente.', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    conn.close()
    return redirect(url_for('proveedores.index'))


@proveedores_bp.route('/api/buscar')
@login_required
def api_buscar():
    """Buscador dinámico por nombre fiscal o comercial (usado en Entradas)."""
    q = request.args.get('q', '').strip()
    incluir_archivados = request.args.get('incluir_archivados') == '1'
    if len(q) < 1:
        return jsonify([])
    conn = get_db()
    filtro_activo = "" if incluir_archivados else "AND activo=1"
    proveedores = conn.execute(f"""
        SELECT id, nombre, nombre_comercial, activo FROM proveedores
        WHERE (nombre LIKE ? OR nombre_comercial LIKE ?) {filtro_activo}
        ORDER BY activo DESC, nombre LIMIT 20
    """, (f'%{q}%', f'%{q}%')).fetchall()
    conn.close()
    return jsonify([dict(p) for p in proveedores])


@proveedores_bp.route('/api/crear', methods=['POST'])
@login_required
def api_crear():
    """Alta rápida de proveedor por AJAX, usada desde el formulario de Entradas
    cuando el buscador no encuentra al proveedor que se necesita capturar."""
    nombre = (request.form.get('nombre') or '').strip()
    nombre_comercial = (request.form.get('nombre_comercial') or '').strip()

    if not nombre:
        return jsonify({'error': 'El nombre fiscal es obligatorio.'}), 400

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO proveedores (nombre, nombre_comercial) VALUES (?, ?)",
            (nombre, nombre_comercial or None)
        )
        conn.commit()
        nuevo_id = cur.lastrowid
        log_actividad(session['user_id'], 'NUEVO_PROVEEDOR',
                       f"Nombre fiscal: {nombre} (alta rápida desde Entradas)")
        return jsonify({'id': nuevo_id, 'nombre': nombre, 'nombre_comercial': nombre_comercial or None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
