# Declaracion de variables de entrada
producto = input('Escribe el nombre del producto: ')
precio = float(input('Escribe el precio unitario: '))
cantidad = int(input('Escribe la cantidad: '))
descuento = int(input('Escribe el porcentaje de descuento: '))
impuesto = int(input('Escribe el porcentaje de impuesto: ')) 

# Calculos

subtotal = precio * cantidad
monto_descuento = subtotal * (descuento / 100)
subtotal_con_descuento = subtotal - monto_descuento
monto_impuesto = subtotal_con_descuento * (impuesto / 100)
total_final = subtotal_con_descuento + monto_impuesto

# Resumen del pedido
resumen = f'''
Producto: {producto}
Precio unitario: {precio:.2f}
Cantidad: {cantidad}
Subtotal: {subtotal:.2f}
Monto del descuento: {monto_descuento:.2f}
Subtotal con descuento: {subtotal_con_descuento:.2f}
Monto del impuesto: {monto_impuesto:.2f}
Total final: {total_final:.2f}
'''
print(resumen)
