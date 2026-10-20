---
name: source-discrepancy
description: Úsala cuando el detector lance SOURCE_DISCREPANCY (el GPS y el radar no coinciden), SOURCE_SILENT (una fuente deja de informar) o GPS_DEGRADED (el GPS informa sin fix, con pocos satélites o con hdop alto), o cuando al diagnosticar otra cosa veas que GPS y radar no coinciden. Distingue spoofing de GPS, pérdida o interferencia del GPS (jamming), fallo de sensor y fuente que deja de informar.
---
# Diagnóstico de una discrepancia entre GPS y radar, o de una fuente que se calla

**Si la detección es `SOURCE_SILENT`, ve directamente al paso 6. Si es `GPS_DEGRADED`, ve directamente al paso 7.**

## Lo que hay que saber
- El **radar** es ruidoso (unos 5 m) pero **no tiene sesgo**: con varias muestras, dice dónde está el dron de verdad.
- El **dron navega con su GPS**. Si el GPS miente, el dron **cree** que va por la ruta y corrige hacia ella, así que **se desvía de verdad** mientras el GPS parece perfecto. Por eso un engaño del GPS (spoofing) no se ve mirando solo el GPS.
- Un spoofing bien hecho **no degrada** la calidad aparente del GPS (`hdop`, `sats`, `fix` normales: `3d`, unos 14 satélites, `hdop` ~1). Una **pérdida o interferencia** del GPS (jamming) sí: `fix: none`, `sats` 0 y `hdop` altísimo. Eso es lo que distingue una de otra.

## Paso 1. Métricas del tramo
Llama a `get_track_metrics(since = sim_time de la detección − 40, until = instante actual)` y mira:
- `gps_deviation_from_plan_m` (dónde dice el GPS que está, respecto al plan);
- `radar_deviation_from_plan_m` (dónde está de verdad, respecto al plan);
- `gps_radar_distance_m` (cuánto discrepan y si crece).

Si `get_track_metrics` devuelve `radar_available: false`, no puedes comprobar el GPS: dilo en la explicación.

## Paso 2. ¿Es spoofing de GPS?
Patrón típico:
- el GPS está **sobre el plan** (`gps_deviation_from_plan_m.mean` < 15);
- el radar está **fuera del plan** y alejándose (`radar_deviation_from_plan_m` creciente);
- la distancia GPS–radar **crece de forma suave y sostenida** (`trend: increasing`), no de golpe.

Comprueba con `get_events(source="gps", last_n=5)` que `hdop`, `sats` y `fix` son normales (eso descarta un fallo del receptor; si no lo son, es una pérdida de GPS: ve al paso 7) y con `get_events(source="meteo", last_n=2)` que el viento no explica nada (el viento movería a las dos fuentes por igual).

Si encaja: **`GPS_SPOOFING`**, `severity: high`, `confidence` 0,8–0,9 (0,6–0,7 si solo encaja en parte). Recomendación: no fiarse del GPS; usar el radar como referencia de posición; avisar al responsable del dron.

## Paso 3. ¿Es un fallo de sensor?
- **GPS degradado:** `hdop` alto (> 3), pocos satélites (< 6), `fix` distinto de `3d` (regla `GPS_DEGRADED`: paso 7), o huecos en los `PositionUpdated` (regla `SOURCE_SILENT`: paso 6).
- **Radar degradado:** `quality` < 0,5 o huecos en los `TrackUpdated`.
- Discrepancia que aparece **de golpe** y desaparece sin patrón.

Si encaja: **`SENSOR_FAULT`**, `severity: medium`, `confidence` 0,5–0,7. Di qué sensor parece fallar. Recomendación: verificar el sensor; usar la otra fuente mientras tanto.

## Paso 4. Fin de un engaño
Si la discrepancia **desaparece de golpe** porque el GPS salta hacia donde estaba el radar, el engaño ha terminado: la desviación que verás a continuación es real y el dron corregirá. No es una anomalía nueva. Trátalo como dice el paso 0 de la skill `route-deviation`.

## Paso 5. Nada encaja
`cause: UNKNOWN`, `severity: medium`, `confidence` ≤ 0,4, con lo que has comprobado.

