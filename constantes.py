# Listas fijas del catálogo. Cambiar aquí si el almacén define nuevas categorías/departamentos.

CATEGORIAS = [
    'Bandas y Baleros',
    'Ferreteria',
    'Formatos',
    'Montaje de grabados',
    'Herramienta',
    'Insumos Caldera'
    'Insumos corrugadora',
    'Grasas, Aceites y Lubricantes',
    'Limpieza',    
    'Electrico',
    'Galvanizado',
    'PVC',
    'Neumatico',
    'Papeleria',
    'Refacciones corrugadora',
    'Pintura',
    'Insumos produccion',
    'Equipo de seguridad',
    'Servicios en general',
    'Sistemas',
    'Taller de suajes',
    'Tintas',
    'Tornilleria',
    'Tarimas',
    'Piezas maquinas',
    'Maquinados',
]

# Estas 2 categorías, al seleccionarse, despliegan un segundo select de máquina/equipo.
CATEGORIAS_CON_MAQUINA = ['Piezas maquinas', 'Maquinados']

MAQUINAS = [
    'Flexo 2',
    'Flexo 5',
    'Flexo 6',
    'Flexo 8',
    'Flexo 9',
    'Flexo 10',
    'Pegadora 1',
    'Pegadora 2',
    'Pegadora laminadora',
    'Pegadora post',
    'Engrapadora china 1',
    'Engrapadora china 2',
    'Engrapadora semi-automatica 1',
    'Engrapadora semi-automatica 2',
    'Engrapadora manual',
    'Flejadora mosca mini',
    'Flejadora paletizadora',
    'Suaje chino 1',
    'Suaje chino 2',
    'Suaje 4',
    'Corrugadora',
    'Caldera',
    'Robot diseño',
    'Hojeadora',
    'Compactadora-trituradora',
    'Otros',  # Si se elige, se captura texto libre en "maquina_otro"
]

# Unidades comunes para las partidas de Requisiciones (lista tipo "sugerencias":
# se puede elegir una o escribir otra distinta si no está en la lista).
UNIDADES = [
    'Pieza',
    'Kilo',
    'Litro',
    'Metro',
    'Caja',
    'Paquete',
    'Bolsa',
    'Bote',
    'Cubeta',
    'Galon',
    'Garrafa',
    'Bidon',
    'Rollo',
    'Par',
    'Juego',
    'Millar',
    'Lote',
    'Servicio',
]

DEPARTAMENTOS = sorted([
    'Hidalgo',
    'Almacen general',
    'Embarques',
    'Almacen rollos',
    'Diseño',
    'Calidad',
    'Seguridad e higiene',
    'Limpieza',
    'Compras',
    'Administracion',
    'Laboratorio de tintas',
    'Produccion',
    'Mantenimiento',
    'Corrugadora',
    'Caldera',
    'Taller de suajes',
    'Comedor',
    'Aduana',
    'Montacargas',
    'Edificios',
    
], key=str.lower)
