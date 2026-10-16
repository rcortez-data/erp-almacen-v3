# Ruta de aprendizaje: Maestro de Python

Este archivo es la bitácora de estudio para avanzar en el curso **Universidad Python - Cero a Experto**. La meta no es terminar videos rápidamente: es poder explicar y construir programas desde cero.

## Prompt maestro

Copia este prompt al iniciar una sesión nueva conmigo:

```text
Quiero que actúes como mi maestro personal de Python y tutor del curso "Universidad Python - Cero a Experto".

## Objetivo
Ayúdame a avanzar de forma progresiva, práctica y medible. Evalúa mi nivel con base en evidencia: mis explicaciones, decisiones, código, errores y capacidad para modificar un programa. No asumas que aprendí algo solo porque vi un video.

## Reglas de enseñanza
1. No me des la solución completa ni escribas el código final por mí.
2. Dame un ejercicio a la vez, relacionado con el tema que estoy estudiando.
3. Si me bloqueo, usa pistas graduales:
   - Pista 1: pregunta conceptual o recordatorio.
   - Pista 2: divide el problema en pasos, sin código completo.
   - Pista 3: señala qué parte revisar o qué herramienta de Python investigar.
   - Pista 4: muestra únicamente un ejemplo mínimo y diferente al ejercicio.
4. Antes de dar otra pista, pídeme que intente de nuevo.
5. Si pego código, revisa primero mi razonamiento y el error. Señala la línea o concepto problemático, pero no reescribas todo el programa.
6. Si no puedo resolverlo, registra honestamente "no logrado hoy", conserva el ejercicio pendiente y prepara un intento guiado para el siguiente día.
7. Solo considera un ejercicio dominado cuando pueda explicar la idea, ejecutar el programa, corregir un error pequeño y hacer una variación sin copiar.

## Nivel y metas diarias
Usa esta escala de niveles:
- L0: todavía no medido; necesita diagnóstico.
- L1: salida, variables, tipos de datos y operaciones sencillas.
- L2: entrada por consola, conversiones, cadenas y validaciones simples.
- L3: condicionales y repetición; puede convertir un requisito en pasos.
- L4: listas, tuplas, conjuntos y diccionarios.
- L5: funciones, parámetros, retorno, alcance y módulos.
- L6: archivos, excepciones y programas de consola completos.
- L7: POO, diseño y proyectos pequeños.
- L8+: bases de datos, APIs, web y proyectos profesionales.

Al inicio de cada sesión dime siempre:
- Fecha local: usa America/Mexico_City.
- Nivel demostrado actual.
- Nivel esperado para hoy.
- Evidencia pendiente para alcanzar ese nivel.
- Deuda de días anteriores, si existe.
- Una meta concreta para esta sesión.

La meta semanal se comprueba el domingo. Si me atraso, no borres la deuda: súmala al siguiente día y propón una compensación razonable. La compensación puede ser un bloque adicional corto o una revisión enfocada; no conviertas la semana en una maratón ni sacrifiques comprensión. Si el domingo sigo atrasado, prioriza consolidar lo esencial y registra qué pasa a la semana siguiente.

## Seguimiento
Si tienes acceso a mi repositorio, actualiza `README.md` después de cada sesión. Si no puedes editarlo, entrega un bloque de texto listo para reemplazar o pegar. Nunca inventes que completé algo.

Cada registro debe indicar:
- fecha;
- video o tema estudiado;
- ejercicio;
- estado: logrado, parcialmente logrado o no logrado;
- nivel demostrado y nivel esperado;
- evidencia observada;
- pistas utilizadas;
- deuda o compensación para el siguiente día;
- próximo paso.

Cuando termine un ejercicio, no me des inmediatamente uno mucho más difícil: primero verifica que pueda explicar y modificar el programa. Después sube la dificultad poco a poco.
```

## Cómo trabajar cada día

1. Abre el curso y anota el título exacto del video que viste.
2. Usa el prompt maestro y comparte únicamente lo necesario: tu explicación, tu código, el error y el resultado.
3. Intenta el ejercicio antes de pedir pistas.
4. Al terminar, pide: `Evalúa mi sesión y actualiza la bitácora sin darme la solución completa.`
5. Guarda este archivo en GitHub para continuar desde otra computadora.

## Escala de evaluación

El nivel no es una calificación escolar. Se determina por lo que puedes hacer sin copiar:

| Evidencia | Peso | Qué demuestra |
|---|---:|---|
| Explicas la idea con tus palabras | 25% | Comprensión conceptual |
| Construyes el programa desde un archivo vacío | 30% | Independencia |
| Corriges un error con una pista | 20% | Depuración |
| Haces una variación del ejercicio | 15% | Transferencia |
| Código legible y nombres claros | 10% | Buenas prácticas |

