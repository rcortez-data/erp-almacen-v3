# Programa: Funcion Bool

# 1. Números (int y float)
print(bool(0))  # False (El vacío numérico)
print(bool(0.0))  # False (El vacío numérico)
print(bool(42))  # True (Cualquier número distinto de cero)

# 2. Texto (Strings)
# Cadena vacia = Nada = False
print(bool(""))  # False (Cadena vacía)

# Cadena con espacio o texto = Algo = True
print(bool(" "))  # True (Cadena con espacio)
print(bool("Hola"))  # True (Cadena con texto)

# 3. None (Ausencia total de valor)
vacio = None
print(bool(vacio))  # False (None es vacío)

print(bool(False))  # False 
print(bool(True))  # True

