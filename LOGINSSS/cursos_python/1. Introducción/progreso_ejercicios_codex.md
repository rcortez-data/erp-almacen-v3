# Progreso de ejercicios de Python

## Alumno

Ricardo

## Punto de continuidad

Última actualización: 22 de octubre de 2026

Estamos trabajando ejercicios prácticos de Python, avanzando uno por uno. El alumno envía su código y se revisa antes de pasar al siguiente ejercicio.

## Temas practicados

- Variables y tipos básicos.
- Conversión con `int()`.
- Operadores de comparación.
- Condicionales: `if`, `elif` y `else`.
- Operadores lógicos: `and` y `or`.
- Listas y diccionarios.
- Ciclos `for` y `while`.
- `range()` en orden normal y descendente.
- Acumuladores para sumas.
- Contadores.
- Promedios evitando dividir entre cero.
- `break` para terminar un ciclo.
- `continue` para ignorar una vuelta.
- Recorrido de listas con ciclos.

## Avance reciente

El alumno resolvió correctamente estos ejercicios:

1. Imprimir del `1` al `10` usando `range()`.
2. Imprimir números pares del `2` al `20`.
3. Imprimir del `10` al `1` en orden descendente.
4. Sumar los números del `1` al `100`, obteniendo `5050`.
5. Usar `break` para detener un ciclo al llegar al `7`.
6. Pedir números hasta que se capture `0`.
7. Sumar números ingresados hasta capturar `0`.
8. Contar números ingresados sin contar el `0`.
9. Encontrar el número mayor.
10. Calcular suma, cantidad, mayor y promedio.
11. Ignorar números negativos usando `continue` y sumar positivos. Completado correctamente; el alumno además integró contador, mayor y promedio de ejercicios anteriores.
12. Recorrer una lista usando `for`, `continue` y `break` para sumar valores positivos hasta encontrar `0`. Completado correctamente; resultado `12`.
13. Recorrer una lista, identificar pares con el operador `%`, usar `append()` y guardar los resultados. Completado correctamente; resultado `[8, 20, 14]`.
14. Filtrar números mayores que `10` usando `continue` y `append()`. Completado correctamente; resultado `[12, 21, 30, 16]`.
15. Filtrar palabras por cantidad de caracteres usando `len()`, `continue` y `append()`. Completado correctamente; resultado `['computadora', 'programacion', 'teclado']`.
16. Aplicar un descuento del `10%` a precios seleccionados usando `continue`, operaciones y `append()`. Completado correctamente; resultado `[135.0, 198.0, 270.0]`.

## Observaciones del maestro

- La lógica principal está avanzando bien.
- El alumno entiende la diferencia entre colocar `print()` dentro o fuera de un ciclo.
- Debe seguir reforzando el orden de las instrucciones dentro del ciclo.
- Debe recordar que una variable como `mayor` no debe reemplazarse en cada vuelta antes de compararla.
- Cuando un ejercicio pide una sola tarea, conviene evitar variables y cálculos que no se necesitan.
- La indentación en Python es importante y el alumno ya está identificando mejor sus errores en VS Code.
- Se permite usar GitHub Copilot como apoyo, pero algunos ejercicios deben resolverse sin autocompletado para reforzar la lógica.

## Ejercicio pendiente

El ejercicio 16 ya fue revisado y quedó aprobado. El siguiente ejercicio es el número 17.

Dada esta lista:

```python
carrito = [
    {"producto": "Pan", "precio": 20, "cantidad": 2},
    {"producto": "Leche", "precio": 25, "cantidad": 3},
    {"producto": "Sopa", "precio": 18, "cantidad": 4}
]
```

Recórrela con un `for` y cumple estas reglas:

- Crea una variable `total` con valor `0`.
- Calcula el subtotal de cada producto: `precio * cantidad`.
- Acumula cada subtotal en `total`.
- Imprime el total final.

Resultado esperado:

```text
182
```

## Cómo continuar

Cuando el alumno regrese, debe enviar el código del ejercicio pendiente. Revisar primero si funciona y después continuar con ejercicios de ciclos y lógica. Más adelante se puede pasar a ejercicios de colecciones y funciones cuando el curso llegue a esos temas.

## Forma de enseñanza acordada

- Explicar en palabras simples y sin extenderse demasiado.
- Entregar un ejercicio a la vez.
- No dar la respuesta completa inmediatamente.
- Señalar el error y dar pistas para que el alumno lo corrija.
- Mostrar la solución completa solo cuando sea necesario o cuando el alumno la pida.
- Mantener los ejercicios relacionados con lo que ya se ha estudiado.
- Convertir ejercicios adecuados en pequeños proyectos prácticos.
