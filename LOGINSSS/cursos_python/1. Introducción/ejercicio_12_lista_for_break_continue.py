# Ahora seguimos con el ejercicio 12:
# numeros = [4, -2, 8, 0, 10, -5, 6]
# Recorre la lista con un for:
# - Si el número es negativo, usa continue.
# - Si el número es 0, usa break.
# - Suma los números positivos anteriores al 0.
# - Imprime la suma final.
# Resultado esperado:
# 12

numeros =[4, -2, 8, 0, 10, -5, 6] 
suma = []
total = 0
for numero in numeros:
    if numero < 0:
        continue
    elif numero == 0:
        break
    else:
        suma.append(numero)
for i in suma:
    total += i
print(total)
