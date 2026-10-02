print("*** Determinar la estación del año ***")

mes = int(input("Ingresa el mes (1-12): "))

if mes in [12, 1, 2]:
    estacion = "Invierno"
elif mes in [3, 4, 5]:
    estacion = "Primavera"
elif mes in [6, 7, 8]:
    estacion = "Verano"
elif mes in [9, 10, 11]:
    estacion = "Otoño"
else:
    estacion = "Estacion Desconocida"

print(f"La estación del año es: {estacion}")