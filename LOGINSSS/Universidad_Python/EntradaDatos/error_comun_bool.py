# ERROR COMÚN DE PRINCIPIANTE
respuest_usuario = "False" # Esto es un texto

# La funcion bool evalua si el string esta vacio
es_verdad = bool(respuest_usuario)

print(f"El valor es: {es_verdad}")  # Esto imprimira True, porque el string no esta vacio
# Output: El valor es: True
# ¿Por que? Porque el string "False" tiene 5 lestras. No esta vacio

# Forma correcta de validar vacio:
texto_vacio = ""
print(bool(texto_vacio))  # Esto imprimira False, porque el string esta vacio
