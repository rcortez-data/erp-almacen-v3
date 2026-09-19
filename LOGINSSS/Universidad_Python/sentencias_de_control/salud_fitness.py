print("*** Bienvenidos al Sistema de Salud y Fitness ***")

# Variables de entrada
nombre_usuario = input("Por favor, ingresa tu nombre: ")
pasos_caminados = int(input("Por favor, ingresa la cantidad de pasos que has caminado hoy: "))

# Constantes
META_PASOS_DIARIOS = 10000
CALORIAS_POR_PASO = 0.04

# Cálculos
calorias_quemadas = pasos_caminados * CALORIAS_POR_PASO
cumplio_meta = pasos_caminados >= META_PASOS_DIARIOS

# Resultados
print(f"\nHola {nombre_usuario}, has caminado {pasos_caminados} pasos hoy.")
print(f"Has quemado aproximadamente {calorias_quemadas:.2f} kcal.")
print(f"¿Has cumplido tu meta diaria de {META_PASOS_DIARIOS} pasos? {'Sí' if cumplio_meta else 'No'}")

if cumplio_meta:
    print("¡Felicidades! Has alcanzado tu meta diaria de pasos.")
else:
    print("No has alcanzado tu meta diaria de pasos. ¡Ánimo para mañana!")

