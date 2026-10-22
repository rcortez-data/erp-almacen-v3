# precios = [80, 150, 220, 50, 300, 90]
# Crea precios_descuento y recorre la lista:
# - Si el precio es menor que 100, usa continue.
# - A los precios de 100 o más aplícales 10% de descuento.
# - Guarda los precios finales con append().
# - Imprime la lista.
# Resultado esperado:
# [135.0, 198.0, 270.0]

precios = [80, 150, 220, 50, 300, 90]
precios_descuentos = []

for precio in precios:
    if precio < 100:
        continue
    else:
        precio = precio - (precio * .10)
    
    precios_descuentos.append(precio)
print(precios_descuentos)