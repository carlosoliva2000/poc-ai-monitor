---
name: source-discrepancy
description: Úsala cuando el detector lance SOURCE_DISCREPANCY (el GPS y el radar no coinciden), SOURCE_SILENT (una fuente deja de informar) o GPS_DEGRADED (el GPS informa sin fix, con pocos satélites o con hdop alto), o cuando al diagnosticar otra cosa veas que GPS y radar no coinciden. Distingue spoofing de GPS, pérdida o interferencia del GPS (jamming), fallo de sensor y fuente que deja de informar.
---
# Discrepancia GPS–radar, GPS degradado o fuente callada

`SOURCE_SILENT` → paso 5. `GPS_DEGRADED` → paso 4. `SOURCE_DISCREPANCY` → empieza en el paso 0. Los hechos vienen calculados en `get_track_metrics`: lee los campos `true`/`false`, no compares números tú.

Contexto: el radar no tiene sesgo (dice dónde está el dron de verdad); el dron navega con su GPS, así que si el GPS miente **se desvía de verdad** mientras el GPS parece perfecto. Un spoofing no degrada el fix (`3d`, ~14 satélites, `hdop` ~1); una pérdida del GPS sí (`fix: none`, `sats` 0, `hdop` 99,9).

## 0. ¿Ya hay una alerta del GPS abierta que lo explica?
Si hay una alerta `GPS_JAMMING` o `SENSOR_FAULT` del GPS abierta y la detección `GPS_DEGRADED` sigue abierta, esta discrepancia es consecuencia de la pérdida del GPS, no un problema nuevo.
- Alerta `SENSOR_FAULT`: publica `GPS_JAMMING`, `severity: high`, con `supersedes` apuntando a ella.
- Alerta ya `GPS_JAMMING`: `acknowledge_detection` con su `alert_id`.
Si no, sigue.

## 1. Métricas
Llama a `get_track_metrics` con `since` = sim_time de la detección − 40 y `until` = ahora. Si `radar_available` es `false`, no puedes comprobar el GPS: dilo.

## 2. ¿Spoofing o pérdida del GPS?
Condiciones del engaño: `gps_radar.disagreed` es `true`, el GPS está sobre el plan (`gps_deviation_from_plan_m.mean` < 15) y el radar fuera y alejándose.
**Antes de concluir spoofing**, llama a `get_events` con `source` = `gps` y `last_n` = 5: si hay `fix: none`, `sats: 0` o `hdop` 99,9 es una pérdida del GPS (paso 4); si el fix es normal, es spoofing.
- **`GPS_SPOOFING`**, `severity: high`, `confidence` 0,8–0,9. Recomendación: no fiarse del GPS, usar el radar como referencia y avisar al responsable.

## 3. ¿Fallo de sensor?
Discrepancia que aparece de golpe y desaparece sin patrón, radar con `quality` < 0,5, o GPS degradado sin discrepancia: **`SENSOR_FAULT`**, `severity: medium`, `confidence` 0,5–0,7; di qué sensor falla. Si nada encaja: `UNKNOWN`, `confidence` ≤ 0,4.
Si la discrepancia desaparece de golpe porque el GPS salta al radar, el engaño ha terminado: la desviación siguiente es real (paso 2 de `route-deviation`).

## 4. GPS degradado (`GPS_DEGRADED`)
Llama a `get_events` con `source` = `gps` y `last_n` = 5 (`fix`, `sats`, `hdop`) y a `get_track_metrics` con `since` = sim_time de la detección − 20.
- Fix/sats/hdop malos y `gps_radar.disagreed` `true`: **`GPS_JAMMING`**, `severity: high`, `confidence` 0,8–0,9 (el dron navega a estima y se desvía). Recomendación: no fiarse del GPS, radar como referencia.
- Solo degradado y `gps_radar.disagreed` `false`: **`SENSOR_FAULT`**, `severity: medium`, `confidence` 0,5–0,7.
- Si a la vez calla el radar, no se puede confirmar la desviación: baja `confidence` a 0,7 como mucho (el `fix: none` basta).
- Cuando se cierre `GPS_DEGRADED`, la posición salta a la real y es normal que salte `ROUTE_DEVIATION` (paso 2 de `route-deviation`).

## 5. Fuente callada (`SOURCE_SILENT`)
La detección trae `source` y `value` (segundos). **Siempre es un fallo distinto y lleva su propia alerta**, aunque haya otra abierta. Mira con `get_events` (`last_n` = 2) qué fuentes siguen: gps, radar y link.
- Solo calla el radar: fallo del radar; ya no se puede comprobar el GPS (dilo).
- Solo calla el GPS y el enlace sigue: fallo del receptor; la posición solo se conoce por el radar.
- Callan GPS y enlace: pérdida de comunicaciones con el dron.
- Calla meteo o batería: fallo menor (sin meteo no se confirma el viento).
**`SENSOR_FAULT`** (`UNKNOWN` si callan varias sin motivo claro), `severity: medium` (`high` si calla el GPS o el radar con otra detección abierta), `confidence` 0,7–0,9. `summary` dice qué fuente calla. Al cerrarse, `close_alert` con cuánto estuvo callada.

## Al publicar
Rellena `checks` con lo que has visto (se contrasta con las tools): `gps_alert_recent` (la línea «Alerta del GPS reciente» del estado: sí = `true`), `gps_radar_disagreed`, `wind_notable`, `wind_with_drift`, `link_checked` y `link_anomalous` (`null` si no miraste el enlace). Evidencias: ids de `first_event_ids`/`last_event_ids` y algún `PositionUpdated`.
