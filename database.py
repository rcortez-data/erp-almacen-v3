import sqlite3
import os
from datetime import datetime, date
from decimal import Decimal
from constantes import CATEGORIAS, DEPARTAMENTOS, UNIDADES
from config import config

DB_BACKEND = os.environ.get("ERP_DB_BACKEND", "sqlite").lower()
DB_PATH = os.environ.get("ERP_DATABASE_PATH") or os.environ.get("DATABASE_PATH") or config.DATABASE_PATH
DATABASE_URL = os.environ.get('DATABASE_URL')


class CompatRow:
    """Fila accesible por indice y por nombre, igual que sqlite3.Row."""
    def __init__(self, columns, values):
        self._columns = columns
        self._values = tuple(
            value.isoformat(sep=' ') if isinstance(value, datetime)
            else value.isoformat() if isinstance(value, date)
            else float(value) if isinstance(value, Decimal)
            else value
            for value in values
        )
        self._mapping = dict(zip(columns, self._values))

    def __getitem__(self, key):
        return self._values[key] if isinstance(key, (int, slice)) else self._mapping[key]

    def __iter__(self):
        return iter(self._values)

    def keys(self):
        return self._columns


def _postgres_sql(query):
    query = query.replace('INSERT OR IGNORE INTO', 'INSERT INTO')
    if 'INSERT INTO' in query.upper() and 'OR IGNORE' not in query.upper():
        # Las consultas que originalmente usaban OR IGNORE se detectan antes
        # del reemplazo mediante el texto original en PostgresCursor.execute.
        pass
    return query.replace('?', '%s')


