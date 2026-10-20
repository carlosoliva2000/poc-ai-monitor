# Contratos de `poc-ai-monitor`

> **Fuente de verdad** de lo que se intercambian los componentes: eventos, topics, mensajes del WebSocket, API HTTP y tools. Versión 0.5 (20/10/2026: simulación en directo y modo interactivo; tipo de fallo `mute`/`loss` (pérdida de GPS) en `control` → `fault`, en `FaultInjected`/`FaultCleared`, en `faults` del YAML y en `state` (`active_faults`, `interactive`); regla `GPS_DEGRADED`, causa `GPS_JAMMING`, evento `InteractiveModeChanged` (ids `plr-` para el estado del reproductor); v0.4: ficheros del generador y YAML de escenario (§8), la ruta de `MissionPlanned` incluye la vuelta a la base; v0.3: `source` y `asset` del sobre, `fix`, `GET /scenarios`, resultado de `get_flight_summary` y `get_track_metrics` sin datos de una fuente, patrón de suscripción de ejemplo corregido en §3; v0.2, 16/10/2026: fallos manuales y regla `SOURCE_SILENT`). Cualquier cambio se hace aquí primero y después en `contracts/python` (Pydantic), `contracts/schemas/` (JSON Schema exportado) y en todos los componentes, en el mismo cambio.

## 1. Convenciones
- **Unidades:** metros, segundos, m/s, grados. Plano x,y con origen en la base: **x hacia el este, y hacia el norte**.
- **Ángulos:** rumbos en grados 0–360, **0 = norte, 90 = este** (sentido horario). El viento se da por **dirección de procedencia** (convención meteorológica): `from_deg: 0` es viento del norte, que empuja hacia el sur.
- **Tiempo:** `sim_time` (s desde el inicio de la simulación, float); `event_time` = `t0` del escenario + `sim_time`, en ISO 8601 UTC; `ingestion_time` lo pone el bus con el reloj de pared, ISO 8601 UTC con milisegundos.
- **Ids:** prefijo por fuente y número con ceros: `gps-000061`, `rad-000030`, `met-0006`, `lnk-0012`, `bat-0006`, `mis-0003`, `det-0001`, `ai-0001`, `ops-0001`, `sim-0001` (fallos), `plr-0001` (estado del reproductor). Únicos en una ejecución.
- **Nombres de campos** en `snake_case`. Textos para personas, en español.

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
- `source`: quién publica. Generador: `d1-gps`, `radar-1`, `meteo-1`, `d1-link`, `d1-bat`, `d1-mission`. Reproductor (estado, modo interactivo y `FaultInjected`/`FaultCleared`): `platform-player`. Módulo de IA: `ai-detector` (detecciones), `ai-monitor` (`AnomalyDetected`, `AlertClosed`), `ai-report` (`ReportGenerated`), `ai-chat-monitor` / `ai-chat-report` (`AgentReply`, `AgentReplyChunk`), `ai-module` (`AgentActivity`). Web (`OperatorMessage`): `web-operator`.
- `asset`: `"d1"` en los topics `air.d1` y `ai.d1`; `"zone1"` en `env.zone1`; `null` en el resto (`sim`, `ops`, `ai.monitor`, `ai.report`, `ai.agent`).
- `seq`: orden global de publicación en la ejecución (lo pone el bus).
- `causation_id`: id del evento que provocó este (p. ej. la detección que provocó una alerta). `null` si no aplica.
- `ephemeral: true` solo para trozos de streaming del chat: se reenvían por el WebSocket pero **no** se guardan en el timeline.
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
| `citadel.pub.evt.air.d1.MissionPlanned.v1`, `.MissionStarted.v1`, `.WaypointReached.v1`, `.MissionCompleted.v1` | Misión | Reproductor |
| `citadel.pub.evt.sim.player.SimulationStarted.v1`, `.SimulationPaused.v1`, `.SimulationResumed.v1`, `.SimulationFinished.v1`, `.SimulationReset.v1`, `.InteractiveModeChanged.v1` | Estado del reproductor y modo interactivo. **El agente no los ve** | Plataforma |
| `citadel.pub.evt.sim.player.FaultInjected.v1`, `.FaultCleared.v1` | Fallo activado o terminado: fuente silenciada (`mute`) o pérdida de GPS (`loss`), manual o programado. **El agente no los ve** | Plataforma |
| `citadel.pub.evt.ai.d1.DetectionRaised.v1`, `.DetectionUpdated.v1`, `.DetectionCleared.v1` | Detector de reglas | Módulo de IA |
| `citadel.pub.evt.ai.d1.AnomalyDetected.v1`, `.AlertClosed.v1` | Agente monitor | Módulo de IA |
| `citadel.pub.evt.ai.d1.ReportGenerated.v1` | Agente de informe | Módulo de IA |
| `citadel.pub.evt.ops.monitor.OperatorMessage.v1`, `citadel.pub.evt.ops.report.OperatorMessage.v1` | Pregunta del operador a cada agente | Web |
| `citadel.pub.evt.ai.monitor.AgentReply.v1`, `citadel.pub.evt.ai.report.AgentReply.v1` | Respuesta completa del chat | Módulo de IA |
| `citadel.pub.evt.ai.monitor.AgentReplyChunk.v1`, `citadel.pub.evt.ai.report.AgentReplyChunk.v1` | Trozo de respuesta en streaming (`ephemeral`) | Módulo de IA |
| `citadel.pub.evt.ai.agent.AgentActivity.v1` | Aviso de que un agente empieza o termina una invocación (`ephemeral`), para la web | Módulo de IA |

