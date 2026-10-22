# palabras = ["sol", "computadora", "pan", "programacion", "luz", "teclado"]
# Crea palabras_largas y recorre la lista:
# - Si la palabra tiene 4 letras o menos, usa continue.
# - Guarda las palabras con más de 4 letras usando append().
# - Imprime la lista.
# Resultado esperado:
# ["computadora", "programacion", "teclado"]

palabras = ["sol", "computadora", "pan", "programacion", "luz", "teclado"]
palabras_largas = []

for palabra in palabras:
    if len(palabra) <= 4:
        continue

    palabras_largas.append(palabra)

print(palabras_largas)