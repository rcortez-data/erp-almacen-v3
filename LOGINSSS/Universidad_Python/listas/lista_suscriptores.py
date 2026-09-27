print('*** Lista de Suscriptores ***')

suscriptores = {'luisa@mail.com', 'marcos@mail.com', 'elena@mail.com' }
print(f'Lista de suscriptores inicial: {suscriptores}')

# Verificar si un nuevo suscriptro ya esta en la lista
nuevo_suscriptor = 'karla@mail.com'
if nuevo_suscriptor in suscriptores:
    print(f'El nuevo suscriptor ya esta en la lista: {nuevo_suscriptor}')
else:
    suscriptores.add(nuevo_suscriptor)
    print(f'El nuevo suscriptor se ha agregado a la lista: {nuevo_suscriptor}')
print(f'Lista de suscriptores actualizada: {suscriptores}')

# Eliminamos un suscriptor
suscriptor_eliminar = 'elena@mail.com'
suscriptores.remove(suscriptor_eliminar)
print(f'\nEl suscriptor {suscriptor_eliminar} ha sido eliminado de la lista')
print(f'Lista de suscriptores actualizada: {suscriptores}')

# Verificamos la cantidad total de suscriptores
print(f'Cantidad total de Suscriptores: {len(suscriptores)}')

# Mostramos todos los suscriptores
print(f'--- Lista de suscriptores ---')
for suscriptor in suscriptores:
    print(f'- {suscriptor}')