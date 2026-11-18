# E7a · Simulador v2

Informe de la fase, **actualizado paso a paso**. Referencia: especificación del núcleo v2 (v1.0, 18/11/2026) y las dos consultas del 18/11. Estado: **paso 1 hecho (parada para revisar)**; pasos 2 a 7 pendientes.

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
