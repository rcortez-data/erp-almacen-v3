print("*** Cajero Automatico ***")

salir = False
saldo = 1000

while not salir:
    print('''Menu:
1. Consultar saldo
2. Retirar
3. Depositar
4. Salir
''')
    opcion = int(input("Seleccione una opcion: "))
    if opcion == 1:
        print(f"\nSaldo disponible: {saldo}\n")
    elif opcion == 2:
        monto_retirar = float(input("\nIngrese el monto a retirar: "))
        if monto_retirar <= saldo:
            saldo -= monto_retirar
            print(f"\nRetiro exitoso. Saldo disponible: {saldo:.2f}\n")
        else:
            print("Saldo insuficiente. Saldo actual {saldo:.2f}\n")
    elif opcion == 3:
        monto_depositar = float(input("\nIngrese el monto a depositar: "))
        saldo += monto_depositar
        print(f"\nDeposito exitoso. Saldo disponible: {saldo}\n")
    elif opcion == 4:
        print("\nSaliendo del cajero automatico. Hasta pronto!\n")
        salir = True
    else:
        print("\nOpcion no valida, Seleccione una opcion del menu\n")
else:
    print("\nTerminando el cajero automatico")