"""
Funciones de utilidad compartidas para evitar duplicación de código.
Optimización: Centralización de lógica común.
"""

import json
from functools import lru_cache
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime, date


# ====== VALIDACIÓN ======

def validar_producto(conn, producto_id: int) -> Optional[Dict]:
    """
    Valida si un producto existe y retorna sus datos.
    
    Args:
        conn: Conexión a la base de datos
        producto_id: ID del producto
        
    Returns:
        Dict con datos del producto o None si no existe
    """
    try:
        producto = conn.execute(
            "SELECT * FROM productos WHERE id=?", (producto_id,)
        ).fetchone()
        return dict(producto) if producto else None
    except Exception as e:
        raise ValueError(f"Error al validar producto: {str(e)}")


def validar_cantidad(cantidad: str, permitir_cero: bool = False) -> Tuple[bool, float, str]:
    """
    Valida y convierte cantidad a float.
    
    Args:
        cantidad: String a validar
        permitir_cero: Si False, rechaza cantidad 0
        
    Returns:
        Tupla (es_válido, valor_float, mensaje_error)
    """
    try:
        valor = float(cantidad)
        
        if valor < 0:
            return False, 0, "La cantidad no puede ser negativa"
        
        if valor == 0 and not permitir_cero:
            return False, 0, "La cantidad debe ser mayor a 0"
        
        return True, valor, ""
    except (ValueError, TypeError):
        return False, 0, "Cantidad inválida"


def validar_email(email: str) -> bool:
    """Valida formato básico de email."""
    import re
    patron = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(patron, email) is not None


def validar_username(username: str, min_length: int = 3) -> Tuple[bool, str]:
    """
    Valida username.
    
    Returns:
        Tupla (es_válido, mensaje_error)
    """
    if len(username) < min_length:
        return False, f"Username debe tener al menos {min_length} caracteres"
    
    if not username.isalnum() and '_' not in username:
        return False, "Username solo puede contener letras, números y guión bajo"
    
    return True, ""


# ====== CÁLCULOS ======

def calcular_cantidad_piezas(
    cantidad: float,
    tiene_conversion: bool,
    factor_conversion: float = 1.0
) -> float:
    """
    Calcula la cantidad en piezas considerando conversión de unidades.
    
    Args:
        cantidad: Cantidad original
        tiene_conversion: Si existe factor de conversión
        factor_conversion: Factor para convertir unidades
        
    Returns:
        Cantidad en piezas
    """
    if not tiene_conversion or factor_conversion == 0:
        return cantidad
    
    return round(cantidad / factor_conversion, 4)


def calcular_importe(cantidad: float, precio: float) -> float:
    """Calcula importe con redondeo a 4 decimales."""
    return round(cantidad * precio, 4)


def calcular_iva(monto: float, tasa: float = 0.16) -> float:
    """Calcula IVA."""
    return round(monto * tasa, 2)


def calcular_total_con_iva(monto: float, tasa: float = 0.16) -> float:
    """Calcula total incluyendo IVA."""
    return round(monto + calcular_iva(monto, tasa), 2)


# ====== FORMATEO ======

def formato_moneda(valor: float, incluir_simbolo: bool = True) -> str:
    """Formatea valor como moneda MXN."""
    formato = f"${valor:,.2f}" if incluir_simbolo else f"{valor:,.2f}"
    return formato


def formato_fecha(fecha_str: str, formato: str = '%d/%m/%Y') -> str:
    """Convierte fecha de formato ISO a formato legible."""
    try:
        if not fecha_str:
            return ""
        dt = datetime.fromisoformat(fecha_str.split()[0])
        return dt.strftime(formato)
    except:
        return fecha_str


def formato_fecha_hora(fecha_str: str, formato: str = '%d/%m/%Y %H:%M') -> str:
    """Formatea fecha y hora."""
    try:
        if not fecha_str:
            return ""
        dt = datetime.fromisoformat(fecha_str)
        return dt.strftime(formato)
    except:
        return fecha_str


def formatear_cantidad(cantidad: float, decimales: int = 2) -> str:
    """Formatea cantidad con separadores de miles."""
    return f"{cantidad:,.{decimales}f}"


# ====== RESPUESTAS JSON ======

def generar_respuesta_json(
    exito: bool,
    mensaje: str = "",
    datos: Optional[Dict] = None,
    codigo: int = 200
) -> Tuple[Dict, int]:
    """
    Genera respuesta JSON estandarizada.
    
    Args:
        exito: Si la operación fue exitosa
        mensaje: Mensaje para el usuario
        datos: Datos adicionales
        codigo: Código HTTP
        
    Returns:
        Tupla (respuesta_dict, codigo_http)
    """
    respuesta = {
        'success': exito,
        'message': mensaje,
        'data': datos or {}
    }
    return respuesta, codigo


