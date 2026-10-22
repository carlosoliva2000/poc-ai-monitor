La simulación «<<scenario>>» (ejecución <<run_id>>) terminó en <<t_label>> (sim_time <<sim_time>> s). Escribe los cuatro apartados que te tocan. Etiquetas de las anomalías: <<labels>>.

## Resumen del vuelo
<<flight_summary>>

## Anomalías (cada una es una cadena de alertas)
<<anomalies>>

## Datos para valorar al monitor
<<assessment_facts>>

## Qué tienes que escribir
Responde directamente con estos títulos y en este orden, sin bloque de código ni texto antes o después:
- `## Resumen`: 3–5 frases. Qué pasó en el vuelo, cuántas anomalías hubo, cuál fue la más grave y si hay alguna abierta al final.
- `## Qué se vio`: un subapartado `### A1`, `### A2`… por cada anomalía de la lista (con su etiqueta), de 2–3 frases con las cifras y las fuentes de los datos de arriba. No repitas la hora, la severidad ni el estado.
- `## Valoración del monitor`: sé crítico. Cuatro viñetas, con estas etiquetas:
  - **Respaldo:** una frase por anomalía (A1, A2…): qué comprobaciones y datos sostienen la causa y qué duda queda (comprobaciones que no encajan entre sí, causa o severidad que cambiaron según «Cambios de la primera alerta a la última», evidencias que no se ven en los datos). Escribe «respaldado por…»; no escribas «correcto», «preciso» ni «acertó».
  - **Retrasos:** las cifras de «Retrasos» (simulación y reloj) y si te parecen largas para un operador.
  - **Fallbacks y rechazos:** la cifra exacta de fallbacks y la de llamadas rechazadas por los guardrails (son números distintos; los de «Fallbacks» y «Rechazos de los guardrails»), y qué tuvo que corregir el monitor (una frase por motivo de rechazo). Si hay rechazos, no escribas que no los hubo.
  - **Ayudas:** nombra cada ayuda de la lista «Ayudas al modelo activas» y di qué parte del resultado puede deberse a ellas (sin ellas el modelo podría fallar).
- `## Recomendaciones`: 2–4 puntos numerados y concretos, para el responsable del dron o del ejercicio, que salgan de los datos de arriba (qué alerta o comprobación revisar, qué retraso reducir). No propongas entrenar el modelo.
