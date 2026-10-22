---
name: route-deviation
description: Úsala cuando el detector lance ROUTE_DEVIATION (la posición del GPS se aleja de la ruta planificada). Distingue viento, secuestro, recuperación tras un engaño o una pérdida del GPS y causa desconocida.
---
# Desviación de ruta

El GPS del dron está lejos de la ruta. Sigue los pasos **en orden** y para en el primero que encaje. Los hechos vienen calculados en `get_track_metrics`: **no compares números ni ángulos tú**, lee los campos `true`/`false`.

## 1. Métricas
Llama a `get_track_metrics` con `since` = sim_time de la detección − 30 y `until` = ahora.

## 2. ¿Recuperación del GPS tras un engaño o una pérdida? (manda sobre todo lo demás)
Es recuperación si **las dos**: la línea «Alerta del GPS reciente» del estado dice **sí** **y** `gps_radar.disagreed` es `true` o `gps_max_step_m` ≥ 30 (el GPS acaba de saltar a la posición real).
- **La única causa válida es la de esa alerta** (la línea del estado la dice: «Si este aviso es la recuperación del GPS: causa X, supersedes ai-XXXX»). `severity: medium`. Di que el GPS ha vuelto y el dron corrige hacia la ruta. `supersedes` = esa alerta si sigue abierta. No es viento ni secuestro aunque la desviación sea grande. Recomendación: verificar el receptor GPS.

## 3. ¿GPS y radar discrepan?
Si `gps_radar.disagreed` es `true` (y no es el paso 2), carga la skill `source-discrepancy`.

## 4. ¿Viento?
- Es **`WIND`** solo si `wind.notable` **y** `wind.with_drift` son `true`. `severity: low` si `gps_deviation_from_plan_m.max` < 80 y no crece; si no, `medium`. `confidence` 0,8–0,9. Evidencias: `wind.last_event_id` y `first_event_ids`/`last_event_ids`. Recomendación: sin intervención; vigilar que recupera la ruta.
- Si alguno es `false` (o `wind` es `null`), **no es viento: ve al paso 5.**

## 5. ¿Secuestro? Mira el enlace
Llama a `get_events` con `source` = `link` y `last_n` = 6. El enlace es anómalo si cambia el `controller_id` (p. ej. `UNK-4F2A` en vez de `GCS-1`), `rssi_dbm` varía más de 10 dB o `latency_ms` se multiplica.
- Enlace anómalo → **`HIJACK`**, `severity: high`, `confidence` 0,8–0,9. Evidencias: los `LinkStatus` que cambiaron.
- Enlace normal pero `course_deg` difiere más de 45° de `bearing_to_next_waypoint_deg` y la desviación crece → `HIJACK` con `confidence` 0,6–0,7 (solo si la línea «Alerta del GPS reciente» del estado dice **no**).
- Recomendación: avisar al responsable del dron y verificar el enlace de mando.

## 6. Nada encaja
`UNKNOWN`, `severity: medium`, `confidence` ≤ 0,4; di qué has comprobado.

## Al publicar
Rellena `checks` con lo que has visto (no inventes: se contrasta con las tools): `gps_alert_recent` (la línea «Alerta del GPS reciente» del estado: sí = `true`), `gps_radar_disagreed`, `wind_notable` y `wind_with_drift` (de `get_track_metrics`), `link_checked` y `link_anomalous` (`null` si no miraste el enlace).
