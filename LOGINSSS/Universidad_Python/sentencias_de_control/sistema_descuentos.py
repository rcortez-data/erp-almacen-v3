print("*** Sistema de Descuentos ***")

MONTO_MINIMO = 1000
es_miembro_descuento = "si"

compra = float(input("Cual fue el monto de tu compra? "))
es_miembro = input("Eres miembro de la tienda? (si/no)? ").strip().lower()
importe_descuento = 0


if compra >= MONTO_MINIMO and es_miembro == es_miembro_descuento:
    importe_descuento = compra * 0.10
    compra -= importe_descuento
    print("\nFelicidades, has obtenido un descuento del 10%")
elif es_miembro == es_miembro_descuento:
    importe_descuento = compra * 0.05
    compra -= importe_descuento
    print("\nFelicidades, has obtenido un descuento del 5%")
elif compra >= MONTO_MINIMO:
    importe_descuento = compra * 0.03
    compra -= importe_descuento
    print("\nFelicidades, has obtenido un descuento del 3%")
else:
    print("""
No obtuviste ningún descuento.
Te invitamos a hacerte miembro de la tienda para obtener descuentos en el futuro.
""")

print("-" * 40)
print("Resumen de la compra:")
print(f"Monto de la compra: ${compra + importe_descuento}")
print(f"Monto del descuento: ${importe_descuento}")
print(f"Monto final de la compra con descuento: ${compra}")
