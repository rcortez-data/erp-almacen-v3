print('*** Agenda en Python ***')
agenda = {
    'carlos':{
        'telefono': '55-55-55',
        'email': 'carlos@mail.com',
        'direccion': 'lima'
    },
    'maria':{
        'telefono': '66-66-66',
        'email': 'maria@mail.com',
        'direccion': 'caña'
        },
    'pedro':{
        'telefono': '77-77-77',
        'email': 'pedro@mail.com',
        'direccion': 'manzana'
    }
}

print(agenda)

# Acceder a la información de un contacto en especifico

print(f'''Informacion del contacto Maria:
    Telefono: {agenda["maria"]['telefono']}
    Email: {agenda["maria"]['email']}
    Direccion: {agenda["maria"]['direccion']}
''')

# Agregar un nuevo contacto
agenda['Ana'] = {
    'telefono': '55678392',
    'email': 'ana@mail.com',
    'direccion': 'Calle salvador dias'
}
print(agenda)

# Eliminar un contacto existente
# agenda.pop('pedro')
# # del agenda['pedro']  cualquiera de las 2 funciones hace lo mismo
# print(agenda) 

# Mostramos los contactos de la agenda

print(f'\nContactos en la Agenda')
for nombre, detalles in agenda.items():
    print(f'''Nombre: {nombre}
Telefono: {detalles['telefono']}
Email: {detalles['email']}
Direccion: {detalles['direccion']}
''')



