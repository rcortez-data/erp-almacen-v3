"""
Clases 05-10-00 y 05-11-00 - Operador and y Descuento VIP

Instrucciones:
- Resuelve los ejercicios en orden.
- Ejecuta este archivo desde VS Code.
- No borres los enunciados; escribe tu codigo debajo de cada uno.
- Cuando termines, dile a Codex: "revisa la clase 05-10-11".
"""

print("*** Ejercicios Clase 05-10-11: Operador and y Descuento VIP ***")


# ============================================================
# EJERCICIO 3 - Entrada a evento
# ============================================================
# Crea estas variables:
# edad = 20
# tiene_boleto = True
#
# Si edad es mayor o igual a 18 Y tiene_boleto es True, imprime:
# Puede entrar
#
# Si no, imprime:
# No puede entrar

edad = 20
tiene_boleto = True

if edad >= 18 and tiene_boleto:
    print("Puede entrar")
else:
    print("No puede entrar")

# ============================================================
# EJERCICIO 4 - Producto con descuento
# ============================================================
# Crea estas variables:
# precio = 120
# tiene_cupon = True
#
# Si precio es mayor o igual a 100 Y tiene_cupon es True, imprime:
# Aplica descuento
#
# Si no, imprime:
# No aplica descuento

precio = 120
tiene_cupon = True

if precio >= 100 and tiene_cupon:
    print("Aplica descuento")
else:
    print("No aplica descuento")

# ============================================================
# EJERCICIO 5 - Corregir condicion
# ============================================================
# Este codigo tiene un error de logica.
# Corrigelo para que solo imprima "Acceso permitido"
# cuando usuario y password sean correctos.

usuario_correcto = "admin"
password_correcta = "1234"

usuario = "admin"
password = "1234"

if usuario == usuario_correcto and password == password_correcta:
    print("Acceso permitido")
else:
    print("Acceso denegado")




# ============================================================
# RETO - Descuento VIP mejorado
# ============================================================
# Crea un sistema de descuento VIP.
#
# Reglas:
# - cantidad_productos debe ser mayor o igual a 10
# - tiene_membresia debe ser "si"
# - total_compra debe ser mayor o igual a 500
#
# Solo si las 3 condiciones se cumplen, imprime:
# Descuento VIP aplicado
#
# Si no, imprime:
# No aplica descuento VIP
#
# Usa input() para pedir:
# - cantidad_productos
# - tiene_membresia
# - total_compra
#
# Pista:
# cantidad_productos debe convertirse a int.
# total_compra puede convertirse a float.
# tiene_membresia puedes normalizarlo con .strip().lower()

print("*** Sistema de Descuento VIP ***")

cantidad_productos = int(input("Cuantos productos comprados: "))
tiene_membresia = input("Tiene membresia (Si/No): ")
tiene_membresia = tiene_membresia.strip().lower()
total_compra = float(input("Total de su compra: "))

if cantidad_productos >= 10 and tiene_membresia == "si" and total_compra >= 500:
    print("Descuento VIP aplicado")
else:
    print("No aplica descuento VIP")