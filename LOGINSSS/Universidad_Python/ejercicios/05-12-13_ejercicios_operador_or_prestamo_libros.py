"""
Clases 05-12-00 y 05-13-00 - Operador or y Prestamo de Libros

Instrucciones:
- Resuelve los ejercicios en orden.
- Ejecuta este archivo desde VS Code.
- No borres los enunciados; escribe tu codigo debajo de cada uno.
- Cuando termines, dile a Codex: "revisa la clase 05-12-13".
"""

print("*** Ejercicios Clase 05-12-13: Operador or y Prestamo de Libros ***")


# ============================================================
# EJERCICIO 3 - Acceso con pase o invitacion
# ============================================================
# Crea estas variables:
# tiene_pase = False
# tiene_invitacion = True
#
# Si tiene_pase es True O tiene_invitacion es True, imprime:
# Puede entrar
#
# Si no, imprime:
# No puede entrar

tiene_pase = False
tiene_invitacion = True

if tiene_pase or tiene_invitacion:
    print("Puede entrar")
else:
    print("No puede entrar")


# ============================================================
# EJERCICIO 4 - Envio gratis
# ============================================================
# Crea estas variables:
# total_compra = 350
# es_cliente_vip = False
#
# Si total_compra es mayor o igual a 500 O es_cliente_vip es True, imprime:
# Envio gratis
#
# Si no, imprime:
# Paga envio

total_compra = 350
es_cliente_vip = False

if total_compra >= 500 or es_cliente_vip:
    print("Envio gratis")
else:
    print("Paga envio")


# ============================================================
# EJERCICIO 5 - Corregir condicion
# ============================================================
# Este codigo tiene un error de logica.
# Corrigelo para que imprima "Puede entrar"
# si la persona es admin O es dueno.

# es_admin = False
# es_dueno = True
#
# if es_admin and es_dueno:
#     print("Puede entrar")
# else:
#     print("No puede entrar")

es_admin = False
es_dueno = True

if es_admin or es_dueno:
    print("Puede entrar")
else:
    print("No puede entrar")



# ============================================================
# RETO - Prestamo de libros mejorado
# ============================================================
# Crea un sistema de prestamo de libros.
#
# Reglas:
# Una persona puede pedir prestado un libro si cumple AL MENOS una condicion:
# - tiene credencial de estudiante
# - vive a 3 km o menos de la biblioteca
# - tiene membresia premium
#
# Usa input() para pedir:
# - tiene_credencial
# - distancia_biblioteca_km
# - tiene_membresia_premium
#
# Normaliza las respuestas de texto con .strip().lower().
#
# Si cumple al menos una condicion, imprime:
# Prestamo aprobado
#
# Si no, imprime:
# Prestamo rechazado

print("*** Sistema de Prestamo de Libros ***")
print()

tiene_credencial = input("Tiene credencial(Si/No)? ")
tiene_credencial = tiene_credencial.strip().lower()
distancia_biblioteca_km = int(input("Distancia a la biblioteca en km: "))
tiene_membresia = input("Tiene membresia (Si/No)? ")
tiene_membresia = tiene_membresia.strip().lower()

if tiene_credencial == "si" or distancia_biblioteca_km <= 3 or tiene_membresia == "si":
    print("Prestamo aprobado")
else:
    print("Prestamo rechazado")

