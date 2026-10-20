# Contratos de `poc-ai-monitor`

> **Fuente de verdad** de lo que se intercambian los componentes: eventos, topics, mensajes del WebSocket, API HTTP y tools. Versión 0.3 (20/10/2026: `source` y `asset` del sobre, `fix`, `GET /scenarios`, resultado de `get_flight_summary` y `get_track_metrics` sin datos de una fuente, patrón de suscripción de ejemplo corregido en §3; v0.2, 16/10/2026: fallos manuales y regla `SOURCE_SILENT`). Cualquier cambio se hace aquí primero y después en `contracts/python` (Pydantic), `contracts/schemas/` (JSON Schema exportado) y en todos los componentes, en el mismo cambio.

## 1. Convenciones
- **Unidades:** metros, segundos, m/s, grados. Plano x,y con origen en la base: **x hacia el este, y hacia el norte**.
- **Ángulos:** rumbos en grados 0–360, **0 = norte, 90 = este** (sentido horario). El viento se da por **dirección de procedencia** (convención meteorológica): `from_deg: 0` es viento del norte, que empuja hacia el sur.
- **Tiempo:** `sim_time` (s desde el inicio de la simulación, float); `event_time` = `t0` del escenario + `sim_time`, en ISO 8601 UTC; `ingestion_time` lo pone el bus con el reloj de pared, ISO 8601 UTC con milisegundos.
- **Ids:** prefijo por fuente y número con ceros: `gps-000061`, `rad-000030`, `met-0006`, `lnk-0012`, `bat-0006`, `mis-0003`, `det-0001`, `ai-0001`, `ops-0001`, `sim-0001`. Únicos en una ejecución.
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
- `source`: quién publica. Generador: `d1-gps`, `radar-1`, `meteo-1`, `d1-link`, `d1-bat`, `d1-mission`. Reproductor (estado y `FaultInjected`/`FaultCleared`): `platform-player`. Módulo de IA: `ai-detector` (detecciones), `ai-monitor` (`AnomalyDetected`, `AlertClosed`), `ai-report` (`ReportGenerated`), `ai-chat-monitor` / `ai-chat-report` (`AgentReply`, `AgentReplyChunk`), `ai-module` (`AgentActivity`). Web (`OperatorMessage`): `web-operator`.
- `asset`: `"d1"` en los topics `air.d1` y `ai.d1`; `"zone1"` en `env.zone1`; `null` en el resto (`sim`, `ops`, `ai.monitor`, `ai.report`, `ai.agent`).
- `seq`: orden global de publicación en la ejecución (lo pone el bus).
- `causation_id`: id del evento que provocó este (p. ej. la detección que provocó una alerta). `null` si no aplica.
- `ephemeral: true` solo para trozos de streaming del chat: se reenvían por el WebSocket pero **no** se guardan en el timeline.
- El generador escribe los eventos sin `seq` ni `ingestion_time`; los pone el bus al publicar.

## 3. Topics
Forma (taxonomía de David, 13/10/2026): `<namespace>.<clasification>.<type>.<domain>.<routing>.<event>.<version>`, con `namespace = citadel`, `clasification = pub` (sin clasificar; es una PoC), `type = evt | cmd`.

| Topic | Evento | Publica |
|---|---|---|
| `citadel.pub.evt.air.d1.PositionUpdated.v1` | Posición del GPS del dron | Reproductor |
| `citadel.pub.evt.air.d1.TrackUpdated.v1` | Traza del radar sobre d1 | Reproductor |
| `citadel.pub.evt.env.zone1.WindReported.v1` | Viento en la zona | Reproductor |
| `citadel.pub.evt.air.d1.LinkStatus.v1` | Enlace de mando | Reproductor |
| `citadel.pub.evt.air.d1.BatteryStatus.v1` | Batería | Reproductor |
| `citadel.pub.evt.air.d1.MissionPlanned.v1`, `.MissionStarted.v1`, `.WaypointReached.v1`, `.MissionCompleted.v1` | Misión | Reproductor |
| `citadel.pub.evt.sim.player.SimulationStarted.v1`, `.SimulationPaused.v1`, `.SimulationResumed.v1`, `.SimulationFinished.v1`, `.SimulationReset.v1` | Estado del reproductor | Plataforma |
| `citadel.pub.evt.sim.player.FaultInjected.v1`, `.FaultCleared.v1` | Fuente silenciada o reactivada (manual o programada). **El agente no los ve** | Plataforma |
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
**`MissionStarted`** `{ "mission_id": "MSN-DEMO" }` · **`WaypointReached`** `{ "waypoint_id": "WP2", "index": 2 }` (lo decide el dron con su GPS) · **`MissionCompleted`** `{ "mission_id": "MSN-DEMO", "completed": true, "reason": "returned_to_base" }` (`reason`: `returned_to_base` | `timeout`)

**`PositionUpdated`** (`gps-`, cada 1 s)
```json
{ "x": 512.3, "y": 140.8, "alt_m": 60.2, "speed_mps": 15.1, "heading_deg": 81.0, "fix": "3d", "sats": 14, "hdop": 0.8 }
```
`speed_mps` y `heading_deg` son los de navegación del propio dron (respecto al suelo, según su GPS). `fix`: `"none"` | `"2d"` | `"3d"` (en los escenarios actuales siempre `"3d"`; los otros quedan para el jamming, mejora futura); `sats`: entero; `hdop`: decimal.

