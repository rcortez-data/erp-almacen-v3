print('*** Manejo de Tuplas ***')

mi_tupla = (1, 2, 3, 4, 5)

print(mi_tupla)
# No podemos modificar una tupla
# mi_tupla[0] = 10  # Esto generaría un error
# mi_tupla.append(6)  # Esto generaría un error porque las tuplas no tienen el método append

# Iteramos los elementos de una tupla
for elemento in mi_tupla:
    print(elemento)
    