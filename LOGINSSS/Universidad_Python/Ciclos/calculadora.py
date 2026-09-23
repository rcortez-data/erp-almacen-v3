print("*** Calculadora ***")

salir = False
while not salir:
    print('''Menu:
1. Sumar
2. Restar
3. Multiplicar
4. Dividir
5. Salir 
''')
    opcion = int(input("Seleccione una opcion: "))
    if opcion == 1:
        num1 = float(input("Ingrese el primer numero: "))
        num2 = float(input("Ingrese el segundo numero: "))
        print(f"\nResultado: {num1 + num2}\n")
    elif opcion == 2:
        num1 = float(input("Ingrese el primer numero: "))
        num2 = float(input("Ingrese el segundo numero: "))
        print(f"\nResultado: {num1 - num2}\n")
    elif opcion == 3:
        num1 = float(input("Ingrese el primer numero: "))
        num2 = float(input("Ingrese el segundo numero: "))
        print(f"\nResultado: {num1 * num2}\n")
    elif opcion == 4:
        num1 = float(input("Ingrese el primer numero: "))
        num2 = float(input("Ingrese el segundo numero: "))
        if num2 != 0:
            print(f"\nResultado: {num1 / num2}\n")
        else:
            print("Error: Division por cero\n")
    elif opcion == 5:
        print(f"\nSaliendo de la calculadora. Hasta pronto!\n")
        salir = True
    else:
        print(f"\nOpcion no valida, seleccione una opcion del menu\n")
else:
    print(f"\nTerminando la calculadora")
