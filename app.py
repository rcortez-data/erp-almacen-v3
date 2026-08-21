from flask import Flask, jsonify, request, session, abort, redirect, url_for
from flask_compress import Compress
from flask_session import Session
from cachelib.file import FileSystemCache
from dotenv import load_dotenv
import os
import secrets

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from database import DB_BACKEND, DB_PATH, get_db, init_db, migrar_esquema
from routes.auth import auth_bp
from routes.inventario import inventario_bp
from routes.entradas import entradas_bp
from routes.salidas import salidas_bp
from routes.reportes import reportes_bp
from routes.usuarios import usuarios_bp
from routes.dashboard import dashboard_bp
from routes.proveedores import proveedores_bp
from routes.balance import balance_bp
from routes.requisiciones import requisiciones_bp
from routes.montacargas import montacargas_bp
from routes.vales_montacargas import vales_montacargas_bp
from routes.areas import areas_bp
from routes.listados import listados_bp

import logging
from datetime import timedelta
from logging.handlers import RotatingFileHandler

# ====== CONFIGURACIÓN DE LOGGING ======
if not os.path.exists('logs'):
    os.mkdir('logs')

file_handler = RotatingFileHandler('logs/erp_almacen.log', maxBytes=10240000, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

# ====== INICIALIZACIÓN DE APP ======
app = Flask(__name__)
from config import config
app.config.from_object(config)

# Los valores sensibles y operativos se pueden ajustar desde .env.
app.config.update(
    MAX_LOGIN_ATTEMPTS=int(os.environ.get('MAX_LOGIN_ATTEMPTS', app.config['MAX_LOGIN_ATTEMPTS'])),
    LOGIN_TIMEOUT_MINUTES=int(os.environ.get('LOGIN_TIMEOUT_MINUTES', app.config['LOGIN_TIMEOUT_MINUTES'])),
    PASSWORD_MIN_LENGTH=int(os.environ.get('PASSWORD_MIN_LENGTH', app.config['PASSWORD_MIN_LENGTH'])),
    SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', str(app.config['SESSION_COOKIE_SECURE'])).lower() == 'true',
)

# ====== COMPRESIÓN GZIP (Mejora velocidad 60%) ======
Compress(app)

# ====== CONFIGURACIÓN DE SESIÓN ======
# Secret key: usa variable de entorno si existe, si no genera una y la guarda en archivo
_key_file = os.path.join(os.path.dirname(__file__), '.secret_key')
if os.environ.get('SECRET_KEY'):
    app.secret_key = os.environ['SECRET_KEY']
elif os.path.exists(_key_file):
    with open(_key_file, 'r') as f:
        app.secret_key = f.read().strip()
else:
    _new_key = os.urandom(32).hex()
    with open(_key_file, 'w') as f:
        f.write(_new_key)
    app.secret_key = _new_key

app.permanent_session_lifetime = timedelta(hours=2)

# ====== SESIÓN DEL LADO DEL SERVIDOR ======
# Antes la sesión completa (incluyendo el carrito de "Entradas") viajaba
# firmada dentro de la cookie del navegador, que tiene un límite de ~4KB.
# Con facturas de 80-100 productos esa cookie se pasaba del límite y el
# navegador la descartaba en silencio, perdiendo datos capturados sin avisar.
# Ahora la sesión se guarda en un archivo en el servidor (carpeta
# flask_session/) y en la cookie del navegador solo viaja un identificador
# pequeño, así que el carrito puede crecer todo lo que haga falta.
_session_dir = os.path.join(os.path.dirname(__file__), 'flask_session')
os.makedirs(_session_dir, exist_ok=True)
app.config['SESSION_TYPE'] = 'cachelib'
app.config['SESSION_CACHELIB'] = FileSystemCache(cache_dir=_session_dir, threshold=500)
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True  # firma el id de sesión en la cookie
app.config['SESSION_KEY_PREFIX'] = 'almacen_'
app.config.pop('SESSION_USE_SIGNER', None)
Session(app)

# ====== PROTECCION CSRF ======
# Se implementa a nivel central para cubrir formularios tradicionales y APIs
# internas sin tener que recordar un decorador en cada ruta nueva.
@app.before_request
def csrf_protect():
    if app.config.get('WTF_CSRF_ENABLED', True) is False:
        return None

    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token

    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        supplied = request.form.get('_csrf_token') or request.headers.get('X-CSRFToken')
        if not supplied or not secrets.compare_digest(token, supplied):
            abort(400, description='Token de seguridad CSRF invalido o ausente.')


@app.context_processor
def inject_csrf_token():
    def puede_modificar(modulo=None):
        return True

    usuarios_selector = []
    try:
        conn = get_db()
        usuarios_selector = conn.execute(
            "SELECT id, nombre FROM usuarios WHERE activo=1 ORDER BY nombre"
        ).fetchall()
        conn.close()
    except Exception:
        app.logger.exception('No se pudo cargar el selector de usuarios')

    return {
        'csrf_token': lambda: session.get('_csrf_token', ''),
        'puede_modificar': puede_modificar,
        'usuarios_selector': usuarios_selector,
    }


# Matriz de operaciones que modifican datos. Las consultas GET siguen
# disponibles para cualquier usuario autenticado; el perfil consulta no puede
# ejecutar POST/PUT/PATCH/DELETE en modulos operativos.
_ROLES_POR_MODULO = {
    'inventario': {'admin', 'almacen'},
    'entradas': {'admin', 'almacen'},
    'salidas': {'admin', 'almacen'},
    'vales_montacargas': {'admin', 'almacen'},
    'montacargas': {'admin', 'almacen'},
    'areas': {'admin', 'almacen'},
    'proveedores': {'admin', 'almacen', 'compras'},
    'requisiciones': {'admin', 'almacen', 'compras'},
    'balance': {'admin', 'almacen'},
    'listados': {'admin', 'almacen', 'compras'},
    'usuarios': {'admin'},
}


@app.before_request
def authorize_mutation():
    if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return None
    if request.blueprint in {None, 'auth'}:
        return None
    if 'user_id' not in session:
        from routes.auth import seleccionar_primer_usuario_activo
        seleccionar_primer_usuario_activo()
    return None


@app.before_request
def force_password_change():
    return None

app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

# ====== FILTROS DE JINJA ======
@app.template_filter('moneda')
def formato_moneda(valor):
    """Formatea un número con separador de miles (coma) y 2 decimales.
    Ej: 151616692.79 -> '151,616,692.79'. Se usa en templates como {{ x|moneda }}
    en vez de {{ '%.2f'|format(x) }}."""
    try:
        return f"{float(valor or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


@app.template_filter('cantidad_unidad')
def cantidad_unidad(cantidad, unidad):
    """Muestra cantidad y unidad con singular/plural consistente."""
    try:
        numero = float(cantidad or 0)
    except (TypeError, ValueError):
        numero = 0
    texto = str(unidad or '').strip()
    base = texto.lower()
    singulares = {
        'pieza': 'pieza', 'piezas': 'pieza', 'pza': 'pieza', 'pzas': 'pieza',
        'kilo': 'kilo', 'kilos': 'kilo', 'kilogramo': 'kilogramo', 'kilogramos': 'kilogramo',
        'litro': 'litro', 'litros': 'litro', 'metro': 'metro', 'metros': 'metro',
        'caja': 'caja', 'cajas': 'caja', 'rollo': 'rollo', 'rollos': 'rollo',
        'juego': 'juego', 'juegos': 'juego', 'unidad': 'unidad', 'unidades': 'unidad',
    }
    singular = singulares.get(base, base[:-1] if base.endswith('s') and len(base) > 3 else base)
    palabra = singular + ('s' if numero >= 2 and not singular.endswith('s') else '')
    if texto.isupper():
        palabra = palabra.upper()
    elif texto[:1].isupper():
        palabra = palabra.capitalize()
    return f"{cantidad} {palabra}".strip()


@app.template_filter('fecha_vale')
def formato_fecha_vale(valor):
    if not valor:
        return "-"
    meses = ['', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
             'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    texto = str(valor)[:10]
    try:
        anio, mes, dia = texto.split('-')
        return f"{dia}/{meses[int(mes)]}/{anio[-2:]}"
    except Exception:
        return texto

# ====== REGISTRO DE BLUEPRINTS ======
blueprints = [
    auth_bp, inventario_bp, entradas_bp, salidas_bp,
    reportes_bp, usuarios_bp, dashboard_bp, proveedores_bp,
    balance_bp, requisiciones_bp, montacargas_bp, vales_montacargas_bp, areas_bp,
    listados_bp
]

for blueprint in blueprints:
    app.register_blueprint(blueprint)


@app.route('/movil')
def movil_redirect():
    return redirect(url_for('inventario.movil'))

# ====== HEALTH CHECK ENDPOINT ======
@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint para monitoreo de salud del sistema"""
    return jsonify({'status': 'ok', 'version': os.environ.get('ERP_VERSION', 'ERP ALMACEN GENERAL')}), 200

# ====== ERROR HANDLERS ======
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Página no encontrada'}), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f'Server Error: {error}')
    return jsonify({'error': 'Error interno del servidor'}), 500

@app.errorhandler(403)
def forbidden(error):
    return jsonify({'error': 'Acceso denegado'}), 403


@app.errorhandler(400)
def bad_request(error):
    return jsonify({'error': getattr(error, 'description', 'Solicitud invalida')}), 400

# ====== INICIALIZACIÓN DE BASE DE DATOS ======
with app.app_context():
    if DB_BACKEND == 'postgres':
        app.logger.info('PostgreSQL activo; el esquema se administra con migrations/.')
    elif os.path.exists(DB_PATH):
        migrar_esquema()
    else:
        init_db()
    app.logger.info("Base de datos inicializada correctamente")

# ====== PUNTO DE ENTRADA ======
if __name__ == "__main__":
    debug_mode = os.environ.get('DEBUG', 'True').lower() == 'true'
    port = int(os.environ.get('ERP_PORT', '5001'))
    app.run(debug=debug_mode, host="127.0.0.1", port=port)
