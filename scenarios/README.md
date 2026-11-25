# Escenarios

Cada YAML describe una misión completa y es **determinista** con su `seed`. Todos usan la misma ruta para que se puedan comparar; cambian las perturbaciones.

| Escenario | Qué tiene | Para qué |
|---|---|---|
| `nominal.yaml` | Viento flojo y ruido normal | Comprobar que **no salta nada** (cero falsas alarmas) |
| `wind.yaml` | Episodio de viento fuerte del norte en el tramo WP1→WP2 | Causa física: `WIND` |
| `spoofing.yaml` | Engaño del GPS en el tramo WP2→WP3 | `GPS_SPOOFING` (y su recuperación) |
| `hijack.yaml` | Cambio de destino no autorizado en el tramo WP4→BASE, con pista en el enlace; se recupera el control | `HIJACK` |
| `faults.yaml` | Nominal con fallos programados: radar silenciado (T+02:00 a T+03:00), pérdida de GPS de 45 s en el tramo WP3→WP4 (T+04:05 a T+04:50) y GPS silenciado (T+05:00 a T+05:12) | `SOURCE_SILENT` → `SENSOR_FAULT`; `GPS_DEGRADED` + `SOURCE_DISCREPANCY` → `GPS_JAMMING` (o `SENSOR_FAULT`), probado de forma automática (lo mismo que se hará a mano con el modo interactivo) |
| `nominal-wind-cmd.yaml` | `nominal` + un comando del instructor `set_wind` a T+01:35 (del norte, 12 m/s, rachas 16, 60 s, rampa 10 s: como el episodio de `demo`) | Repetir sin web ni LLM un viento puesto por el instructor: `WIND`, con su etiqueta |
| `demo.yaml` | Las tres anomalías en un mismo vuelo | La demo |
| `endurance.yaml` | Vuelo largo con viento a favor a la ida y de cara a la vuelta (10 m/s del oeste, 6 km, batería de 100 Wh): la estima de la energía para volver con el viento cae por debajo de lo que queda y el dron vuelve solo (`failsafe_return`, T+270), llega a 15 % → bajo, 7 % → crítico y aterriza al 5 % (`failsafe_land`, `reason: landed`) | Batería: `low` → `critical`, `cannot_reach_home`, failsafes por niveles |
| `jamming.yaml` | Un emisor de interferencia junto a los primeros tramos (T+110–270) que baja el C/N0 y el AGC según la distancia, degrada el GPS y le quita el fix 25 s (T+190–215) | C/N0 y AGC con un emisor; `gps.quality` y `gps.availability` |
| `demo-battery.yaml` | `demo` con la batería silenciada desde T+00:25 hasta el final (`faults`: `mute`, `end_s` 900, recortado al fin del vuelo) | Un fallo de sensor que sigue abierto mientras pasan las demás anomalías (un `SENSOR_FAULT` es de una sola fuente) |
| `demo-meteo.yaml` | `demo` con la estación meteorológica silenciada desde T+00:25 hasta el final (`faults`: `mute`, `end_s` 900, recortado al fin del vuelo) | Sin datos de viento no se puede confirmar `WIND` (el guardrail exige viento notable); el viento, el spoofing y el secuestro pasan con un `SENSOR_FAULT` de la estación abierto |

