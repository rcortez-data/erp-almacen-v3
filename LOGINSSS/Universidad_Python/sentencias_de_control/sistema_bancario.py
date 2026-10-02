print("*** Bienvenidos al Sistema Bancario ***")

salir_sistema_txt = input("Deseas salir del sistema (si/no)? ")
salir_sistema = salir_sistema_txt.strip().lower() == "si"

if not salir_sistema:
    print("Continuando dentro del sistema")
else:
    print("Saliendo del sistema")
