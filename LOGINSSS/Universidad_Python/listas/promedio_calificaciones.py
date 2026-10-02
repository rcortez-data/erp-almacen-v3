print('*** Promedio de Calificaciones ***')

calificaciones = []
suma_calificaciones = 0

numero_calificaciones = int(input('Proporciona el numero de calificaciones a evaluar: '))

for indice in range(numero_calificaciones):
    calificacion = float(input(f'Calificacion [{indice}] = '))
    calificaciones.append(calificacion)
    suma_calificaciones += calificacion
print(f'\nLas calificaciones proporcionadas son: {calificaciones}')

promedio = suma_calificaciones / numero_calificaciones
print(f'\nPromedio de las calificaciones: {promedio}')


# Calculamos el promedio de las calificaciones
# Sum(iterable)
# suma_calificaciones = sum(calificaciones)
# promedio = suma_calificaciones / numero_calificaciones
# print(f'\nPromedio de las calificaciones: {promedio}')

