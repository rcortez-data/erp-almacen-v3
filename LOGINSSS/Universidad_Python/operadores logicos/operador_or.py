print("*** Operador logico or ***")
condicion1 = False
condicion2 = False
# El operador or regresa True si cualquiera de los operandos es True
resultado = condicion1 or condicion2
print(f"Resultado {condicion1} or {condicion2} es: {resultado}")


# Sistema prestamo de libros

print("*** Sistema Prestamo de Libros ***")

DISTANCIA_PERMITIDA_KM = 3
tiene_credencial = input("Cuentas con credencial de estudiante (Si/No)? ")
distancia_biblioteca_km = int(input("A cuantos km vives de la biblioteca? "))

es_elegible_prestamo = (tiene_credencial.strip().lower() == "si" 
                        or distancia_biblioteca_km <= DISTANCIA_PERMITIDA_KM)

print(f"Eres elegible prestamo de libros? {es_elegible_prestamo}")
