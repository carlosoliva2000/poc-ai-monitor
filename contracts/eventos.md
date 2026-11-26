# Contratos de `poc-ai-monitor`

> **Fuente de verdad** de lo que se intercambian los componentes: eventos, topics, mensajes del WebSocket y API HTTP. Versión 1.5 (26/11/2026, **aditiva y sin cambios en el bus**; la D1a, API del simulador): el simulador expone, además del `/ws` y los `GET /api/*` de hoy, una **API REST versionada `/api/v1`** con endpoints por asset (`d1`, `radar-1`, `meteo-1`, `gcs-1`) en su propio formato, flujo SSE con `Last-Event-ID`, control del ejercicio e *injects* del instructor (la verdad solo por `/api/v1/instructor/*`); se documenta en `contracts/api/README.md` y su OpenAPI (`contracts/api/sim-api-v1.json`, modelos en `poc_contracts.sim_api`). Los eventos, topics y mensajes del WebSocket no cambian; una orden de `control` sin escenario cargado (menos `load` e `interactive`) da siempre `error` «no scenario is loaded». Versión 1.4 (26/11/2026, **aditiva**; la E7d, asistente LLM): `IncidentHypothesis.ranked` y `.checks` (hipótesis estructurada: causas ordenadas con lo que las apoya y lo que falta, y qué comprobar con una fuente de lista cerrada), `IncidentEnriched.model` y `.prompt_sha`, evento **`ExerciseInjects`** (dominio `sim`, `sim.instructor`: lo programado en el ejercicio, tomado de `labels.json`; solo lo recibe el proceso del instructor, nunca el del alumno), evento **`DebriefGenerated`** (`ai.instructor`, fuente `ai-debrief`: el debriefing con la verdad) tres nombres de agente (`assistant`, `translator`, `debrief`) y la **etiqueta de proceso en los ids** de `ai-`, `act-` y `chk-` (`ai-a-0001`; `ai-0001` sigue valiendo). Versión 1.3 (25/11/2026, **cambio que rompe**; la E7c): `IncidentKind` pasa a un catálogo de 15 tipos (`LINK_DEGRADED`, `GPS_NO_FIX`, `SOURCE_SILENT`, `RADAR_OUT_OF_RANGE`, `BATTERY_LOW`, `BATTERY_CRITICAL`, `CANNOT_REACH_HOME`, `FAILSAFE`; **fuera `BATTERY`**, que nadie publicaba) e `IncidentUpdated.subject` (opcional: la fuente o el modo); se quitan la API de tools (`POST /api/tools/{name}`, §7 y `contracts/python/.../tools.py`, con sus esquemas `tools/*` y `api/tool_*`), «esperar al agente» (`control` → `wait_agent`, `wait_agent` en `state` y en `run_meta.json`, `SimulationPaused.reason: waiting_agent`) y el uso de `reason: waiting_agent` por el reproductor: el monitor de situación lee solo del bus y nadie publica ya `Detection*`. Los eventos del módulo anterior (detecciones, alertas, `AgentToolCall`) **siguen en el contrato** sin publicador (se quitarán con la D1). Versión 1.2 (25/11/2026, aditiva salvo un renombrado en `labeling`): `sensors.gps.cn0_nominal_dbhz` (45,0) y `agc_nominal_db` (0,0), el C/N0 y el AGC de un receptor sano, que eran constantes del simulador (con los valores por defecto `runs/` sale idéntico); y `labeling.wind_notable_over_limit` (0,4) en lugar de `labeling.wind_notable_mps` (5,0): el viento «notable» es una fracción de `drone.wind_limit_mps` (4,8 m/s con el Matrice 300; los estados de los once escenarios no cambian). Versión 1.1 (19/11/2026, aditiva: **incidentes**: eventos `IncidentUpdated` (fuente `ai-monitor`; el monitor de situación publica un evento por transición de cada incidente: abierto, en recuperación, cerrado, cambio de nombre o de severidad) e `IncidentEnriched` (fuente `ai-enricher`; el texto del asistente sobre una revisión de un incidente, que no lo cambia); los eventos de alertas siguen para el módulo anterior). Versión 1.0 (E7a, simulador v2, cerrada el 25/11/2026; **cambio que rompe, el primero**): fuera `WindReported.gust_mps` y `station_id`, `TrackUpdated.radar_id` y `quality`, `BatteryStatus.voltage_v`, la racha de los comandos del instructor, de `get_track_metrics` (`wind.max_gust_mps`, `now.wind_gust_mps`; `notable` = velocidad media ≥ 5 m/s) y de `propose_wind`, y `radar.id`, `meteo.id` y la racha del YAML; `PositionUpdated.heading_deg` → `course_deg` (rumbo **sobre el suelo**) y, sin fix, el GPS no da posición, altitud, velocidad ni rumbo (`null`; la estima va en `AutopilotStatus`); eventos nuevos `GnssStatus` y `AutopilotStatus`; `LinkStatus` lo mide nuestra estación (sin `controller_id`, con `packet_loss_pct`; `null` en `rssi_dbm` y `latency_ms` con el enlace caído; el secuestro y el `mute` del enlace son enlace caído en los dos sentidos, con failsafe); `BatteryStatus` con potencia y tiempo restante, y `failsafe_land`; `MissionPlanned.mission_controller_id` (de `mission.controller_id` del YAML, `GCS-1` por defecto); un plan que no cabe en `max_duration_s` termina por `timeout`, no da error; verdad ampliada en `truth.json` y fichero nuevo `states.jsonl` con el estado de cada faceta por segundo (§8.3 y §8.7); en el YAML, `drone.wind_limit_mps`, `max_airspeed_mps` y `lateral_ki_per_s`, el estimador y el failsafe, los parámetros del receptor, el radar con posición, la estación en tierra, el enlace con física, la batería con consumo, los emisores y el bloque `labeling`. **La física del simulador v2 es la única** (estimador a bordo, receptor GNSS, radar y estación con geometría, enlace con física y batería con consumo): no hay interruptores en el YAML. Se quitan `hijack.link_hint`, `sensors.link.controller_id` y `sensors.battery.drain_pct_per_min`. Versión 0.19 (17/11/2026, aditiva: **quién decide la alerta**: `AnomalyDetected` lleva `decided_by` (`table` | `llm`, opcional; sin él, el LLM) y `rule_id` (la fila de la tabla de decisión, opcional), para el monitor con `monitor.engine: table` o `hybrid`, la tabla de decisión del módulo de IA; con el LLM las alertas no cambian; **episodios de degradación** del GPS y del enlace en el YAML del escenario (`sensors.gps.episodes` y `sensors.link.episodes`, opcionales), sus etiquetas `gps_degraded` y `link_degraded` y el fichero `unlabeled_episodes.json` para los episodios sin etiqueta (§8.1 y §8.4); un escenario sin episodios genera exactamente lo mismo que antes; evento **`AlertEnriched`** (fuente `ai-enricher`): la interpretación del LLM de una alerta que decidió la tabla con `monitor.engine: hybrid`, que llega después de la alerta y no la cambia; v0.18, 12/11/2026, aditiva: **comandos del instructor**: evento `InstructorCommand` (id `cmd-`, dominio `sim`, `platform-player`) con `command` `set_wind` o `cancel_wind`, `params` (viento: `from_deg`, `speed_mps`, `gust_mps`, `ramp_s`, `duration_s`), `issued_by` (`panel` | `llm` | `scenario`) y `text`; mensaje `control` → `instructor` del WebSocket (solo `web`, solo con el modo interactivo encendido); `commands` opcional en el YAML del escenario; el agente del instructor es una tercera conversación (`conversation_id: instructor`, `OperatorMessage.context` y `AgentReply.proposal`); el módulo de IA no se suscribe al comando, así que ni el detector ni el monitor lo ven; v0.17, 12/11/2026, aditiva: `now` de `get_track_metrics` lleva `route_trend`, `route_change_m` y `route_trend_source` (si el dron se acerca o se aleja de la ruta en los últimos segundos); `since` y `until` de `get_events` y `get_track_metrics` aceptan también texto (`T+03:42`), `last_s` (ventana hacia atrás desde «ahora»), `get_events` sin `source` o con `all` da todas las fuentes (cada evento con `feed`), un `since` posterior al instante de partida se rechaza y un `until` posterior se recorta diciéndolo (`until_clipped_to`, `note`); v0.16, 05/11/2026: regla nueva `LINK_ANOMALY` del detector sobre `LinkStatus` (`source: link`, `unit: ms`) y su fila en `detections_by_rule` de `get_flight_summary`; la recuperación del secuestro es una alerta `HIJACK` en fase `recovering` que decide el código con el cierre de esa detección; un `SENSOR_FAULT` es de una sola fuente (la de las detecciones que lo abrieron); `labels.json` del secuestro espera también `LINK_ANOMALY`; el escenario `demo-battery`; v0.15, 04/11/2026: campo `gps_fix` en el bloque `now` de `get_track_metrics`, aditivo; sin fix, `now` no da la distancia GPS–radar ni la desviación del GPS; v0.14, 04/11/2026: campo `phase` (`active` | `recovering`) en `AnomalyDetected`, en `publish_alert` y en `get_my_alerts`, aditivo, con `active` por defecto; la recuperación del GPS es una fase de la alerta y su severidad (`low` o `medium`) la elige el modelo; v0.13, 04/11/2026: bloque `now` en el resultado de `get_track_metrics`, aditivo, sin cambios en eventos, topics ni WebSocket; v0.12, 29/10/2026: mensajes propios `truth_feed` y `truth` del WebSocket para enviar a la web la posición real en directo, fuera del bus y solo a clientes `web` que la piden; v0.11, 28/10/2026: evento efímero `AgentToolCall` (id `tcl-`) con cada llamada a tool de los agentes, para depurar desde la web; el GPS admite `loss` y `mute` a la vez (receptor muerto); v0.10, 22/10/2026; 23/10/2026: textos de los ejemplos y de los errores en inglés, sin cambio de campos: `chk-` y `act-` para los eventos efímeros (`AgentReplyChunk`, `AgentActivity`); `run_meta.json` lo escribe la plataforma (§8.6); `load` y `reset` apagan el modo interactivo; la recuperación excluyente comprueba también `severity medium`; v0.9, 22/10/2026: con «esperar al agente», el reproductor pausa también con `DetectionCleared` y se reanuda con la respuesta del monitor a ese cierre; `publish_alert` rechaza un `supersedes` que no cambia ni la causa ni la severidad; v0.8, 21/10/2026: ids opcionales en `publish_alert`, `acknowledge_detection` y `close_alert` (los rellena el módulo); v0.7: hechos calculados en `get_track_metrics` (`wind.notable`, `wind.with_drift`, `gps_radar.disagreed`, `gps_max_step_m`) y `checks` en `publish_alert` y en `AnomalyDetected`; v0.6: respuesta del monitor a cada detección: evento `DetectionAcknowledged`, tool `acknowledge_detection` y fallbacks de §4; `wind` en el resultado de `get_track_metrics`; v0.5, 20/10/2026: simulación en directo y modo interactivo; tipo de fallo `mute`/`loss` (pérdida de GPS) en `control` → `fault`, en `FaultInjected`/`FaultCleared`, en `faults` del YAML y en `state` (`active_faults`, `interactive`); regla `GPS_DEGRADED`, causa `GPS_JAMMING`, evento `InteractiveModeChanged` (ids `plr-` para el estado del reproductor); v0.4: ficheros del generador y YAML de escenario (§8), la ruta de `MissionPlanned` incluye la vuelta a la base; v0.3: `source` y `asset` del sobre, `fix`, `GET /scenarios`, resultado de `get_flight_summary` y `get_track_metrics` sin datos de una fuente, patrón de suscripción de ejemplo corregido en §3; v0.2, 16/10/2026: fallos manuales y regla `SOURCE_SILENT`). Cualquier cambio se hace aquí primero y después en `contracts/python` (Pydantic), `contracts/schemas/` (JSON Schema exportado) y en todos los componentes, en el mismo cambio.

