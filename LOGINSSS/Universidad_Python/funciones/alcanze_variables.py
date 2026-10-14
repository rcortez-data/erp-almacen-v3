print('*** Alcanze de variables ***')

# Variable global
contador_global = 0

def incrementar_contador():
    # Declaramnos una variable local
    contador_local = 0

    # Usar la variable global
    global contador_global
    # Incrementar la variable global
    contador_global += 1

    # Incrementar la variable local
    contador_local += 1

    # Imprimir ambos contadores
    print(f'Contador local: {contador_local}')
    print(f'Contador global: {contador_global}\n')

# Llamamos varias veces la funcion
incrementar_contador()
incrementar_contador()
incrementar_contador()

# Terminando el programa
print(f'Valor variable global: {contador_global}')

