print("*** Sistema de Empleados ***")
nombre_empleado = input("Ingrese el nombre del empleado: ")
edad_empleado = int(input("Ingrese la edad del empleado: "))
salario_empleado = float(input("Ingrese el salario del empleado: "))
es_jefe_departamento = input("¿Es jefe de departamento? (si/no) ")

# Vamos a convertir a un tipo bool la variable es_jefe_departamento
es_jefe_departamento = es_jefe_departamento.lower() == "si"

# Imprimir los valores del empleado
print(f"\nDatos del empleado")
print(f"Nombre del empleado: {nombre_empleado}")
print(f"Edad del empleado: {edad_empleado}")
print(f"Salario del empleado: {salario_empleado:.2f}")
print(f"Es jefe de departamento: {es_jefe_departamento}")