## 1. Convenciones
- **Unidades:** metros, segundos, m/s, grados. Plano x,y con origen en la base: **x hacia el este, y hacia el norte**.
- **Ángulos:** rumbos en grados 0–360, **0 = norte, 90 = este** (sentido horario). El viento se da por **dirección de procedencia** (convención meteorológica): `from_deg: 0` es viento del norte, que empuja hacia el sur.
- **Tiempo:** `sim_time` (s desde el inicio de la simulación, float); `event_time` = `t0` del escenario + `sim_time`, en ISO 8601 UTC; `ingestion_time` lo pone el bus con el reloj de pared, ISO 8601 UTC con milisegundos.
- **Ids:** prefijo por fuente y número con ceros: `gps-000061`, `rad-000030`, `met-0006`, `lnk-0012`, `bat-0006`, `gns-000061`, `apl-000061`, `mis-0003`, `det-0001`, `ai-0001` (alertas, cierres, reconocimientos, incidentes y su texto, informe y respuestas del chat), `chk-0001` (trozos de streaming del chat, `AgentReplyChunk`), `act-0001` (`AgentActivity`), `tcl-0001` (`AgentToolCall`), `ops-0001`, `sim-0001` (fallos), `cmd-0001` (comandos del instructor), `inj-0001` (`ExerciseInjects`), `plr-0001` (estado del reproductor). Únicos en una ejecución. Los eventos efímeros llevan su propio prefijo y contador para que los ids `ai-` de alertas y respuestas no den saltos. **Con varios procesos en el mismo bus (v1.4):** el id puede llevar, tras el prefijo, **una letra minúscula con el proceso del módulo de IA que lo publica** (`ai-m-0001` el monitor, `ai-a-0001` el asistente del alumno, `ai-i-0001` el del instructor; lo mismo con `act-` y `chk-`), porque comparten prefijo y la plataforma rechaza un id repetido: así no se pisan por muchos eventos que publiquen. Sin etiqueta (`ai-0001`) sigue siendo válido (`<prefijo>(-<letra>)?-<número>`).
- **Nombres de campos** en `snake_case`. Textos para personas y para el modelo, en inglés.

## 2. Sobre (común a todos los eventos)
```json
{
  "event_id": "gps-000061",
  "topic": "citadel.pub.evt.air.d1.PositionUpdated.v1",
  "type": "PositionUpdated",
  "source": "d1-gps",
  "asset": "d1",
  "seq": 214,
  "sim_time": 61.0,
  "event_time": "2026-10-20T10:01:01Z",
  "ingestion_time": "2026-10-20T08:15:32.418Z",
  "causation_id": null,
  "ephemeral": false,
  "payload": { }
}
```
- `source`: quién publica. Generador: `d1-gps`, `radar-1`, `meteo-1`, `d1-link`, `d1-bat`, `d1-gnss`, `d1-autopilot`, `d1-mission`. Reproductor (estado, modo interactivo, `FaultInjected`/`FaultCleared`, `InstructorCommand` y `ExerciseInjects`): `platform-player`. Módulo de IA: `ai-detector` (detecciones), `ai-monitor` (`AnomalyDetected`, `AlertClosed`, `DetectionAcknowledged`; `IncidentUpdated`, v1.1), `ai-enricher` (`AlertEnriched`, v0.19; `IncidentEnriched`, v1.1), `ai-report` (`ReportGenerated`), `ai-debrief` (`DebriefGenerated`, v1.4), `ai-chat-monitor` / `ai-chat-report` / `ai-chat-instructor` (`AgentReply`, `AgentReplyChunk`), `ai-module` (`AgentActivity`, `AgentToolCall`). Web (`OperatorMessage`): `web-operator` (en el chat del instructor, `web-instructor`, para que `get_events` con `operator` nunca lo devuelva).
- `asset`: `"d1"` en los topics `air.d1` y `ai.d1`; `"zone1"` en `env.zone1`; `null` en el resto (`sim`, `ops`, `ai.monitor`, `ai.report`, `ai.agent`).
- `seq`: orden global de publicación en la ejecución (lo pone el bus).
- `causation_id`: id del evento que provocó este (p. ej. la detección que provocó una alerta). `null` si no aplica.
- `ephemeral: true` solo para los trozos de streaming del chat, `AgentActivity` y `AgentToolCall`: se reenvían por el WebSocket pero **no** se guardan en el timeline.
- El generador escribe los eventos sin `seq` ni `ingestion_time`; los pone el bus al publicar.

## 3. Topics
Forma: `<namespace>.<clasification>.<type>.<domain>.<routing>.<event>.<version>`, con `namespace = citadel`, `clasification = pub` (sin clasificar; es una PoC), `type = evt | cmd`.

| Topic | Evento | Publica |
|---|---|---|
| `citadel.pub.evt.air.d1.PositionUpdated.v1` | Posición del GPS del dron | Reproductor (simulación en directo) |
| `citadel.pub.evt.air.d1.TrackUpdated.v1` | Traza del radar sobre d1 | Reproductor |
| `citadel.pub.evt.env.zone1.WindReported.v1` | Viento en la zona | Reproductor |
| `citadel.pub.evt.air.d1.LinkStatus.v1` | Enlace de mando | Reproductor |
| `citadel.pub.evt.air.d1.BatteryStatus.v1` | Batería | Reproductor |
| `citadel.pub.evt.air.d1.GnssStatus.v1`, `.AutopilotStatus.v1` (v1.0) | Estado del receptor GNSS y del autopiloto | Reproductor |
| `citadel.pub.evt.air.d1.MissionPlanned.v1`, `.MissionStarted.v1`, `.WaypointReached.v1`, `.MissionCompleted.v1` | Misión | Reproductor |
| `citadel.pub.evt.sim.player.SimulationStarted.v1`, `.SimulationPaused.v1`, `.SimulationResumed.v1`, `.SimulationFinished.v1`, `.SimulationReset.v1`, `.InteractiveModeChanged.v1` | Estado del reproductor y modo interactivo. **El agente no los ve** | Plataforma |
| `citadel.pub.evt.sim.player.FaultInjected.v1`, `.FaultCleared.v1` | Fallo activado o terminado: fuente silenciada (`mute`) o pérdida de GPS (`loss`), manual o programado. **El agente no los ve** | Plataforma |
| `citadel.pub.evt.sim.instructor.InstructorCommand.v1` | Comando del instructor aplicado (viento puesto o cancelado), desde el panel, desde una propuesta del LLM confirmada o programado en el escenario. **El agente no lo ve** (ni el módulo de IA lo recibe) | Plataforma |
| `citadel.pub.evt.sim.instructor.ExerciseInjects.v1` (v1.4) | Lo programado en el ejercicio (anomalías de `labels.json`), publicado tras `SimulationStarted`. **Solo para el proceso del instructor del asistente; el alumno y su asistente no lo ven** | Plataforma |
| `citadel.pub.evt.ai.d1.DetectionRaised.v1`, `.DetectionUpdated.v1`, `.DetectionCleared.v1` | Detector de reglas | Módulo de IA |
| `citadel.pub.evt.ai.d1.AnomalyDetected.v1`, `.AlertClosed.v1`, `.DetectionAcknowledged.v1` | Agente monitor | Módulo de IA |
| `citadel.pub.evt.ai.d1.AlertEnriched.v1` (v0.19) | Interpretación del LLM en el híbrido | Módulo de IA |
| `citadel.pub.evt.ai.d1.IncidentUpdated.v1`, `.IncidentEnriched.v1` (v1.1) | Monitor de situación (estado de cada incidente) y texto del asistente sobre él | Módulo de IA |
| `citadel.pub.evt.ai.d1.ReportGenerated.v1` | Informe del asistente | Módulo de IA |
| `citadel.pub.evt.ai.instructor.DebriefGenerated.v1` (v1.4) | Debriefing del instructor, con la verdad (`ai.instructor`: no llega a la vista del alumno) | Módulo de IA |
| `citadel.pub.evt.ops.monitor.OperatorMessage.v1`, `citadel.pub.evt.ops.report.OperatorMessage.v1`, `citadel.pub.evt.ops.instructor.OperatorMessage.v1` | Pregunta del operador a cada agente (la del instructor, al agente del instructor) | Web |
| `citadel.pub.evt.ai.monitor.AgentReply.v1`, `citadel.pub.evt.ai.report.AgentReply.v1`, `citadel.pub.evt.ai.instructor.AgentReply.v1` | Respuesta completa del chat | Módulo de IA |
| `citadel.pub.evt.ai.monitor.AgentReplyChunk.v1`, `citadel.pub.evt.ai.report.AgentReplyChunk.v1`, `citadel.pub.evt.ai.instructor.AgentReplyChunk.v1` | Trozo de respuesta en streaming (`ephemeral`) | Módulo de IA |
| `citadel.pub.evt.ai.agent.AgentActivity.v1` | Aviso de que un agente empieza o termina una invocación (`ephemeral`), para la web | Módulo de IA |
| `citadel.pub.evt.ai.agent.AgentToolCall.v1` | Una llamada a tool de un agente, con argumentos y resultado (`ephemeral`), para depurar en la web. **Ningún agente, tool ni detector lo ve** | Módulo de IA |

Suscripciones con comodines: `*` = un segmento, `>` = el resto. Ejemplos: `citadel.pub.evt.air.d1.>` (todo lo del dron), `citadel.*.evt.ai.d1.Detection*` **no vale** (los comodines van por segmento entero); usa `citadel.pub.evt.ai.d1.>` (o `citadel.pub.evt.ai.d1.*.v1`) y filtra por `type`. Ojo: los topics tienen siete segmentos (el último es la versión), así que `citadel.pub.evt.ai.d1.*` **no casa con nada**.

## 4. Eventos (payload)