## Campos
- `seed`, `t0` (ISO UTC; `event_time = t0 + sim_time`), `max_duration_s` (si se alcanza, `MissionCompleted` con `completed: false, reason: timeout`).
- `drone`: velocidad de crucero, aceleración máxima, velocidad de giro máxima, altitud, radio de aceptación de waypoint y `lookahead_m` (distancia del punto de mira: el dron apunta a un punto situado `lookahead_m` por delante de su posición proyectada sobre el tramo pendiente).
- `mission`: `id`, `controller_id` (opcional, `GCS-1` por defecto: `MissionPlanned.mission_controller_id`), `waypoints` (la base `BASE` está en (0, 0) y se añade al principio y, con `return_to_base: true`, al final).
- `sensors`: periodo y ruido de cada fuente (ver `contracts/eventos.md`).
- `wind.base` (constante) y `wind.episodes` (con rampa de subida y bajada de `ramp_s`). `from_deg` es la **procedencia**. Sin racha desde el contrato v1.0.
- `drone.wind_limit_mps` (opcional, v1.0; por defecto 12 ⚠️): viento máximo con el que el dron mantiene la ruta; por encima, `environment.wind` vale `beyond_limit`.
- `drone.max_airspeed_mps` (opcional, v1.0; por defecto 17, modo P del DJI Matrice 300 RTK): velocidad máxima respecto al aire, separada de la de crucero: si el viento la supera, el dron deriva. `drone.lateral_ki_per_s` (0,05 ⚠️): ganancia integral del error lateral.
- **Guiado de multirrotor** (v1.0; no hay interruptores, es la única física). El dron controla su **velocidad sobre el suelo** (perfil de frenado según el giro del siguiente punto: 0 con un giro de 90° o más y en el último punto; frena hasta medio radio del punto), con el viento compensado por el lazo de velocidad (se limita la velocidad respecto al aire a `max_airspeed_mps`, frenando a lo largo del tramo antes que dejar de compensar), la integral lateral, el radio de aceptación del YAML (**5 m** en un multirrotor) más la **regla de la perpendicular**, el morro hacia el siguiente punto y el giro del morro limitado por `max_turn_rate_dps` (**100 °/s**, el yaw máximo del Matrice 300 RTK). Sin GPS (`loss`) el estimador a bordo solo predice, con el último viento estimado. Modos del autopiloto: `mission`, `failsafe_hold`, `failsafe_return` y `failsafe_land` (`Simulator.set_mode`; los disparan el enlace y la batería).
- **Estimador a bordo, receptor GPS, radar con posición y estación en tierra** (v1.0): el dron navega con su estima (GPS con ruido filtrado con la velocidad respecto al aire y el viento estimado), el **receptor GPS** tiene ruido con memoria (`sensors.gps.gm_sigma_m`/`gm_tau_s` más `white_sigma_m`, σ proporcional al `hdop`, `sats` y `hdop` con variación lenta; evento `GnssStatus`), el **radar** tiene posición (`sensors.radar.x/y`, `sigma_per_km_m`, `max_range_m`) y la **estación en tierra** mide el viento del dron por un factor y con retraso (`sensors.meteo.factor`, `lag_s`). Valores de partida ⚠️ salvo los del dron (ficha del Matrice 300 RTK).
- **Enlace con física, batería con consumo y emisores** (v1.0): **enlace** (RSSI = `rssi_dbm` a 1 km − 20·log10(d_km), pérdida de paquetes logística en el RSSI, la telemetría del dron solo llega si llega su paquete, `LinkStatus` medido por nuestra estación; el secuestro y el `mute` del enlace son enlace caído; failsafe tras `drone.link_loss_timeout_s` = 10 s con `drone.link_loss_action` = `continue` | `hold` | `return` | `land`), **batería** (`sensors.battery.capacity_wh`, `hover_power_w`, `efficiency`, reserva para volver, niveles de PX4: 15 % aviso, 7 % volver, 5 % aterrizar, o «no llega a casa») y **emisores** (`emitters`: interferencia con posición y ventana; `spoofing.emitter`: posición del emisor de engaño; el C/N0 y el AGC del receptor salen de la distancia). Aterrizar (`failsafe_land`) mantiene la posición `drone.land_duration_s` (20 s ⚠️) y termina el vuelo con `MissionCompleted` `completed: false`, `reason: landed`.
- `labeling` (opcional, v1.0): umbrales operativos de las etiquetas por faceta (`states.jsonl`): viento notable, σ del GPS y latencia o pérdida del enlace para «degradada», 25/15 m de la situación del dron y niveles de la batería. Valores de partida ⚠️ en `contracts/eventos.md` §8.7.
- `commands` (lista, opcional; v0.18): comandos del instructor programados, `{at_s, command, params}` con `command` = `set_wind` | `cancel_wind` y `params` = `{from_deg, speed_mps, gust_mps, ramp_s, duration_s}` (`null` en `cancel_wind`). Un `set_wind` es un episodio de viento que **sustituye** al que haya (con su rampa); `duration_s: null` dura hasta un `cancel_wind` (que baja con la rampa) o el fin del vuelo. Publica `InstructorCommand` con `issued_by: scenario` y genera su etiqueta de viento (ventana: del comando a su fin).
- `spoofing` (o `null`): desde `start_s` hasta `end_s`, el GPS reportado = real + desfase que crece a `drift_rate_mps` en la dirección `direction_deg`. En `end_s` el desfase vuelve a cero de golpe.
- `faults` (lista, puede estar vacía): `{source, mode, start_s, end_s}` con `source` = `gps` | `radar` | `meteo` | `link` | `battery` y `mode` = `mute` | `loss`. Con `mute` la fuente deja de publicarse en la ventana (el dron vuela igual). `loss` solo existe para el GPS: el dron navega a estima (su estimador solo predice, con el último viento estimado), el GPS publica `fix: none`, `sats: 0` y `hdop` alto y **sin posición, altitud, velocidad ni rumbo** (`null`; la estima va en `AutopilotStatus`), y la trayectoria real se va desviando si el viento cambia; al terminar, el estimador vuelve a corregir con el GPS. Cada fallo publica `FaultInjected`/`FaultCleared` (`origin: scenario`). Los fallos manuales (modo interactivo) hacen lo mismo, pero los activa el usuario en directo.
- `hijack` (o `null`): desde `start_s`, el objetivo del controlador pasa a `target`; en `end_s` (o nunca, si es `null`) se recupera el control y el dron vuelve a seguir el tramo pendiente (se reincorpora a la ruta). `target` es la posición de la estación del secuestrador; durante el secuestro nuestro enlace está caído y la telemetría del dron no llega.
- `sensors.gps.episodes` y `sensors.link.episodes` (listas, opcionales): episodios de degradación de una fuente; ver el apartado siguiente.

