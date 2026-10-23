# productos = [
#     {"nombre": "Pan", "precio": 20},
#     {"nombre": "Leche", "precio": 25},
#     {"nombre": "Sopa", "precio": 18},
#     {"nombre": "Arroz", "precio": 30}
# ]
# Usa la misma lista de productos.
# Recórrela con un for y cuenta cuántos productos tienen un precio mayor o igual que 20.
# Resultado esperado:
# 3

productos = [
    {"nombre": "Pan", "precio": 20},
    {"nombre": "Leche", "precio": 25},
    {"nombre": "Sopa", "precio": 18},
    {"nombre": "Arroz", "precio": 30}
]

mayor = 0

for producto in productos:
    if producto['precio'] >= 20:
        mayor += 1
print(mayor)