# Ejercicio 11: continue
# Pide números hasta que el usuario escriba 0.
# - Si escribe un número negativo, ignóralo usando continue.
# - Suma solamente los números positivos.
# - Al final imprime la suma.
# Ejemplo:
# Ingresa un número: 10
# Ingresa un número: -5
# Ingresa un número: 8
# Ingresa un número: 0
# La suma de positivos es: 18
# Pista: primero revisa si el número es negativo, después si es 0.

suma = 0
contador = 0
mayor = 0
promedio = 0 
while True:
    numero = int(input("Ingresa un número: "))

    if numero == 0:
        break

    if numero < 0:
        continue

    suma += numero
    contador += 1

    if numero > mayor:
        mayor = numero

if contador > 0:
    promedio = suma / contador
else:
    promedio = 0




print(f"La suma total es: {suma}")
print(f"Se ingresaron {contador} números")
print(f"El número mayor es: {mayor}")
print(f'El promedio es: {promedio}')
print(f'La suma total de positivos es: {suma}')