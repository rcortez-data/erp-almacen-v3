# Usa la misma lista de productos.
# Recórrela con un for y:
# 1. Suma todos los precios.
# 2. Cuenta cuántos productos hay.
# 3. Calcula el promedio.
# 4. Imprime el resultado.
# Resultado esperado:
# 23.25

productos = [
    {"nombre": "Pan", "precio": 20},
    {"nombre": "Leche", "precio": 25},
    {"nombre": "Sopa", "precio": 18},
    {"nombre": "Arroz", "precio": 30}
]
suma = 0
cantidad = 0
promedio = 0
for producto in productos:
    suma += producto['precio']
    cantidad += 1
    promedio = suma / cantidad

print(promedio)