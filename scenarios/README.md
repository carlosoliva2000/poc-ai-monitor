# Escenarios

Cada YAML describe una misión completa y es **determinista** con su `seed`. Todos usan la misma ruta para que se puedan comparar; cambian las perturbaciones.

| Escenario | Qué tiene | Para qué |
|---|---|---|
| `nominal.yaml` | Viento flojo y ruido normal | Comprobar que **no salta nada** (cero falsas alarmas) |
| `wind.yaml` | Episodio de viento fuerte del norte en el tramo WP1→WP2 | Causa física: `WIND` |
| `spoofing.yaml` | Engaño del GPS en el tramo WP2→WP3 | `GPS_SPOOFING` (y su recuperación) |
| `hijack.yaml` | Cambio de destino no autorizado en el tramo WP4→BASE, con pista en el enlace; se recupera el control | `HIJACK` |
| `faults.yaml` | Nominal con fallos programados: radar silenciado (T+02:00 a T+03:00), pérdida de GPS de 45 s en el tramo WP3→WP4 (T+04:05 a T+04:50) y GPS silenciado (T+05:00 a T+05:12) | `SOURCE_SILENT` → `SENSOR_FAULT`; `GPS_DEGRADED` + `SOURCE_DISCREPANCY` → `GPS_JAMMING` (o `SENSOR_FAULT`), probado de forma automática (lo mismo que se hará a mano con el modo interactivo) |
| `demo.yaml` | Las tres anomalías en un mismo vuelo | La demo |

## Campos
- `seed`, `t0` (ISO UTC; `event_time = t0 + sim_time`), `max_duration_s` (si se alcanza, `MissionCompleted` con `completed: false, reason: timeout`).
- `drone`: velocidad de crucero, aceleración máxima, velocidad de giro máxima, altitud, radio de aceptación de waypoint y `lookahead_m` (distancia del punto de mira: el dron apunta a un punto situado `lookahead_m` por delante de su posición proyectada sobre el tramo pendiente).
- `mission`: `id`, `waypoints` (la base `BASE` está en (0, 0) y se añade al principio y, con `return_to_base: true`, al final).
- `sensors`: periodo y ruido de cada fuente (ver `contracts/eventos.md`).
- `wind.base` (constante) y `wind.episodes` (con rampa de subida y bajada de `ramp_s`). `from_deg` es la **procedencia**.
- `spoofing` (o `null`): desde `start_s` hasta `end_s`, el GPS reportado = real + desfase que crece a `drift_rate_mps` en la dirección `direction_deg`. En `end_s` el desfase vuelve a cero de golpe.
- `faults` (lista, puede estar vacía): `{source, mode, start_s, end_s}` con `source` = `gps` | `radar` | `meteo` | `link` | `battery` y `mode` = `mute` | `loss`. Con `mute` la fuente deja de publicarse en la ventana (el dron vuela igual). `loss` solo existe para el GPS: el dron navega a estima (integra su velocidad respecto al aire, sin conocer el viento), el GPS publica la posición estimada con `fix: none`, `sats: 0` y `hdop` alto, y la trayectoria real se va desviando; al terminar, la posición salta a la real. Cada fallo publica `FaultInjected`/`FaultCleared` (`origin: scenario`). Los fallos manuales (modo interactivo) hacen lo mismo, pero los activa el usuario en directo.
- `hijack` (o `null`): desde `start_s`, el objetivo del controlador pasa a `target`; en `end_s` (o nunca, si es `null`) se recupera el control y el dron vuelve a seguir el tramo pendiente (se reincorpora a la ruta). `link_hint` cambia el `LinkStatus` durante el secuestro.

## Salida del generador (`runs/<escenario>/`)
- `plan.json`: waypoints y trayectoria planificada (vuelo sin perturbaciones; `t, x, y, speed_mps, heading_deg` cada segundo).
- `truth.json`: trayectoria real (`t, x, y, speed_mps, heading_deg, course_deg` cada segundo) y viento real. **El agente no la ve.**
- `events.jsonl`: eventos a publicar, ordenados por `sim_time` (sin `seq` ni `ingestion_time`).
- `labels.json`: una entrada por anomalía, generada a partir del YAML:
```json
{ "id": "A1", "type": "wind", "source": null, "start_s": 95.0, "end_s": 150.0,
  "expected_rules": ["ROUTE_DEVIATION"], "expected_cause": "WIND", "also_accepted_causes": [],
  "eval_window": [95.0, 210.0] }
```
`eval_window` = de `start_s` a `end_s + 60`: una alerta con la causa esperada dentro de esa ventana cuenta como acierto. Para el spoofing también vale la alerta de recuperación (`GPS_SPOOFING`) tras `end_s`. Para cada fallo programado (`F1`, `F2`… por orden de inicio; la ventana es `[start_s, end_s)`): `{"id": "F1", "type": "source_silent", "source": "radar", "start_s": 120.0, "end_s": 180.0, "expected_rules": ["SOURCE_SILENT"], "expected_cause": "SENSOR_FAULT", "also_accepted_causes": [], "eval_window": [120.0, 240.0]}`. Una pérdida de GPS (`type: gps_loss`) espera `["GPS_DEGRADED", "SOURCE_DISCREPANCY", "ROUTE_DEVIATION"]` y la causa `GPS_JAMMING` (también vale `SENSOR_FAULT`, en `also_accepted_causes`); el `ROUTE_DEVIATION` es el de la recuperación, cuando el GPS salta a la posición real.
- `plan_xy.png`, `scenario_xy.png`, `scenario_time.png` (con `plot_scenario.py`).

## Criterios de aceptación del generador
Entre paréntesis, los valores de referencia de una simulación de la misma física sin sensores ni ruido.
- `nominal`: desviación de la verdad y del GPS respecto al plan < 15 m en todo el vuelo, esquinas incluidas (≈ 13 m); distancia GPS–radar dentro del ruido.
- `wind`: desviación máxima entre 40 y 120 m durante el episodio (≈ 52 m); GPS y radar coinciden; el dron recupera la ruta.
- `spoofing`: el GPS se mantiene a < 15 m del plan mientras dura el engaño (< 10 m); la verdad (y el radar) se alejan hasta unos 70–90 m (≈ 75 m); al final del engaño el GPS salta y el dron corrige.
- `hijack`: la verdad y el GPS se alejan cientos de metros hacia el `target` (≈ 700 m); `LinkStatus` cambia durante el secuestro; tras recuperar el control se reincorpora a la ruta, vuelve a la base y la misión se completa.
- `faults`: trayectoria idéntica a `nominal` hasta T+245 s, y eventos de las fuentes idénticos a los de `nominal` salvo los silenciados y los del GPS durante la pérdida (a partir de ella cambia el GPS y la trayectoria). En `events.jsonl` no hay `TrackUpdated` entre 120 y 180 s ni `PositionUpdated` entre 300 y 312 s, y están los `FaultInjected`/`FaultCleared` correspondientes. Durante la pérdida (245–290 s) el `PositionUpdated` lleva `fix: none`, `sats: 0` y `hdop` alto; la verdad se desvía más de 40 m de la ruta mientras el GPS (la estima) sigue a menos de 15 m, y el radar ve la desviación real.
- `demo`: las tres anomalías se ven separadas en el tiempo, en el orden wind → spoofing → hijack.
Si con estos parámetros no se cumple algún criterio, ajusta los parámetros del YAML, no la física.
