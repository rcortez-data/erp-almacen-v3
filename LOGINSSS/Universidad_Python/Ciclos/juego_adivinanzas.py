'''import random

print("*** Juego de Adivinanzas ***\n")

numero_secreto = random.randint(1, 50)
intentos = 0

while intentos < 10:
    intento = int(input("\nElige un numero entre 1 al 50: "))
    intentos += 1
    if intento == numero_secreto:
        print(f"\nFelicidades Adivinaste el numero secreto en {intentos} intentos.")
        break
    else:
        if intento > numero_secreto:
            print("\nTu numero es mayor que el numero secreto, intenta de nuevo.")
        else:
            print("\nTu numero es menor que el numero secreto, intenta de nuevo.")
else:
    print(f"\nLo siento, no adivinaste. El número era {numero_secreto}.")
print("\nFin del juego.")
'''


from random import randint

print("*** Juego de Adivinanzas ***\n")

numero_secreto = randint(1, 50)
intentos = 0
adivinanza = None
INTENTOS_MAXIMOS = 5

while adivinanza != numero_secreto and intentos < INTENTOS_MAXIMOS:
    adivinanza = int(input("\nAdivina el numero secreto (1-50): "))
    # Agregamos una ayuda para orientar al jugador
    if adivinanza < numero_secreto:
        print("El numero secreto es mayor.")
    elif adivinanza > numero_secreto:
        print("El numero secreto es menor.")
    intentos += 1

if adivinanza == numero_secreto:
    print(f"\nFelicidades Adivinaste el numero secreto en {intentos} intentos.")
else:
    print(f"\nLo siento, no adivinaste el numero secreto. El numero era {numero_secreto}.")
print("\nFin del juego.")