Suscripciones con comodines: `*` = un segmento, `>` = el resto. Ejemplos: `citadel.pub.evt.air.d1.>` (todo lo del dron), `citadel.*.evt.ai.d1.Detection*` **no vale** (los comodines van por segmento entero); usa `citadel.pub.evt.ai.d1.>` (o `citadel.pub.evt.ai.d1.*.v1`) y filtra por `type`. Ojo: los topics tienen siete segmentos (el último es la versión), así que `citadel.pub.evt.ai.d1.*` **no casa con nada**.

## 4. Eventos (payload)

### Del escenario
**`MissionPlanned`** (`mis-`, `sim_time: 0`)
```json
{ "mission_id": "MSN-DEMO", "cruise_speed_mps": 15.0, "altitude_m": 60.0, "acceptance_radius_m": 20.0,
  "waypoints": [ {"id": "BASE", "x": 0.0, "y": 0.0, "eta_s": 0.0},
                 {"id": "WP1", "x": 400.0, "y": 900.0, "eta_s": 66.5} ] }
```
`waypoints` es la ruta completa: la base (`BASE`), los waypoints y **otra vez la base** como último punto (la vuelta); `eta_s` es el instante previsto de llegada en un vuelo sin perturbaciones. La polilínea de esos puntos es la ruta planificada con la que se mide la desviación. El índice de `WaypointReached` es la posición en esa lista (`BASE` = 0; la llegada final a la base lleva el último índice).

**`MissionStarted`** `{ "mission_id": "MSN-DEMO" }` · **`WaypointReached`** `{ "waypoint_id": "WP2", "index": 2 }` (lo decide el dron con su GPS) · **`MissionCompleted`** `{ "mission_id": "MSN-DEMO", "completed": true, "reason": "returned_to_base" }` (`reason`: `returned_to_base` | `timeout`)

**`PositionUpdated`** (`gps-`, cada 1 s)
```json
{ "x": 512.3, "y": 140.8, "alt_m": 60.2, "speed_mps": 15.1, "heading_deg": 81.0, "fix": "3d", "sats": 14, "hdop": 0.8 }
```
`speed_mps` y `heading_deg` son los de navegación del propio dron (respecto al suelo, según su GPS). `fix`: `"none"` | `"2d"` | `"3d"`; `sats`: entero; `hdop`: decimal. En vuelo normal: `"3d"`, 14 satélites, `hdop` 0,8. **Durante una pérdida de GPS** (`loss`, §4 «Del reproductor») el dron sigue publicando `PositionUpdated` con su **posición estimada** (navega a estima), `fix: "none"`, `sats: 0` y `hdop` alto (99,9):
```json
{ "x": 498.7, "y": 902.1, "alt_m": 60.1, "speed_mps": 14.9, "heading_deg": 12.0, "fix": "none", "sats": 0, "hdop": 99.9 }
```
Al recuperarse, la posición salta a la real.

