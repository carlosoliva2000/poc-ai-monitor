# E7a · Simulador v2

Informe de la fase, **actualizado paso a paso**. Referencia: especificación del núcleo v2 (v1.0, 18/11/2026) y las dos consultas del 18/11. Estado: **pasos 1 a 4 hechos (parada del paso 3+4 para revisar)**; pasos 5 a 7 pendientes.

## Decisiones de Carlos (18/11/2026)
1. `runs/` se regenera en el paso 1 solo por el contrato, con la prueba de la proyección.
2. Los caminos antiguos y los interruptores se borran **después** del commit de la parada del paso 7a, avisando antes (paso 7b).
3. Fuera `LinkStatus.controller_id`; el `mute` del enlace es enlace caído en los dos sentidos, con failsafe (**pasos 5 y 6**: en el paso 1 el enlace no cambia).
4. Acto 1 de `demo` con un viento por encima del límite del dron; parámetros del dron de un multirrotor real con fuente (⚠️ si no se comprueba).

## Paso 1 · Contrato v1.0, verdad ampliada y etiquetas por faceta

### Qué se cambió
- **Contrato v1.0** (parte del paso 1; el resto, en los pasos 2 a 6): fuera `WindReported.gust_mps` y `station_id`, `TrackUpdated.radar_id` y `quality`, `BatteryStatus.voltage_v`, la racha de los comandos del instructor, de `get_track_metrics` y de `propose_wind`, y `radar.id`, `meteo.id` y la racha del YAML; `PositionUpdated.heading_deg` → `course_deg` (rumbo sobre el suelo); `MissionPlanned.mission_controller_id`; plan que no cabe → `timeout` (no error). `contracts/eventos.md`, Pydantic, `contracts/schemas/` (64 esquemas, con `files/states_row.json`), `agent-assets/tools.json` y la web (`lib/contracts.ts`, formato, instructor) actualizados.
- **Ruido:** los campos quitados siguen gastando sus números aleatorios (se descartan) para que el resto del ruido salga igual.
- **Verdad ampliada** (`truth.json`, por segundo): `leg_index`, `ref_dist_m` (distancia al segmento pendiente), `est_x/est_y`, `mode`, `link_up`, `battery_soc`, `gps_sigma_m`, `cn0_dbhz`, `emitters_active` y `emitters`. **Con la física actual algunos son provisionales** (C/N0 constante, sin emisores, la estima es el GPS sin ruido, la pérdida de paquetes vale 0, el radar siempre en alcance, la batería lineal): cobran sentido en los pasos 3 a 6.
- **`states.jsonl`** (nuevo, `generator/states.py`): estado de cada faceta por segundo con las reglas de la consulta §3 (`n/a`, `?` con el estado real en `hidden`, calidad por valor físico, situación respecto a la referencia del modo con 25/15 m, causa con prioridad y pegajosa). Umbrales en el bloque `labeling` del YAML (⚠️ de partida). `drone.wind_limit_mps` (por defecto 12 ⚠️; el valor con fuente llega en el paso 2). `plot_scenario.py` dibuja `scenario_states.png`.
- **`unexplained`:** estado de aviso (desviado sin causa activa) que **no** es una etiqueta de la verdad; debe valer 0 en los escenarios.

### Prueba y resultado
- **Proyección v0.19 → v1.0** (script de un solo uso, comparando `runs/` de antes con lo generado ahora): en los **9 escenarios** coinciden los eventos (sin los campos quitados y con `course_deg`), la verdad (sin los campos nuevos), el plan, las etiquetas y la duración. `plan.json` y `labels.json` no cambian.
- `states.jsonl` de `demo`: `drone.situation` = en ruta 0–104 · desviado 105–147 · volviendo 148–150 · en ruta 151–181 · desviado 182–221 · volviendo 222–228 · en ruta 229–337 · desviado 338–379 · volviendo 380–435 · en ruta 436–556; `drone.cause` = viento 105–150 · posición engañada 182–228 · control ajeno 338–435. Secuestro: `link.availability` perdido y GPS/batería `?` (T+335–379). Coincide con la consulta.
- **`unexplained`:** 0 instantes en todos los escenarios salvo `spoofing` (7, T+229–235), que es el artefacto de las esquinas del guiado actual; desaparece con el guiado del paso 2.
- Tests: contratos 197 (+1 skip), plataforma 319 (con los nuevos de `test_states.py`), web 63, módulo de IA 447.

