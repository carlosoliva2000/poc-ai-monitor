<!-- Plantilla del prompt de objetivo del monitor. El código elige la sección según el tipo de detección
     y sustituye los marcadores <<...>>. Lo que va antes de la primera sección es común. -->
Instante actual: <<t_label>> (sim_time <<sim_time>> s).

Estado:
- Alertas abiertas: <<open_alerts>>
- Tus últimas decisiones: <<last_decisions>>

## raised
Nueva detección:
```json
<<detection_json>>
```
Tarea: diagnostica la causa más probable y publica una alerta con `publish_alert`.

## updated
La detección <<detection_id>> ha empeorado:
```json
<<detection_json>>
```
Alertas tuyas asociadas: <<related_alerts>>.
Tarea: comprueba si tu diagnóstico sigue siendo correcto. Si cambia la causa o la severidad, publica una alerta nueva con `supersedes`. Si no cambia nada, responde con una frase.

## cleared
La detección <<detection_id>> se ha cerrado:
```json
<<detection_json>>
```
Alertas tuyas asociadas: <<related_alerts>>.
Tarea: si la situación se ha normalizado, cierra la alerta con `close_alert` y di por qué. Si crees que el problema sigue (por ejemplo, otra fuente sigue mal), no la cierres y explica por qué en una frase.
