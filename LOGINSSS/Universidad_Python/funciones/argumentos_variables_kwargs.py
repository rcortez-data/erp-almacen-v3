# *args - arguments - tupla
# **kwargs - keyword arguments (key, value) como un dict
print('*** Argumentos variables en forma de dict ***')

def superheroe_superpoderes(nombre, *args, **kwargs):
    print(f'Superheroes: {nombre} - {args} - Mas info: {kwargs}')

# Llamamos la funcion
superheroe_superpoderes('Spiderman', 'Instinto aracnido', edad=17, empresa='Marvel')
superheroe_superpoderes('IronMan', 'Armadura', 'Playboy', edad=45)

# Es opcional enviar argumentos variables
superheroe_superpoderes('')