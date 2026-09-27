print('*** Lista de Suscriptores ***')

# Definimos el set inicial
#suscriptores = {} # Aqui se define un diccionario vacio
suscriptores = set() # Asi se define un set vacio

numero_suscriptores = int(input('Proporciona el numero de suscriptores iniciales: '))
for _ in range(numero_suscriptores):
    suscriptores.add(input('Nuevo suscriptor (email): '))

print(f'Lista de suscriptores inicial: {suscriptores}')

# Verificar si un nuevo suscriptro ya esta en la lista
nuevo_suscriptor = input('Proporciona el nuevo suscriptor: ')
if nuevo_suscriptor in suscriptores:
    print(f'El nuevo suscriptor ya esta en la lista: {nuevo_suscriptor}')
else:
    suscriptores.add(nuevo_suscriptor)
    print(f'El nuevo suscriptor se ha agregado a la lista: {nuevo_suscriptor}')
print(f'Lista de suscriptores actualizada: {suscriptores}')

# Eliminamos un suscriptor
suscriptor_eliminar = input('Proporciona el suscriptor a eliminar: ')
suscriptores.remove(suscriptor_eliminar)
print(f'\nEl suscriptor {suscriptor_eliminar} ha sido eliminado de la lista')
print(f'Lista de suscriptores actualizada: {suscriptores}')

# Verificamos la cantidad total de suscriptores
print(f'Cantidad total de Suscriptores: {len(suscriptores)}')

# Mostramos todos los suscriptores
print(f'--- Lista de suscriptores ---')
for suscriptor in suscriptores:
    print(f'- {suscriptor}')

