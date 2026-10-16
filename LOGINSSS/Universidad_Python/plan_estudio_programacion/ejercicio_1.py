'''
El programa debe calcular y mostrar:

1. subtotal;
2. monto del descuento;
3. subtotal con descuento;
4. monto del impuesto;
5. total final;
6. un pequeño resumen legible del pedido.

### Condiciones

- Convierte los datos numéricos al tipo apropiado antes de operar.
- Usa nombres de variables descriptivos.
- Muestra dinero con dos decimales.
- Prueba al menos estos casos: un producto sin descuento y otro con descuento e impuesto.
- No copies la solución del curso ni uses funciones, bucles, listas o librerías externas.

### Criterios de terminado

- El programa ejecuta sin errores con datos válidos.
- Las operaciones siguen un orden lógico.
- Puedes explicar qué representa cada variable.
- Puedes cambiar los datos sin modificar la lógica.
- Puedes comprobar manualmente si el total obtenido tiene sentido.

### Pistas permitidas

**Pista 1:** separa el problema en entrada → conversión → cálculos → presentación.  
**Pista 2:** expresa cada porcentaje como una fracción antes de calcular el monto correspondiente.  
**Pista 3:** revisa si el impuesto se aplica al subtotal original o al subtotal después del descuento; elige una regla, escríbela como comentario y sé consistente.  
**Pista 4:** si el resultado muestra demasiados decimales, investiga el formato de números decimales en cadenas de formato. No copies un programa completo.

### Qué debes entregar para la evaluación

Pega en la sesión:

1. tu código;
2. una ejecución con datos de prueba y su salida;
3. una explicación breve de la fórmula del total;
4. cualquier error que hayas encontrado y cómo intentaste corregirlo.

No te daré la solución completa. Si no terminas hoy, escribe `no logrado hoy`, conserva tu intento y mañana continuaremos desde la primera parte que falle.
'''
producto = input('Nombre del producto: ')
precio = float(input('Precio: '))
cantidad = float(input('Cantidad: '))
descuento = int(input('Porcentaje de descuento: '))
impuesto = int(input('Porcentaje de impuesto: '))
monto_impuesto = (impuesto / 100) * precio
monto_descuento = (descuento / 100) * precio
subtotal = precio * cantidad
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