**`TrackUpdated`** (`rad-`, cada 2 s) `{ "radar_id": "radar-1", "x": 505.0, "y": 151.2, "speed_mps": 14.2, "course_deg": 83.0, "quality": 0.9 }`

**`WindReported`** (`met-`, cada 10 s) `{ "station_id": "meteo-1", "speed_mps": 4.2, "gust_mps": 6.0, "from_deg": 350.0 }`

**`LinkStatus`** (`lnk-`, cada 5 s) `{ "controller_id": "GCS-1", "rssi_dbm": -62.0, "latency_ms": 45.0 }`

**`BatteryStatus`** (`bat-`, cada 10 s) `{ "battery_pct": 87.5, "voltage_v": 22.9 }`

### Del reproductor
**`SimulationStarted`** `{ "scenario": "demo", "run_id": "20261020-101500", "duration_s": 420.0, "total_events": 913 }` (`duration_s` y `total_events` son los de la ejecución **sin intervenciones**, los de `runs/<escenario>/`; con fallos manuales la ejecución real puede ser distinta) · **`SimulationPaused`** `{ "reason": "user" }` (`reason`: `user` | `waiting_agent`; un paso con la simulación aún sin arrancar también la publica, para que el siguiente `play` publique su `SimulationResumed`) · **`SimulationResumed`** `{}` · **`SimulationFinished`** `{ "scenario": "demo", "run_id": "…" }` · **`SimulationReset`** `{}`

**`InteractiveModeChanged`** (`plr-`) `{ "interactive": true }`: el modo interactivo (que permite inyectar fallos en directo) se enciende o se apaga.

**`FaultInjected`** / **`FaultCleared`** (`sim-`) `{ "source": "radar", "mode": "mute", "origin": "manual" }` (`source`: `gps` | `radar` | `meteo` | `link` | `battery`; `mode`: `mute` | `loss`; `origin`: `manual` | `scenario`). Dos tipos de fallo: **`mute`** (cualquier fuente): la fuente deja de publicarse y el dron vuela igual. **`loss`** (solo `gps`): el dron navega a estima: integra su velocidad respecto al aire (sin conocer el viento), el controlador sigue el plan con esa estimación (puede dar por alcanzado un waypoint que no ha alcanzado) y la trayectoria real se va desviando; mientras dura, el GPS publica `PositionUpdated` con la posición estimada, `fix: "none"`, `sats: 0` y `hdop` alto; al recuperarse, la posición salta a la real y el controlador corrige. Una fuente solo puede tener un fallo a la vez. El enlace de mando, el radar, la meteo y la batería solo admiten `mute`.

### Del detector (módulo de IA)
**`DetectionRaised`** / **`DetectionUpdated`** (`det-`)
```json
{ "detection_id": "det-0002", "rule": "ROUTE_DEVIATION", "severity": "medium",
  "value": 34.8, "threshold": 30.0, "unit": "m",
  "source": null,
  "window": {"since": 80.0, "until": 84.0},
  "trigger_event_ids": ["gps-000083", "gps-000084"],
  "message": "La posición del GPS se aleja 34,8 m de la ruta planificada" }
```
`rule`: `ROUTE_DEVIATION` | `SOURCE_DISCREPANCY` | `SOURCE_SILENT` | `GPS_DEGRADED`. `source`: la fuente afectada; obligatoria en `SOURCE_SILENT` (`gps` | `radar` | `meteo` | `link` | `battery`; `value` = segundos sin eventos, `unit: "s"`) y `"gps"` en `GPS_DEGRADED` (`value` = el `hdop` del último `PositionUpdated`, `threshold: 3.0`, `unit: "hdop"`; el `message` dice qué falla: `fix`, `sats` o `hdop`), `null` en las demás. `severity`: `low` | `medium` | `high`. `DetectionUpdated` usa el mismo `detection_id` y una severidad mayor.

Ejemplo de `GPS_DEGRADED`:
```json
{ "detection_id": "det-0004", "rule": "GPS_DEGRADED", "severity": "high",
  "value": 99.9, "threshold": 3.0, "unit": "hdop",
  "source": "gps",
  "window": {"since": 245.0, "until": 245.0},
  "trigger_event_ids": ["gps-000245"],
  "message": "El GPS ha perdido el fix (fix none, 0 satélites, hdop 99,9)" }
```