### Del escenario
**`MissionPlanned`** (`mis-`, `sim_time: 0`)
```json
{ "mission_id": "MSN-DEMO", "cruise_speed_mps": 15.0, "altitude_m": 60.0, "acceptance_radius_m": 20.0, "mission_controller_id": "GCS-1",
  "waypoints": [ {"id": "BASE", "x": 0.0, "y": 0.0, "eta_s": 0.0},
                 {"id": "WP1", "x": 400.0, "y": 900.0, "eta_s": 66.5} ] }
```
`waypoints` es la ruta completa: la base (`BASE`), los waypoints y **otra vez la base** como último punto (la vuelta); `eta_s` es el instante previsto de llegada en un vuelo sin perturbaciones. La polilínea de esos puntos es la ruta planificada con la que se mide la desviación. El índice de `WaypointReached` es la posición en esa lista (`BASE` = 0; la llegada final a la base lleva el último índice).

**`MissionStarted`** `{ "mission_id": "MSN-DEMO" }` · **`WaypointReached`** `{ "waypoint_id": "WP2", "index": 2 }` (lo decide el dron con su GPS) · **`MissionCompleted`** `{ "mission_id": "MSN-DEMO", "completed": true, "reason": "returned_to_base" }` (`reason`: `returned_to_base` | `timeout` | `landed`, este con `completed: false`: el failsafe de aterrizar, v1.0)

**`PositionUpdated`** (`gps-`, cada 1 s)
```json
{ "x": 512.3, "y": 140.8, "alt_m": 60.2, "speed_mps": 15.1, "course_deg": 81.0, "fix": "3d", "sats": 14, "hdop": 0.8 }
```
`speed_mps` y `course_deg` son los de navegación del propio dron (velocidad y **rumbo sobre el suelo**, según su GPS; el rumbo del morro no va aquí). `fix`: `"none"` | `"2d"` | `"3d"`; `sats`: entero; `hdop`: decimal. En vuelo normal: `"3d"`, 14 satélites, `hdop` 0,8. **Durante una pérdida de GPS** (`loss`, §4 «Del reproductor») el dron sigue publicando `PositionUpdated` con su **posición estimada** (navega a estima), `fix: "none"`, `sats: 0` y `hdop` alto (99,9):
```json
{ "x": 498.7, "y": 902.1, "alt_m": 60.1, "speed_mps": 14.9, "course_deg": 12.0, "fix": "none", "sats": 0, "hdop": 99.9 }
```
Al recuperarse, la posición salta a la real. **Sin fix el receptor no da posición, altitud, velocidad ni rumbo** (v1.0): van a `null` (un GPS real sin fix no los da) y la estima del dron va en `AutopilotStatus`:
```json
{ "x": null, "y": null, "alt_m": null, "speed_mps": null, "course_deg": null, "fix": "none", "sats": 0, "hdop": 99.9 }
```

**`TrackUpdated`** (`rad-`, cada 2 s) `{ "x": 505.0, "y": 151.2, "speed_mps": 14.2, "course_deg": 83.0 }`

**`WindReported`** (`met-`, cada 10 s) `{ "speed_mps": 4.2, "from_deg": 350.0 }`

**`LinkStatus`** (`lnk-`, cada 5 s) lo mide **nuestra estación** (v1.0) y no lleva `controller_id`: `{ "rssi_dbm": -70.1, "latency_ms": 44.8, "packet_loss_pct": 0.0 }`. El RSSI cae con la distancia a la base (`rssi_dbm` del YAML es el de 1 km, menos `20·log10(d_km)`; un episodio lo atenúa), la pérdida de paquetes es logística en el RSSI (50 % con `loss_rssi50_dbm`) y `packet_loss_pct` es la fracción de la telemetría del dron perdida en los últimos 10 s. **Con el enlace caído** (secuestro, `mute` del enlace o señal bajo `rssi_floor_dbm`) llegan `rssi_dbm` y `latency_ms` a `null` y `packet_loss_pct: 100.0`. Nunca se silencia. **La telemetría del dron (`PositionUpdated`, `GnssStatus`, `AutopilotStatus`, `BatteryStatus` y `WaypointReached`) solo llega si llega su paquete**; el radar y la estación son independientes. **Failsafe:** tras `drone.link_loss_timeout_s` (10 s) sin enlace con nuestra estación el dron actúa según `drone.link_loss_action` (`continue` por defecto, `hold`, `return` o `land`); un secuestro no lo dispara (el dron obedece a otro). El controlador ajeno queda solo en la verdad (`emitters`).

**`BatteryStatus`** (`bat-`, cada 10 s) lleva la carga, la potencia eléctrica y el tiempo restante al ritmo actual (v1.0): `{ "battery_pct": 87.5, "power_w": 410.0, "time_remaining_s": 2790.0 }`. Consumo según la potencia de un multirrotor (curva en U respecto al aire, Zeng et al., arXiv:1804.02238) dividida por la eficiencia; **failsafe** por niveles de PX4: aviso al 15 % (`battery.level: low`, sin cambio de modo), volver a casa por debajo del 7 % (`critical`), aterrizar por debajo del 5 %, o volver cuando la energía que queda no alcanza para llegar a casa con el viento estimado (`battery.endurance: cannot_reach_home`, con una reserva del 10 % y mantenido 5 s).

**`GnssStatus`** (`gns-`, v1.0, cada periodo del GPS; callado si el GPS está en `mute`) `{ "h_acc_m": 2.4, "cn0_dbhz": 45.3, "agc_db": 0.1 }`: `h_acc_m` es la precisión horizontal que dice el receptor (con `loss`, 99,9), `cn0_dbhz` la relación portadora/ruido media y `agc_db` el control automático de ganancia (0 = nominal; dependen de la distancia a los emisores: una **interferencia** baja el C/N0 y baja el AGC; un **engaño** sube el C/N0 y baja el AGC). El receptor dice lo mismo con el GPS engañado (no sabe que lo está): la σ real es la del ruido, no la del engaño.

**`AutopilotStatus`** (`apl-`, v1.0, cada periodo del GPS)
```json
{ "mode": "mission", "heading_deg": 71.2, "airspeed_mps": 15.0,
  "wind_est_speed_mps": 2.1, "wind_est_from_deg": 301.5, "innovation_m": 0.8,
  "est_x": 512.3, "est_y": 140.8, "ground_speed_mps": 15.1, "course_deg": 81.0 }
```
`mode`: `mission` | `failsafe_return` | `failsafe_hold` | `failsafe_land`; `heading_deg` es el rumbo del **morro** (el de `PositionUpdated.course_deg` es el del suelo); `airspeed_mps` la velocidad respecto al aire; `wind_est_*` el viento estimado a bordo (m/s y procedencia: lo que dice el estimador, no la estación); `innovation_m` la distancia entre el GPS y lo que predice la estima en la última medida (`null` sin GPS: la estima no se corrige y sigue con el último viento estimado); `est_x`, `est_y`, `ground_speed_mps` y `course_deg` son la **estima** del dron (posición, velocidad y rumbo sobre el suelo): lo que el GPS no da sin fix.

### Del reproductor
**`SimulationStarted`** `{ "scenario": "demo", "run_id": "20261020-101500", "duration_s": 420.0, "total_events": 913 }` (`duration_s` y `total_events` son los de la ejecución **sin intervenciones**, los de `runs/<escenario>/`; con fallos manuales la ejecución real puede ser distinta) · **`SimulationPaused`** `{ "reason": "user" }` (`reason`: `user`; un paso con la simulación aún sin arrancar también la publica, para que el siguiente `play` publique su `SimulationResumed`) · **`SimulationResumed`** `{}` · **`SimulationFinished`** `{ "scenario": "demo", "run_id": "…" }` · **`SimulationReset`** `{}`

**`InteractiveModeChanged`** (`plr-`) `{ "interactive": true }`: el modo interactivo (que permite inyectar fallos en directo) se enciende o se apaga. Cada `load` (y el `reset`, que es un `load` del mismo escenario) **lo apaga**: si estaba encendido, el timeline nuevo empieza con `SimulationStarted` y un `InteractiveModeChanged` con `interactive: false`.

**`FaultInjected`** / **`FaultCleared`** (`sim-`) `{ "source": "radar", "mode": "mute", "origin": "manual" }` (`source`: `gps` | `radar` | `meteo` | `link` | `battery`; `mode`: `mute` | `loss`; `origin`: `manual` | `scenario`). Dos tipos de fallo: **`mute`** (cualquier fuente): la fuente deja de publicarse y el dron vuela igual. **`loss`** (solo `gps`): el dron navega a estima: integra su velocidad respecto al aire (sin conocer el viento), el controlador sigue el plan con esa estimación (puede dar por alcanzado un waypoint que no ha alcanzado) y la trayectoria real se va desviando; mientras dura, el GPS publica `PositionUpdated` con la posición estimada, `fix: "none"`, `sats: 0` y `hdop` alto; al recuperarse, la posición salta a la real y el controlador corrige. Una fuente solo puede tener un fallo a la vez, **salvo el GPS, que puede tener `loss` y `mute` a la vez** (receptor muerto), en cualquier orden y sea cual sea el origen de cada uno: el dron navega a estima (como en `loss`) y el GPS no publica nada (como en `mute`). Al terminar uno sigue el otro: sin `mute`, vuelven los `PositionUpdated` sin fix; sin `loss`, el GPS vuelve a la posición real pero sigue callado. Cada fallo tiene su `FaultInjected`/`FaultCleared` y los dos figuran en `state.active_faults`. El enlace de mando, el radar, la meteo y la batería solo admiten `mute` y un único fallo.

**`InstructorCommand`** (`cmd-`, v0.18): la plataforma lo publica al aplicar un comando del instructor desde el instante actual. **El comando es del instructor, no del ejercicio que ve la IA:** va en el dominio `sim`, ninguna tool lo devuelve y el módulo de IA no se suscribe a él, así que el monitor descubre el viento por sus efectos (la estación lo mide y el dron se desvía), como con un episodio del escenario.
```json
{ "command": "set_wind",
  "params": {"from_deg": 0.0, "speed_mps": 12.0, "ramp_s": 10.0, "duration_s": 60.0},
  "issued_by": "panel", "text": null }
```
- `command`: `set_wind` | `cancel_wind` (`params: null`; vuelve al viento del escenario). Se podrán añadir otros comandos sin romper el evento.
- `params` (m/s y grados; `from_deg` es la **procedencia**, 0 = del norte): `from_deg` y `speed_mps` **empujan al dron**; `ramp_s` suaviza la subida y la bajada del episodio (la velocidad se interpola, la procedencia cambia de golpe); `duration_s` en segundos, `null` = hasta nuevo aviso. Rangos: `from_deg` 0–360 (360 = 0), `speed_mps` 0–40, `ramp_s` mayor que 0 y hasta 120, `duration_s` mayor que 0 y hasta 1800 (o `null`).
- `issued_by`: `panel` (el panel de la web), `llm` (una propuesta del agente del instructor que el instructor ha confirmado; `text` es su frase original) o `scenario` (programado en `commands` del YAML).
- **Efecto:** el viento del instructor es un episodio más, aplicado **después** de los del escenario, así que **sustituye** al viento que haya (no se suma): sube con su rampa desde el viento de ese instante hasta `speed_mps`, dura `duration_s` y baja con la misma rampa al del escenario. Un `set_wind` nuevo sustituye al anterior sin saltos (el anterior se mantiene mientras sube el nuevo) y `cancel_wind` baja el activo con su rampa; cancelar sin viento del instructor en curso es un error. Determinista y sin ruido propio: la estación lo mide con su ruido de siempre y el dron se desvía con la física de siempre.

