print('*** Manejo de Tuplas ***')

mi_tupla = (1, 2, 3, 4, 5)

print(mi_tupla)
# No podemos modificar una tupla
# mi_tupla[0] = 10  # Esto generaría un error
# mi_tupla.append(6)  # Esto generaría un error porque las tuplas no tienen el método append

# Iteramos los elementos de una tupla
for elemento in mi_tupla:
    print(elemento)

# Crear una tupla para una coordenada z, y
coordenada = (3, 5)
# Accedemos a cada elemento de la tupla
print(f'\nCoordenada en el eje x: {coordenada[0]}')
print(f'Coordenada en el eje Y: {coordenada[1]}')

# Crear una tupla unitaria
tupla_un_elemento = 10,
print(f'Tupla de un elemento: {tupla_un_elemento}')

# Tupla anidada
tupla_anidada = (1, (2, 3), (4, 5))
print(f'Segundo elemento tupla anidad: {tupla_anidada[1]}')