**`DetectionCleared`** `{ "detection_id": "det-0002", "rule": "ROUTE_DEVIATION", "duration_s": 46.0, "max_value": 71.5 }`

### Del agente monitor
**`AnomalyDetected`** (`ai-`, `causation_id` = la detección que lo provocó)
```json
{ "alert_id": "ai-0003", "detection_ids": ["det-0002"],
  "cause": "WIND", "severity": "low", "confidence": 0.8,
  "summary": "Deriva por viento fuerte del norte; el dron corrige solo",
  "explanation": "Entre T+01:20 y T+01:24 el GPS y el radar coinciden (≤ 6 m) y ambos se alejan 35 m del plan hacia el sur (182°). La estación meteo reporta 14 m/s del norte (met-0008). La deriva va a favor del viento.",
  "recommendation": "Sin intervención. Vigilar que recupera la ruta antes de WP3.",
  "evidence_event_ids": ["gps-000084", "rad-000042", "met-0008"],
  "supersedes": null, "as_of_sim_time": 84.0, "fallback": false }
```
`cause`: `WIND` | `HIJACK` | `GPS_SPOOFING` | `SENSOR_FAULT` | `GPS_JAMMING` | `UNKNOWN` (reservada para el futuro: `REPLAY`). `supersedes`: `alert_id` de una alerta anterior a la que esta sustituye (p. ej. al cambiar la causa). `fallback: true` si lo publicó el módulo porque el agente no concluyó.

**`AlertClosed`** `{ "alert_id": "ai-0003", "reason": "La desviación se ha corregido (det-0002 cerrada)", "as_of_sim_time": 130.0 }`

### Del agente de informe
**`ReportGenerated`** `{ "run_id": "…", "markdown": "# Informe…", "alerts_count": 3 }`

### Del chat
**`OperatorMessage`** (`ops-`) `{ "conversation_id": "monitor", "text": "¿Por qué crees que es viento?" }`
**`AgentReplyChunk`** (`ephemeral: true`) `{ "conversation_id": "monitor", "reply_to": "ops-0004", "delta": "Porque la" }`
**`AgentReply`** `{ "conversation_id": "monitor", "reply_to": "ops-0004", "text": "Porque la estación…", "tool_calls": ["get_events", "get_track_metrics"] }`
**`AgentActivity`** (`ephemeral: true`) `{ "agent": "monitor", "state": "started", "invocation_id": "inv-0007", "causation_id": "det-0002" }` (`agent`: `monitor` | `report` | `chat-monitor` | `chat-report`; `state`: `started` | `finished`)

## 5. WebSocket (`ws://127.0.0.1:8100/ws`)
Mensajes JSON con el campo `op`.

Cliente → plataforma:
| `op` | Campos | Qué hace |
|---|---|---|
| `hello` | `client: "web" \| "ai-module"` | Primer mensaje |
| `subscribe` | `patterns: ["citadel.pub.evt.>"]` | Se suscribe (acumula) |
| `publish` | `event` (sobre sin `seq` ni `ingestion_time`) | Publica en el bus. La plataforma valida el sobre y rechaza topics que no sean de ese cliente (web: solo `ops`; módulo de IA: solo `ai`) |
| `control` | **Solo clientes `web`**: si lo manda otro tipo de cliente (p. ej. `ai-module`), la plataforma responde `error` ("solo los clientes de tipo web pueden enviar control") y no hace nada. Si el módulo de IA necesita una señal para el reproductor (p. ej. para «esperar al agente»), se define como mensaje propio en este documento, no como `control` genérico. `action: "load" \| "play" \| "pause" \| "step" \| "reset" \| "speed" \| "wait_agent" \| "interactive" \| "fault"`, `value` | `load` con nombre de escenario (si no está generado, la plataforma lo genera antes de cargarlo); `speed` con 0.5/1/2/4/8/16; `wait_agent` con `true`/`false`; `interactive` con `true`/`false` (modo interactivo, apagado por defecto; se puede cambiar en cualquier momento y queda registrado en el timeline con `InteractiveModeChanged`); `fault` con `{"source": "gps", "mode": "loss", "active": true}` (activa o termina un fallo desde el instante actual; `loss` solo para `gps`). **`fault` solo se acepta con el modo interactivo encendido**: apagado, la plataforma responde `error` ("el modo interactivo está apagado: actívalo para inyectar fallos") y no cambia nada. Un fallo programado por el escenario acaba solo: no se puede terminar a mano |

