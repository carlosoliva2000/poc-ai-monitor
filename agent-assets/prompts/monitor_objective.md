<!-- Plantilla del prompt de objetivo del monitor. El código elige las secciones según el tipo de
     cada aviso pendiente y sustituye los marcadores <<...>>. Lo que va antes de la primera sección
     es común. -->
Instante actual: <<t_label>> (sim_time <<sim_time>> s).

Estado:
- Alertas abiertas: <<open_alerts>>
- Detecciones abiertas: <<open_detections>>
- Alerta del GPS reciente (abierta o cerrada hace ≤ 60 s): <<gps_alert_recent>>
- Tus últimas decisiones: <<last_decisions>>

## batch
Tienes <<count>> avisos del detector pendientes de respuesta (detecciones: <<detection_ids>>). **Cada uno necesita respuesta.** Si son del mismo problema, agrúpalos en una sola alerta (`publish_alert` con todas sus `detection_ids`) o en un solo `acknowledge_detection`.

## raised
Nueva detección <<detection_id>>: <<detection_json>>
Alertas tuyas asociadas: <<related_alerts>>.
Tarea: diagnostica la causa más probable y responde:
- Si no hay una alerta abierta que ya lo explique: `publish_alert` (alerta nueva).
- Si una alerta abierta ya lo explica y no cambia nada: `acknowledge_detection` con su `alert_id`.
- Si pertenece a una alerta abierta pero cambia la causa o la severidad: `publish_alert` con `supersedes` apuntando a ella.
- Si decides que no hace falta alerta: `acknowledge_detection` sin `alert_id`.

## updated
La detección <<detection_id>> ha empeorado: <<detection_json>>
Alertas tuyas asociadas: <<related_alerts>>.
Tarea: comprueba si tu diagnóstico sigue siendo correcto. Si cambia la causa o la severidad, publica una alerta nueva con `publish_alert` y `supersedes`. Si no cambia nada, responde con `acknowledge_detection` y el `alert_id` de la alerta.

## cleared
La detección <<detection_id>> se ha cerrado y era la **última detección abierta** de la alerta <<last_open_alert>>: <<detection_json>>
Alertas tuyas asociadas: <<related_alerts>>.
Tarea: llama **una sola vez** a `get_track_metrics` con `since` = <<detection_since>> y `until` = <<sim_time>> (desde el inicio de la detección hasta ahora) y decide con ese resultado. Si la situación se ha normalizado (la desviación vuelve a bajar y GPS y radar coinciden), cierra con `close_alert` y di por qué. Si crees que el problema sigue (por ejemplo, otra fuente sigue mal), no la cierres: responde con `acknowledge_detection` (con el `alert_id`) y explica por qué en `reason`.

## reminder
Aún no has respondido a: <<pending>>. Un texto no cuenta como respuesta: responde ahora llamando a `publish_alert`, `acknowledge_detection` o `close_alert`.
