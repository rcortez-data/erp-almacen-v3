print("*** Bienvenidos a la Casa de los Espejos ***")

edad = int(input("Por favor, ingresa tu edad: "))
tienes_miedo_oscuridad = input("¿Tienes miedo a la oscuridad? (si/no): ")
tienes_miedo_oscuridad = tienes_miedo_oscuridad.strip().lower() == "si"

if not tienes_miedo_oscuridad and edad >= 10:
    print("Puedes entrar a la Casa de los Espejos.")
else:
    print("No puedes entrar a la Casa de los Espejos.")
    