Plataforma → cliente:
| `op` | Campos |
|---|---|
| `event` | `event` (sobre completo) |
| `state` | `status: "idle" \| "running" \| "paused" \| "finished"`, `scenario`, `run_id`, `sim_time`, `speed`, `wait_agent`, `interactive`, `active_faults` (lista de objetos con `source`, `mode` y `origin`), `cursor` (eventos publicados hasta ahora), `total_events` (los esperados sin intervenciones; se envía al conectar, al cambiar y cada 0,5 s mientras corre) |
| `error` | `message` |

## 6. API HTTP (`http://127.0.0.1:8100/api`)
- `GET /scenarios` → `{"scenarios": [{"name": "demo", "description": "…", "generated": true, "duration_s": 556.0}]}`. `generated` = existe `runs/<name>/events.jsonl`; `duration_s` es `null` si no está generado. `load` de un escenario no generado lo genera antes de cargarlo. `GET /state` → como el mensaje `state`.
- `GET /plan` → `plan.json` del escenario cargado (§8.2: waypoints y trayectoria planificada). Lo usa la web.
- `GET /truth` → la verdad de la simulación **en curso** (§8.3: misma forma que `truth.json`, desde 0 hasta el instante actual, con los fallos manuales ya aplicados). **Solo para la capa «verdad» de la web y del visor.** Ninguna tool la usa.
- `GET /timeline?source=&type=&since=&until=&limit=` → un objeto con `events` (lista de sobres completos, por `sim_time` y `seq`; con `limit`, los últimos) y `truncated` (si recortó). Sin corte temporal; es para la web y la evaluación.
- `POST /tools/{name}` con el JSON de argumentos → `{"ok": true, "result": …}` o `{"ok": false, "error": "…"}`. **Aplica el corte temporal:** `until` efectivo = mínimo entre lo pedido y el `sim_time` actual.

## 7. Tools
Los esquemas que ve el modelo están en `agent-assets/tools.json` (formato OpenAI). Resultados:

- **`get_events`** → `{"events": [ {"event_id": "met-0008", "type": "WindReported", "sim_time": 80.0, "t": "T+01:20", "speed_mps": 13.8, "gust_mps": 16.2, "from_deg": 352.0} ], "truncated": false}` (cada evento: id, tipo, `sim_time`, `t` y los campos de su payload, sin el resto del sobre). `source` admite `gps`, `radar`, `meteo`, `link`, `battery`, `mission`, `detector`, `monitor`, `operator` (nunca eventos del dominio `sim`: ni estado del reproductor ni fallos). Por defecto `last_n = 10`, máximo 50. Correspondencia con el `source` del sobre: `gps`→`d1-gps`, `radar`→`radar-1`, `meteo`→`meteo-1`, `link`→`d1-link`, `battery`→`d1-bat`, `mission`→`d1-mission`, `detector`→`ai-detector`, `monitor`→`ai-monitor`, `operator`→`web-operator`.
- **`get_mission_plan`** → payload de `MissionPlanned` más `next_waypoint` según los `WaypointReached` hasta ahora.
- **`get_track_metrics(since, until)`** →
```json
{ "since": 60.0, "until": 90.0,
  "gps_deviation_from_plan_m": {"mean": 38.2, "max": 71.5, "trend": "increasing"},
  "radar_deviation_from_plan_m": {"mean": 37.0, "max": 69.8, "trend": "increasing"},
  "gps_radar_distance_m": {"mean": 4.1, "max": 9.0, "trend": "stable"},
  "drift_direction_deg": 182.0,
  "course_deg": {"gps": 95.0, "radar": 96.0},
  "bearing_to_next_waypoint_deg": 71.0, "next_waypoint": "WP2",
  "mean_speed_mps": {"gps": 14.6, "radar": 14.4},
  "samples": {"gps": 30, "radar": 15},
  "gps_available": true, "radar_available": true,
  "last_seen_sim_time": {"gps": 90.0, "radar": 90.0},
  "first_event_ids": ["gps-000060", "rad-000030"], "last_event_ids": ["gps-000090", "rad-000045"] }
```
`trend`: `increasing` | `decreasing` | `stable` (`null` con menos de 3 muestras). `drift_direction_deg`: hacia dónde se aleja del plan (del punto más cercano de la ruta a la posición), con el GPS.