### Tests adaptados, borrados y nuevos
- **Adaptados** (solo quitar la racha / renombrar): `test_bus`, `test_viewer_state`, `test_instructor`, `test_disturbances`, `test_tools`, `test_api`, `test_simulator`, `test_controller` (parámetros del viento), `test_plots` (cuatro figuras), `test_determinism` (incluye `states.jsonl`), contratos (`test_commands`, `test_doc_examples`, `helpers`), `web/lib/instructor.test.ts`.
- **Borrado:** `test_radar_and_meteo_ids_must_match_the_envelope_source` (el campo ya no existe). El caso de `test_computed_facts_wind` que dependía de la racha ahora dice lo contrario: sin racha, la subida del viento aún no es «notable».
- **Nuevos** (`test_states.py`, 5 tests): catálogo completo en cada fila; la causa y la situación siguen las inyecciones de `demo`; el secuestro es enlace perdido y la telemetría `?`; con el GPS no disponible sus otras facetas son `n/a`; calidad del GPS por σ real (no por la ventana del episodio).

### Módulo de IA (congelado hasta la E7c)
24 ficheros de `ai-module-py/tests/` quedan **pendientes de la E7c** (lista y motivo en `ai-module-py/tests/conftest.py`: no se ejecutan, no se borran): 5 ya no se importan (`MAX_WIND_GUST_MPS`) y el resto falla con los payloads v0.19 o se cuelga esperando al bus (`test_bus_client`). Pasan 447. También quedan para la E7b/E7c las variantes de la E6 (`experiments/e6-variantes/grid.yaml` y `tools/experiments/*`, con YAML v0.19).

### Para el paso 2 (a destacar)
- Una vez con el guiado de multirrotor, `states` de `spoofing` debe dar 0 `unexplained`.
- `wind_limit_mps` y `max_airspeed_mps` se fijan con la ficha de un multirrotor real (pendiente de comprobar en la documentación del fabricante).

### Mensaje de commit propuesto (paso 1)
```
feat: E7a step 1 - contract v1.0, extended truth and per-facet states

Drop gust_mps, quality, radar_id, station_id and voltage_v, rename the GPS
heading_deg to course_deg, add mission_controller_id. The generator writes
the extended truth and states.jsonl (state of each facet per second). The AI
module tests that depend on the v0.19 payloads are marked pending for E7c.
```

## Paso 2 · Guiado de multirrotor (interruptor `simulator.multirotor_guidance`)

### Qué se cambió
- **Interruptor** `simulator.multirotor_guidance` (por defecto `false` = el guiado de hoy). Con él **apagado, `runs/` sale byte a byte igual** (`git status` limpio tras regenerar; test nuevo `test_the_committed_runs_are_what_the_scenarios_generate` para los 9 escenarios).
- **Valores del dron con fuente.** `max_airspeed_mps` = **17 m/s** (modo P del DJI Matrice 300 RTK; en modo S, 23 m/s), `wind_limit_mps` = **12 m/s** (resistencia al viento) y, desde la revisión del paso 2, giro del morro de **100 °/s** (yaw máximo de la ficha; la especificación decía 90 °/s: **hay que actualizarla**). Fuente, comprobada por Carlos el 19/11/2026: <https://www.dji.com/matrice-300/info>: sin ⚠️. Decisión de Carlos: `wind_limit` se queda en 12 (el de la ficha): entre 12 y 17 m/s el entorno está `beyond_limit` mientras el dron aguanta. El resto (aceleración 2 m/s², radio 5 m, punto de mira 40 m, `lateral_ki_per_s` 0,05) son los de la especificación o ⚠️.
- **Guiado** (`generator/controller.py` y `Simulator._advance_multirotor`):
  - punto de mira sobre el tramo (como hoy) para la dirección;
  - **perfil de velocidad**: `v = min(crucero, √(v_paso² + 2·a·(d − r/2)))`; `v_paso` = crucero · cos(giro), 0 con un giro ≥ 90° o en el último punto, y limitada para que el cambio de velocidad con la aceleración limitada no abra la esquina más de 6 m (⚠️ `CORNER_OPENING_M`);
  - **integral lateral** con tope (3 m/s) y solo con error < 15 m;
  - **lazo de velocidad**: la velocidad respecto al aire sigue a `v_suelo − viento` con la aceleración limitada y `|v_aire| ≤ max_airspeed`; si no cabe, se frena a lo largo del tramo antes que dejar de compensar, y si el viento supera `max_airspeed` el dron **deriva** a sotavento;
  - **radio de aceptación** del YAML (5 m) y **regla de la perpendicular**; morro hacia el siguiente punto con giro limitado; sin GPS no conoce el viento (deriva con él);
  - **modos** `mission`, `failsafe_hold` (lazo P al punto de espera) y `failsafe_return` (tramo recto a casa), con `Simulator.set_mode`; los dispararán el enlace y la batería (pasos 5 y 6). El secuestro lleva el dron al punto del secuestrador y se queda allí. La referencia de `ref_dist_m` sigue al modo.
