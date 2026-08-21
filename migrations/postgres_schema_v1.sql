-- ERP Almacen v3 lab
-- Esquema PostgreSQL inicial para prueba de migracion.
-- No ejecutar sobre produccion sin respaldo y validacion previa.

BEGIN;

CREATE TABLE IF NOT EXISTS usuarios (
    id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'consulta' CHECK (rol IN ('admin', 'almacen', 'compras', 'produccion', 'mantenimiento', 'consulta')),
    activo INTEGER DEFAULT 1,
    debe_cambiar_password INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS actividad (
    id BIGSERIAL PRIMARY KEY,
    usuario_id BIGINT REFERENCES usuarios(id),
    accion TEXT NOT NULL,
    detalle TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categorias (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS productos (
    id BIGSERIAL PRIMARY KEY,
    codigo TEXT UNIQUE NOT NULL,
    descripcion TEXT NOT NULL,
    categoria_id BIGINT REFERENCES categorias(id),
    categoria_nombre_historico TEXT,
    categoria_historica TEXT,
    unidad_medida TEXT NOT NULL,
    ubicacion TEXT,
    departamento TEXT,
    departamento_nombre_historico TEXT,
    maquina TEXT,
    maquina_otro TEXT,
    unidad_compra TEXT,
    factor_conversion NUMERIC,
    stock_actual NUMERIC DEFAULT 0,
    stock_minimo NUMERIC DEFAULT 0,
    precio_unitario NUMERIC DEFAULT 0,
    activo INTEGER DEFAULT 1,
    baja_por TEXT,
    baja_folio TEXT,
    baja_fecha TIMESTAMP,
    estado_fisico TEXT,
    proveedor_nombre_historico TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS proveedores (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL,
    nombre_comercial TEXT,
    contacto TEXT,
    activo INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS entradas (
    id BIGSERIAL PRIMARY KEY,
    folio TEXT UNIQUE NOT NULL,
    producto_id BIGINT REFERENCES productos(id),
    es_servicio INTEGER DEFAULT 0,
    concepto_servicio TEXT,
    cantidad NUMERIC NOT NULL,
    precio_unitario NUMERIC DEFAULT 0,
    importe NUMERIC DEFAULT 0,
    no_requisicion TEXT,
    no_factura TEXT,
    orden_compra TEXT,
    no_remision TEXT,
    proveedor_id BIGINT REFERENCES proveedores(id),
    proveedor_nombre_historico TEXT,
    departamento TEXT,
    tipo_movimiento TEXT DEFAULT 'normal',
    cantidad_piezas NUMERIC,
    usuario_id BIGINT REFERENCES usuarios(id),
    observaciones TEXT,
    folio_excel TEXT,
    moneda TEXT DEFAULT 'MXN',
    aplica_iva INTEGER,
    compra_gas INTEGER DEFAULT 0,
    sin_oc INTEGER DEFAULT 0,
    remision_sin_oc INTEGER DEFAULT 0,
    factura_pagada_sin_oc INTEGER DEFAULT 0,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS salidas (
    id BIGSERIAL PRIMARY KEY,
    folio TEXT UNIQUE NOT NULL,
    producto_id BIGINT REFERENCES productos(id),
    cantidad NUMERIC NOT NULL,
    responsable TEXT NOT NULL,
    area TEXT,
    no_vale TEXT,
    tipo_movimiento TEXT DEFAULT 'normal',
    usuario_id BIGINT REFERENCES usuarios(id),
    observaciones TEXT,
    folio_excel TEXT,
    es_servicio INTEGER DEFAULT 0,
    concepto_servicio TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS montacargas (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL,
    activo INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS areas (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL,
    activo INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vales_montacargas (
    id BIGSERIAL PRIMARY KEY,
    folio TEXT UNIQUE NOT NULL,
    no_vale TEXT NOT NULL,
    responsable TEXT NOT NULL,
    area TEXT,
    area_id BIGINT REFERENCES areas(id),
    area_nombre_historico TEXT,
    montacargas_id BIGINT REFERENCES montacargas(id),
    montacargas_nombre_historico TEXT,
    cantidad NUMERIC NOT NULL,
    unidad TEXT DEFAULT 'piezas',
    observaciones TEXT,
    usuario_id BIGINT REFERENCES usuarios(id),
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conteos_fisicos (
    id BIGSERIAL PRIMARY KEY,
    producto_id BIGINT REFERENCES productos(id),
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    existencia_fisica NUMERIC NOT NULL,
    salidas_manual NUMERIC,
    existencia_inicio NUMERIC,
    entradas_mes NUMERIC,
    usuario_id BIGINT REFERENCES usuarios(id),
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(producto_id, anio, mes)
);

CREATE TABLE IF NOT EXISTS cierres_mensuales_periodos (
    id BIGSERIAL PRIMARY KEY,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    estado TEXT NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto', 'cerrado')),
    cerrado_por BIGINT REFERENCES usuarios(id),
    cerrado_en TIMESTAMP,
    reabierto_por BIGINT REFERENCES usuarios(id),
    reabierto_en TIMESTAMP,
    motivo_reapertura TEXT,
    UNIQUE(anio, mes)
);

CREATE TABLE IF NOT EXISTS folios (
    tipo TEXT PRIMARY KEY,
    ultimo INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS folios_diarios (
    fecha DATE PRIMARY KEY,
    folio INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS requisiciones (
    id BIGSERIAL PRIMARY KEY,
    folio INTEGER NOT NULL,
    fecha_requisicion DATE,
    fecha_necesita DATE,
    departamento TEXT,
    solicitante TEXT,
    asunto TEXT,
    visto_bueno TEXT,
    autorizo TEXT,
    orden_compra TEXT,
    no_factura TEXT,
    no_remision TEXT,
    estado TEXT DEFAULT 'pendiente',
    estado_recepcion TEXT,
    no_entrada_vinculada TEXT,
    observaciones TEXT,
    usuario_id BIGINT REFERENCES usuarios(id),
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS requisicion_items (
    id BIGSERIAL PRIMARY KEY,
    requisicion_id BIGINT REFERENCES requisiciones(id) ON DELETE CASCADE,
    orden INTEGER,
    cantidad NUMERIC NOT NULL,
    unidad TEXT,
    descripcion TEXT NOT NULL,
    cantidad_recibida NUMERIC DEFAULT 0,
    recibido INTEGER DEFAULT 0,
    producto_id BIGINT REFERENCES productos(id)
);

CREATE TABLE IF NOT EXISTS requisicion_item_recepciones (
    id BIGSERIAL PRIMARY KEY,
    requisicion_item_id BIGINT REFERENCES requisicion_items(id) ON DELETE CASCADE,
    cantidad NUMERIC NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_id BIGINT REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS bloques_balance (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL,
    descripcion TEXT,
    activo INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bloque_productos (
    id BIGSERIAL PRIMARY KEY,
    bloque_id BIGINT REFERENCES bloques_balance(id) ON DELETE CASCADE,
    producto_id BIGINT REFERENCES productos(id),
    orden INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_productos_codigo ON productos(codigo);
CREATE INDEX IF NOT EXISTS idx_entradas_fecha ON entradas(fecha);
CREATE INDEX IF NOT EXISTS idx_entradas_producto ON entradas(producto_id);
CREATE INDEX IF NOT EXISTS idx_salidas_fecha ON salidas(fecha);
CREATE INDEX IF NOT EXISTS idx_salidas_producto ON salidas(producto_id);
CREATE INDEX IF NOT EXISTS idx_requisiciones_estado ON requisiciones(estado);
CREATE INDEX IF NOT EXISTS idx_requisiciones_fecha ON requisiciones(fecha);
CREATE UNIQUE INDEX IF NOT EXISTS idx_requisiciones_folio_unico ON requisiciones(folio);
CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username);
CREATE INDEX IF NOT EXISTS idx_proveedores_nombre ON proveedores(nombre);
CREATE INDEX IF NOT EXISTS idx_actividad_timestamp ON actividad(timestamp);
CREATE INDEX IF NOT EXISTS idx_bloque_productos_bloque ON bloque_productos(bloque_id);
CREATE INDEX IF NOT EXISTS idx_bloque_productos_producto ON bloque_productos(producto_id);
CREATE INDEX IF NOT EXISTS idx_vales_montacargas_fecha ON vales_montacargas(fecha);
CREATE INDEX IF NOT EXISTS idx_vales_montacargas_montacargas ON vales_montacargas(montacargas_id);

COMMIT;