**`ExerciseInjects`** (`inj-`, v1.4): lo que el ejercicio tiene programado. La plataforma lo publica **una vez** tras cada `SimulationStarted` (también tras un `reset`), con las etiquetas de `runs/<escenario>/labels.json` (solo lectura). Los fallos y órdenes en directo no están aquí: llegan como `FaultInjected` e `InstructorCommand`. **Es la verdad del ejercicio:** va en el dominio `sim`, solo lo recibe el proceso del instructor del asistente y la vista del alumno de la web no lo enseña.
```json
{ "injects": [ {"id": "A1", "type": "wind", "source": null, "start_s": 95.0, "end_s": 150.0},
               {"id": "F1", "type": "source_silent", "source": "radar", "start_s": 120.0, "end_s": 180.0} ] }
```
`type`: el `type` de la etiqueta (§8.4: `wind` | `hijack` | `gps_spoofing` | `source_silent` | `gps_loss` | `gps_degraded` | `link_degraded`).

### Del detector (módulo de IA)
**`DetectionRaised`** / **`DetectionUpdated`** (`det-`)
```json
{ "detection_id": "det-0002", "rule": "ROUTE_DEVIATION", "severity": "medium",
  "value": 34.8, "threshold": 30.0, "unit": "m",
  "source": null,
  "window": {"since": 80.0, "until": 84.0},
  "trigger_event_ids": ["gps-000083", "gps-000084"],
  "message": "The GPS position is 34.8 m away from the planned route" }
```
`rule`: `ROUTE_DEVIATION` | `SOURCE_DISCREPANCY` | `SOURCE_SILENT` | `GPS_DEGRADED` | `LINK_ANOMALY` (v0.16). `source`: la fuente afectada; obligatoria en `SOURCE_SILENT` (`gps` | `radar` | `meteo` | `link` | `battery`; `value` = segundos sin eventos, `unit: "s"`), `"gps"` en `GPS_DEGRADED` (`value` = el `hdop` del último `PositionUpdated`, `threshold: 3.0`, `unit: "hdop"`; el `message` dice qué falla: `fix`, `sats` o `hdop`) y `"link"` en `LINK_ANOMALY` (`value` = la latencia en ms del último `LinkStatus`, `threshold` = el umbral de latencia, `unit: "ms"`; el `message` dice si ha cambiado el controlador o si se han degradado la señal o la latencia), `null` en las demás. `severity`: `low` | `medium` | `high`. `DetectionUpdated` usa el mismo `detection_id` y una severidad mayor.

Ejemplo de `GPS_DEGRADED`:
```json
{ "detection_id": "det-0004", "rule": "GPS_DEGRADED", "severity": "high",
  "value": 99.9, "threshold": 3.0, "unit": "hdop",
  "source": "gps",
  "window": {"since": 245.0, "until": 245.0},
  "trigger_event_ids": ["gps-000245"],
  "message": "The GPS has lost the fix (fix none, 0 satellites, hdop 99.9)" }
```

Ejemplo de `LINK_ANOMALY` (v0.16; con la v1.0 `LinkStatus` ya no trae `controller_id` y el detector está congelado hasta la E7c): abre si el `controller_id` deja de ser el primero visto en la ejecución (el de la misión) o si la latencia o el RSSI pasan sus umbrales (`high` con otro controlador, `medium` si solo se degrada la calidad; un `DetectionUpdated` la sube a `high` si más tarde cambia el controlador) y se cierra cuando vuelve el controlador de la misión y el enlace está normal (latencia y RSSI dentro de los umbrales de cierre) durante `close_hold_s`. No sabe de causas. Umbrales en `ai-module-py/src/ai_module/config/detector.yaml`.
```json
{ "detection_id": "det-0001", "rule": "LINK_ANOMALY", "severity": "high",
  "value": 122.4, "threshold": 90.0, "unit": "ms",
  "source": "link",
  "window": {"since": 335.0, "until": 335.0},
  "trigger_event_ids": ["lnk-0067"],
  "message": "The command link has changed controller: GCS-1 → UNK-4F2A (latency 122.4 ms, signal -76.2 dBm)" }
```

**`DetectionCleared`** `{ "detection_id": "det-0002", "rule": "ROUTE_DEVIATION", "duration_s": 46.0, "max_value": 71.5 }`

### Del agente monitor
**`AnomalyDetected`** (`ai-`, `causation_id` = la detección que lo provocó)
```json
{ "alert_id": "ai-0003", "detection_ids": ["det-0002"],
  "cause": "WIND", "severity": "low", "confidence": 0.8,
  "summary": "Drift caused by strong northerly wind; the drone corrects by itself",
  "explanation": "Between T+01:20 and T+01:24 GPS and radar agree (≤ 6 m) and both move 35 m away from the plan towards the south (182°). The weather station reports 14 m/s from the north (met-0008). The drift goes with the wind.",
  "recommendation": "No intervention. Watch that it recovers the route before WP3.",
  "evidence_event_ids": ["gps-000084", "rad-000042", "met-0008"],
  "supersedes": null, "as_of_sim_time": 84.0, "fallback": false, "phase": "active",
  "checks": { "gps_alert_recent": false, "gps_radar_disagreed": false, "wind_notable": true,
              "wind_with_drift": true, "link_checked": false, "link_anomalous": null } }
```
`cause`: `WIND` | `HIJACK` | `GPS_SPOOFING` | `SENSOR_FAULT` | `GPS_JAMMING` | `UNKNOWN` (reservada para el futuro: `REPLAY`). **Quién la decide (v0.19):** `decided_by` es `table` cuando la decide la tabla de decisión del módulo de IA (`monitor.engine: table` o `hybrid`: causa, severidad, confianza, fase y ciclo de vida, sin LLM), con `rule_id` = la fila de la tabla `cause` que encajó (`C01`…; `null` en las de fallback); `llm` o sin el campo, el LLM del monitor (las alertas del LLM no lo llevan, como antes de la v0.19). Los dos campos son opcionales; la tabla es un dato (`ai-module-py/src/ai_module/config/decision_table.yaml`) con forma de DMN. `supersedes`: `alert_id` de una alerta anterior a la que esta sustituye (p. ej. al cambiar la causa o la severidad); las alertas encadenadas por `supersedes` son **una sola alerta** (un episodio). `fallback: true` si lo publicó el módulo porque el agente no concluyó. `phase` (v0.14): `active` (por defecto) mientras el problema del episodio sigue; `recovering` cuando ha terminado y la situación vuelve a la normalidad (en la práctica, la recuperación del GPS: el GPS ha vuelto, salta a la posición real y el dron corrige hacia la ruta). La **severidad** es el riesgo operativo ahora y la **causa** la del episodio: una alerta `recovering` conserva la causa (`GPS_SPOOFING`, por ejemplo) y lleva la severidad actual (`low` o `medium`, nunca `high`). Una cadena de `supersedes` se lee «causa → en recuperación → cerrada». `checks` (opcional, `null` en las alertas de fallback): las comprobaciones que el monitor declaró antes de elegir la causa, para que el operador vea por qué se decidió: `gps_alert_recent` (hay una alerta del GPS abierta o cerrada hace 60 s o menos), `gps_radar_disagreed`, `wind_notable` y `wind_with_drift` (los hechos de `get_track_metrics`; falsos si no se llamó), `link_checked` (se miró el enlace con `get_events`) y `link_anomalous` (`null` si no se miró). El módulo comprueba que coinciden con los resultados de las tools de esa invocación (§7).

**`AlertClosed`** `{ "alert_id": "ai-0003", "reason": "The deviation has been corrected (det-0002 cleared)", "as_of_sim_time": 130.0 }`

**`AlertEnriched`** (v0.19; `ai-`, fuente `ai-enricher`, `causation_id` = el `alert_id`) `{ "alert_id": "ai-0003", "text": "The drone is being pushed south by the northerly wind and is already turning back towards the route.", "hypothesis": null, "decided_by": "llm", "as_of_sim_time": 84.0, "alert_status": "open" }`
Solo con `monitor.engine: hybrid`: la tabla decide la alerta y, **después y sin esperar**, el LLM escribe una interpretación en palabras llanas. **No cambia la alerta**: causa, severidad, confianza, fase y ciclo de vida son los de la tabla. El módulo comprueba el texto antes de publicarlo (sin nombres internos, sin cifras, horas ni ids que no estuvieran en lo que recibió el LLM); si no pasa, no se publica y queda en la traza. `hypothesis` solo en las alertas `UNKNOWN`, y es opcional: lleva `cause`, `confidence` (≤ 0,4) y `evidence_event_ids`, con una causa de la lista distinta de `UNKNOWN` y evidencias que el módulo consultó al decidir la alerta. **Es una hipótesis, no un diagnóstico.** `as_of_sim_time` es el de la alerta; `alert_status` (`open`, `superseded` o `closed`), el estado de la alerta al publicarse: si estaba sustituida o cerrada antes de empezar la llamada, no se pide. No es una respuesta a un aviso: el reproductor no lo espera, y lleva una fuente propia para que ninguna tool de datos lo devuelva (los chats no lo ven).

**`DetectionAcknowledged`** (`ai-`, `causation_id` = el `event_id` del evento de detección al que responde)
```json
{ "detection_id": "det-0002", "alert_id": "ai-0003", "reason": "The same wind drift continues; alert ai-0003 already explains it", "as_of_sim_time": 258.0, "fallback": false }
```
`alert_id`: la alerta abierta a la que pertenece la detección, o `null` si el monitor decide que no hace falta alerta (o no concluye, con `fallback: true`).

**Cada evento de detección recibe respuesta.** Por cada `DetectionRaised`, `DetectionUpdated` y `DetectionCleared`, el monitor publica **al menos un** evento de `ai-monitor` con su `event_id` como `causation_id`. Desde la v1.3 el reproductor ya no espera al agente: esto describe al módulo anterior, sin publicador desde la E7c. Qué publica:

