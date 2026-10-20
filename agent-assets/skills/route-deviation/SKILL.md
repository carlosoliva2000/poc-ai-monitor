---
name: route-deviation
description: Úsala cuando el detector lance ROUTE_DEVIATION (la posición del GPS se aleja de la ruta planificada). Distingue viento, secuestro, recuperación tras un engaño o una pérdida del GPS y causa desconocida.
---
# Diagnóstico de una desviación de ruta

Una desviación de ruta significa que el GPS del dron está lejos de la ruta planificada. Puede ser físico (viento), un cambio de destino no autorizado (secuestro) o la consecuencia de que el GPS estaba mintiendo o sin señal y ha vuelto a informar bien. Sigue los pasos en orden y para en el primero que encaje.

## Paso 0. ¿Viene de un engaño o una pérdida del GPS que acaba de terminar?
Mira el estado que te han pasado y, si hace falta, `get_my_alerts`. Si hay una alerta `GPS_SPOOFING` abierta o reciente (o una `SOURCE_DISCREPANCY` que se acaba de cerrar) **y** en `get_track_metrics` el GPS y el radar vuelven a coincidir, esta desviación es la **posición real** que el engaño había ocultado: el GPS ha «saltado» a donde estaba el dron de verdad.
- Publica una alerta con `cause: GPS_SPOOFING`, `severity: medium`, que diga que el engaño ha terminado y que el dron corrige hacia la ruta, con `supersedes` apuntando a la alerta de spoofing si sigue abierta.
- Recomendación: verificar la integridad del receptor GPS antes de volver a confiar en él.

Lo mismo si hay una alerta `GPS_JAMMING` o `SENSOR_FAULT` del GPS abierta o reciente (o una detección `GPS_DEGRADED` que se acaba de cerrar) **y** el GPS y el radar vuelven a coincidir: la desviación es la **posición real** que la pérdida del GPS había ocultado (el dron navegó a estima y se desvió). Publica una alerta con **esa misma causa**, `severity: medium`, que diga que el GPS ha vuelto y que el dron corrige hacia la ruta, con `supersedes` apuntando a la alerta anterior si sigue abierta.

## Paso 1. Métricas del tramo
Llama a `get_track_metrics(since = sim_time de la detección − 30, until = instante actual)`.

## Paso 2. ¿Coinciden GPS y radar?
- **Coinciden** si `gps_radar_distance_m.mean` < 15 y su `trend` no es `increasing`. Entonces el dron está de verdad donde dice el GPS: sigue al paso 3.
- **No coinciden**: carga la skill `source-discrepancy` y sigue esa.

## Paso 3. ¿Es viento?
Llama a `get_events(source="meteo", last_n=3)`. Mira el `sim_time` del último `WindReported` frente al instante actual: **si tiene más de 30 s, no puedes confirmar el viento** (la estación puede estar callada). Entonces la causa es `UNKNOWN`, o `WIND` con `confidence` ≤ 0,5 si la deriva es coherente con el último viento conocido; en cualquier caso, dilo en la explicación.
- Viento **fuerte** si `speed_mps` ≥ 8 o `gust_mps` ≥ 12.
- El viento empuja **hacia** `from_deg + 180` (mod 360). Ejemplo: `from_deg: 0` (viento del norte) empuja hacia 180 (sur).
- Compara esa dirección con `drift_direction_deg`. Si el viento es fuerte y la diferencia es ≤ 60°, la causa es **`WIND`**.
  - `severity: low` si la desviación máxima es < 80 m y no crece; `medium` si es mayor o sigue creciendo.
  - `confidence`: 0,8–0,9 si coinciden viento, dirección de deriva y GPS–radar.
  - Recomendación: sin intervención; vigilar que el dron recupera la ruta.
- Nota: con viento lateral es normal que el rumbo del dron (`heading_deg`) no coincida con su dirección de avance (`course_deg`). No es una anomalía.

## Paso 4. ¿Es un secuestro?
Si no hay viento fuerte o la deriva no va a favor del viento:
- Compara `course_deg` con `bearing_to_next_waypoint_deg`. Si difieren más de 45° y la desviación **crece**, el dron no va hacia su siguiente waypoint: se dirige a otro sitio.
- Llama a `get_events(source="link", last_n=6)`. Refuerza la hipótesis un cambio de `controller_id`, un salto de RSSI de más de 10 dB o una latencia anómala cerca del inicio de la desviación.
- Si se cumple lo primero, la causa es **`HIJACK`**, `severity: high`. `confidence` 0,8–0,9 si además hay pista en el enlace; 0,6–0,7 si no.
- Recomendación: avisar al responsable del dron y verificar el enlace de mando y quién lo controla. Tú no puedes actuar.

## Paso 5. Nada encaja
`cause: UNKNOWN`, `severity: medium`, `confidence` ≤ 0,4. Explica qué has comprobado y qué falta. Recomendación: revisión por el operador.

## Evidencias que citar
Los ids de `first_event_ids` y `last_event_ids` de `get_track_metrics`, el `WindReported` que hayas usado y, si aplica, el `LinkStatus` que cambió.
