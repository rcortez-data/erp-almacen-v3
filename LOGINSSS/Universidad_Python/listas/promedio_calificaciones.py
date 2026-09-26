print('*** Promedio de Calificaciones ***')

calificaciones = []

numero_calificaciones = int(input('Proporciona el numero de calificaciones a evaluar: '))

for indice in range(numero_calificaciones):
    calificacion = int(input(f'Calificacion [{indice}] = '))
    calificaciones.append(calificacion)

print(f'\nLas calificaciones proporcionadas son: {calificaciones}')

for promedio in calificaciones:
    promedio = calificacion + calificacion / numero_calificaciones
print(f'Promedio de las calificaciones: {promedio}')