## Episodios de degradación del GPS y del enlace
Una fuente puede degradarse durante una ventana sin fallar del todo: el GPS sigue con fix 3D pero con menos satélites o peor `hdop`, y el enlace sigue con el mismo controlador pero con más latencia o menos señal. Se escriben dentro del bloque de la fuente:
```yaml
sensors:
  gps:
    period_s: 1.0
    sigma_m: 1.5
    sats: 14
    hdop: 0.8
    episodes:
      - {start_s: 150.0, end_s: 210.0, ramp_s: 10.0, sats: 4, hdop: 9.0}
      - {start_s: 250.0, end_s: 300.0, ramp_s: 20.0, sats: 11, hdop: 1.4, labeled: false}
  link:
    period_s: 5.0
    controller_id: GCS-1
    rssi_dbm: -62.0
    latency_ms: 45.0
    episodes:
      - {start_s: 330.0, end_s: 390.0, latency_ms: 250.0, rssi_dbm: -85.0}
```
Escenario completo de ejemplo: `platform/tests/data/degradations-example.yaml` (el `nominal` con estos tres episodios).

- **Ventana y rampa:** `start_s` y `end_s` en segundos de simulación (`end_s` > `start_s`); `ramp_s` (s, por defecto 0) es la rampa de subida y de bajada, como en los episodios de viento: el valor publicado va del nominal al objetivo en `ramp_s` segundos desde `start_s` y vuelve al nominal en los últimos `ramp_s` segundos antes de `end_s` (con 0 cambia de golpe; si la ventana es más corta que dos rampas, no llega al objetivo). Un episodio que empieza después del fin del vuelo no cuenta; uno que acaba después se recorta al fin del vuelo. Dos episodios de la misma fuente no se pueden solapar.
- **GPS:** `sats` (número de satélites, entero, al menos 4) y `hdop` (adimensional, mayor que 0), al menos uno de los dos; lo que no se dé se queda en el valor nominal del bloque `gps`. Con la rampa, `sats` se redondea a entero. El `fix` sigue en `3d` y la posición no cambia (ni su ruido). Una pérdida total del fix no es un episodio: es el fallo `loss`, y si coincide con un episodio manda la pérdida.
- **Enlace:** `latency_ms` (ms, ≥ 0) y `rssi_dbm` (dBm), al menos uno; lo que no se dé se queda en el nominal del bloque `link`. El ruido de siempre se suma encima. Un secuestro (`hijack`) es enlace caído y manda sobre el episodio.
- **Determinismo:** un episodio no gasta números aleatorios (solo cambia el valor sobre el que se publica la medida), así que todo lo demás sale igual que sin él y un escenario sin episodios genera exactamente lo mismo que antes.
- **`labeled`** (por defecto `true`): quien escribe el escenario decide, **por la intención**, si el episodio es una degradación que el monitor debe diagnosticar (`true`) o el ruido normal de un vuelo (`false`), sin pensar en si llegará a hacer saltar alguna regla del detector.
  - Con `labeled: true` el episodio tiene etiqueta en `labels.json`, numerada `F1`, `F2`… junto con los fallos programados, por orden de inicio: `gps_degraded` (`source: gps`, `expected_rules: ["GPS_DEGRADED"]`, `expected_cause: SENSOR_FAULT`, también vale `GPS_JAMMING`) o `link_degraded` (`source: link`, `expected_rules: ["LINK_ANOMALY"]`, `expected_cause: SENSOR_FAULT`, también vale `UNKNOWN`; `HIJACK` es un fallo). No hay frontera por magnitud: una degradación fuerte del GPS no deja de aceptar `SENSOR_FAULT`, y fallar es atribuirla a un engaño, al viento o a un secuestro. Ventana de evaluación: de `start_s` a `end_s + 60`. La etiqueta termina donde empieza lo que anula el episodio (una pérdida de GPS o el secuestro); si eso ya está activo al empezar, empieza cuando termina, y si lo cubre entero, no hay etiqueta.
  - Con `labeled: false` no hay etiqueta: el episodio va a `unlabeled_episodes.json` (`U1`, `U2`…, con su fuente, su ventana y las reglas que miden esa fuente). En la evaluación, los avisos de esas reglas dentro de la ventana son informativos (no son falsas alarmas); una alerta con causa de ataque (`GPS_SPOOFING`, `GPS_JAMMING`, `HIJACK`) o `WIND` sí es una falsa alarma; `SENSOR_FAULT` o `UNKNOWN`, no.

