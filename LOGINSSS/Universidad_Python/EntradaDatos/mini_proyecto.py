# Mini Proyecto: Caja De Tienda
# Vas a crear un programa que simule el resumen de compra de una tienda.
# Crea una lista llamada carrito con varios productos. Cada producto será un diccionario con:
# "producto"
# "precio"
# "cantidad"

print("*** Caja de Tienda ***")

total = 0
carrito = [

    {"producto": "Leche", "precio": 25, "cantidad": 10},
    {"producto": "Pan", "precio": 5, "cantidad": 30},
    {"producto": "Sopa", "precio": 11, "cantidad": 15},
    {"producto": "Papas", "precio": 18, "cantidad": 5},
    {"producto": "Refresco", "precio": 36, "cantidad": 12},
    {"producto": "Galletas", "precio": 20, "cantidad": 6},

]

for item in carrito:
    subtotal = item["precio"] * item["cantidad"]
    total += subtotal
    print(f"{item['producto']}: {item['cantidad']} x ${item['precio']} = ${subtotal}")

print("-" * 20)
print(f"Total sin descuento: ${total:.2f}")

if total >= 100:
    descuento = total * 0.10
else:
    descuento = 0

total_final = total - descuento

print(f"Descuento: ${descuento:.2f}")
print(f"Total final: ${total_final:.2f}")

if descuento > 0:
    print(f"¡Se aplico descuento!")
else:
    print(f"¡No se aplico descuento!")