- Comparación con PX4 y ArduPilot (ya en la consulta §7.3): lazo de velocidad con integral y perfil que frena al acercarse a cada punto, como los dos; radio entre el de PX4 (10 m) y el de ArduPilot (2 m); el viento se compensa en el lazo de velocidad, no con un término lateral aparte.

### Resultado (`tools/e7a_guidance_compare.py` → `experiments/e7a/guidance_compare.{png,md}`)
| Caso | Guiado | Duración (s) | Desviación máx. (m) | Segundos desviado | Sin causa (s) |
|---|---|---|---|---|---|
| nominal | hoy | 441 | 11,2 | 0 | 0 |
| nominal | multirrotor | 459 | 10,7 | 0 | 0 |
| wind (18 m/s) | hoy | 484 | 186,5 | 47 | 0 |
| wind (18 m/s) | multirrotor | 502 | 65,7 | 43 | 0 |
| demo (18 m/s en el acto 1) | hoy | 570 | 631,8 | 108 | 0 |
| demo (18 m/s en el acto 1) | multirrotor | 528 | 246,7 | 91 | 0 |

- **Duración:** +18 s en `nominal` (frena en las esquinas y llega a casa casi parado).
- **Esquinas:** < 11 m, sin falsas desviaciones. `spoofing` pasa de 7 s `unexplained` (artefacto de las esquinas) a 0.
- **Viento:** con 12 m/s (el del episodio de `demo` hoy) **no hay desviación** (máx. 9 m en el episodio); con 6 m/s de costado se queda a menos de 3 m de la línea (el guiado de hoy, 16 m). Con viento por encima de 17 m/s deriva: 17 → 27 m, 17,5 → 46 m, **18 → 66 m**, 19 → 105 m, 22 → 225 m. En el acto 1 de `demo` pondré **18 m/s** (≈ el desvío de unos 50 m de hoy; ⚠️ 18 m/s es mucho viento: es la forma de que supere la velocidad máxima del dron).
- `environment.wind` pasa a `beyond_limit` por encima de 12 m/s, pero el dron solo se desvía por encima de 17: entre 12 y 17 el entorno está «fuera de límites» y el dron aguanta (decisión de especificación: `wind_limit` es el viento máximo con el que mantiene la ruta; con la ficha de DJI es menor que la velocidad máxima respecto al aire). **A decidir contigo en la parada:** si prefieres que `wind_limit` y `max_airspeed` coincidan (17) o que el dron se desvíe a partir de 12.
- Con el interruptor encendido **no cambia ningún escenario** (siguen apagados: se encienden en el paso 7).

### Tests
- **Nuevos** (`test_guidance.py`, 7): mantiene la línea con viento lateral que puede compensar; deriva con viento por encima de su velocidad máxima; frena en las esquinas (< 15 m) y llega casi parado; límites de aceleración y de giro del morro (`nominal` y `demo`); `failsafe_hold` anula el viento (velocidad 0 y morro quieto); `failsafe_return` va recto a casa y completa. Más `test_the_committed_runs_are_what_the_scenarios_generate` (9 casos, interruptores como estén en el YAML).
- **Sin borrar** `test_controller` (guiado de hoy, interruptor apagado): sus tests de error estacionario con viento (L·tan(asin(w/v))) se borrarán en el paso 7b con el camino antiguo.
- Plataforma 335, contratos 197.

### Mensaje de commit propuesto (paso 2)
```
feat: E7a step 2 - multirotor guidance behind a switch

Velocity-controlled guidance with braking before each waypoint, lateral
integral, air-speed limit separate from cruise, 5 m acceptance radius with
the perpendicular rule and autopilot modes (mission, hold, return). Off by
default: runs/ is byte for byte the same.
```

## Pasos 3 y 4 · Estimador a bordo, receptor GNSS, radar y estación

