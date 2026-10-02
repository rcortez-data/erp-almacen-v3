import math

print("*** Constantes en Python ***")

PI = 3.14159
print("El valor de PI es: ", PI)

NOMBRE_BASE_DATOS = 'cliente_db'
print('Nombre de la base de datos:', NOMBRE_BASE_DATOS)

# Esto No se debe hacer, no se debe modificar el valor de una constante

NOMBRE_BASE_DATOS = 'listado_cliente_db'
print('No cambiar el valor de una constante:', NOMBRE_BASE_DATOS)


# usar una constante del lenguaje python, aunque en este caso no esta en mayusculas
print('Valor de math.pi', math.pi)
