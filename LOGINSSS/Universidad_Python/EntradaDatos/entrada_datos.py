# Programa: Entrada Datos Python
nombre = input("Ingrese su nombre: ")
print(f"Tu nombre es: {nombre}")

# Cuidado con la conversion de tipos al trabajar con valores numericos
# Forma correcta: Envolver con int() o float()

# Para enteros (edad, cantidad)
edad = int(input("Ingrese su edad: "))
print(f"Tu edad es: {edad}")
print(edad + 5) # ¡funciona! (20 + 25 = 25)

# Para decimales (precio, altura)
altura = float(input("Ingrese su altura: "))
print(f"Tu altura es: {altura}")
