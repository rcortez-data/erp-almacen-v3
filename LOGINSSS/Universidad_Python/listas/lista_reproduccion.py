print('*** Lista de Reproduccion ***')

# Creamos la lista vacia
lista_reproduccion = []

numero_canciones = int(input('Cuantas canciones deseas agregar? '))

# Iteramos cada elemento de la lista para agregar un nuevo elemento
for indice in range(numero_canciones):
    cancion = input(f'Proporciona la cancion {indice + 1}: ')
    lista_reproduccion.append(cancion)

# Ordenar la lista en orden alfabetico. sort
lista_reproduccion.sort()


# Mostra la lista iterando sus elementos
print('\nIteramos el Playlist')
for cancion in lista_reproduccion:
    print(f'- {cancion}')