calculadora = input("¿Desea usar la calculadora? (si/no): ")
if calculadora.lower() == "si":
    while True:
        try:
            num1 = float(input("Ingrese el primer número: "))
            operador = input("Ingrese el operador (+, -, *, /): ")
            num2 = float(input("Ingrese el segundo número: "))

            if operador == "+":
                resultado = num1 + num2
            elif operador == "-":
                resultado = num1 - num2
            elif operador == "*":
                resultado = num1 * num2
            elif operador == "/":
                if num2 != 0:
                    resultado = num1 / num2
                else:
                    print("Error: División por cero no permitida.")
                    continue
            else:
                print("Operador no válido. Intente de nuevo.")
                continue

            print(f"Resultado: {resultado:.2f}")
        except ValueError:
            print("Entrada no válida. Por favor, ingrese números válidos.")