**Sin datos de una fuente en la ventana** no se inventa nada: `gps_available` / `radar_available` son `false`, `samples` lleva el recuento real (0) y `last_seen_sim_time` el `sim_time` del último evento de esa fuente hasta el instante actual (`null` si nunca hubo). Lo que depende de la fuente que falta va a `null`: sin radar, `radar_deviation_from_plan_m`, `gps_radar_distance_m`, `course_deg.radar` y `mean_speed_mps.radar`; sin GPS, `gps_deviation_from_plan_m`, `gps_radar_distance_m`, `course_deg.gps` y `mean_speed_mps.gps`. `drift_direction_deg`, `bearing_to_next_waypoint_deg` y `next_waypoint` salen del GPS: `null` si no hay GPS. Si una fuente tiene muestras solo en parte de la ventana, se calcula con las que haya y `samples` lo refleja. `first_event_ids` / `last_event_ids` solo incluyen las fuentes con muestras.
- **`get_my_alerts(only_open)`** → `{"alerts": [ {"alert_id": "ai-0003", "cause": "WIND", "severity": "low", "confidence": 0.8, "summary": "…", "status": "open", "sim_time": 84.0} ]}` (`status`: `open` | `closed` | `superseded`)
- **`get_flight_summary`** (solo informe) →
```json
{ "mission_id": "MSN-DEMO", "duration_s": 556.0,
  "mission_completed": true, "completion_reason": "returned_to_base",
  "distance_m": {"gps": 7480.5, "radar": 7512.0},
  "waypoints_planned": ["WP1", "WP2", "WP3", "WP4"],
  "waypoints_reached": [{"waypoint_id": "WP1", "sim_time": 66.0}],
  "detections_by_rule": {"ROUTE_DEVIATION": 2, "SOURCE_DISCREPANCY": 1, "SOURCE_SILENT": 0, "GPS_DEGRADED": 0},
  "alerts_by_cause": {"WIND": 1, "HIJACK": 1, "GPS_SPOOFING": 1, "SENSOR_FAULT": 0, "GPS_JAMMING": 0, "UNKNOWN": 0},
  "alerts_open": 0, "alerts_closed": 3 }
```
`waypoints_planned` y `waypoints_reached` no incluyen `BASE`. Siempre con todas las claves (0 si no hay). `completion_reason`: `returned_to_base` | `timeout` | `null` (la misión aún no ha terminado). `distance_m.gps` / `.radar` son `null` si esa fuente no tiene muestras. Nunca incluye información del dominio `sim` (fallos inyectados ni modo interactivo).
- **`publish_alert`**, **`close_alert`**, **`load_skill`**: las ejecuta el módulo de IA. `publish_alert` devuelve `{"ok": true, "alert_id": "ai-0003"}` o `{"ok": false, "errors": ["…"]}` (validación: Pydantic, ids de evidencia existentes y con `sim_time` ≤ `as_of_sim_time`).

## 8. Ficheros del generador
El generador (`platform/`) lee `scenarios/<nombre>.yaml` y escribe `runs/<nombre>/`: `plan.json`, `truth.json`, `events.jsonl` y `labels.json`. Modelos en `poc_contracts.scenario` y `poc_contracts.run_files`; esquemas en `contracts/schemas/files/`. Los números de los ficheros JSON van redondeados (posiciones y velocidades a 2 decimales en plan y verdad, a 1 en los eventos).