Interruptores nuevos en `simulator`: `onboard_estimator` (necesita `multirotor_guidance` y `gps_receiver`), `gps_receiver`, `radar_geometry` y `ground_station`. Todos apagados por defecto: **`runs/` sale byte a byte igual** (comprobado: `git status` limpio tras regenerar y el test de `runs/` versionados). Cada fuente de ruido nueva usa su propio generador con semilla estable (`zlib.crc32`, `generator/receiver.py::stable_rng`: `gps_gm`, `gps_white`, `gps_hdop`, `gps_sats`, `gnss_receiver`); el del generador único sigue sacando (y descartando) los mismos números aleatorios, así que el resto del ruido no cambia.

### Qué se cambió
- **Estimador a bordo** (`receiver.Estimator`, filtro complementario a 1 Hz): predice con la velocidad respecto al aire más el viento estimado y se corrige con el GPS; la innovación mueve la posición (`α` = 0,6) y el viento (`k_w` = 0,5 m/s por m) ⚠️ (ver «Ajuste» abajo). **Sin GPS solo predice, con el último viento estimado** (decisión de la revisión). El guiado, la llegada a los puntos (radio 5 m y perpendicular) y el lazo de velocidad usan la estima y el viento estimado, no la verdad. `AutopilotStatus` (`apl-`, 1 s): modo, rumbo del morro, velocidad respecto al aire, viento estimado (m/s y procedencia) e innovación (`null` sin GPS).
- **Receptor GPS** (`receiver.GnssModel`, `gps_receiver`): ruido de posición con memoria (Gauss-Markov de primer orden, σ 1,5 m y τ 90 s ⚠️) más un ruido blanco pequeño (0,3 m ⚠️), σ proporcional al `hdop` efectivo; `sats` (±1) y `hdop` (±0,25) con variación lenta y acotada (AR(1) recortado, sin saltos) ⚠️. `GnssStatus` (`gns-`, 1 s): `h_acc_m` (la precisión que dice el receptor; con el engaño no cambia: el receptor no sabe que lo engañan), `cn0_dbhz` y `agc_db` (hoy constantes más ruido: dependerán de los emisores en el paso 5). Con el receptor, `speed_mps`/`course_deg` publicados son siempre del suelo (en pérdida, el de la estima: ya no cambian de significado).
- **Radar** (`radar_geometry`): `sensors.radar.x/y`, σ = `sigma_m` + `sigma_per_km_m` · distancia (2 m/km ⚠️) y `max_range_m` (6000 ⚠️): fuera de alcance no hay traza (`radar.availability: out_of_range`, el ruido se sigue gastando). `plan.json` lleva `radar` (posición y alcance) para pintarlo.
- **Estación en tierra** (`ground_station`): viento del dron × `factor` (0,8 ⚠️), media móvil de `lag_s` (30 s ⚠️), con su ruido de siempre.
- Contrato: eventos `GnssStatus` y `AutopilotStatus`, `AutopilotMode`, y la configuración (`eventos.md`, Pydantic, 66 esquemas).

### Ajuste del estimador (por qué `α` 0,6 y `k_w` 0,5)
Al acabar el episodio de viento (18 → 2 m/s) el viento estimado tarda en bajar y el dron **rebota al otro lado** de la ruta. Con `α` 0,4 y `k_w` 0,1 el rebote era de 43 m (y 4 s de `unexplained` en `spoofing`); con 0,6 y 0,5 es de **19 m** (por debajo de los 25 de «desviado») y `nominal` sigue en 9 m. Subir más empeora `nominal` (13 m con 0,8 y 1,2).

### Esquinas (revisión, punto 3): de dónde salen los 9–10,7 m
- **Causa:** al cambiar de tramo el guiado pide la velocidad de crucero por el tramo nuevo, y la velocidad respecto al aire cambia con la aceleración limitada (`T = |Δv| / a`, de 4 a 6 s). La velocidad perpendicular al tramo nuevo, `v_paso · sin(giro)`, se anula en ese tiempo y el dron se abre `v_paso · sin(giro) · T / 2`. Mi `CORNER_OPENING_M` de 6 m del paso 2 despreciaba que `Δv` es con el crucero y no con `v_paso`: la apertura real salía de 8,7 a 10,8 m.
- **Arreglo** (`controller.corner_opening`/`corner_speed`): la velocidad de paso es la mayor con la que la apertura estimada no pasa de 6 m (bisección; el factor del punto de mira, 0,9 · sin(giro), calibrado con el vuelo). Resultado sin ruido: **6,2 a 7,1 m** (antes 8,7 a 10,8); con todo el ruido del estimador, el máximo de `nominal` es **9,1 m** (< 15). Coste: la velocidad de paso baja a 2–3 m/s y `nominal` dura 460 s (antes 459).
- No lo bajo más: queda un margen de ~6 m para el ruido, sin alargar mucho el vuelo.