## Paso 6. Una fuente ha dejado de informar (`SOURCE_SILENT`)
La detección trae `source` (la fuente callada) y `value` (segundos sin eventos).
1. Comprueba qué fuentes **siguen** informando: `get_events(source=…, last_n=2)` de `gps`, `radar` y `link` (mira el `sim_time` del último evento de cada una frente al instante actual).
2. Interpreta:
   - **Solo calla el radar:** fallo del radar o de su enlace con tierra. Consecuencia importante: **ya no se puede comprobar el GPS**, así que un spoofing pasaría desapercibido mientras dure. Dilo en la explicación.
   - **Solo calla el GPS y el enlace de mando sigue informando:** el dron sigue comunicándose, pero no reporta posición: fallo del receptor o del reporte de posición. La posición solo se conoce por el radar.
   - **Callan el GPS y el enlace a la vez:** pérdida de comunicaciones con el dron (no es un fallo de un sensor concreto). La posición solo se conoce por el radar.
   - **Calla la meteo o la batería:** fallo menor; solo afecta a lo que se puede diagnosticar (sin meteo no se puede confirmar que una desviación sea por viento).
3. Publica **`SENSOR_FAULT`** (o `UNKNOWN` si callan varias fuentes y no está claro por qué), `severity: medium` (`high` si calla el GPS o el radar mientras hay otra detección abierta), `confidence` 0,7–0,9 según lo claro que sea el patrón. En `summary` di qué fuente calla.
4. Recomendación: verificar la fuente; usar la otra como referencia de posición mientras tanto.
5. Cuando llegue el `DetectionCleared` de esa fuente, cierra la alerta indicando cuánto tiempo estuvo callada.

## Paso 7. El GPS informa con mala calidad (`GPS_DEGRADED`)
La detección dice que el último `PositionUpdated` trae `fix` distinto de `3d`, menos de 6 satélites o `hdop` > 3.
1. Mira `get_events(source="gps", last_n=5)`: `fix`, `sats` y `hdop`.
2. Llama a `get_track_metrics(since = sim_time de la detección − 20, until = instante actual)` y mira si `gps_radar_distance_m` **crece** (`trend: increasing`).
3. Interpreta:
   - **`fix`/`sats`/`hdop` malos y la distancia GPS–radar crece:** el dron ha perdido la señal del GPS y navega a estima (sin conocer el viento), así que **se desvía de verdad** mientras el GPS publica una posición estimada que parece seguir la ruta. Causa **`GPS_JAMMING`** (pérdida o interferencia del GPS), `severity: high`, `confidence` 0,8–0,9. Recomendación: no fiarse del GPS; usar el radar como referencia de posición; avisar al responsable del dron.
   - **Solo está degradado y la distancia GPS–radar sigue baja y estable (< 15 m):** el receptor va mal pero el dron aún no se desvía. Causa **`SENSOR_FAULT`**, `severity: medium`, `confidence` 0,5–0,7. Recomendación: verificar el receptor GPS; vigilar la posición con el radar.
   - **Es spoofing, no esto**, si `fix`, `sats` y `hdop` son normales: vuelve al paso 2.
4. **Si a la vez ha llegado un `SOURCE_SILENT` de otra fuente** (mira el estado y `get_my_alerts`), tenlo en cuenta: con el **radar callado** no puedes comprobar si el dron se desvía, así que la distancia GPS–radar no se puede evaluar; di que la desviación no se puede confirmar y baja la `confidence` (≤ 0,7), pero el `fix: none` ya basta para `GPS_JAMMING` o `SENSOR_FAULT`. Si callan también el enlace de mando y el GPS, piensa antes en una pérdida de comunicaciones con el dron.
5. Cuando llegue el `DetectionCleared` de `GPS_DEGRADED` (el GPS vuelve), cierra la alerta. La posición saltará a la real y es normal que a continuación salte `ROUTE_DEVIATION`: se trata con el paso 0 de la skill `route-deviation`.

## Evidencias que citar
Ids de `first_event_ids` y `last_event_ids` de `get_track_metrics` (GPS y radar), algún `PositionUpdated` con su `fix`, `sats` y `hdop` y, si lo usas, el `WindReported`.