### 8.1 YAML de escenario (`scenarios/<nombre>.yaml`)
Todos los campos son obligatorios (los que admiten `null` lo dicen); no se admiten campos desconocidos. `name` debe coincidir con el nombre del fichero. Ejemplo completo:
```yaml
name: demo
description: Las tres anomalías en un vuelo.
seed: 42
t0: "2026-10-20T10:00:00Z"        # event_time = t0 + sim_time (ISO 8601 UTC, segundos enteros)
max_duration_s: 900              # si se alcanza: MissionCompleted con completed false y reason timeout
drone: {cruise_speed_mps: 15.0, max_accel_mps2: 2.0, max_turn_rate_dps: 40.0, altitude_m: 60.0,
        acceptance_radius_m: 25.0, lookahead_m: 40.0}
mission:
  id: MSN-DEMO
  waypoints: [{id: WP1, x: 500.0, y: 1200.0}, {id: WP2, x: 1600.0, y: 1500.0}]
  return_to_base: true           # obligatorio; por ahora solo se admite true
sensors:
  gps: {period_s: 1.0, sigma_m: 1.5, sats: 14, hdop: 0.8}
  radar: {id: radar-1, period_s: 2.0, sigma_m: 5.0}
  meteo: {id: meteo-1, period_s: 10.0, sigma_mps: 0.5, sigma_deg: 8.0}
  link: {period_s: 5.0, controller_id: GCS-1, rssi_dbm: -62.0, latency_ms: 45.0}
  battery: {period_s: 10.0, start_pct: 100.0, drain_pct_per_min: 1.2}
wind:
  base: {speed_mps: 2.0, gust_mps: 3.5, from_deg: 300.0}
  episodes: [{start_s: 95.0, end_s: 150.0, ramp_s: 10.0, speed_mps: 12.0, gust_mps: 16.0, from_deg: 350.0}]
spoofing: {start_s: 168.0, end_s: 222.0, drift_rate_mps: 1.5, direction_deg: 45.0}   # o null
hijack:                                                                              # o null
  start_s: 335.0
  end_s: 380.0                   # o null: el control no se recupera
  target: {x: 1500.0, y: -1400.0}
  link_hint: {controller_id: UNK-4F2A, rssi_dbm: -79.0, latency_ms: 120.0}
faults: [{source: radar, mode: mute, start_s: 120.0, end_s: 180.0}]   # lista, puede estar vacía
```
`faults[].mode`: `mute` | `loss` (`loss` solo con `source: gps`). `radar.id` y `meteo.id` solo pueden ser `radar-1` y `meteo-1` (son el `source` del sobre). Significado de cada bloque en `scenarios/README.md`. Las desviaciones típicas de lo que no sale del YAML (altitud, velocidad y rumbo del GPS, calidad del radar, RSSI, latencia, batería) son constantes del generador.

### 8.2 `plan.json`
Vuelo del mismo controlador **sin** viento, spoofing ni secuestro. `waypoints` es la misma lista que `MissionPlanned` (con la base al final); `trajectory`, una muestra por segundo más la última (`t`, `x`, `y`, `speed_mps` respecto al suelo, `heading_deg`). Ejemplo (recortado: el real trae una muestra por segundo hasta `duration_s`):
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
La trayectoria real y el viento real, una muestra por segundo más la última (en `GET /truth`, hasta el instante actual). **El agente nunca lo ve**; lo usan las gráficas, la evaluación y la capa «verdad» de la web. `heading_deg` es el rumbo del morro; `course_deg`, el rumbo sobre el suelo (distintos cuando hay viento); `speed_mps`, la velocidad sobre el suelo. En `wind`, `from_deg` es la procedencia.
```json
{ "duration_s": 556.3,
  "trajectory": [ {"t": 0.0, "x": 0.0, "y": 0.0, "speed_mps": 0.0, "heading_deg": 22.62, "course_deg": 22.62},
                  {"t": 1.0, "x": 2.12, "y": 0.03, "speed_mps": 2.57, "heading_deg": 20.1, "course_deg": 70.05} ],
  "wind": [ {"t": 0.0, "speed_mps": 2.0, "gust_mps": 3.5, "from_deg": 300.0},
            {"t": 1.0, "speed_mps": 2.0, "gust_mps": 3.5, "from_deg": 300.0} ] }
```