Para subir de nivel se requiere al menos 80% de evidencia y una variación funcional. Ver el video, leer la solución o copiar el código sirve para estudiar, pero no cuenta como dominio.

## Semana de arranque

Fecha de inicio: **15 de octubre de 2026**  
Meta de cierre: **domingo 18 de octubre de 2026**  
Meta de la semana: demostrar L2 en un programa pequeño de consola.

| Día | Nivel esperado | Meta acumulada | Compensación si hay atraso |
|---|---|---|---|
| Jue 15 | L1 en diagnóstico | Variables, tipos y operaciones | Terminar el diagnóstico antes de avanzar |
| Vie 16 | L2 inicial | Entrada, conversión y salida clara | +20 min de práctica dirigida |
| Sáb 17 | L2 consolidado | Validar al menos un caso normal y uno límite | Repetir solo la parte fallida |
| Dom 18 | L2 demostrado | Resolver una variación y explicar el programa | Cerrar deuda esencial; no saltar de tema |

Regla de deuda: cada bloque incompleto se copia al siguiente día. La deuda máxima recomendada es de un bloque; si crece, se reduce el contenido nuevo y se refuerza la base.

## Estado actual

- Curso: [Universidad Python - Cero a Experto](https://www.udemy.com/course/universidad-python-desde-cero-hasta-experto-django-flask-rest-web/)
- Video indicado: [lecture/45329979](https://www.udemy.com/course/universidad-python-desde-cero-hasta-experto-django-flask-rest-web/learn/lecture/45329979#content)
- Título exacto del video: pendiente de confirmar desde la sesión de Udemy
- Nivel demostrado: **L0 — diagnóstico pendiente**
- Nivel esperado hoy: **L1 — completar el ejercicio diagnóstico**
- Deuda: ninguna

## Ejercicio 001 — Ficha de pedido

**Objetivo:** comprobar variables, tipos, entrada por consola, conversiones, operaciones y salida formateada. No uses funciones, listas ni clases todavía, aunque ya las conozcas.

### Enunciado

Crea desde un archivo vacío un programa de consola que capture los datos de un pedido de una tienda:

- nombre del producto;
- precio unitario;
- cantidad;
- porcentaje de descuento;
- porcentaje de impuesto.

El programa debe calcular y mostrar:

1. subtotal;
2. monto del descuento;
3. subtotal con descuento;
4. monto del impuesto;
5. total final;
6. un pequeño resumen legible del pedido.

### Condiciones

- Convierte los datos numéricos al tipo apropiado antes de operar.
- Usa nombres de variables descriptivos.
- Muestra dinero con dos decimales.
- Prueba al menos estos casos: un producto sin descuento y otro con descuento e impuesto.
- No copies la solución del curso ni uses funciones, bucles, listas o librerías externas.

### Criterios de terminado

- El programa ejecuta sin errores con datos válidos.
- Las operaciones siguen un orden lógico.
- Puedes explicar qué representa cada variable.
- Puedes cambiar los datos sin modificar la lógica.
- Puedes comprobar manualmente si el total obtenido tiene sentido.

### Pistas permitidas

**Pista 1:** separa el problema en entrada → conversión → cálculos → presentación.  
**Pista 2:** expresa cada porcentaje como una fracción antes de calcular el monto correspondiente.  
**Pista 3:** revisa si el impuesto se aplica al subtotal original o al subtotal después del descuento; elige una regla, escríbela como comentario y sé consistente.  
**Pista 4:** si el resultado muestra demasiados decimales, investiga el formato de números decimales en cadenas de formato. No copies un programa completo.

### Qué debes entregar para la evaluación

Pega en la sesión:

1. tu código;
2. una ejecución con datos de prueba y su salida;
3. una explicación breve de la fórmula del total;
4. cualquier error que hayas encontrado y cómo intentaste corregirlo.

No te daré la solución completa. Si no terminas hoy, escribe `no logrado hoy`, conserva tu intento y mañana continuaremos desde la primera parte que falle.

## Bitácora de sesiones

### 2026-10-15

- Tema/video: video 45329979; título pendiente de confirmar.
- Ejercicio: 001 — Ficha de pedido.
- Estado: pendiente de intento.
- Nivel demostrado: L0.
- Nivel esperado: L1.
- Evidencia: aún no entregada.
- Pistas utilizadas: ninguna.
- Deuda: ninguna.
- Próximo paso: resolver el ejercicio desde un archivo vacío y traer código, salida y dudas.

<!--
Plantilla para futuras sesiones:

### AAAA-MM-DD
- Tema/video:
- Ejercicio:
- Estado: logrado / parcialmente logrado / no logrado.
- Nivel demostrado:
- Nivel esperado:
- Evidencia:
- Pistas utilizadas:
- Deuda o compensación:
- Próximo paso:
-->
