print("*** Sistema de Descuentos ***")

MONTO_MINIMO = 1000
es_miembro_descuento = "si"

compra = int(input("Cual fue el monto de tu compra? "))
es_miembro = input("Eres miembro de la tienda? (si/no)? ")
es_miembro = es_miembro.strip().lower





if compra >= MONTO_MINIMO and es_miembro == es_miembro_descuento:
    print("Felicidades, has obtenido un descuento del 10%")
elif es_miembro == es_miembro_descuento:
    print("Felicidades, has obtenido un descuento del 5%")
else:
    print("Tienes un descuento del 0%")