### 8.4 `labels.json`
Una etiqueta por anomalía (`A1`, `A2`… por orden de inicio: viento por episodio, spoofing, secuestro) y por fallo programado, `mute` o `loss` (`F1`, `F2`… por orden de inicio). Solo para evaluar. Campos: `type` (`wind` | `hijack` | `gps_spoofing` | `source_silent` | `gps_loss`), `source` (la fuente en fallo; `null` si no es un fallo), `start_s`, `end_s` (en un secuestro sin fin, el fin de la misión), `expected_rules` (reglas del detector que se esperan en la ventana; basta con que salte una), `expected_cause`, `also_accepted_causes` (otras causas que también cuentan como acierto; casi siempre vacía) y `eval_window` (de `start_s` a `end_s` más 60 s: una alerta con la causa esperada dentro de la ventana cuenta como acierto). En el spoofing las reglas esperadas son `SOURCE_DISCREPANCY` y también `ROUTE_DEVIATION`, porque al acabar el engaño el GPS salta a la verdad, lejos de la ruta. **Ese `ROUTE_DEVIATION` es esperado:** en la evaluación cuenta como acierto si el monitor lo atribuye a `GPS_SPOOFING` (recuperación tras el engaño) y como fallo de diagnóstico si lo atribuye a otra causa. Un fallo `loss` (`gps_loss`) espera `GPS_DEGRADED`, `SOURCE_DISCREPANCY` y `ROUTE_DEVIATION` (por lo mismo: al recuperarse, el GPS salta a la real), `expected_cause: GPS_JAMMING` y `also_accepted_causes: ["SENSOR_FAULT"]`; su `ROUTE_DEVIATION` se evalúa como el del spoofing (acierto con `GPS_JAMMING` o `SENSOR_FAULT`).
```json
{ "labels": [ { "id": "A1", "type": "wind", "source": null, "start_s": 95.0, "end_s": 150.0,
                "expected_rules": ["ROUTE_DEVIATION"], "expected_cause": "WIND", "also_accepted_causes": [],
                "eval_window": [95.0, 210.0] },
              { "id": "F1", "type": "source_silent", "source": "radar", "start_s": 120.0, "end_s": 180.0,
                "expected_rules": ["SOURCE_SILENT"], "expected_cause": "SENSOR_FAULT", "also_accepted_causes": [],
                "eval_window": [120.0, 240.0] } ] }
```

### 8.5 `events.jsonl`
Un `EventDraft` (§2, sin `seq` ni `ingestion_time`) por línea, ordenado por `sim_time` y, a igualdad de instante, así: misión, fallos, GPS, radar, meteo, enlace, batería. **Es lo que produce el simulador en directo de la plataforma ejecutado hasta el final sin intervenciones** (mismo código, paso de 0,1 s): el reproductor en directo, sin intervenciones y con el modo interactivo apagado, publica exactamente estos eventos. Para eso, el ruido de todas las fuentes se saca siempre en el mismo orden (por instante: GPS, radar, meteo, enlace, batería), aunque una fuente esté silenciada o en pérdida.
- **Ids:** los de las fuentes llevan el número de orden de la medición (`gps-000061` es la que cae en t = 61 s), así que un fallo programado deja huecos en la numeración, igual que lo haría uno manual. Los de misión (`mis-`) y los de fallos (`sim-`) son secuenciales. **Numeración:** los fallos (programados y manuales) los numera el simulador por orden de aparición (`sim-0001`…); el estado del reproductor (`SimulationStarted`…, `InteractiveModeChanged`) usa `plr-` y no está en `events.jsonl`.
- **Fallos programados:** en `[start_s, end_s)`, una fuente en `mute` no publica y el GPS en `loss` publica la posición estimada sin fix (§4); se escriben `FaultInjected` en `start_s` y `FaultCleared` en `end_s` (`origin: scenario`). Un `mute` no cambia el ruido de nada: con la misma semilla, un escenario con silenciados tiene los mismos eventos que el equivalente sin ellos, menos los silenciados. Un `loss` cambia la trayectoria real y, desde su inicio, todo lo que depende de ella (GPS y radar).
- **Fin del vuelo:** las fuentes dejan de emitir al terminar la misión; `MissionCompleted` lleva el `sim_time` de ese instante. Un fallo o una anomalía que acabaría después se recorta al fin de la misión (`FaultCleared` y el `end_s` de su etiqueta); uno que empezaría después no se escribe.
- **Determinismo:** misma semilla y mismo YAML, ficheros idénticos byte a byte.