def generar_error_json(mensaje: str, codigo: int = 400, detalles: Optional[Dict] = None) -> Tuple[Dict, int]:
    """Genera respuesta JSON de error estandarizada."""
    respuesta = {
        'success': False,
        'message': mensaje,
        'details': detalles or {}
    }
    return respuesta, codigo


# ====== BÚSQUEDA Y FILTRADO ======

def construir_condicion_busqueda(
    termino: str,
    campos: List[str],
    usar_like: bool = True
) -> Tuple[str, List[str]]:
    """
    Construye condición SQL para búsqueda en múltiples campos.
    
    Args:
        termino: Término a buscar
        campos: Lista de nombres de campos
        usar_like: Si usar LIKE o búsqueda exacta
        
    Returns:
        Tupla (condición_sql, parámetros)
    """
    if not termino or not campos:
        return "", []
    
    termino = termino.strip()
    if not termino:
        return "", []
    
    if usar_like:
        termino = f"%{termino}%"
        condiciones = " OR ".join([f"{campo} LIKE ?" for campo in campos])
        parametros = [termino] * len(campos)
    else:
        condiciones = " OR ".join([f"{campo} = ?" for campo in campos])
        parametros = [termino] * len(campos)
    
    return f"({condiciones})", parametros


# ====== PAGINACIÓN ======

def calcular_paginacion(
    total_registros: int,
    pagina: int,
    por_pagina: int = 25
) -> Dict[str, Any]:
    """
    Calcula información de paginación.
    
    Args:
        total_registros: Total de registros disponibles
        pagina: Número de página actual (comienza en 1)
        por_pagina: Registros por página
        
    Returns:
        Dict con información de paginación
    """
    pagina = max(1, pagina)
    total_paginas = (total_registros + por_pagina - 1) // por_pagina
    offset = (pagina - 1) * por_pagina
    
    return {
        'pagina_actual': pagina,
        'total_paginas': total_paginas,
        'total_registros': total_registros,
        'por_pagina': por_pagina,
        'offset': offset,
        'has_prev': pagina > 1,
        'has_next': pagina < total_paginas,
        'rango_inicio': offset + 1,
        'rango_fin': min(offset + por_pagina, total_registros)
    }


# ====== CACHÉ (Optimización) ======

@lru_cache(maxsize=128)
def obtener_categorias_cached(conn_id: int = 0) -> List[str]:
    """
    Obtiene lista de categorías con caché.
    Nota: En producción usar Redis.
    """
    from database import get_db
    conn = get_db()
    categorias = conn.execute("SELECT nombre FROM categorias ORDER BY nombre").fetchall()
    conn.close()
    return [cat['nombre'] for cat in categorias]


# ====== AUDITORÍA ======

def registrar_cambio(
    usuario_id: int,
    tabla: str,
    registro_id: int,
    accion: str,
    cambios_antes: Optional[Dict] = None,
    cambios_despues: Optional[Dict] = None
) -> Dict:
    """
    Registra cambios en auditoría.
    
    Args:
        usuario_id: ID del usuario que hizo el cambio
        tabla: Nombre de la tabla
        registro_id: ID del registro modificado
        accion: Tipo de acción (CREATE, UPDATE, DELETE)
        cambios_antes: Valores anteriores (para UPDATE)
        cambios_despues: Valores nuevos (para UPDATE/CREATE)
        
    Returns:
        Dict con resumen del cambio
    """
    return {
        'usuario_id': usuario_id,
        'tabla': tabla,
        'registro_id': registro_id,
        'accion': accion,
        'timestamp': datetime.now().isoformat(),
        'cambios_antes': cambios_antes,
        'cambios_despues': cambios_despues
    }


# ====== CONVERSIÓN DE TIPOS ======

def seguro_int(valor: Any, default: int = 0) -> int:
    """Convierte a int de forma segura."""
    try:
        return int(valor)
    except (ValueError, TypeError):
        return default


def seguro_float(valor: Any, default: float = 0.0) -> float:
    """Convierte a float de forma segura."""
    try:
        return float(valor)
    except (ValueError, TypeError):
        return default


def seguro_bool(valor: Any) -> bool:
    """Convierte a bool de forma segura."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.lower() in ('true', 'yes', '1', 'on')
    return bool(valor)


# ====== DICTS Y LISTAS ======

def flatten_dict(d: Dict, parent_key: str = '', sep: str = '_') -> Dict:
    """Aplana un diccionario anidado."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def filtrar_dict(d: Dict, claves: List[str]) -> Dict:
    """Filtra diccionario a solo las claves especificadas."""
    return {k: d.get(k) for k in claves if k in d}


# ====== BATCH PROCESSING ======

def dividir_en_lotes(lista: List, tamaño_lote: int) -> List[List]:
    """Divide una lista en lotes de tamaño específico."""
    lotes = []
    for i in range(0, len(lista), tamaño_lote):
        lotes.append(lista[i:i + tamaño_lote])
    return lotes
