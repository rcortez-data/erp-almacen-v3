print('*** Sistema de Inventarios ***')

inventario = []

numero_productos = int(input('Cuantos productos deseas agregar al inventario? '))

for _ in range(numero_productos):
    print(f'Proporciona los valores del producto {_ + 1}')
    nombre = input('Nombre: ')
    precio = float(input('Precio: '))
    cantidad = int(input('Cantidad: '))
    # Creamos el diccionario con el detalle del producto
    producto = {'id': _ + 1, 'nombre': nombre, 'precio':precio, 'cantidad':cantidad}
    # Agregamos el nuevo producto al inventario
    inventario.append(producto)

# Mostrar el inventario inicial

print(f'\nInventario inicia: {inventario}')

# Buscar un producto por id
id_buscar = int(input('\nIngresa el ID del producto a buscar: '))
producto_encontrado = None
for producto in inventario:
    if producto['id'] == id_buscar:
        producto_encontrado = producto
    break

if producto_encontrado is not None:
    print('Informacion del producto encontrado: ')
    print(f'''Id: {producto_encontrado['id']}
Nombre: {producto_encontrado['nombre']}
Precio: {producto_encontrado['precio']}
Cantidad: {producto_encontrado['cantidad']}''')
else:
    print(f'Producto con ID {id_buscar} NO encontrado')

# Mostrar el inventario detallado
print(f'\n--- Inventario detallado ---')
for producto in inventario:
    print(f'''Id: {producto['id']}
Nombre: {producto['nombre']}
Precio: {producto['precio']}
Cantidad: {producto['cantidad']}
''')