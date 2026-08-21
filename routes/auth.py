from functools import wraps

from flask import Blueprint, flash, redirect, request, session, url_for
from database import get_db, log_actividad

auth_bp = Blueprint('auth', __name__)


def _aplicar_usuario_en_sesion(user):
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['nombre'] = user['nombre']
    session['rol'] = 'admin'
    session['debe_cambiar_password'] = False


def seleccionar_primer_usuario_activo():
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM usuarios WHERE activo=1 ORDER BY nombre LIMIT 1"
    ).fetchone()
    conn.close()
    if user:
        _aplicar_usuario_en_sesion(user)
    return user


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            seleccionar_primer_usuario_activo()
        return f(*args, **kwargs)
    return decorated


def rol_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated
    return decorator


@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    seleccionar_primer_usuario_activo()
    return redirect(url_for('dashboard.index'))


@auth_bp.route('/seleccionar-usuario', methods=['POST'])
def seleccionar_usuario():
    user_id = request.form.get('user_id', type=int)
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM usuarios WHERE id=? AND activo=1", (user_id,)
    ).fetchone()
    conn.close()
    if not user:
        flash('Selecciona un usuario activo.', 'warning')
    else:
        _aplicar_usuario_en_sesion(user)
        log_actividad(user['id'], 'SELECCION_USUARIO', f"Usuario activo: {user['nombre']}")
    return redirect(request.referrer or url_for('dashboard.index'))


@auth_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('nombre', None)
    session.pop('rol', None)
    session.pop('debe_cambiar_password', None)
    return redirect(url_for('auth.login'))


@auth_bp.route('/cambiar-password', methods=['GET', 'POST'])
@login_required
def cambiar_password():
    flash('El sistema ya no usa contrasenas; cambia de usuario desde la parte superior.', 'info')
    return redirect(url_for('dashboard.index'))
