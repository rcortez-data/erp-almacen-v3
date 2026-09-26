print("*** Sistema de creacion y validacion de password ***")

password = input("Ingrese su password (Debe tener al menos 6 caracteres): ")
while len(password) < 6:
    print("Error: La password debe tener al menos 6 caracteres.")
    password = input("Ingrese un nuevo password (Debe tener al menos 6 caracteres): ")
else:
    print("Password creada exitosamente.")