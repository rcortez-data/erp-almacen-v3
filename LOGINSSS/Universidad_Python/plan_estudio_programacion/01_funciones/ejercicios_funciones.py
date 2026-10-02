"""Ejercicios de funciones. No borres los enunciados; escribe debajo de cada uno."""

# F01 - Crea calcular_total(precio, cantidad) y devuelve el total.
# Agrega una validacion para evitar precios o cantidades negativos.
precio = int(input('Digita el precio: '))
cantidad = int(input('Digita la candidad: '))
if precio and cantidad > 0:
    calcular_total = precio * cantidad
    print(f'La cantidad total es: {calcular_total}')
else:
    print('Digita una cantidad superior a cero.')

# F02 - Crea estado_stock(stock, minimo) que devuelva "OK", "BAJO" o "SIN EXISTENCIA".
# Prueba con 10, 3; 3, 3; y 0, 3.


# F03 - Crea buscar_producto(productos, codigo).
# productos es una lista de diccionarios con codigo, nombre y existencia.
# Devuelve el diccionario encontrado o None si no existe.


# F04 - Crea funciones separadas para mostrar_menu, pedir_opcion y ejecutar_opcion.
# El programa debe permitir consultar existencias, agregar una entrada y salir.


# F05 - Mini proyecto: genera un reporte de inventario.
# Usa al menos cinco funciones: cargar datos, calcular valor, detectar faltantes,
# mostrar resumen y generar un reporte final.

