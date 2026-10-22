# numeros = [3, 8, 11, 20, 7, 14, 5]
# Recórrela con un for:
# - Crea una lista llamada pares.
# - Si el número es par, agrégalo con append().
# - Si es impar, usa continue.
# - Imprime pares.
# Resultado esperado:
# [8, 20, 14]

numeros = [3, 8, 11, 20, 7, 14, 5]
pares = []
for numero in numeros:
    if numero % 2 != 0:
        continue
    pares.append(numero)
print(pares)
