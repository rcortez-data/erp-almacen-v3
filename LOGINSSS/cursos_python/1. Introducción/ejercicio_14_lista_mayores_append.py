# numeros = [12, 5, 21, 8, 30, 7, 16]
# mayores = []
# Recorre la lista y:
# - Si el número es menor o igual a 10, usa continue.
# - Si es mayor que 10, agrégalo a mayores con append().
# - Imprime la lista.
# Resultado esperado:
# [12, 21, 30, 16]

numeros = [12, 5, 21, 8, 30, 7, 16]
mayores = []
for numero in numeros:
    if numero <= 10:
        continue
    else:
        mayores.append(numero)
print(mayores)