| Caso | Respuesta |
|---|---|
| Alerta nueva | `AnomalyDetected` |
| Pertenece a una alerta abierta y cambia la causa, la severidad o la fase | `AnomalyDetected` con `supersedes` |
| Pertenece a una alerta abierta y no cambia nada | `DetectionAcknowledged` con `alert_id` |
| No hace falta alerta | `DetectionAcknowledged` con `alert_id: null` |
| El agente no concluye (texto final tras un recordatorio, tope de iteraciones, tiempo agotado o error del LLM) en un `DetectionRaised` **sin ninguna alerta abierta que la explique** (un `SENSOR_FAULT` abierto de otra fuente no la explica: v0.16) | `AnomalyDetected` con `cause: UNKNOWN` y `fallback: true` |
| El agente no concluye en cualquier otro caso | `DetectionAcknowledged` con `fallback: true` y `alert_id: null` |
| `DetectionCleared` y a la alerta le quedan detecciones abiertas, o no tiene alerta, o ya está cerrada | `DetectionAcknowledged` determinista (sin LLM) |
| `DetectionCleared` de una `LINK_ANOMALY` cuya alerta es un `HIJACK` en fase `active` y a la que aún le queda abierto un `ROUTE_DEVIATION` (v0.16) | El LLM publica la **recuperación del secuestro**: `AnomalyDetected` `HIJACK` con `supersedes` esa alerta y `phase: recovering` (severidad `low` o `medium`); reconocerla se rechaza. Si no concluye, `DetectionAcknowledged` con `fallback: true` |
| `DetectionCleared` de la última detección abierta de una alerta | El LLM decide: `AlertClosed`, o `DetectionAcknowledged` si cree que el problema sigue. Si no concluye, el módulo publica un `AlertClosed` con `reason` «todas sus detecciones se han cerrado» |

Si una alerta incluye varias detecciones del lote, la `AnomalyDetected` responde a la primera y el resto reciben un `DetectionAcknowledged` enlazado a esa alerta. Ninguna de estas respuestas la ve ni la cuenta `get_my_alerts` (solo `AnomalyDetected` y `AlertClosed`).

### Del monitor de situación (v1.1)
**`IncidentUpdated`** (`ai-`, fuente `ai-monitor`, `causation_id: null`): el estado de un incidente, **un evento por transición**. Un incidente cambia de estado, no se sustituye: la web se queda con el último por `incident_id`.
```json
{ "incident_id": "inc-0002", "revision": 3,
  "kind": "GPS_SPOOFING", "name": "GPS spoofing",
  "state": "recovering", "severity": "medium", "confidence": "confirmed",
  "opened_at": 200.0, "as_of_sim_time": 252.0,
  "change": "state",
  "evidence": [
    {"facet": "gps.integrity", "state": "reliable", "rule_id": "GI-02",
     "conditions": [{"feature": "cn0_rise_db", "op": ">=", "threshold": 4.0, "value": -0.7}]},
    {"facet": "drone.situation", "state": "returning", "rule_id": "DS-03",
     "conditions": [{"feature": "radar_route_dev_m", "op": ">", "threshold": 15.0, "value": 79.7}]}],
  "context": [{"feature": "wind_est_mps", "value": 2.6}],
  "checks": ["Compare the GPS with the radar track", "Check C/N0 and AGC of the receiver"],
  "evidence_event_ids": ["gns-000252", "rad-000126"],
  "decided_by": "table", "table": "handwritten-video" }
```
- `incident_id`: el del incidente (`inc-0001`…, lo pone el monitor; no es el `event_id`). `revision` crece en cada transición del incidente, desde 1 (la apertura).
- `kind` (v1.3): `WIND` | `GPS_SPOOFING` | `HIJACK` | `LINK_LOSS` | `LINK_DEGRADED` | `GPS_DEGRADED` | `GPS_NO_FIX` | `DEAD_RECKONING` | `SOURCE_SILENT` | `RADAR_OUT_OF_RANGE` | `BATTERY_LOW` | `BATTERY_CRITICAL` | `CANNOT_REACH_HOME` | `FAILSAFE` | `UNDETERMINED` (esta, la salida cuando la confianza es baja: no es una etiqueta de la verdad). `subject`: solo con `SOURCE_SILENT` (`gps`, `radar`, `meteo` o `battery`) y `FAILSAFE` (`failsafe_return`, `failsafe_hold` o `failsafe_land`); `null` en el resto. `name`: el nombre para personas («GPS spoofing», «Hijack», «Radar silent»…); un incidente puede cambiar de nombre hacia otro más grave **de su misma familia** (`LINK_DEGRADED` → `LINK_LOSS` → `HIJACK`; `GPS_DEGRADED` → `GPS_NO_FIX` → `DEAD_RECKONING`; `FAILSAFE` → `BATTERY_LOW` → `CANNOT_REACH_HOME` → `BATTERY_CRITICAL`) o desde `UNDETERMINED` a la causa que se confirma; puede haber **varios incidentes abiertos a la vez**, uno por familia.
- `state`: `open` | `recovering` (la causa ha desaparecido y el dron aún vuelve) | `closed`.
- `change`: qué cambió en esta revisión: `opened` (solo la revisión 1) | `state` | `renamed` (el tipo pasa a uno más grave sin cerrar el incidente: p. ej. `LINK_LOSS` → `HIJACK`) | `severity` | `evidence` (cambia el estado de alguna faceta de sus evidencias —p. ej. la situación del dron pasa de `on_route` a `deviated`— sin cambiar el estado, el nombre ni la severidad: la web actualiza las evidencias y el asistente no vuelve a interpretar) | `closed` (solo con `state: closed`).
- `severity`: `low` | `medium` | `high`, el riesgo **ahora** (baja en recuperación). `confidence`: `confirmed` (≥ 0,9) | `probable` (0,6–0,9) | `possible` (< 0,6), en niveles.
- `evidence`: el camino de la tabla que decidió, faceta → estado → fila (`rule_id`) → condiciones con su umbral y su valor en ese instante (`op`: `>=`, `<=`, `>`, `<`, `==`, `!=`). Así la web lo dibuja sin saber de tablas. `context`: lo que no decide pero ayuda (p. ej. viento fuerte sin desviación). `checks`: qué comprobar, para el operador. `evidence_event_ids`: los eventos que sostienen el estado.
- `decided_by`: siempre `table`; `table`: el nombre de la tabla que se ejecutó.

**`IncidentEnriched`** (`ai-`, fuente `ai-enricher`, `causation_id` = el `event_id` del `IncidentUpdated` que interpreta)
```json
{ "incident_id": "inc-0002", "revision": 3, "state": "recovering",
  "text": "The spoofing has stopped: the GPS jumped back about 80 m to where the radar sees the drone, and the drone is now flying back to the route.",
  "hypothesis": null, "role": "explain", "decided_by": "llm", "as_of_sim_time": 252.0,
  "model": "Qwen/Qwen3-14B-AWQ", "prompt_sha": "3f9a1c7e0b52" }
```
El texto del asistente sobre una revisión del incidente (`revision` y `state` son los de esa revisión). **No cambia el incidente** y no es una respuesta a un aviso (el reproductor no lo espera). `role`: `explain` (explica qué pasa) | `hypothesis` (solo en `UNDETERMINED`: entonces `hypothesis` lleva `kind` distinto de `UNDETERMINED`, `confidence: possible` y `evidence_event_ids`; **es una hipótesis, no un diagnóstico**). `decided_by`: siempre `llm`. `model` y `prompt_sha` (v1.4, opcionales): el modelo y la huella de los prompts con que se escribió. Lleva una fuente propia, como `AlertEnriched`, para que ninguna tool de datos lo devuelva.

**Hipótesis estructurada (v1.4):** además de `kind` (la primera causa), `confidence` y `evidence_event_ids`, la hipótesis lleva `ranked` (hasta 3 causas ordenadas, `kind` de la primera = `kind`; cada una con `supports`, lo que la apoya, y `missing`, lo que falta, hasta 3 frases cada uno; las causas posibles son `WIND`, `GPS_SPOOFING`, `HIJACK` y `DEAD_RECKONING`) y `checks` (hasta 4: `target` de la lista cerrada `gps` | `receiver` | `radar` | `meteo` | `link` | `battery` | `autopilot` y la frase). Así se puede medir si la primera causa acierta y si lo que pide comprobar incluye la fuente que distingue la causa verdadera. Las dos listas pueden ir vacías (las hipótesis de la v1.1).
```json
{ "kind": "GPS_SPOOFING", "confidence": "possible", "evidence_event_ids": ["gns-000252", "rad-000126"],
  "ranked": [ {"kind": "GPS_SPOOFING", "supports": ["The radar is 32 m from the GPS position"], "missing": ["C/N0 has not risen"]},
              {"kind": "WIND", "supports": ["The drone drifts to one side"], "missing": ["The station reports calm wind"]} ],
  "checks": [ {"target": "radar", "text": "Compare the GPS position with the radar track"},
              {"target": "receiver", "text": "Check C/N0 and AGC of the GPS receiver"} ] }
```

### Del agente de informe
**`ReportGenerated`** `{ "run_id": "…", "markdown": "# Informe…", "alerts_count": 3 }` (`alerts_count`: alertas distintas; una cadena de `supersedes` cuenta como una)

**`DebriefGenerated`** (`ai-`, v1.4, fuente `ai-debrief`, topic `ai.instructor`) `{ "run_id": "…", "markdown": "# Debriefing…", "injects_count": 3 }`: el debriefing del instructor al terminar el ejercicio, con lo inyectado frente a lo detectado. Lleva la verdad, así que va por `ai.instructor`, que la vista del alumno no recibe.

### Del chat
**`OperatorMessage`** (`ops-`) `{ "conversation_id": "monitor", "text": "Why do you think it is wind?" }`
**`AgentReplyChunk`** (`ephemeral: true`) `{ "conversation_id": "monitor", "reply_to": "ops-0004", "delta": "Porque la" }`
**`AgentReply`** `{ "conversation_id": "monitor", "reply_to": "ops-0004", "text": "Because the station…", "tool_calls": ["get_events", "get_track_metrics"] }`
**`AgentActivity`** (`ephemeral: true`) `{ "agent": "monitor", "state": "started", "invocation_id": "inv-0007", "causation_id": "det-0002" }` (`agent`: `monitor` | `report` | `chat-monitor` | `chat-report` | `chat-instructor` | `assistant` | `translator` | `debrief`; `state`: `started` | `finished`)

