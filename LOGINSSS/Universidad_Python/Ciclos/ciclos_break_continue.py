print('*** Break y Continue ***')

# Ejemplo con break
print('Palabra break:')
for numero in range(1,10):
    if numero % 2 == 0: # Numero Par
        print(numero)
        break # Salimos del ciclo inmediatamente


# Ejemplo con continue
print('\nPalabra continue: ')
for numero in range(1, 10):
    if numero % 2 == 1: # Numero impar
        continue
    print(numero) # numeros pares

