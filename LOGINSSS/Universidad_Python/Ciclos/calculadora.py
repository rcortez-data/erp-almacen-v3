print("*** Calculadora ***")

salir = False
while not salir:
    print('''\nOperaciones que puedes Realizar:
    1. Sumar
    2. Restar
    3. Multiplicar
    4. Dividir
    5. Salir''')
    try:
        opcion = int(input("Seleccione una opcion: "))
    except ValueError:
        print("\nError: debe seleccionar una opcion numerica")
        continue

    if opcion in (1, 2, 3, 4):
        try:
            num1 = float(input("Ingrese el primer valor: "))
            num2 = float(input("Ingrese el segundo valor: "))
        except ValueError:
            print("\nError: debe ingresar valores numericos")
            continue

        if opcion == 1:
            resultado = num1 + num2
        elif opcion == 2:
            resultado = num1 - num2
        elif opcion == 3:
            resultado = num1 * num2
        elif num2 != 0:
            resultado = num1 / num2
        else:
            print("\nError: division por cero")
            continue

        print(f"\nResultado: {resultado:.2f}")
    elif opcion == 5:
        print(f"\nSaliendo de la calculadora. Hasta pronto!")
        salir = True
    else:
        print(f"\nOpcion no valida, seleccione una opcion del menu")
else:
    print(f"\nTerminando la calculadora")
