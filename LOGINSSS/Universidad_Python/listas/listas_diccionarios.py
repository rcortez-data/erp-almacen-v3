print('*** Listas y Diccionarios ***')

personas = [
    {'nombre':'Regina',
     'apellido':'Flores',
     'edad': 21},

     {'nombre':'Alejandro',
      'apellido':'Reyes',
      'edad': 32}
]
print(personas)

# Acceder a un diccionario desde una lista
print(f'''Detalle del primer elemento de la lista
    Nombre: {personas[0]['nombre']}
    Apellido: {personas[0]['apellido']}
    Edad: {personas[0]['edad']}''')

# Recorrer los elementos de la lista
print()
for contador, persona in enumerate(personas):
    print(f'{contador + 1} - persona {persona}')
    #print(f'Detalle: Nombre: {persona['nombre']}, Apellido: {persona['apellido']}, Edad: {persona['edad']}')