"""
Clase 05-08-00 - Operadores de comparacion

Instrucciones:
- Resuelve los ejercicios en orden.
- Ejecuta este archivo desde VS Code.
- No borres los enunciados; escribe tu codigo debajo de cada uno.
- Cuando termines, dile a Codex: "revisa la clase 05-08-00".
"""

print("*** Ejercicios Clase 05-08-00: Operadores de Comparacion ***")


# ============================================================
# EJERCICIO 3 - Puede votar
# ============================================================
# Crea una variable llamada edad.
# Si edad es mayor o igual a 18, imprime:
# Puede votar
# Si no, imprime:
# No puede votar

edad = 18
if edad >= 18:
    print("Puede votar")
else:
    print("No puede votar")


# ============================================================
# EJERCICIO 4 - Precio con descuento
# ============================================================
# Crea dos variables:
# precio_original
# precio_actual
#
# Imprime True si precio_actual es menor que precio_original.
# Imprime False si no lo es.

precio_original = 200
precio_actual = 220
if precio_actual < precio_original:
    print(True)
else:
    print(False)



# ============================================================
# EJERCICIO 5 - Corregir codigo
# ============================================================
# Este codigo tiene un error de logica/sintaxis.
# Corrigelo para que compare si a y b son iguales.

a = 10
b = 10
resultado = a == b
print(resultado)




# ============================================================
# RETO - Validador de acceso basico
# ============================================================
# Crea estas variables:
# usuario_correcto = "admin"
# password_correcta = "1234"
#
# Luego crea:
# usuario = "admin"
# password = "1234"
#
# Si usuario y password son correctos, imprime:
# Acceso permitido
#
# Si no, imprime:
# Acceso denegado
#
# Pista: puedes usar and.

usuario_correcto = "admin"
password_correcta = "1234"

usuario = "admin"
password = "1234"

if usuario == usuario_correcto and password == password_correcta:
    print("Acceso permitido")
else:
    print("Acceso denegado")



# Reto 2:
# El programa debe imprimir:
# - "Excelente" si la calificación es mayor o igual a 90
# - "Aprobado" si la calificación es mayor o igual a 70
# - "Reprobado" si la calificación es menor que 70
# Pista: usa if, elif, else.



calificacion = 85
if calificacion >= 90:
    print("Excelente")
elif calificacion >= 70:
    print("Aprobado")
else:
    print("Reprobado")
