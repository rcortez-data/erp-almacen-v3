from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from routes.auth import login_required, rol_required
from database import get_db, log_actividad

montacargas_bp = Blueprint('montacargas', __name__, url_prefix='/montacargas')


@montacargas_bp.route('/')
@login_required
def index():
    q = request.args.get('q', '').strip()
    ver = request.args.get('ver', 'activos')
    conn = get_db()
    query = "SELECT * FROM montacargas WHERE 1=1"
    params = []
    if ver == 'activos':
        query += " AND activo = 1"
    elif ver == 'archivados':
        query += " AND activo = 0"
    if q:
        query += " AND nombre LIKE ?"
        params.append(f'%{q}%')
    query += " ORDER BY activo DESC, nombre"
    montacargas = conn.execute(query, params).fetchall()

    total_activos = conn.execute("SELECT COUNT(*) FROM montacargas WHERE activo=1").fetchone()[0]
    total_archivados = conn.execute("SELECT COUNT(*) FROM montacargas WHERE activo=0").fetchone()[0]

    conn.close()
    return render_template('montacargas/index.html', montacargas=montacargas, q=q, ver=ver,
                           total_activos=total_activos, total_archivados=total_archivados)


@montacargas_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        if not nombre:
            flash('El nombre o número del montacargas es obligatorio.', 'danger')
            return render_template('montacargas/form.html', montacargas_item=None)
        conn = get_db()
        try:
            conn.execute("INSERT INTO montacargas (nombre) VALUES (?)", (nombre,))
            conn.commit()
            log_actividad(session['user_id'], 'NUEVO_MONTACARGAS', f"Nombre: {nombre}")
            flash('Montacargas registrado correctamente.', 'success')
            return redirect(url_for('montacargas.index'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
        finally:
            conn.close()
    return render_template('montacargas/form.html', montacargas_item=None)


@montacargas_bp.route('/editar/<int:mid>', methods=['GET', 'POST'])
@login_required
def editar(mid):
    conn = get_db()
    item = conn.execute("SELECT * FROM montacargas WHERE id=?", (mid,)).fetchone()
    conn.close()
    if not item:
        flash('Montacargas no encontrado.', 'danger')
        return redirect(url_for('montacargas.index'))
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        activo = int(request.form.get('activo', 1))
        if not nombre:
            flash('El nombre o número del montacargas es obligatorio.', 'danger')
            return render_template('montacargas/form.html', montacargas_item=item)
        conn = get_db()
        try:
            conn.execute("UPDATE montacargas SET nombre=?, activo=? WHERE id=?", (nombre, activo, mid))
            conn.commit()
            log_actividad(session['user_id'], 'EDITAR_MONTACARGAS', f"ID: {mid} | Nombre: {nombre}")
            flash('Montacargas actualizado.', 'success')
            return redirect(url_for('montacargas.index'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
        finally:
            conn.close()
    return render_template('montacargas/form.html', montacargas_item=item)


@montacargas_bp.route('/eliminar/<int:mid>', methods=['POST'])
@login_required
@rol_required('admin')
def eliminar(mid):
    conn = get_db()
    item = conn.execute("SELECT * FROM montacargas WHERE id=?", (mid,)).fetchone()
    if not item:
        flash('Montacargas no encontrado.', 'danger')
        conn.close()
        return redirect(url_for('montacargas.index'))
    try:
        # Los vales que ya lo referencian no se borran: se guarda el nombre tal como
        # estaba (montacargas_nombre_historico) para no perder el dato histórico.
        conn.execute("""
            UPDATE vales_montacargas SET montacargas_nombre_historico = COALESCE(montacargas_nombre_historico, ?),
                                          montacargas_id = NULL
            WHERE montacargas_id=?
        """, (item['nombre'], mid))
        conn.execute("DELETE FROM montacargas WHERE id=?", (mid,))
        conn.commit()
        log_actividad(session['user_id'], 'ELIMINAR_MONTACARGAS', f"ID: {mid} | Nombre: {item['nombre']}")
        flash(f"Montacargas \"{item['nombre']}\" eliminado permanentemente.", 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    conn.close()
    return redirect(url_for('montacargas.index'))


@montacargas_bp.route('/api/crear', methods=['POST'])
@login_required
def api_crear():
    """Alta rápida de montacargas por AJAX, usada desde el formulario de Vales
    de montacargas cuando el que se necesita no está en la lista fija."""
    nombre = (request.form.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'error': 'El nombre o número del montacargas es obligatorio.'}), 400

    conn = get_db()
    try:
        existente = conn.execute("SELECT id, nombre, activo FROM montacargas WHERE nombre=?", (nombre,)).fetchone()
        if existente:
            if not existente['activo']:
                conn.execute("UPDATE montacargas SET activo=1 WHERE id=?", (existente['id'],))
                conn.commit()
            return jsonify({'id': existente['id'], 'nombre': existente['nombre']})
        cur = conn.execute("INSERT INTO montacargas (nombre) VALUES (?)", (nombre,))
        conn.commit()
        nuevo_id = cur.lastrowid
        log_actividad(session['user_id'], 'NUEVO_MONTACARGAS',
                       f"Nombre: {nombre} (alta rápida desde Vales de montacargas)")
        return jsonify({'id': nuevo_id, 'nombre': nombre})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
