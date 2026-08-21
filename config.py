"""
Configuración centralizada de la aplicación ERP Almacén v2.5
Soporta desarrollo, testing y producción.
"""

import os
from datetime import timedelta

class Config:
    """Configuración base"""
    # Sesión
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    SESSION_COOKIE_SECURE = False  # True en producción con HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Base de datos
    DATABASE_PATH = os.path.join(os.path.dirname(__file__), "almacen.db")
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'logs/erp_almacen.log'
    LOG_MAX_BYTES = 10240000  # 10 MB
    LOG_BACKUP_COUNT = 10
    
    # Seguridad
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_TIMEOUT_MINUTES = 15
    PASSWORD_MIN_LENGTH = 8
    REQUIRE_STRONG_PASSWORD = True
    
    # Performance
    CACHE_TIMEOUT = 1800  # 30 minutos
    PAGINATION_SIZE = 25
    MAX_IMPORT_SIZE = 10000  # máximo registros en importación
    BATCH_PROCESS_SIZE = 100  # tamaño de lotes en procesamiento
    
    # Compresión
    COMPRESS_LEVEL = 6
    COMPRESS_MIN_SIZE = 1024  # Mínimo de bytes para comprimir
    
    # Reportes
    REPORT_TIMEZONE = 'America/Mexico_City'
    DEFAULT_IVA_RATE = 0.16  # 16%
    
    # Límites de negocio
    MIN_STOCK_WARNING = True
    ENABLE_AUDIT_LOG = True
    ENABLE_AUTO_BACKUP = True
    BACKUP_RETENTION_DAYS = 30


class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False
    LOG_LEVEL = 'DEBUG'


class TestingConfig(Config):
    """Configuración para testing"""
    DEBUG = False
    TESTING = True
    DATABASE_PATH = ':memory:'  # BD en memoria para tests
    SESSION_COOKIE_SECURE = False
    MAX_LOGIN_ATTEMPTS = 3


class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True  # Solo con HTTPS
    LOG_LEVEL = 'WARNING'
    REQUIRE_STRONG_PASSWORD = True
    MAX_LOGIN_ATTEMPTS = 3


# Seleccionar configuración según ambiente
def get_config():
    """Retorna la configuración según el ambiente"""
    env = os.environ.get('FLASK_ENV', 'development').lower()
    
    if env == 'production':
        return ProductionConfig()
    elif env == 'testing':
        return TestingConfig()
    else:
        return DevelopmentConfig()


config = get_config()
