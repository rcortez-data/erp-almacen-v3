print("*** Sistema de Reserva de Hotel ***")

# Entrada de datos del cliente
nombre_cliente = input("Nombre del cliente: ")
dias_estadia = int(input("Ingresa la cantidad de días de tu estadía: "))
cuarto_vista_mar = input("¿Deseas un cuarto con vista al mar? (sí/no): ")

# Constantes

CUARTO_SIN_VISTA_MAR = 150.50
CUARTO_CON_VISTA_MAR = 190.50

# Calculos
if cuarto_vista_mar.strip().lower() == "si":
    costo_total = dias_estadia * CUARTO_CON_VISTA_MAR
else:
    costo_total = dias_estadia * CUARTO_SIN_VISTA_MAR

# Resultados
print()
print("-" * 10, "Detalles de la Reservacion", "-" * 10)
print(f"Cliente: {nombre_cliente}")
print(f"Días de estadía: {dias_estadia}")
print(f"Costo total: ${costo_total:.2f}")
print(f"Habitación con vista al mar: {'Si' if cuarto_vista_mar.strip().lower() == 'si' else 'No'}")