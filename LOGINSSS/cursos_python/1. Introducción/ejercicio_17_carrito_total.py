#  carrito = [
#      {"producto": "Pan", "precio": 20, "cantidad": 2},
#      {"producto": "Leche", "precio": 25, "cantidad": 3},
#      {"producto": "Sopa", "precio": 18, "cantidad": 4}
#  ]
# Recorre el carrito y:
# - Crea total = 0.
# - Calcula el subtotal de cada producto: precio * cantidad.
# - Acumula cada subtotal en total.
# - Imprime el total final.
# Resultado esperado:
# 182

carrito = [
     {"producto": "Pan", "precio": 20, "cantidad": 2},
     {"producto": "Leche", "precio": 25, "cantidad": 3},
     {"producto": "Sopa", "precio": 18, "cantidad": 4}
        ]
total = 0
subtotal = 0
for carro in carrito:
    subtotal = carro['precio'] * carro['cantidad']
for sub in subtotal:
    sub += total
print(total)