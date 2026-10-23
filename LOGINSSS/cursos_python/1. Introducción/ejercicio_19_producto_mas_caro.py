# productos = [
#     {"nombre": "Pan", "precio": 20},
#     {"nombre": "Leche", "precio": 25},
#     {"nombre": "Sopa", "precio": 18},
#     {"nombre": "Arroz", "precio": 30}
# ]
# Recórrela con un ciclo for y encuentra el producto con el precio más alto.
# Resultado esperado:
# Arroz
# 30

productos = [
    {"nombre": "Pan", "precio": 20},
    {"nombre": "Leche", "precio": 25},
    {"nombre": "Sopa", "precio": 18},
    {"nombre": "Arroz", "precio": 30}
]

mayor = 0
producto_mayor = []

for producto in productos:
    if producto['precio'] > mayor:
        mayor = producto["precio"]
        producto_mayor = producto['nombre']
print(producto_mayor)
print(mayor)