## Salida del generador (`runs/<escenario>/`)
- `plan.json`: waypoints y trayectoria planificada (vuelo sin perturbaciones; `t, x, y, speed_mps, heading_deg` cada segundo).
- `truth.json`: trayectoria real (`t, x, y, speed_mps, heading_deg, course_deg` cada segundo) con la **verdad ampliada** de la v1.0 (tramo pendiente, distancia a la referencia del modo, estima, modo, enlace, carga, σ real del GPS, C/N0 y emisores) y el viento real. **El agente no la ve.**
- `states.jsonl` (v1.0): el estado de cada faceta por segundo (`gps.availability`… `drone.cause`), con `n/a` y `?` explícitos; `scenario_states.png` lo dibuja. Solo para el generador, la evaluación y la vista del instructor.
- `events.jsonl`: eventos a publicar, ordenados por `sim_time` (sin `seq` ni `ingestion_time`).
- `labels.json`: una entrada por anomalía, generada a partir del YAML:
```json
{ "id": "A1", "type": "wind", "source": null, "start_s": 95.0, "end_s": 150.0,
  "expected_rules": ["ROUTE_DEVIATION"], "expected_cause": "WIND", "also_accepted_causes": [],
  "eval_window": [95.0, 210.0] }
```
`eval_window` = de `start_s` a `end_s + 60`: una alerta con la causa esperada dentro de esa ventana cuenta como acierto. Para el spoofing también vale la alerta de recuperación (`GPS_SPOOFING`) tras `end_s`. Para cada fallo programado (`F1`, `F2`… por orden de inicio; la ventana es `[start_s, end_s)`): `{"id": "F1", "type": "source_silent", "source": "radar", "start_s": 120.0, "end_s": 180.0, "expected_rules": ["SOURCE_SILENT"], "expected_cause": "SENSOR_FAULT", "also_accepted_causes": [], "eval_window": [120.0, 240.0]}`. Una pérdida de GPS (`type: gps_loss`) espera `["GPS_DEGRADED", "SOURCE_DISCREPANCY", "ROUTE_DEVIATION"]` y la causa `GPS_JAMMING` (también vale `SENSOR_FAULT`, en `also_accepted_causes`); el `ROUTE_DEVIATION` es el de la recuperación, cuando el GPS salta a la posición real.
- `unlabeled_episodes.json`: solo si el escenario tiene episodios de degradación con `labeled: false` (ver arriba). Como `labels.json`, solo lo usa la evaluación.
- `plan_xy.png`, `scenario_xy.png`, `scenario_time.png` y `scenario_states.png` (con `plot_scenario.py`).