### Resultado (`tools/e7a_guidance_compare.py` → `experiments/e7a/`)
| Caso | Simulador | Duración (s) | Desviación máx. (m) | Segundos desviado |
|---|---|---|---|---|
| nominal | hoy | 441 | 11,2 | 0 |
| nominal | multirrotor (paso 2) | 461 | 7,1 | 0 |
| nominal | v2 completo | 460 | 9,1 | 0 |
| wind (18 m/s) | hoy | 484 | 186,5 | 47 |
| wind (18 m/s) | multirrotor (paso 2) | 504 | 59,7 | 42 |
| wind (18 m/s) | v2 completo | 505 | 77,0 | 45 |
| demo (18 m/s) | hoy | 570 | 631,8 | 108 |
| demo (18 m/s) | multirrotor (paso 2) | 528 | 223,3 | 90 |
| demo (18 m/s) | v2 completo | 525 | 155,2 | 92 |

**Desviación máxima por acto de `demo`** (revisión, punto 4; acto 1 con 18 m/s en las tres columnas; el «hoy» con 18 m/s es mucho peor que con los 12 m/s de la demo actual, 52 m):

| Simulador | Viento (T+95–168) | Engaño (T+168–335) | Secuestro (T+335–fin) |
|---|---|---|---|
| hoy | 186 m | 76 m | 632 m |
| multirrotor (paso 2) | 60 m | 83 m | 223 m |
| v2 completo (pasos 2-4) | 77 m | 76 m | 155 m |

El secuestro llega menos lejos con el simulador v2 porque el dron frena en las esquinas y el punto del secuestrador se alcanza en menos tiempo de secuestro desde otra posición; no es comparable uno a uno.

- **Estimador y engaño:** con `spoofing`, la innovación **no lo delata** (máx. 0,8 m) mientras el dron se va 82 m de la ruta; el viento estimado sube a 3,0 m/s (el real son 2): el estimador absorbe la deriva de 1,5 m/s como viento.
- **Sin GPS** (revisión, punto 2): con el viento constante la estima, con el último viento estimado, apenas deriva (**8 m** en 45 s de pérdida: **`faults` ya no da `dead_reckoning`**). Si el viento cambia durante la pérdida (14 m/s del norte), el dron se desvía 181 m y el estado es `dead_reckoning`. **Para el paso 7:** `faults` tiene que llevar un cambio de viento durante la pérdida de GPS.
- **Receptor:** `sats` 13–15 y `hdop` 0,55–0,88 en `nominal` (sin saltos); `h_acc_m` medio 1,9 m.

### Tests
- **Nuevos** (`test_receiver.py`, 7): la trayectoria depende del ruido pero no de si se publican eventos, y dos generaciones coinciden; el estimador aprende el viento sin sensor; el error del GPS tiene memoria y `sats`/`hdop` varían despacio; sin GPS la estima conserva el último viento (con viento constante no deriva, con un cambio sí y sale `dead_reckoning`); el estimador absorbe el engaño lento (innovación pequeña); el radar pierde precisión con la distancia y no llega más allá de su alcance (`out_of_range`); la estación mide una fracción del viento con retraso.
- Plataforma **342**, contratos **199**. Ninguno borrado.

### Pendientes de la revisión del paso 2
- **`failsafe_land`** (punto 1): se añade en el **paso 5**, junto con los failsafes del enlace y de la batería (el aterrizaje termina el vuelo con `MissionCompleted.reason: landed`).

### Mensaje de commit propuesto (pasos 3 y 4)
```
feat: E7a steps 3-4 - onboard estimator, GNSS receiver, radar and station

Behind four switches (all off: runs/ is byte for byte the same). A
complementary-filter estimator with an estimated wind (dead reckoning keeps
the last estimate), a GPS receiver with Gauss-Markov error, hdop-scaled
sigma and slow sats/hdop variation, a radar with position, range and
distance-dependent sigma, and a ground station with factor and lag. New
events GnssStatus and AutopilotStatus (contract v1.0). Corner speed now
keeps the corner opening under about 7 m.
```