**`TrackUpdated`** (`rad-`, cada 2 s) `{ "radar_id": "radar-1", "x": 505.0, "y": 151.2, "speed_mps": 14.2, "course_deg": 83.0, "quality": 0.9 }`

**`WindReported`** (`met-`, cada 10 s) `{ "station_id": "meteo-1", "speed_mps": 4.2, "gust_mps": 6.0, "from_deg": 350.0 }`

**`LinkStatus`** (`lnk-`, cada 5 s) `{ "controller_id": "GCS-1", "rssi_dbm": -62.0, "latency_ms": 45.0 }`

**`BatteryStatus`** (`bat-`, cada 10 s) `{ "battery_pct": 87.5, "voltage_v": 22.9 }`

### Del reproductor
**`SimulationStarted`** `{ "scenario": "demo", "run_id": "20261020-101500", "duration_s": 420.0, "total_events": 913 }` · **`SimulationPaused`** `{ "reason": "user" }` (`reason`: `user` | `waiting_agent`) · **`SimulationResumed`** `{}` · **`SimulationFinished`** `{ "scenario": "demo", "run_id": "…" }` · **`SimulationReset`** `{}`

**`FaultInjected`** / **`FaultCleared`** (`sim-`) `{ "source": "radar", "origin": "manual" }` (`source`: `gps` | `radar` | `meteo` | `link` | `battery`; `origin`: `manual` | `scenario`). Mientras una fuente está silenciada, el reproductor descarta sus eventos al publicar.

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
`rule`: `ROUTE_DEVIATION` | `SOURCE_DISCREPANCY` | `SOURCE_SILENT`. `source`: la fuente afectada; obligatoria en `SOURCE_SILENT` (`gps` | `radar` | `meteo` | `link` | `battery`; `value` = segundos sin eventos, `unit: "s"`), `null` en las demás. `severity`: `low` | `medium` | `high`. `DetectionUpdated` usa el mismo `detection_id` y una severidad mayor.

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
`cause`: `WIND` | `HIJACK` | `GPS_SPOOFING` | `SENSOR_FAULT` | `UNKNOWN` (reservados para el futuro: `GPS_JAMMING`, `REPLAY`). `supersedes`: `alert_id` de una alerta anterior a la que esta sustituye (p. ej. al cambiar la causa). `fallback: true` si lo publicó el módulo porque el agente no concluyó.

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
| `control` | `action: "load" \| "play" \| "pause" \| "step" \| "reset" \| "speed" \| "wait_agent" \| "fault"`, `value` | `load` con nombre de escenario (si no está generado, la plataforma lo genera antes de cargarlo); `speed` con 0.5/1/2/4/8/16; `wait_agent` con `true`/`false`; `fault` con `{"source": "radar", "muted": true}` (silencia o reactiva una fuente desde el instante actual) |

Plataforma → cliente:
| `op` | Campos |
|---|---|
| `event` | `event` (sobre completo) |
| `state` | `status: "idle" \| "running" \| "paused" \| "finished"`, `scenario`, `run_id`, `sim_time`, `speed`, `wait_agent`, `muted_sources` (lista), `cursor`, `total_events` (se envía al conectar, al cambiar y cada 0,5 s mientras corre) |
| `error` | `message` |

## 6. API HTTP (`http://127.0.0.1:8100/api`)
- `GET /scenarios` → `{"scenarios": [{"name": "demo", "description": "…", "generated": true, "duration_s": 556.0}]}`. `generated` = existe `runs/<name>/events.jsonl`; `duration_s` es `null` si no está generado. `load` de un escenario no generado lo genera antes de cargarlo. `GET /state` → como el mensaje `state`.
- `GET /plan` → `plan.json` del escenario cargado (waypoints y trayectoria planificada). Lo usa la web.
- `GET /truth` → `truth.json`. **Solo para la capa «verdad» de la web.** Ninguna tool lo usa.
- `GET /timeline?source=&type=&since=&until=&limit=` → eventos del timeline (sin corte temporal; es para la web y la evaluación).
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
  "detections_by_rule": {"ROUTE_DEVIATION": 2, "SOURCE_DISCREPANCY": 1, "SOURCE_SILENT": 0},
  "alerts_by_cause": {"WIND": 1, "HIJACK": 1, "GPS_SPOOFING": 1, "SENSOR_FAULT": 0, "UNKNOWN": 0},
  "alerts_open": 0, "alerts_closed": 3 }
```
Siempre con todas las claves (0 si no hay). `completion_reason`: `returned_to_base` | `timeout` | `null` (la misión aún no ha terminado). `distance_m.gps` / `.radar` son `null` si esa fuente no tiene muestras. Nunca incluye información del dominio `sim` (fallos inyectados).
- **`publish_alert`**, **`close_alert`**, **`load_skill`**: las ejecuta el módulo de IA. `publish_alert` devuelve `{"ok": true, "alert_id": "ai-0003"}` o `{"ok": false, "errors": ["…"]}` (validación: Pydantic, ids de evidencia existentes y con `sim_time` ≤ `as_of_sim_time`).