## Criterios de aceptación del generador (simulador v2)
Los mide `platform_app.scenario_metrics` (y `test_acceptance.py`) sobre `runs/`. Entre paréntesis, lo medido hoy.
- `nominal`: desviación de la verdad y del GPS respecto al plan < 15 m, esquinas incluidas, con todo el ruido del estimador (9,1 m); distancia GPS–radar dentro del ruido (< 30 m en media móvil de 3: el radar tiene σ ≈ 10 m a 2,5 km); `states.jsonl` sin un solo segundo `unexplained`.
- `wind` (18 m/s, por encima de los 17 m/s de velocidad máxima respecto al aire): el dron no puede compensarlo y deriva; desviación máxima de la verdad en el episodio + 30 s entre 40 y 120 m (77 m); GPS y radar coinciden; recupera la ruta. `environment.wind` es `beyond_limit` por encima de 12 m/s.
- `spoofing`: el GPS se mantiene a < 20 m del plan mientras dura el engaño (el dron navega con su estima, que absorbe la deriva: innovación < 1 m); la verdad se aleja entre 50 y 100 m (80 m); el radar ve lo mismo que la verdad; al acabar, el GPS salta (> 40 m) y el dron corrige. El C/N0 sube y el AGC baja con el emisor de engaño.
- `hijack`: **nuestra estación pierde el enlace** durante el secuestro: no llega ni `PositionUpdated`, ni `GnssStatus`, ni `AutopilotStatus`, ni `BatteryStatus`, y `LinkStatus` dice 100 % de pérdida (sin controlador); el radar sigue y ve cómo el dron se aleja (> 100 m; 146 m en `demo`); tras recuperar el control se reincorpora a la ruta y la misión se completa. No salta nuestro failsafe.
- `faults`: trayectoria idéntica a `nominal` hasta T+245 s (la pérdida de GPS empieza ahí) y eventos de las fuentes idénticos salvo los silenciados. Sin eventos de radar entre 120 y 180 s ni de GPS entre 300 y 312 s. Pérdida de GPS (245–290): `fix: none`, `sats: 0`, `hdop` alto y **posición, altitud, velocidad y rumbo `null`**; la estima (`AutopilotStatus`) sigue a < 25 m del plan; el viento cambia a T+250 (12 m/s del norte), la estima no lo sabe y la verdad se desvía (112 m, `dead_reckoning`); el radar lo ve; al volver, el GPS está lejos de la estima (> 40 m). El viento coincide con la pérdida: no es una anomalía de viento aparte en la comprobación.
- `demo-battery` y `demo-meteo`: los mismos eventos que `demo` salvo los de la batería o la estación desde T+25 s, con `FaultInjected`/`FaultCleared` y la etiqueta `F1`. **Con el simulador v2 el vuelo depende del ruido del estimador, pero un `mute` no cambia la trayectoria**: la batería callada no cambia nada de lo que se publica, y la estación callada tampoco.
- `nominal-wind-cmd`: lo mismo que `nominal` hasta T+95 s y, desde el comando (18 m/s del norte), el dron deriva; la etiqueta `A1` es de viento (T+95 a T+155). El comando no gasta números aleatorios.
- `demo`: las tres anomalías se ven separadas en el tiempo, en el orden viento → engaño → secuestro. Viento: el dron se desvía (77 m) y recupera; engaño: sale `spoofed_position`; secuestro: enlace perdido, telemetría con hueco y `control ajeno` hasta que vuelve a la ruta. `drone.cause` nunca vale `unexplained`.
- `endurance`: el dron vuelve por su cuenta (T+231, `failsafe_return`) y llega a casa con el 14,7 % de carga; `battery.endurance` pasa a `cannot_reach_home` a T+223.
- `jamming`: C/N0 y AGC caen con la distancia al emisor (mínimo de 21,7 dB-Hz a 187 m); el GPS se degrada (σ real 5,7 m) y pierde el fix 25 s.
Si con estos parámetros no se cumple algún criterio, ajusta los parámetros del YAML, no la física.