**`AgentToolCall`** (`tcl-`, `ephemeral: true`, `source: ai-module`, `causation_id` = el de su `AgentActivity`: la **primera** detección del lote que lanzó la invocación del monitor, o el `ops-` de la pregunta del chat)
```json
{ "agent": "monitor", "invocation_id": "inv-0007", "index": 2, "iteration": 1,
  "tool": "get_track_metrics", "arguments": "{\"since\": 60, \"until\": 90}",
  "status": "ok", "result": "{\"since\":60.0,…}", "error": null, "truncated": false }
```
Se publica al terminar cada llamada a tool, para depurar desde la web. `index`: orden de la llamada en la invocación (desde 1); `iteration`: la llamada al LLM que la pidió (desde 1); `arguments`: el texto de argumentos tal como lo dio el modelo; `status`: `ok` | `error` (JSON inválido, tool desconocida o fallo de la tool) | `rejected` (la tool devolvió `ok: false` con `errors`: validación o guardrails) | `aborted` (el modelo repite por segunda vez una llamada rechazada y se corta la invocación); `result`: lo que se devolvió al modelo (JSON compacto, o una skill tal cual), `null` si `aborted`; `error`: el mensaje de error o de rechazo, `null` si `ok`. **Para la web `arguments` se recorta a 1000 caracteres y `result` a 2000** (`truncated: true` si se recortó alguno). Es **solo para la web**: es efímero (no va al timeline, así que ninguna tool lo devuelve), el módulo de IA lo descarta al recibirlo (ni el detector, ni el monitor, ni los chats, ni el informe lo ven ni lo cuentan, y no puede ser evidencia de una alerta) y no cambia nada de lo que ve el modelo, de `AgentReply.tool_calls` ni de las trazas. El módulo lo publica por defecto; se apaga con `--no-tool-call-events`.

### Del chat del instructor (v0.18)
Tercera conversación (`conversation_id: instructor`, topics `ops.instructor` y `ai.instructor`, source `web-instructor` y `ai-chat-instructor`) con el agente del instructor, que **propone y no publica**: interpreta una frase en inglés y en m/s y devuelve una propuesta ya validada; solo cuando el instructor la confirma, la web manda el comando por `control` → `instructor` (`issued_by: llm`, con la frase original). El código, no el LLM, convierte el rumbo a grados, pone los valores por defecto (los dice) y valida. Sin tools de datos.

`OperatorMessage` lleva `context` (solo en esta conversación): el viento del instructor activo, porque el módulo no ve el comando.
```json
{ "conversation_id": "instructor", "text": "Stronger",
  "context": {"active_wind": {"from_deg": 0.0, "speed_mps": 12.0, "remaining_s": 41.0}} }
```
`AgentReply` lleva `proposal` (solo en esta conversación, la última propuesta válida de la invocación; `defaults_used` dice qué parámetros rellenó el código):
```json
{ "conversation_id": "instructor", "reply_to": "ops-0009", "text": "Proposed: wind from NE (45°), 8 m/s, 60 s, ramp 10 s.",
  "tool_calls": ["propose_wind"],
  "proposal": {"command": "set_wind", "params": {"from_deg": 45.0, "speed_mps": 8.0, "ramp_s": 10.0, "duration_s": 60.0},
               "defaults_used": ["duration_s", "ramp_s"]} }
```

## 5. WebSocket (`ws://127.0.0.1:8100/ws`)
Mensajes JSON con el campo `op`.

Cliente → plataforma:
| `op` | Campos | Qué hace |
|---|---|---|
| `hello` | `client: "web" \| "ai-module"` | Primer mensaje |
| `subscribe` | `patterns: ["citadel.pub.evt.>"]` | Se suscribe (acumula) |
| `publish` | `event` (sobre sin `seq` ni `ingestion_time`) | Publica en el bus. La plataforma valida el sobre y rechaza topics que no sean de ese cliente (web: solo `ops`; módulo de IA: solo `ai`) |
| `truth_feed` | `active: true \| false` | **Solo clientes `web`** (otro tipo → `error`: "only clients of type web can receive the truth"). Con `true`, la plataforma empieza a enviarle mensajes `truth` (ver abajo); con `false` los deja. Apagado por defecto y por conexión |
| `control` | **Solo clientes `web`**: si lo manda otro tipo de cliente (p. ej. `ai-module`), la plataforma responde `error` ("only clients of type web can send control") y no hace nada. Si el módulo de IA necesita una señal para el reproductor, se define como mensaje propio en este documento, no como `control` genérico. `action: "load" \| "play" \| "pause" \| "step" \| "reset" \| "speed" \| "interactive" \| "fault"`, `value` | `load` con nombre de escenario (si no está generado, la plataforma lo genera antes de cargarlo); `speed` con 0.5/1/2/4/8/16; `interactive` con `true`/`false` (modo interactivo, apagado por defecto; se puede cambiar en cualquier momento y queda registrado en el timeline con `InteractiveModeChanged`; **cada `load` y `reset` lo apaga**, así que hay que volver a encenderlo después de cargar); `fault` con `{"source": "gps", "mode": "loss", "active": true}` (activa o termina un fallo desde el instante actual; `loss` solo para `gps`; el GPS acepta `loss` y `mute` a la vez, cualquier otra fuente un solo fallo: activar un segundo fallo en ella, o repetir el mismo modo, devuelve `error`). **`fault` solo se acepta con el modo interactivo encendido**: apagado, la plataforma responde `error` ("interactive mode is off: turn it on to inject faults") y no cambia nada. Un fallo programado por el escenario acaba solo: no se puede terminar a mano |

**`control` → `instructor` (v0.18):** `value` es `{"command": "set_wind", "params": {"from_deg": 0.0, "speed_mps": 12.0, "ramp_s": 10.0, "duration_s": 60.0}, "issued_by": "panel", "text": null}` (`cancel_wind` con `params: null`; `issued_by` `panel` o `llm`, y con `llm` el `text` es obligatorio). Solo clientes `web` y **solo con el modo interactivo encendido** (apagado: `error` «interactive mode is off: turn it on to send instructor commands»). Aplica el comando desde el instante actual y publica `InstructorCommand`; un valor fuera de rango, o un `cancel_wind` sin viento del instructor en curso, devuelve `error`.

Plataforma → cliente:
| `op` | Campos |
|---|---|
| `event` | `event` (sobre completo) |
| `state` | `status: "idle" \| "running" \| "paused" \| "finished"`, `scenario`, `run_id`, `sim_time`, `speed`, `interactive`, `active_faults` (lista de objetos con `source`, `mode` y `origin`; el GPS puede aparecer dos veces, con `loss` y con `mute`), `cursor` (eventos publicados hasta ahora), `total_events` (los esperados sin intervenciones; se envía al conectar, al cambiar y cada 0,5 s mientras corre) |
| `truth` | `run_id`, `t`, `x`, `y`, `heading_deg` (rumbo del **morro**), `course_deg` (rumbo sobre el suelo), `speed_mps`: la última muestra real con `t` ≤ `sim_time` actual. **No es un evento**: no tiene sobre ni topic, no pasa por el bus ni va al timeline, y **solo se envía a clientes `web` con `truth_feed` activo** (nunca al módulo de IA). Cada 0,1 s de reloj mientras la simulación corre, al activar el feed y tras `load`, `reset` o `step`. Es para el icono de la posición real de la web; la traza sigue con `GET /truth` |
| `error` | `message` |

## 6. API HTTP (`http://127.0.0.1:8100/api`)
- `GET /scenarios` → `{"scenarios": [{"name": "demo", "description": "…", "generated": true, "duration_s": 556.0}]}`. `generated` = existe `runs/<name>/events.jsonl`; `duration_s` es `null` si no está generado. `load` de un escenario no generado lo genera antes de cargarlo. `GET /state` → como el mensaje `state`.
- `GET /plan` → `plan.json` del escenario cargado (§8.2: waypoints y trayectoria planificada). Lo usa la web.
- `GET /truth` → la verdad de la simulación **en curso** (§8.3: misma forma que `truth.json`, desde 0 hasta el instante actual, con los fallos manuales ya aplicados). **Solo para la capa «verdad» de la web y del visor.** Ninguna tool la usa.
- `GET /timeline?source=&type=&since=&until=&limit=` → un objeto con `events` (lista de sobres completos, por `sim_time` y `seq`; con `limit`, los últimos) y `truncated` (si recortó). Sin corte temporal; es para la web y la evaluación.

## 6 bis. API del simulador por asset (v1.5)
Cara nueva y versionada (`http://127.0.0.1:8100/api/v1`; host y puerto configurables) para quien integre el simulador como plataforma externa: `GET /assets`, `/assets/{id}`, `/assets/{id}/state`, `/assets/{id}/messages` (cursor `seq`), `/assets/{id}/stream` (SSE con `id` = `seq`, `heartbeat` y `gap`), `/exercise/*` (control) y `/instructor/*` (fallos, comandos, *injects*, verdad). Cada mensaje lleva una cabecera propia (`seq`, `run_id`, `asset_id`, `subject`, `type`, `id`, tiempos) y en `data` el payload del evento del §4 sin cambios; un adaptador que lee la API reconstruye los eventos del bus (`tools/sim_api/adapter.py`; prueba de equivalencia en `demo` y en los 11 escenarios). La verdad del ejercicio no sale por los assets. Detalle, ejemplos y OpenAPI en `contracts/api/`.

## 7. Tools
Retirado en la v1.3: no hay API de tools. El monitor de situación y el asistente (E7d) leen solo los eventos del bus (el asistente consulta lo recibido en su propio proceso). Los esquemas de tool del asistente (`agent-assets/*_tools.json`) son suyos, no un contrato entre componentes.

## 8. Ficheros del generador
El generador (`platform/`) lee `scenarios/<nombre>.yaml` y escribe `runs/<nombre>/`: `plan.json`, `truth.json`, `events.jsonl`, `labels.json` y, solo si el escenario tiene episodios de degradación con `labeled: false`, `unlabeled_episodes.json` (v0.19). Modelos en `poc_contracts.scenario` y `poc_contracts.run_files`; esquemas en `contracts/schemas/files/`. Los números de los ficheros JSON van redondeados (posiciones y velocidades a 2 decimales en plan y verdad, a 1 en los eventos).

