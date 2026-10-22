# Declaracion de variables de entrada
producto = input('Escribe el nombre del producto: ')
precio = float(input('Escribe el precio unitario: '))
cantidad = int(input('Escribe la cantidad: '))
descuento = int(input('Escribe el porcentaje de descuento: '))
impuesto = int(input('Escribe el porcentaje de impuesto: ')) 

# Calculos

subtotal = precio * cantidad
monto_descuento = (descuento / 100) * subtotal
monto_impuesto = (impuesto / 100) * subtotal
subtotal_descuento = subtotal - monto_descuento
subtotal_impuesto = subtotal + monto_impuesto
total = subtotal - subtotal_descuento + subtotal_impuesto
print(f'''
-Producto: {producto}
-Precio: {precio}
-Cantidad: {cantidad}
-Descuento: {descuento}
-Impuesto: {impuesto}
-------------------------------
subtotal: {subtotal}
total: {total}
''')