class PostgresCursor:
    def __init__(self, connection):
        self.connection = connection
        self.cursor = connection._raw.cursor()

    def execute(self, query, params=()):
        was_ignore = 'INSERT OR IGNORE INTO' in query.upper()
        query = _postgres_sql(query)
        if was_ignore and 'ON CONFLICT' not in query.upper():
            query = query.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
        self.cursor.execute(query, tuple(params or ()))
        self.connection._last_rowcount = self.cursor.rowcount
        return self

    def executemany(self, query, params):
        self.cursor.executemany(_postgres_sql(query), params)
        self.connection._last_rowcount = self.cursor.rowcount
        return self

    def _wrap(self, row):
        if row is None: return None
        columns = [item.name for item in self.cursor.description]
        return CompatRow(columns, row)

    def fetchone(self): return self._wrap(self.cursor.fetchone())
    def fetchall(self): return [self._wrap(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        for row in self.cursor:
            yield self._wrap(row)

    @property
    def lastrowid(self):
        with self.connection._raw.cursor() as cursor:
            cursor.execute('SELECT LASTVAL()')
            return cursor.fetchone()[0]

    @property
    def rowcount(self): return self.cursor.rowcount


class PostgresConnection:
    def __init__(self, url):
        import psycopg
        self._raw = psycopg.connect(url)
        self._last_rowcount = 0

    def cursor(self): return PostgresCursor(self)
    def execute(self, query, params=()): return self.cursor().execute(query, params)
    def executemany(self, query, params): return self.cursor().executemany(query, params)
    def commit(self): return self._raw.commit()
    def rollback(self): return self._raw.rollback()
    def close(self): return self._raw.close()
    @property
    def total_changes(self): return max(0, self._last_rowcount)


def get_db():
    if DB_BACKEND == 'postgres':
        if not DATABASE_URL:
            raise RuntimeError('ERP_DB_BACKEND=postgres requiere DATABASE_URL.')
        return PostgresConnection(DATABASE_URL)
    if DB_BACKEND != "sqlite":
        raise RuntimeError(f"Motor de base de datos no soportado: {DB_BACKEND}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nombre TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'consulta' CHECK(rol IN ('admin', 'almacen', 'compras', 'produccion', 'mantenimiento', 'consulta')),
            activo INTEGER DEFAULT 1,
            debe_cambiar_password INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS actividad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER REFERENCES usuarios(id),
            accion TEXT NOT NULL,
            detalle TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS unidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            codigo_barras TEXT UNIQUE,
            descripcion TEXT NOT NULL,
            categoria_id INTEGER REFERENCES categorias(id),
            categoria_nombre_historico TEXT,
            unidad_medida TEXT NOT NULL,
            ubicacion TEXT,
            departamento TEXT,
            departamento_nombre_historico TEXT,
            maquina TEXT,
            maquina_otro TEXT,
            unidad_compra TEXT,
            factor_conversion REAL,
            tipo_conversion TEXT DEFAULT 'uso_a_compra',
            stock_actual REAL DEFAULT 0,
            stock_minimo REAL DEFAULT 0,
            precio_unitario REAL DEFAULT 0,
            activo INTEGER DEFAULT 1,
            baja_por TEXT,
            baja_folio TEXT,
            baja_fecha TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            nombre_comercial TEXT,
            contacto TEXT,
            activo INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS entradas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE NOT NULL,
            producto_id INTEGER REFERENCES productos(id),
            es_servicio INTEGER DEFAULT 0,
            concepto_servicio TEXT,
            cantidad REAL NOT NULL,
            precio_unitario REAL DEFAULT 0,
            importe REAL DEFAULT 0,
            no_requisicion TEXT,
            no_factura TEXT,
            orden_compra TEXT,
            no_remision TEXT,
            recuperacion_almacen INTEGER DEFAULT 0,
            proveedor_id INTEGER REFERENCES proveedores(id),
            proveedor_nombre_historico TEXT,
            departamento TEXT,
            ubicacion TEXT,
            uso TEXT,
            tipo_movimiento TEXT DEFAULT 'normal',
            cantidad_piezas REAL,
            usuario_id INTEGER REFERENCES usuarios(id),
            observaciones TEXT,
            folio_excel TEXT,
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            fecha_vale TEXT
        );

        CREATE TABLE IF NOT EXISTS salidas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE NOT NULL,
            producto_id INTEGER REFERENCES productos(id),
            cantidad REAL NOT NULL,
            responsable TEXT NOT NULL,
            area TEXT,
            no_vale TEXT,
            tipo_vale TEXT,
            maquina TEXT,
            no_factura TEXT,
            no_remision TEXT,
            tipo_movimiento TEXT DEFAULT 'normal',
            usuario_id INTEGER REFERENCES usuarios(id),
            observaciones TEXT,
            folio_excel TEXT,
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            fecha_vale TEXT
        );

        CREATE TABLE IF NOT EXISTS montacargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vales_montacargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE NOT NULL,
            no_vale TEXT NOT NULL,
            responsable TEXT NOT NULL,
            area TEXT,
            montacargas_id INTEGER REFERENCES montacargas(id),
            montacargas_nombre_historico TEXT,
            cantidad REAL NOT NULL,
            unidad TEXT DEFAULT 'piezas',
            observaciones TEXT,
            usuario_id INTEGER REFERENCES usuarios(id),
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            fecha_vale TEXT
        );

        CREATE TABLE IF NOT EXISTS material_por_pedir (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER REFERENCES productos(id),
            codigo TEXT,
            descripcion TEXT NOT NULL,
            cantidad REAL DEFAULT 0,
            unidad TEXT,
            prioridad TEXT DEFAULT 'normal',
            motivo TEXT,
            solicitado INTEGER DEFAULT 0,
            fecha_solicitado TEXT,
            orden_compra TEXT,
            requisicion_id INTEGER REFERENCES requisiciones(id),
            requisicion_folio TEXT,
            notas_pedido TEXT,
            usuario_id INTEGER REFERENCES usuarios(id),
            pedido_por_usuario_id INTEGER REFERENCES usuarios(id),
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS conteos_fisicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER REFERENCES productos(id),
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            existencia_fisica REAL NOT NULL,
            usuario_id INTEGER REFERENCES usuarios(id),
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(producto_id, anio, mes)
        );

        CREATE TABLE IF NOT EXISTS cierres_mensuales_periodos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL CHECK(mes BETWEEN 1 AND 12),
            estado TEXT NOT NULL DEFAULT 'abierto' CHECK(estado IN ('abierto', 'cerrado')),
            cerrado_por INTEGER REFERENCES usuarios(id),
            cerrado_en TEXT,
            reabierto_por INTEGER REFERENCES usuarios(id),
            reabierto_en TEXT,
            motivo_reapertura TEXT,
            UNIQUE(anio, mes)
        );

        CREATE TABLE IF NOT EXISTS folios (
            tipo TEXT PRIMARY KEY,
            ultimo INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS folios_diarios (
            fecha TEXT PRIMARY KEY,
            folio INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS requisiciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio INTEGER NOT NULL,
            fecha_requisicion TEXT,
            fecha_necesita TEXT,
            departamento TEXT,
            solicitante TEXT,
            asunto TEXT,
            visto_bueno TEXT,
            autorizo TEXT,
            orden_compra TEXT,
            no_factura TEXT,
            no_remision TEXT,
            estado TEXT DEFAULT 'pendiente',
            observaciones TEXT,
            usuario_id INTEGER REFERENCES usuarios(id),
            fecha TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS requisicion_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requisicion_id INTEGER REFERENCES requisiciones(id) ON DELETE CASCADE,
            orden INTEGER,
            cantidad REAL NOT NULL,
            unidad TEXT,
            descripcion TEXT NOT NULL,
            cantidad_recibida REAL DEFAULT 0,
            producto_id INTEGER REFERENCES productos(id),
            recepcion_manual INTEGER DEFAULT 0,
            recepcion_manual_at TEXT,
            recepcion_manual_usuario_id INTEGER REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS requisicion_item_recepciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requisicion_item_id INTEGER REFERENCES requisicion_items(id) ON DELETE CASCADE,
            cantidad REAL NOT NULL,
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            usuario_id INTEGER REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS personal_mantenimiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            codigo_barras TEXT UNIQUE,
            nombre TEXT NOT NULL,
            area TEXT,
            turno TEXT,
            tipo_responsable TEXT DEFAULT 'mantenimiento',
            activo INTEGER DEFAULT 1,
            observaciones TEXT,
            fecha_alta TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS material_prestamo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            codigo_barras TEXT UNIQUE,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            categoria TEXT,
            ubicacion TEXT,
            foto_ruta TEXT,
            foto_ubicacion_ruta TEXT,
            estado TEXT DEFAULT 'disponible'
                CHECK(estado IN ('disponible', 'prestado', 'danado', 'perdido', 'mantenimiento', 'baja')),
            activo INTEGER DEFAULT 1,
            observaciones TEXT,
            fecha_alta TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS prestamos_mantenimiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL REFERENCES material_prestamo(id),
            trabajador_recibe_id INTEGER NOT NULL REFERENCES personal_mantenimiento(id),
            trabajador_devuelve_id INTEGER REFERENCES personal_mantenimiento(id),
            fecha_prestamo TEXT DEFAULT CURRENT_TIMESTAMP,
            fecha_devolucion TEXT,
            usuario_prestamo_id INTEGER REFERENCES usuarios(id),
            usuario_devolucion_id INTEGER REFERENCES usuarios(id),
            estado TEXT DEFAULT 'prestado' CHECK(estado IN ('prestado', 'devuelto', 'perdido')),
            estado_devolucion TEXT,
            recibe_codigo_historico TEXT,
            recibe_nombre_historico TEXT,
            recibe_area_historico TEXT,
            devuelve_codigo_historico TEXT,
            devuelve_nombre_historico TEXT,
            devuelve_area_historico TEXT,
            observaciones_prestamo TEXT,
            observaciones_devolucion TEXT
        );

        CREATE TABLE IF NOT EXISTS etiquetas_produccion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto TEXT NOT NULL,
            uso TEXT NOT NULL,
            pictograma TEXT DEFAULT 'advertencia',
            activo INTEGER DEFAULT 1,
            observaciones TEXT,
            fecha_alta TEXT DEFAULT CURRENT_TIMESTAMP,
            fecha_actualizacion TEXT
        );
    """)

    # Insertar folios iniciales
    c.execute("INSERT OR IGNORE INTO folios VALUES ('entrada', 0)")
    c.execute("INSERT OR IGNORE INTO folios VALUES ('salida', 0)")
    c.execute("INSERT OR IGNORE INTO folios VALUES ('producto', 0)")
    c.execute("INSERT OR IGNORE INTO folios VALUES ('vale_montacargas', 0)")
    c.execute("INSERT OR IGNORE INTO folios VALUES ('personal_mantenimiento', 0)")
    c.execute("INSERT OR IGNORE INTO folios VALUES ('material_prestamo', 0)")

    # Usuario admin por defecto
    from werkzeug.security import generate_password_hash
    c.execute("""
        INSERT OR IGNORE INTO usuarios (username, password, nombre, rol)
        VALUES (?, ?, ?, ?)
    """, ('admin', generate_password_hash('admin123'), 'Administrador', 'admin'))

    # Categorías fijas
    for cat in CATEGORIAS:
        c.execute("INSERT OR IGNORE INTO categorias (nombre) VALUES (?)", (cat,))
    for unidad in UNIDADES:
        c.execute("INSERT OR IGNORE INTO unidades (nombre) VALUES (?)", (unidad,))

    conn.commit()
    conn.close()
    migrar_esquema()
    print("Base de datos inicializada.")


def migrar_esquema():
    """Agrega columnas nuevas a bases de datos ya existentes (no rompe datos)."""
    conn = get_db()
    c = conn.cursor()

    # Amplia el catalogo de roles de las bases V2/V3 antiguas, que tenian un
    # CHECK limitado exclusivamente a "admin". La reconstruccion conserva IDs,
    # hashes de contrasena, estado y fechas de todos los usuarios.
    usuarios_sql = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='usuarios'"
    ).fetchone()
    roles_sql = usuarios_sql[0] or '' if usuarios_sql else ''
    if usuarios_sql and ("'produccion'" not in roles_sql or "'mantenimiento'" not in roles_sql):
        columnas_usuario = {
            fila[1] for fila in c.execute('PRAGMA table_info(usuarios)').fetchall()
        }
        tiene_cambio_password = 'debe_cambiar_password' in columnas_usuario
        columna_extra_def = ', debe_cambiar_password INTEGER DEFAULT 0' if tiene_cambio_password else ''
        columna_extra = ', debe_cambiar_password' if tiene_cambio_password else ''
        conn.commit()
        conn.execute('PRAGMA foreign_keys = OFF')
        try:
            conn.execute('BEGIN')
            conn.execute(f"""
                CREATE TABLE usuarios_nueva (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    rol TEXT NOT NULL DEFAULT 'consulta'
                        CHECK(rol IN ('admin', 'almacen', 'compras', 'produccion', 'mantenimiento', 'consulta')),
                    activo INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    {columna_extra_def}
                )
            """)
            conn.execute(f"""
                INSERT INTO usuarios_nueva (id, username, password, nombre, rol, activo, created_at{columna_extra})
                SELECT id, username, password, nombre,
                       CASE WHEN rol IN ('admin', 'almacen', 'compras', 'produccion', 'mantenimiento', 'consulta') THEN rol ELSE 'consulta' END,
                       activo, created_at{columna_extra}
                FROM usuarios
            """)
            conn.execute('DROP TABLE usuarios')
            conn.execute('ALTER TABLE usuarios_nueva RENAME TO usuarios')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute('PRAGMA foreign_keys = ON')

    def col_existe(tabla, columna):
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({tabla})").fetchall()]
        return columna in cols

    def index_existe(nombre_index):
        resultado = c.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (nombre_index,)
        ).fetchone()
        return resultado is not None

    columnas_nuevas = {
        'usuarios': [('debe_cambiar_password', 'INTEGER DEFAULT 0')],
        'productos': [('codigo_barras', 'TEXT'),
                       ('maquina', 'TEXT'), ('maquina_otro', 'TEXT'),
                       ('unidad_compra', 'TEXT'), ('factor_conversion', 'REAL'),
                       ('tipo_conversion', "TEXT DEFAULT 'uso_a_compra'"),
                       ('estado_fisico', 'TEXT'), ('categoria_nombre_historico', 'TEXT'),
                       ('departamento_nombre_historico', 'TEXT'),
                       ('proveedor_nombre_historico', 'TEXT'),
                       ('stock_origen', "TEXT DEFAULT 'ALMACEN'"),
                       ('producto_origen_id', 'INTEGER')],
        'entradas': [('departamento', 'TEXT'), ('tipo_movimiento', 'TEXT'),
                     ('ubicacion', 'TEXT'), ('uso', 'TEXT'),
                     ('cantidad_piezas', 'REAL'), ('folio_excel', 'TEXT'),
                     ('proveedor_nombre_historico', 'TEXT'),
                     ('es_servicio', 'INTEGER DEFAULT 0'), ('concepto_servicio', 'TEXT'),
                     ('moneda', "TEXT DEFAULT 'MXN'"),
                     ('aplica_iva', 'INTEGER'),
                     ('compra_gas', 'INTEGER DEFAULT 0'),
                     ('recuperacion_almacen', 'INTEGER DEFAULT 0'),
                     ('fecha_vale', 'TEXT')],
        'salidas': [('no_vale', 'TEXT'), ('tipo_movimiento', 'TEXT'),
                    ('area', 'TEXT'), ('folio_excel', 'TEXT'),
                    ('es_servicio', 'INTEGER DEFAULT 0'), ('concepto_servicio', 'TEXT'),
                    ('tipo_vale', 'TEXT'), ('maquina', 'TEXT'),
                    ('maquina_otro', 'TEXT'), ('proveedor', 'TEXT'),
                    ('orden_compra', 'TEXT'), ('no_factura', 'TEXT'), ('no_remision', 'TEXT'),
                    ('fecha_vale', 'TEXT')],
        'proveedores': [('nombre_comercial', 'TEXT')],
        'vales_montacargas': [('area_id', 'INTEGER REFERENCES areas(id)'),
                              ('area_nombre_historico', 'TEXT'),
                              ('fecha_vale', 'TEXT')],
        'conteos_fisicos': [('salidas_manual', 'REAL'),
                            ('existencia_inicio', 'REAL'),
                            ('entradas_mes', 'REAL')],
        'material_por_pedir': [('requisicion_id', 'INTEGER REFERENCES requisiciones(id)'),
                               ('requisicion_folio', 'TEXT')],
        'requisicion_items': [('recepcion_manual', 'INTEGER DEFAULT 0'),
                              ('recepcion_manual_at', 'TEXT'),
                              ('recepcion_manual_usuario_id', 'INTEGER REFERENCES usuarios(id)')],
    }
    for tabla, columnas in columnas_nuevas.items():
        for columna, tipo in columnas:
            if not col_existe(tabla, columna):
                c.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")

    # Las credenciales temporales existentes obligan al usuario a cambiar su
    # contrasena en el siguiente inicio de sesion.
    from werkzeug.security import check_password_hash
    for usuario in c.execute('SELECT id, password FROM usuarios').fetchall():
        if check_password_hash(usuario['password'], 'admin123'):
            c.execute('UPDATE usuarios SET debe_cambiar_password=1 WHERE id=?', (usuario['id'],))

    # ====== Catálogo de áreas (por si la BD es anterior a este cambio) ======
    c.execute("""
        CREATE TABLE IF NOT EXISTS areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for dep in DEPARTAMENTOS:
        c.execute("INSERT OR IGNORE INTO areas (nombre) VALUES (?)", (dep,))

    # ====== Catálogo de unidades ======
    c.execute("""
        CREATE TABLE IF NOT EXISTS unidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for unidad in UNIDADES:
        c.execute("INSERT OR IGNORE INTO unidades (nombre) VALUES (?)", (unidad,))

    # ====== Codigos de barras internos ======
    # Formato inicial: TENSA + codigo de producto, por ejemplo TENSA-PRD-000001.
    # No usa codigos comerciales externos.
    codigos_usados = set()
    for producto in c.execute("SELECT id, codigo FROM productos ORDER BY LOWER(codigo), id").fetchall():
        codigo_barras = generar_codigo_barras_producto(producto['codigo'])
        if codigo_barras in codigos_usados:
            codigo_barras = generar_codigo_barras_producto(producto['codigo'], producto['id'])
        codigos_usados.add(codigo_barras)
        c.execute(
            "UPDATE productos SET codigo_barras=? WHERE id=?",
            (codigo_barras, producto['id'])
        )

    # Migra los vales que ya tenían área como texto libre: si el texto coincide
    # con un área del catálogo se enlaza por id; si no coincide, se guarda como
    # histórico para no perder el dato (igual que se hizo con montacargas).
    if col_existe('vales_montacargas', 'area_id'):
        vales_sin_migrar = c.execute("""
            SELECT id, area FROM vales_montacargas
            WHERE area IS NOT NULL AND area != '' AND area_id IS NULL AND area_nombre_historico IS NULL
        """).fetchall()
        for v in vales_sin_migrar:
            match = c.execute("SELECT id FROM areas WHERE nombre=?", (v['area'],)).fetchone()
            if match:
                c.execute("UPDATE vales_montacargas SET area_id=? WHERE id=?", (match['id'], v['id']))
            else:
                c.execute("UPDATE vales_montacargas SET area_nombre_historico=? WHERE id=?", (v['area'], v['id']))

    # ====== Historial de recepciones parciales de partidas de requisición ======
    # Permite registrar varias entregas de una misma partida (ej. llegan 1000 kg
    # hoy y 500 kg después), cada una con su propia fecha automática, en vez de
    # un solo número que se sobreescribe y pierde el historial.
    c.execute("""
        CREATE TABLE IF NOT EXISTS requisicion_item_recepciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requisicion_item_id INTEGER REFERENCES requisicion_items(id) ON DELETE CASCADE,
            cantidad REAL NOT NULL,
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            usuario_id INTEGER REFERENCES usuarios(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS cierres_mensuales_periodos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL CHECK(mes BETWEEN 1 AND 12),
            estado TEXT NOT NULL DEFAULT 'abierto' CHECK(estado IN ('abierto', 'cerrado')),
            cerrado_por INTEGER REFERENCES usuarios(id),
            cerrado_en TEXT,
            reabierto_por INTEGER REFERENCES usuarios(id),
            reabierto_en TEXT,
            motivo_reapertura TEXT,
            UNIQUE(anio, mes)
        )
    """)
    # ====== PERSONAL Y MATERIAL A PRÉSTAMO PARA MANTENIMIENTO ======
    c.execute("""
        CREATE TABLE IF NOT EXISTS personal_mantenimiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            codigo_barras TEXT UNIQUE,
            nombre TEXT NOT NULL,
            area TEXT,
            turno TEXT,
            tipo_responsable TEXT DEFAULT 'mantenimiento',
            activo INTEGER DEFAULT 1,
            observaciones TEXT,
            fecha_alta TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS material_prestamo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            codigo_barras TEXT UNIQUE,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            categoria TEXT,
            ubicacion TEXT,
            foto_ruta TEXT,
            foto_ubicacion_ruta TEXT,
            estado TEXT DEFAULT 'disponible'
                CHECK(estado IN ('disponible', 'prestado', 'danado', 'perdido', 'mantenimiento', 'baja')),
            activo INTEGER DEFAULT 1,
            observaciones TEXT,
            fecha_alta TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS prestamos_mantenimiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL REFERENCES material_prestamo(id),
            trabajador_recibe_id INTEGER NOT NULL REFERENCES personal_mantenimiento(id),
            trabajador_devuelve_id INTEGER REFERENCES personal_mantenimiento(id),
            fecha_prestamo TEXT DEFAULT CURRENT_TIMESTAMP,
            fecha_devolucion TEXT,
            usuario_prestamo_id INTEGER REFERENCES usuarios(id),
            usuario_devolucion_id INTEGER REFERENCES usuarios(id),
            estado TEXT DEFAULT 'prestado' CHECK(estado IN ('prestado', 'devuelto', 'perdido')),
            estado_devolucion TEXT,
            recibe_codigo_historico TEXT,
            recibe_nombre_historico TEXT,
            recibe_area_historico TEXT,
            devuelve_codigo_historico TEXT,
            devuelve_nombre_historico TEXT,
            devuelve_area_historico TEXT,
            observaciones_prestamo TEXT,
            observaciones_devolucion TEXT
        )
    """)
    for columna, tipo in [
        ('tipo_responsable', "TEXT DEFAULT 'mantenimiento'"),
    ]:
        if not col_existe('personal_mantenimiento', columna):
            c.execute(f"ALTER TABLE personal_mantenimiento ADD COLUMN {columna} {tipo}")
    if not col_existe('material_prestamo', 'foto_ubicacion_ruta'):
        c.execute("ALTER TABLE material_prestamo ADD COLUMN foto_ubicacion_ruta TEXT")
    for columna, tipo in [
        ('recibe_codigo_historico', 'TEXT'),
        ('recibe_nombre_historico', 'TEXT'),
        ('recibe_area_historico', 'TEXT'),
        ('devuelve_codigo_historico', 'TEXT'),
        ('devuelve_nombre_historico', 'TEXT'),
        ('devuelve_area_historico', 'TEXT'),
        ('estado_devolucion', 'TEXT'),
    ]:
        if not col_existe('prestamos_mantenimiento', columna):
            c.execute(f"ALTER TABLE prestamos_mantenimiento ADD COLUMN {columna} {tipo}")
    c.execute("INSERT OR IGNORE INTO folios VALUES ('personal_mantenimiento', 0)")
    c.execute("INSERT OR IGNORE INTO folios VALUES ('material_prestamo', 0)")

    # ====== ETIQUETAS PRODUCCIÓN ======
    c.execute("""
        CREATE TABLE IF NOT EXISTS etiquetas_produccion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto TEXT NOT NULL,
            uso TEXT NOT NULL,
            pictograma TEXT DEFAULT 'advertencia',
            activo INTEGER DEFAULT 1,
            observaciones TEXT,
            fecha_alta TEXT DEFAULT CURRENT_TIMESTAMP,
            fecha_actualizacion TEXT
        )
    """)
    conn.commit()
    
    # ====== OPTIMIZACIÓN: Agregar índices para búsquedas rápidas ======
    indices = [
        ("idx_productos_codigo", "CREATE INDEX IF NOT EXISTS idx_productos_codigo ON productos(codigo)"),
        ("idx_productos_codigo_barras", "CREATE UNIQUE INDEX IF NOT EXISTS idx_productos_codigo_barras ON productos(codigo_barras)"),
        ("idx_entradas_fecha", "CREATE INDEX IF NOT EXISTS idx_entradas_fecha ON entradas(fecha)"),
        ("idx_entradas_producto", "CREATE INDEX IF NOT EXISTS idx_entradas_producto ON entradas(producto_id)"),
        ("idx_salidas_fecha", "CREATE INDEX IF NOT EXISTS idx_salidas_fecha ON salidas(fecha)"),
        ("idx_salidas_producto", "CREATE INDEX IF NOT EXISTS idx_salidas_producto ON salidas(producto_id)"),
        ("idx_requisiciones_estado", "CREATE INDEX IF NOT EXISTS idx_requisiciones_estado ON requisiciones(estado)"),
        ("idx_requisiciones_fecha", "CREATE INDEX IF NOT EXISTS idx_requisiciones_fecha ON requisiciones(fecha)"),
        ("idx_requisiciones_folio_unico", "CREATE UNIQUE INDEX IF NOT EXISTS idx_requisiciones_folio_unico ON requisiciones(folio)"),
        ("idx_usuarios_username", "CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username)"),
        ("idx_proveedores_nombre", "CREATE INDEX IF NOT EXISTS idx_proveedores_nombre ON proveedores(nombre)"),
        ("idx_actividad_timestamp", "CREATE INDEX IF NOT EXISTS idx_actividad_timestamp ON actividad(timestamp)"),
    ]
    
    for nombre, sql in indices:
        if not index_existe(nombre):
            c.execute(sql)

    c.execute("""
        CREATE TABLE IF NOT EXISTS folios_diarios (
            fecha TEXT PRIMARY KEY,
            folio INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS requisiciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio INTEGER NOT NULL,
            fecha_requisicion TEXT,
            fecha_necesita TEXT,
            departamento TEXT,
            solicitante TEXT,
            asunto TEXT,
            visto_bueno TEXT,
            autorizo TEXT,
            orden_compra TEXT,
            no_factura TEXT,
            no_remision TEXT,
            estado TEXT DEFAULT 'pendiente',
            observaciones TEXT,
            usuario_id INTEGER REFERENCES usuarios(id),
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            fecha_vale TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS requisicion_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requisicion_id INTEGER REFERENCES requisiciones(id) ON DELETE CASCADE,
            orden INTEGER,
            cantidad REAL NOT NULL,
            unidad TEXT,
            descripcion TEXT NOT NULL,
            cantidad_recibida REAL DEFAULT 0,
            recepcion_manual INTEGER DEFAULT 0,
            recepcion_manual_at TEXT,
            recepcion_manual_usuario_id INTEGER REFERENCES usuarios(id)
        )
    """)
    if not col_existe('requisicion_items', 'producto_id'):
        c.execute("ALTER TABLE requisicion_items ADD COLUMN producto_id INTEGER REFERENCES productos(id)")

    c.execute("INSERT OR IGNORE INTO folios VALUES ('requisicion', 0)")

    # ====== BLOQUES PREDEFINIDOS PARA BALANCE MENSUAL ======
    c.execute("""
        CREATE TABLE IF NOT EXISTS bloques_balance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            descripcion TEXT,
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS bloque_productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bloque_id INTEGER REFERENCES bloques_balance(id) ON DELETE CASCADE,
            producto_id INTEGER REFERENCES productos(id),
            orden INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Crear índices para búsquedas rápidas en bloques
    if not index_existe("idx_bloque_productos_bloque"):
        c.execute("CREATE INDEX IF NOT EXISTS idx_bloque_productos_bloque ON bloque_productos(bloque_id)")
    if not index_existe("idx_bloque_productos_producto"):
        c.execute("CREATE INDEX IF NOT EXISTS idx_bloque_productos_producto ON bloque_productos(producto_id)")

    # Configuracion independiente para los analisis de consumo del Dashboard.
    c.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_consumo_productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
            grupo TEXT NOT NULL CHECK (grupo IN ('produccion', 'caldera')),
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(producto_id, grupo)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_tipo_cambio (
            fecha TEXT PRIMARY KEY,
            usd_mxn REAL NOT NULL,
            fuente TEXT,
            actualizado_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_consumo_inicio (
            producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
            grupo TEXT NOT NULL CHECK (grupo IN ('produccion', 'caldera')),
            anio INTEGER NOT NULL,
            cantidad REAL NOT NULL DEFAULT 0,
            actualizado_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (producto_id, grupo, anio)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_dashboard_consumo_grupo ON dashboard_consumo_productos(grupo, activo)")

    # Agrega categorías nuevas que no existían todavía (no borra ni renombra las viejas)
    for cat in CATEGORIAS:
        c.execute("INSERT OR IGNORE INTO categorias (nombre) VALUES (?)", (cat,))

    # Limpieza: "Limpieza (grasas, aceites y lubricantes)" quedó de una migración anterior,
    # antes de separarla en "Grasas, Aceites y Lubricantes" y "Limpieza". Si algún producto
    # todavía la usa, se reasigna a "Limpieza" para no perder el dato, y se borra la categoría
    # vieja para que ya no aparezca en los selects.
    vieja = c.execute(
        "SELECT id FROM categorias WHERE nombre='Limpieza (grasas, aceites y lubricantes)'").fetchone()
    if vieja:
        nueva = c.execute("SELECT id FROM categorias WHERE nombre='Limpieza'").fetchone()
        if nueva:
            c.execute("UPDATE productos SET categoria_id=? WHERE categoria_id=?", (nueva[0], vieja[0]))
        c.execute("DELETE FROM categorias WHERE id=?", (vieja[0],))

    # Folio para reporte diario de entradas
    c.execute("INSERT OR IGNORE INTO folios VALUES ('reporte_diario', 7020)")

    # ====== CATÁLOGO DE MONTACARGAS Y VALES DE SALIDA POR MONTACARGAS ======
    # Apartado independiente para llevar el control de cuántas piezas (tanques)
    # saca cada montacarguista y en cuál montacargas, sin afectar el stock del
    # inventario (a diferencia de la tabla `salidas`).
    c.execute("""
        CREATE TABLE IF NOT EXISTS montacargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS vales_montacargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE NOT NULL,
            no_vale TEXT NOT NULL,
            responsable TEXT NOT NULL,
            area TEXT,
            montacargas_id INTEGER REFERENCES montacargas(id),
            montacargas_nombre_historico TEXT,
            cantidad REAL NOT NULL,
            unidad TEXT DEFAULT 'piezas',
            observaciones TEXT,
            usuario_id INTEGER REFERENCES usuarios(id),
            fecha TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("INSERT OR IGNORE INTO folios VALUES ('vale_montacargas', 0)")
    if not index_existe("idx_vales_montacargas_fecha"):
        c.execute("CREATE INDEX IF NOT EXISTS idx_vales_montacargas_fecha ON vales_montacargas(fecha)")
    if not index_existe("idx_vales_montacargas_montacargas"):
        c.execute("CREATE INDEX IF NOT EXISTS idx_vales_montacargas_montacargas ON vales_montacargas(montacargas_id)")

    # ====== MATERIAL POR PEDIR ======
    # Lista independiente para registrar material agotado o por agotarse.
    # No mueve inventario; sirve para seguimiento hasta marcar "ya se pidió".
    c.execute("""
        CREATE TABLE IF NOT EXISTS material_por_pedir (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER REFERENCES productos(id),
            codigo TEXT,
            descripcion TEXT NOT NULL,
            cantidad REAL DEFAULT 0,
            unidad TEXT,
            prioridad TEXT DEFAULT 'normal',
            motivo TEXT,
            solicitado INTEGER DEFAULT 0,
            fecha_solicitado TEXT,
            orden_compra TEXT,
            requisicion_id INTEGER REFERENCES requisiciones(id),
            requisicion_folio TEXT,
            notas_pedido TEXT,
            usuario_id INTEGER REFERENCES usuarios(id),
            pedido_por_usuario_id INTEGER REFERENCES usuarios(id),
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    """)
    if not index_existe("idx_material_por_pedir_solicitado"):
        c.execute("CREATE INDEX IF NOT EXISTS idx_material_por_pedir_solicitado ON material_por_pedir(solicitado, fecha)")
    if not index_existe("idx_material_por_pedir_producto"):
        c.execute("CREATE INDEX IF NOT EXISTS idx_material_por_pedir_producto ON material_por_pedir(producto_id)")

    # ====== CATÁLOGO DE ÁREAS (mismo patrón que montacargas) ======
    # Alta rápida desde el formulario de Vales de Montacargas, igual que el
    # catálogo de montacargas, en vez de un campo de texto libre.
    c.execute("""
        CREATE TABLE IF NOT EXISTS areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for dep in DEPARTAMENTOS:
        c.execute("INSERT OR IGNORE INTO areas (nombre) VALUES (?)", (dep,))

    conn.commit()
    conn.close()


def obtener_unidades(conn=None, solo_activas=True):
    cerrar = conn is None
    if conn is None:
        conn = get_db()
    query = "SELECT * FROM unidades WHERE 1=1"
    if solo_activas:
        query += " AND activo=1"
    query += " ORDER BY LOWER(nombre)"
    filas = conn.execute(query).fetchall()
    if cerrar:
        conn.close()
    return filas


def obtener_nombres_unidades(conn=None, solo_activas=True):
    return [u['nombre'] for u in obtener_unidades(conn, solo_activas)]


def next_folio(tipo):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo = ?", (tipo,))
    c.execute("SELECT ultimo FROM folios WHERE tipo = ?", (tipo,))
    num = c.fetchone()[0]
    conn.commit()
    conn.close()
    prefix = "ENT" if tipo == "entrada" else "SAL"
    return f"{prefix}-{str(num).zfill(6)}"


def get_folio_diario(fecha_iso):
    """
    Folio consecutivo automático basado en la fecha.
    
    Sistema de folios por fecha:
    - 29 de julio 2026 = folio 7136
    - 30 de julio 2026 = folio 7137
    - 31 de julio 2026 = folio 7138
    - Y así consecutivamente, calculado automáticamente desde la fecha
    
    No se puede corregir manualmente.
    """
    from datetime import date as date_class
    
    # Fecha base: 29 de julio de 2026
    fecha_base = date_class(2026, 7, 29)
    folio_base = 7136
    
    try:
        fecha_actual = datetime.strptime(fecha_iso, '%Y-%m-%d').date()
        dias_diferencia = (fecha_actual - fecha_base).days
        folio = folio_base + dias_diferencia
        return folio
    except:
        # Si hay error, retornar folio por defecto
        return folio_base


def set_folio_diario(fecha_iso, folio_nuevo):
    """
    FUNCIÓN DESACTIVADA: El folio se calcula automáticamente por fecha.
    No se permite corregir manualmente.
    
    El sistema calcula automáticamente:
    - 29 de julio 2026 = folio 7136
    - 30 de julio 2026 = folio 7137
    - 31 de julio 2026 = folio 7138
    """
    pass  # No hace nada, folio es automático


def set_folio_counter(tipo, valor):
    """Corrige a mano el contador de un folio simple (tabla `folios`), ej. 'requisicion',
    para que el siguiente folio generado siga desde el número real usado en papel."""
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO folios VALUES (?, 0)", (tipo,))
    c.execute("UPDATE folios SET ultimo=? WHERE tipo=?", (valor, tipo))
    conn.commit()
    conn.close()


def next_folio_requisicion():
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO folios VALUES ('requisicion', 0)")
    c.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo = 'requisicion'")
    num = c.execute("SELECT ultimo FROM folios WHERE tipo = 'requisicion'").fetchone()[0]
    conn.commit()
    conn.close()
    return num


def generar_codigo_producto():
    """Genera un código secuencial único para productos nuevos: PRD-000001, PRD-000002, ..."""
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO folios VALUES ('producto', 0)")
    c.execute("UPDATE folios SET ultimo = ultimo + 1 WHERE tipo = 'producto'")
    c.execute("SELECT ultimo FROM folios WHERE tipo = 'producto'")
    num = c.fetchone()[0]
    conn.commit()
    conn.close()
    return f"PRD-{str(num).zfill(6)}"


def generar_codigo_barras_producto(codigo_producto, producto_id=None):
    """Genera el codigo de barras interno: TENSA + codigo de producto."""
    codigo = str(codigo_producto or '').strip().upper().replace(' ', '')
    if producto_id is not None:
        return f"TENSA-{codigo}-{producto_id}"
    return f"TENSA-{codigo}"


def log_actividad(usuario_id, accion, detalle=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO actividad (usuario_id, accion, detalle) VALUES (?,?,?)",
        (usuario_id, accion, detalle)
    )
    conn.commit()
    conn.close()