### 8.1 YAML de escenario (`scenarios/<nombre>.yaml`)
Todos los campos son obligatorios (los que admiten `null` lo dicen; `commands` y los `episodes` de `sensors.gps` y `sensors.link` son opcionales); no se admiten campos desconocidos. `name` debe coincidir con el nombre del fichero. Ejemplo completo:
```yaml
name: demo
description: Las tres anomalías en un vuelo.
seed: 42
t0: "2026-10-20T10:00:00Z"        # event_time = t0 + sim_time (ISO 8601 UTC, segundos enteros)
max_duration_s: 900              # si se alcanza: MissionCompleted con completed false y reason timeout
drone: {cruise_speed_mps: 15.0, max_accel_mps2: 2.0, max_turn_rate_dps: 40.0, altitude_m: 60.0,
        acceptance_radius_m: 25.0, lookahead_m: 40.0,
        wind_limit_mps: 12.0, max_airspeed_mps: 17.0, lateral_ki_per_s: 0.05,
        estimator_position_gain: 0.6, estimator_wind_gain: 0.5,
        link_loss_timeout_s: 10.0, link_loss_action: continue, land_duration_s: 20.0}   # opcionales (v1.0)
mission:
  id: MSN-DEMO
  controller_id: GCS-1           # opcional (v1.0; por defecto GCS-1): `MissionPlanned.mission_controller_id`
  waypoints: [{id: WP1, x: 500.0, y: 1200.0}, {id: WP2, x: 1600.0, y: 1500.0}]
  return_to_base: true           # obligatorio; por ahora solo se admite true
sensors:
  gps: {period_s: 1.0, sigma_m: 1.5, sats: 14, hdop: 0.8}   # v1.0, opcionales: gm_sigma_m, gm_tau_s, white_sigma_m; v1.2: cn0_nominal_dbhz (45.0) y agc_nominal_db (0.0)
  radar: {period_s: 2.0, sigma_m: 5.0}   # v1.0, opcionales: x, y, sigma_per_km_m, max_range_m
  meteo: {period_s: 10.0, sigma_mps: 0.5, sigma_deg: 8.0}   # v1.0, opcionales: factor, lag_s
  link: {period_s: 5.0, rssi_dbm: -62.0, latency_ms: 45.0}   # v1.0 (`rssi_dbm`: el de 1 km de la base), opcionales: rssi_floor_dbm, loss_rssi50_dbm, loss_slope_db
  battery: {period_s: 10.0, start_pct: 100.0}   # v1.0, opcionales: capacity_wh, hover_power_w, efficiency, return_reserve, failsafe_return_pct, failsafe_land_pct, endurance_action
wind:
  base: {speed_mps: 2.0, from_deg: 300.0}
  episodes: [{start_s: 95.0, end_s: 150.0, ramp_s: 10.0, speed_mps: 12.0, from_deg: 350.0}]
spoofing: {start_s: 168.0, end_s: 222.0, drift_rate_mps: 1.5, direction_deg: 45.0}   # o null
hijack:                                                                              # o null
  start_s: 335.0
  end_s: 380.0                   # o null: el control no se recupera
  target: {x: 1500.0, y: -1400.0}   # posición de la estación del secuestrador
faults: [{source: radar, mode: mute, start_s: 120.0, end_s: 180.0}]   # lista, puede estar vacía
emitters: []                     # opcional (v1.0): emisores de interferencia {id, x, y, power_db, start_s, end_s}; `spoofing.emitter` {x, y, power_db}
labeling: {wind_notable_over_limit: 0.4, gps_sigma_bad_m: 5.0, link_latency_bad_ms: 100.0, link_loss_bad_pct: 20.0,
          deviated_m: 25.0, returning_m: 15.0, battery_low_pct: 15.0, battery_critical_pct: 7.0}   # opcional (v1.0): umbrales de las etiquetas de `states.jsonl`
commands:                        # opcional (v0.18; por defecto, vacía): comandos del instructor programados
  - {at_s: 95.0, command: set_wind, params: {from_deg: 350.0, speed_mps: 12.0, ramp_s: 10.0, duration_s: 60.0}}
```
`faults[].mode`: `mute` | `loss` (`loss` solo con `source: gps`). `commands[]` (v0.18): `at_s`, `command` (`set_wind` | `cancel_wind`) y `params` (los de §4 «`InstructorCommand`»); se aplican en `at_s` con `issued_by: scenario`, y un `cancel_wind` sin viento del instructor en curso es un error al generar. Significado de cada bloque en `scenarios/README.md`. Las desviaciones típicas de lo que no sale del YAML (altitud, velocidad y rumbo del GPS, calidad del radar, RSSI, latencia, batería) son constantes del generador.

**Episodios de degradación (v0.19).** `sensors.gps.episodes` y `sensors.link.episodes` (listas opcionales; por defecto, vacías) degradan una fuente durante una ventana:
```yaml
sensors:
  gps:
    period_s: 1.0
    sigma_m: 1.5
    sats: 14
    hdop: 0.8
    episodes: [{start_s: 150.0, end_s: 210.0, ramp_s: 10.0, sats: 4, hdop: 9.0}]
  link:
    period_s: 5.0
    rssi_dbm: -62.0
    latency_ms: 45.0
    episodes: [{start_s: 330.0, end_s: 390.0, latency_ms: 250.0, rssi_dbm: -85.0, labeled: false}]
```
Campos comunes: `start_s` (≥ 0), `end_s` (> `start_s`), `ramp_s` (≥ 0, por defecto 0: el valor cambia de golpe; con rampa, sube y baja como un episodio de viento: nivel `min(1, (t − start_s)/ramp_s, (end_s − t)/ramp_s)`) y `labeled` (por defecto `true`). GPS: `sats` (entero, ≥ 4) y `hdop` (> 0), al menos uno; el `fix` sigue en `3d` (perderlo es el fallo `loss`, que manda si coincide con un episodio). Enlace: `latency_ms` (≥ 0) y `rssi_dbm`, al menos uno; un secuestro es enlace caído y manda sobre el episodio. Lo que no se dé se queda en el valor nominal. Los episodios de una misma fuente no se pueden solapar. Un episodio solo cambia el valor sobre el que se publica la medida (el ruido del enlace se suma igual que siempre; `sats` y `hdop` del GPS no llevan ruido) y no saca números aleatorios nuevos, así que un escenario sin episodios genera exactamente lo mismo que antes.

### 8.2 `plan.json`
Vuelo del mismo controlador **sin** viento, spoofing, secuestro ni ruido. Lleva además `radar` (`x`, `y`, `max_range_m`: para pintarlo en el mapa). `waypoints` es la misma lista que `MissionPlanned` (con la base al final); `trajectory`, una muestra por segundo más la última (`t`, `x`, `y`, `speed_mps` respecto al suelo, `heading_deg`). Ejemplo (recortado: el real trae una muestra por segundo hasta `duration_s`):
```json
{ "mission_id": "MSN-DEMO", "cruise_speed_mps": 15.0, "altitude_m": 60.0, "acceptance_radius_m": 25.0,
  "duration_s": 435.3,
  "waypoints": [ {"id": "BASE", "x": 0.0, "y": 0.0, "eta_s": 0.0},
                 {"id": "WP1", "x": 500.0, "y": 1200.0, "eta_s": 88.8},
                 {"id": "BASE", "x": 0.0, "y": 0.0, "eta_s": 435.3} ],
  "trajectory": [ {"t": 0.0, "x": 0.0, "y": 0.0, "speed_mps": 0.0, "heading_deg": 22.62},
                  {"t": 1.0, "x": 0.42, "y": 1.02, "speed_mps": 2.0, "heading_deg": 22.62} ] }
```

### 8.3 `truth.json`
La trayectoria real, el viento real y el resto de la **verdad ampliada** (v1.0), una muestra por segundo más la última (en `GET /truth`, hasta el instante actual). **El agente nunca la ve**; lo usan las gráficas, la evaluación, las etiquetas por faceta y la capa «verdad» de la web. `heading_deg` es el rumbo del morro; `course_deg`, el rumbo sobre el suelo (distintos cuando hay viento); `speed_mps`, la velocidad sobre el suelo. Verdad ampliada: `leg_index` (índice del waypoint pendiente en la ruta), `ref_dist_m` (distancia real a la **referencia del modo**: el tramo pendiente en misión; se mide al segmento, no a la recta), `est_x`/`est_y` (estima del dron), `mode` (modo del autopiloto: `mission` | `failsafe_return` | `failsafe_hold` | `failsafe_land` | `foreign_control`), `link_up` (llegan los paquetes del dron a nuestra estación), `battery_soc` (carga real, %), `gps_sigma_m` (σ real de la posición del receptor: la del YAML escalada por el `hdop` efectivo), `cn0_dbhz` (C/N0 real) y `emitters_active` (ids de los emisores activos). `emitters`: lista estática de emisores y estaciones ajenas con posición (`id`, `kind` = `spoofer` | `jammer` | `hijacker`, `x`, `y`; con `simulator.emitters`; la estación del secuestrador está en el `target` del secuestro). `emitters_active`: los activos en ese instante. En `wind`, `from_deg` es la procedencia.
```json
{ "duration_s": 556.3,
  "trajectory": [ {"t": 1.0, "x": 2.12, "y": 0.03, "speed_mps": 2.57, "heading_deg": 20.1, "course_deg": 70.05,
                   "leg_index": 1, "ref_dist_m": 1.3, "est_x": 2.12, "est_y": 0.03, "mode": "mission",
                   "link_up": true, "battery_soc": 99.9, "gps_sigma_m": 1.5, "cn0_dbhz": 45.0, "emitters_active": [] } ],
  "wind": [ {"t": 0.0, "speed_mps": 2.0, "from_deg": 300.0} ],
  "emitters": [] }
```

### 8.4 `labels.json`
Una etiqueta por anomalía (`A1`, `A2`… por orden de inicio: viento por episodio, spoofing, secuestro) y por fallo programado, `mute` o `loss`, o episodio de degradación etiquetado (`F1`, `F2`… por orden de inicio, fallos y degradaciones juntos). Solo para evaluar. Campos: `type` (`wind` | `hijack` | `gps_spoofing` | `source_silent` | `gps_loss` | `gps_degraded` | `link_degraded`), `source` (la fuente en fallo o degradada; `null` si no es de una fuente), `start_s`, `end_s` (en un secuestro sin fin, el fin de la misión), `expected_rules` (reglas del detector que se esperan en la ventana; basta con que salte una), `expected_cause`, `also_accepted_causes` (otras causas que también cuentan como acierto; casi siempre vacía) y `eval_window` (de `start_s` a `end_s` más 60 s: una alerta con la causa esperada dentro de la ventana cuenta como acierto). En el spoofing las reglas esperadas son `SOURCE_DISCREPANCY` y también `ROUTE_DEVIATION`, porque al acabar el engaño el GPS salta a la verdad, lejos de la ruta. **Ese `ROUTE_DEVIATION` es esperado:** en la evaluación cuenta como acierto si el monitor lo atribuye a `GPS_SPOOFING` (recuperación tras el engaño) y como fallo de diagnóstico si lo atribuye a otra causa. **Un viento puesto por un comando del instructor genera su etiqueta de viento** (`wind`, `ROUTE_DEVIATION`, causa `WIND`) con la ventana del comando: del `set_wind` a su fin por duración, por el siguiente comando (otro `set_wind` o un `cancel_wind`) o por el fin del vuelo. Si el comando está programado, la escribe el generador (`A…`, con los episodios del YAML); si es en directo, la evaluación la saca de los `InstructorCommand` de la ejecución (`A101`…, solo con `issued_by` distinto de `scenario`), igual que las de los fallos manuales. Ningún agente ve las etiquetas. El secuestro espera también `LINK_ANOMALY` (v0.16: el cambio del controlador del enlace salta antes que la desviación de la ruta) además de `ROUTE_DEVIATION`. Un fallo `loss` (`gps_loss`) espera `GPS_DEGRADED`, `SOURCE_DISCREPANCY` y `ROUTE_DEVIATION` (por lo mismo: al recuperarse, el GPS salta a la real), `expected_cause: GPS_JAMMING` y `also_accepted_causes: ["SENSOR_FAULT"]`; su `ROUTE_DEVIATION` se evalúa como el del spoofing (acierto con `GPS_JAMMING` o `SENSOR_FAULT`). **Degradaciones (v0.19):** `gps_degraded` (`source: gps`) espera `GPS_DEGRADED`, `expected_cause: SENSOR_FAULT` y `also_accepted_causes: ["GPS_JAMMING"]`, sin frontera por magnitud; `link_degraded` (`source: link`) espera `LINK_ANOMALY`, `expected_cause: SENSOR_FAULT` y `also_accepted_causes: ["UNKNOWN"]` (`HIJACK` es un fallo de diagnóstico). Una degradación **termina donde empieza lo que la anula en el generador** (la pérdida de GPS para `gps_degraded`, el secuestro para `link_degraded`): si eso ya está activo al empezar, la etiqueta empieza cuando termina, y si lo cubre entero, no hay etiqueta (lo mismo para la ventana de un episodio sin etiqueta). Un episodio con `labeled: false` no tiene etiqueta: va a `unlabeled_episodes.json` (`{"episodes": [{"id": "U1", "source": "gps", "start_s": 250.0, "end_s": 300.0, "rules": ["GPS_DEGRADED"], "eval_window": [250.0, 360.0]}]}`, `U1`… por orden de inicio; `rules`, las reglas que miden esa fuente). La evaluación cuenta aparte lo que pasa en su ventana: los avisos de esas reglas son informativos (no son falsas alarmas) y una alerta con causa de ataque (`GPS_SPOOFING`, `GPS_JAMMING`, `HIJACK`) o `WIND` sí es una falsa alarma; `SENSOR_FAULT` o `UNKNOWN`, no. Ningún agente ve el fichero.
```json
{ "labels": [ { "id": "A1", "type": "wind", "source": null, "start_s": 95.0, "end_s": 150.0,
                "expected_rules": ["ROUTE_DEVIATION"], "expected_cause": "WIND", "also_accepted_causes": [],
                "eval_window": [95.0, 210.0] },
              { "id": "F1", "type": "source_silent", "source": "radar", "start_s": 120.0, "end_s": 180.0,
                "expected_rules": ["SOURCE_SILENT"], "expected_cause": "SENSOR_FAULT", "also_accepted_causes": [],
                "eval_window": [120.0, 240.0] } ] }
```

