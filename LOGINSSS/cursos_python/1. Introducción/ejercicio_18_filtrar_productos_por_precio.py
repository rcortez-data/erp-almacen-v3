# productos = [
#     {"nombre": "Pan", "precio": 20},
#     {"nombre": "Leche", "precio": 25},
#     {"nombre": "Sopa", "precio": 18}
# ]
# Recorre la lista con un ciclo for y muestra únicamente el nombre de los productos cuyo precio sea mayor que 20.
# Resultado esperado:
# Leche

productos = [
    {"nombre": "Pan", "precio": 20},
    {"nombre": "Leche", "precio": 25},
    {"nombre": "Sopa", "precio": 18}
]

for producto in productos:
    if producto['precio'] > 20:
        print(producto['nombre'])