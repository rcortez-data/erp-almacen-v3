print(f"*** Operador and ***")
# Regresa verdadero si ambos valores a evaluar son verdaderos
condicion1 = True
condicion2 = True
resultado = condicion1 and condicion2
print(f"Resultado {condicion1} and {condicion2}: {resultado}")


# Sistema Descuento VIP
print("***  Sistema de Descuentos VIP ***")

NO_PRODUCTOS_DESCUENTO = 10
cantidad_productos = int(input("Cuantos productos compraste hoy? "))
tiene_membresia = input("Tienes la membresia de la tienda (Si/No)? ")

es_elegible_descuento = (cantidad_productos >= NO_PRODUCTOS_DESCUENTO 
                         and tiene_membresia.strip().lower() == "si")

print(f"Tienes acceso al decuento VIP? {es_elegible_descuento}")

