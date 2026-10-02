import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from database import get_db, log_actividad
from routes.auth import login_required


def _validar_password(password):
    """Devuelve un mensaje si la contraseña no cumple la política configurada."""
    password = password or ""
    minimo = int(current_app.config.get('PASSWORD_MIN_LENGTH', 8))
    if len(password) < minimo:
        return f'La contraseña debe tener al menos {minimo} caracteres.'
    if current_app.config.get('REQUIRE_STRONG_PASSWORD', False):
        if not any(c.islower() for c in password):
            return 'La contraseña debe incluir minúsculas.'
        if not any(c.isupper() for c in password):
            return 'La contraseña debe incluir mayúsculas.'
        if not any(c.isdigit() for c in password):
            return 'La contraseña debe incluir números.'
    return None

usuarios_bp = Blueprint('usuarios', __name__, url_prefix='/usuarios')


def _username_desde_nombre(nombre):
    base = re.sub(r'[^a-z0-9]+', '.', nombre.lower()).strip('.') or 'usuario'
    return base[:40]


def _username_disponible(conn, nombre, uid=None):
    base = _username_desde_nombre(nombre)
    username = base
    consecutivo = 2
    while True:
        fila = conn.execute(
            "SELECT id FROM usuarios WHERE username=? AND (? IS NULL OR id<>?)",
            (username, uid, uid),
        ).fetchone()
        if not fila:
            return username
        username = f"{base}.{consecutivo}"
        consecutivo += 1


@usuarios_bp.route('/')
@login_required
def index():
    conn = get_db()
    usuarios = conn.execute(
        "SELECT * FROM usuarios ORDER BY activo DESC, nombre"
    ).fetchall()
    conn.close()
    return render_template('usuarios/index.html', usuarios=usuarios)


@usuarios_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        if not nombre:
            flash('Captura el nombre del usuario.', 'danger')
            return render_template('usuarios/form.html', usuario=None)
        conn = get_db()
        try:
            username = _username_disponible(conn, nombre)
            conn.execute("""
                INSERT INTO usuarios (username, password, nombre, rol, activo, debe_cambiar_password)
                VALUES (?,?,?,?,1,0)
            """, (username, generate_password_hash('acceso-libre-no-login'), nombre, 'admin'))
            conn.commit()
            log_actividad(session['user_id'], 'NUEVO_USUARIO', f"Nombre: {nombre}")
            flash('Usuario dado de alta correctamente.', 'success')
            return redirect(url_for('usuarios.index'))
        except Exception as e:
            conn.rollback()
            flash(f'Error: {str(e)}', 'danger')
        finally:
            conn.close()
    return render_template('usuarios/form.html', usuario=None)


@usuarios_bp.route('/editar/<int:uid>', methods=['GET', 'POST'])
@login_required
def editar(uid):
    conn = get_db()
    usuario = conn.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    if not usuario:
        conn.close()
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('usuarios.index'))

    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        activo = int(request.form.get('activo', 1))
        if not nombre:
            flash('Captura el nombre del usuario.', 'danger')
            conn.close()
            return render_template('usuarios/form.html', usuario=usuario)
        try:
            username = _username_disponible(conn, nombre, uid)
            conn.execute(
                "UPDATE usuarios SET nombre=?, username=?, activo=?, rol='admin', debe_cambiar_password=0 WHERE id=?",
                (nombre, username, activo, uid),
            )
            conn.commit()
            if session.get('user_id') == uid and not activo:
                session.pop('user_id', None)
                session.pop('username', None)
                session.pop('nombre', None)
                session.pop('rol', None)
            log_actividad(session.get('user_id') or uid, 'EDITAR_USUARIO', f"ID: {uid} | Nombre: {nombre}")
            flash('Usuario actualizado.', 'success')
            return redirect(url_for('usuarios.index'))
        except Exception as e:
            conn.rollback()
            flash(f'Error: {str(e)}', 'danger')
    conn.close()
    return render_template('usuarios/form.html', usuario=usuario)


@usuarios_bp.route('/actividad')
@login_required
def actividad():
    conn = get_db()
    logs = conn.execute("""
        SELECT a.*, u.nombre, u.username FROM actividad a
        LEFT JOIN usuarios u ON a.usuario_id=u.id
        ORDER BY a.timestamp DESC LIMIT 200
    """).fetchall()
    conn.close()
    return render_template('usuarios/actividad.html', logs=logs)