**Lo que la evaluación cuenta aparte (E6; no cambia el formato de las etiquetas):** un aviso con dos o más etiquetas candidatas (ventanas solapadas que esperan su regla) es **ambiguo** y no cuenta como acierto ni como fallo; un `ROUTE_DEVIATION` entre el fin de la `eval_window` de un secuestro y la vuelta real del dron a la ruta (la primera muestra de `truth.json` a 10 m o menos de la ruta de `plan.json`) es **dudoso** y no es falsa alarma; y, con la opción `--honest-unknown`, una alerta `UNKNOWN` sobre una etiqueta cuya causa necesita una fuente callada en ese instante por un fallo programado (la estación para `WIND`, el radar para `GPS_SPOOFING`, el enlace para `HIJACK`) es un **«`UNKNOWN` honesto»**, también aparte.

### 8.5 `events.jsonl`
Un `EventDraft` (§2, sin `seq` ni `ingestion_time`) por línea, ordenado por `sim_time` y, a igualdad de instante, así: misión, fallos, comandos del instructor, GPS, receptor GNSS, autopiloto, radar, meteo, enlace, batería. **Es lo que produce el simulador en directo de la plataforma ejecutado hasta el final sin intervenciones** (mismo código, paso de 0,1 s): el reproductor en directo, sin intervenciones y con el modo interactivo apagado, publica exactamente estos eventos. Para eso, el ruido de todas las fuentes se saca siempre en el mismo orden (por instante: GPS, radar, meteo, enlace, batería), aunque una fuente esté silenciada o en pérdida.
- **Ids:** los de las fuentes llevan el número de orden de la medición (`gps-000061` es la que cae en t = 61 s), así que un fallo programado deja huecos en la numeración, igual que lo haría uno manual. Los de misión (`mis-`), los de fallos (`sim-`) y los de comandos (`cmd-`) son secuenciales. **Numeración:** los fallos (programados y manuales) los numera el simulador por orden de aparición (`sim-0001`…); el estado del reproductor (`SimulationStarted`…, `InteractiveModeChanged`) usa `plr-` y no está en `events.jsonl`.
- **Fallos programados:** (si un fallo manual del mismo modo ya está activo en esa fuente, o la fuente no es el GPS y ya tiene cualquier fallo, el programado se omite; el GPS admite dos fallos de modos distintos, sean programados o manuales, en cualquier combinación) en `[start_s, end_s)`, una fuente en `mute` no publica y el GPS en `loss` publica la posición estimada sin fix (§4); se escriben `FaultInjected` en `start_s` y `FaultCleared` en `end_s` (`origin: scenario`). Un `mute` no cambia el ruido de nada: con la misma semilla, un escenario con silenciados tiene los mismos eventos que el equivalente sin ellos, menos los silenciados. Un `loss` cambia la trayectoria real y, desde su inicio, todo lo que depende de ella (GPS y radar).
- **Fin del vuelo:** las fuentes dejan de emitir al terminar la misión; `MissionCompleted` lleva el `sim_time` de ese instante. Un fallo o una anomalía que acabaría después se recorta al fin de la misión (`FaultCleared` y el `end_s` de su etiqueta); uno que empezaría después no se escribe.
- **Determinismo:** misma semilla y mismo YAML, ficheros idénticos byte a byte.

### 8.6 `run_meta.json`
Lo escribe **la plataforma** en `runs/<escenario>/<run_id>/` (junto al `timeline.jsonl`), no el comando que lance la ejecución, así que existe también cuando se maneja desde la web. Modelo `poc_contracts.run_files.RunMeta`, esquema en `contracts/schemas/files/run_meta.json`. Se crea en el primer `play` o `step` con los valores de ese instante (velocidad y modo interactivo), se reescribe en cada cambio durante la ejecución (`*_changes`, con el `sim_time` del cambio; los anteriores al primer play no cuentan) y al volcar el timeline. La evaluación lo pone en la cabecera de `eval.md`. No lleva la duración en reloj: la saca del timeline.
```json
{ "scenario": "demo", "run_id": "20261022-110035", "speed": 4.0, "speed_changes": [{"sim_time": 120.0, "value": 8.0}],
  "interactive": false, "interactive_changes": [] }
```

### 8.7 `states.jsonl` (v1.0)
El estado de cada **faceta** por segundo, escrito por el generador a partir de la verdad ampliada y del YAML (no por un script aparte). Una línea por segundo (`StateRow`, `poc_contracts.states`, esquema en `contracts/schemas/files/states_row.json`): `facets` (todas las facetas del catálogo) y `hidden` (el estado que habría tenido cada faceta con `?`). **Solo para el generador, la evaluación y la vista del instructor: el agente nunca lo ve.** La etiqueta empieza con el suceso; el retraso en detectarlo se mide aparte.

| Entidad | Faceta | Estados |
|---|---|---|
| GPS | `gps.availability` | `normal`, `no_data`, `no_fix` |
| | `gps.quality` | `good`, `degraded` |
| | `gps.integrity` | `reliable`, `spoofed` |
| Radar | `radar.availability` | `normal`, `no_data`, `out_of_range` |
| Enlace | `link.availability` | `connected`, `lost` |
| | `link.quality` | `good`, `degraded` |
| Estación | `meteo.availability` | `normal`, `no_data` |
| Batería | `battery.availability` | `normal`, `no_data` |
| | `battery.level` | `normal`, `low`, `critical` |
| | `battery.endurance` | `sufficient`, `cannot_reach_home` |
| Entorno | `environment.wind` | `calm`, `notable`, `beyond_limit` |
| Dron | `drone.mode` | `mission`, `failsafe_return`, `failsafe_hold`, `failsafe_land`, `foreign_control` |
| | `drone.situation` | `on_route`, `deviated`, `returning` |
| | `drone.cause` | `foreign_control`, `spoofed_position`, `dead_reckoning`, `wind`, `unexplained` |

Reglas (umbrales en el bloque `labeling` del YAML, ⚠️ de partida):
- **`n/a`** (no aplica) y **`?`** (no observable) valen en cualquier faceta. Con la disponibilidad de una entidad distinta de `normal` (o `connected`), sus demás facetas valen `n/a`.
- **`?`**: toda la telemetría del dron (las facetas del GPS y de la batería) con el enlace perdido; el estado real queda en `hidden`. Las facetas del dron (`drone.*`) nunca valen `?`: son lo que el monitor tiene que inferir. Radar, estación y entorno no dependen del enlace.
- **Calidad por valor físico**, no por la ventana del episodio: `gps.quality` = `degraded` si la σ real de la posición supera `gps_sigma_bad_m`; `link.quality` = `degraded` si la latencia supera `link_latency_bad_ms` o los paquetes perdidos `link_loss_bad_pct`.
- **Viento** (medio, en el dron, sin racha): `calm` por debajo de `wind_notable_over_limit` × `drone.wind_limit_mps` (0,4 × el límite: 4,8 m/s con el Matrice 300; v1.2, antes 5 m/s absolutos), `notable` hasta `drone.wind_limit_mps`, `beyond_limit` desde ahí.
- **Batería:** `level` = `low` por debajo del 15 %, `critical` por debajo del 7 %; `endurance` = `cannot_reach_home` si la energía que queda no alcanza para volver a casa con el viento actual.
- **Situación** respecto a la referencia del modo: `deviated` por encima de `deviated_m` (25 m); vuelve a `on_route` por debajo de `returning_m` (15 m); entre medias, `returning` si venía de `deviated` y ya no hay ninguna causa activa.
- **Causa** solo con situación distinta de `on_route` (con `on_route` vale `n/a`). Prioridad: `foreign_control` > `spoofed_position` > `dead_reckoning` > `wind` > `unexplained`, entre las causas activas. Es **pegajosa**: en `returning` se mantiene la del último `deviated`; si el dron vuelve a desviarse con otra causa activa, la sustituye. `unexplained` (desviado sin ninguna causa activa) **no es una etiqueta de la verdad**: es un aviso para quien escribe el escenario, y debe valer 0 instantes (el sistema dirá «sin determinar» cuando la confianza sea baja).
- El `mode` y la `situation` se miden **respecto a la referencia del modo**: un failsafe de vuelta bien ejecutado es `on_route`.
```json
{"t": 168, "facets": {"gps.availability": "normal", "gps.quality": "good", "gps.integrity": "spoofed", "radar.availability": "normal", "link.availability": "connected", "link.quality": "good", "meteo.availability": "normal", "battery.availability": "normal", "battery.level": "normal", "battery.endurance": "sufficient", "environment.wind": "calm", "drone.mode": "mission", "drone.situation": "on_route", "drone.cause": "n/a"}, "hidden": {}}
```
