print('*** Repeticion de un mensaje ***')

mensaje = input('Proporciona un mensaje a repetir: ')
numero_de_repeticiones = int(input('Proporciona el numero de repeticiones: '))

# Iterar sobre el rango de repeteciones

for _ in range(numero_de_repeticiones):
    #print(f'{i+1} - {mensaje}')
    print(mensaje)