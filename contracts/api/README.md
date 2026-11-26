# API del simulador (`/api/v1`) · diseño

Para quien integra el simulador como **plataforma externa del ejercicio**: lee los datos de cada asset, controla el ejercicio y, aparte, recibe lo que solo es del instructor. El OpenAPI exportado está en [`sim-api-v1.json`](sim-api-v1.json) (se sirve también en `/api/v1/openapi.json` y `/api/v1/docs`; se regenera con `uv run --project platform python -m platform_app.sim_api.export_openapi`). Los modelos son `poc_contracts.sim_api`.

**Estado:** implementada y probada (versión 1.0.0 de la API). Cubierta por tests de equivalencia con el bus (`demo` y los 11 escenarios). Consumidor de referencia en `tools/sim_api/`.

## 1. Qué es y qué no es
- **Es** la cara del simulador: el generador, el reproductor, los escenarios, el control del ejercicio y los *injects*. Cada asset da sus datos en **su propio formato**; el integrador los traduce al formato del bus.
- **No es** el bus: no hay topics, ni lo que publica la IA (`ai.*`), ni los mensajes del operador (`ops.*`), ni la línea temporal. El WebSocket `/ws` y los `GET /api/*` de hoy siguen igual, para la web y los procesos de IA.
- **Solo `localhost` y sin autenticación** de momento: no se expone fuera de una red de confianza.
- Todo en inglés (mensajes de error, descripciones); unidades del SI: metros, segundos, m/s, grados. Plano x,y con origen en la base, **x al este, y al norte**; rumbos 0–360 con 0 = norte; el viento por su procedencia.

## 2. Inventario de assets
`GET /api/v1/assets` (vacío mientras no hay escenario cargado: la ficha sale del escenario).

| `id` | `type` | `subject` | Mensajes (`type`) |
|---|---|---|---|
| `d1` | `drone` | `d1` | `PositionUpdated`, `GnssStatus`, `AutopilotStatus`, `BatteryStatus`, `MissionPlanned`, `MissionStarted`, `WaypointReached`, `MissionCompleted` |
| `radar-1` | `radar` | `d1` | `TrackUpdated` |
| `meteo-1` | `weather_station` | `zone1` | `WindReported` |
| `gcs-1` | `ground_station` | `d1` | `LinkStatus` |

- `id` es **quien publica**; `subject` es **de quién habla** (el radar mide el dron; la estación meteorológica, la zona; la estación de tierra mide el enlace con el dron). Las dos cosas van en cada mensaje.
- La **estación de tierra** (`gcs-1`) es un asset propio: mide el enlace de mando (`LinkStatus`) y recibe la telemetría del dron. **La telemetría del dron (`d1`) es la que llega a la estación**: si el enlace cae, el dron deja de dar mensajes aunque siga volando (y entonces `gcs-1` lo cuenta en `LinkStatus`).
- Cada asset trae su **configuración** (`config`): lo que se conoce de antemano por su ficha técnica. Es lo que el monitor necesita para interpretar sus datos.

```json
{ "scenario_loaded": true,
  "assets": [
    { "id": "d1", "type": "drone", "name": "Drone d1", "subject": "d1",
      "message_types": ["PositionUpdated", "GnssStatus", "AutopilotStatus", "BatteryStatus",
                        "MissionPlanned", "MissionStarted", "WaypointReached", "MissionCompleted"],
      "config": { "max_airspeed_mps": 17.0, "wind_limit_mps": 12.0, "cruise_speed_mps": 15.0,
                  "gps_period_s": 1.0, "battery_period_s": 10.0,
                  "gps_sigma_m": 1.5, "cn0_nominal_dbhz": 45.0, "agc_nominal_db": 0.0,
                  "mission_controller_id": "GCS-1" } },
    { "id": "radar-1", "type": "radar", "name": "Radar 1", "subject": "d1",
      "message_types": ["TrackUpdated"],
      "config": { "x": 0.0, "y": 0.0, "period_s": 2.0, "sigma_m": 5.0,
                  "sigma_per_km_m": 2.0, "max_range_m": 6000.0 } },
    { "id": "meteo-1", "type": "weather_station", "name": "Weather station 1", "subject": "zone1",
      "message_types": ["WindReported"], "config": { "period_s": 10.0 } },
    { "id": "gcs-1", "type": "ground_station", "name": "Ground station 1", "subject": "d1",
      "message_types": ["LinkStatus"],
      "config": { "x": 0.0, "y": 0.0, "period_s": 5.0, "controller_id": "GCS-1" } } ] }
```
**Nunca** salen por el inventario: el viento, los episodios, el engaño, el secuestro, los emisores ni los fallos.

## 3. Formato del mensaje de un asset
Una cabecera propia y, en `data`, **el payload del evento del contrato sin cambios** (`contracts/eventos.md` §4). Sin topics, `source`, `causation_id` ni `ephemeral`.
```json
{ "seq": 214, "run_id": "20261020-101500", "asset_id": "d1", "subject": "d1",
  "type": "PositionUpdated", "id": "gps-000060",
  "sim_time": 60.0, "time_utc": "2026-10-20T10:01:00Z", "received_utc": "2026-11-26T08:15:32.418Z",
  "data": { "x": 322.2, "y": 773.2, "alt_m": 59.7, "speed_mps": 15.1, "course_deg": 22.0,
            "fix": "3d", "sats": 13, "hdop": 0.55 } }
```
- **`seq`**: entero que crece por asset durante la vida del proceso. **No se reinicia** al cargar otro escenario ni al reiniciar: un cursor guardado nunca se confunde con otro.
- **`id`**: el `event_id` del contrato (`gps-000060`). Se conserva porque los incidentes lo citan como evidencia.
- **`sim_time`**: segundos de simulación. **`time_utc`**: el tiempo del ejercicio (`t0` del escenario + `sim_time`). **`received_utc`**: el reloj de pared al publicarse.
- **`type` + `subject`** bastan para reconstruir el topic y la fuente del bus (tabla del apartado 8).
- Los `data` de `AutopilotStatus`, `GnssStatus`, etc. son los de §4 del contrato. Sin fix, `PositionUpdated` lleva `null` en posición, altitud, velocidad y rumbo.

**Ciclo de vida de la ejecución.** Por **cada asset** salen, con su propio `seq`, `RunStarted` (`data`: `{"duration_s": 556.3}`), `RunReset` y `RunFinished` (`data`: `{}`), con `id` `run-<run_id>-RunStarted`… y el `sim_time` del instante. **Sin el nombre del escenario** (delata la clase de anomalía): solo el `run_id`.

## 4. Endpoints (`/api/v1`)
| Método y ruta | Qué hace |
|---|---|
| `GET /assets` · `GET /assets/{id}` | Inventario y ficha de un asset. 404 si no existe. |
| `GET /assets/{id}/state` | `run_id`, estado del ejercicio, `sim_time` y el último mensaje de cada tipo. |
| `GET /assets/{id}/messages?since=-1&limit=1000&types=A,B&run_id=` | Histórico de la ejecución, paginado por `seq`: `{asset_id, messages, next, has_more}`. `since` es exclusivo (`-1` = desde el principio); `next` es el `seq` del último mensaje **examinado** (con `types`, avanza aunque la página salga vacía). `run_id` por defecto es la ejecución en curso; solo se guarda la actual y la anterior. `types` filtra también los mensajes de ciclo de vida (pídelos por su nombre). |
| `GET /assets/{id}/stream?types=&since=` | Flujo en directo (SSE, apartado 5). |
| `GET /exercise` | Estado del ejercicio (el mensaje `state` del WebSocket): `status`, `scenario`, `run_id`, `sim_time`, `speed`, `interactive`, `active_faults`, `cursor`, `total_events`. |
| `GET /exercise/scenarios` | Lo mismo que `GET /api/scenarios`. |
| `POST /exercise/load` `{scenario}` · `/play` · `/pause` · `/step` · `/reset` | Control. Devuelven el estado. |
| `PUT /exercise/speed` `{value}` · `PUT /exercise/interactive` `{value}` | `value` ∈ 0,5 · 1 · 2 · 4 · 8 · 16; modo interactivo (cada carga o reinicio lo apaga). |
| `POST /instructor/faults` `{source, mode, active}` · `POST /instructor/commands` | *Injects* del instructor, con la validación de hoy (apartado 6). |
| `GET /instructor/injects` · `GET /instructor/truth` · `GET /instructor/stream` | La verdad del ejercicio (apartado 6). |

**Rutas por id y no por tipo** (`/assets/{id}/…`, no `/drone/…`): admite varios drones y trata igual el radar, la estación meteorológica y la de tierra.

## 5. Flujo en directo (SSE)
`GET /assets/{id}/stream` (`text/event-stream`):
```
event: message
id: 214
data: {"seq": 214, "run_id": "…", "asset_id": "d1", …}

event: heartbeat
data: {"run_id": "20261020-101500", "status": "running", "sim_time": 61.0, "speed": 1.0}
```
- **`event: message`** lleva `id: <seq>`.
- **`event: heartbeat`** cada segundo de reloj, **sin `id`** (no mueve el cursor). Dice hasta dónde ha llegado el ejercicio: **no vendrá nada de ese asset con un `sim_time` menor**. Así una fuente callada (silenciada, o el radar fuera de alcance) no se confunde con una conexión caída, y quien mezcla varios assets puede ordenarlos.
- **Reanudación:** `Last-Event-ID` (o `?since=N`, con prioridad la cabecera). Se repite lo conservado con `seq > N` y se sigue en directo. Sin ninguno de los dos, el flujo empieza en directo; `since=-1` repite todo lo conservado. Si lo pedido ya no se conserva, `event: gap` con `{requested, first_available}` y se sigue desde lo que hay.
- **Sin pérdidas ni duplicados:** el servidor lee de un registro por asset, por índice, sin una cola por cliente: un cliente lento no pierde mensajes (solo se retrasa).
- **Pausa:** no llegan mensajes y el `heartbeat` dice `paused`. **Velocidad:** solo cambia el ritmo (`speed` en el `heartbeat` y en `/exercise`). **Reset o carga:** llegan `RunReset` y después `RunStarted`; el `seq` sigue sin reiniciarse. **Fin:** `RunFinished`; el flujo sigue abierto (el `heartbeat` dice `finished`).
- **Tiempo de cada mensaje:** `sim_time` y `time_utc` (simulado) y `received_utc` (pared).
- Cabecera `Cache-Control: no-cache`; el servidor no envía `retry:`.

## 6. Control del ejercicio y parte del instructor
- **Control** (`/exercise/*`): las mismas órdenes y la misma validación que el `control` del WebSocket; las dos caras comparten el código. Una orden por REST llega a los clientes del `/ws` **igual** que si la diera la web: su mensaje `state` y los eventos que provoca.
- **Errores:** 404 (escenario, asset o `run_id` desconocido; lecturas sin escenario cargado: `/assets/{id}`, `/instructor/truth`), **409** (la orden no procede; sin escenario cargado, siempre «no scenario is loaded», antes que cualquier otro motivo: «interactive mode is off: turn it on to inject faults», simulación terminada, un fallo repetido, `cancel_wind` sin viento del instructor; el `detail` es el mismo texto que el `error` del WebSocket), 422 (cuerpo no válido: `loss` fuera del GPS, velocidad no admitida, rangos del viento).
- **Parte del instructor** (`/instructor/*`), separada y **no necesaria para ningún worker de asset**:
  - `faults` (`mute` en cualquier fuente; `loss` solo en el GPS) y `commands` (`set_wind` / `cancel_wind`), **solo con el modo interactivo encendido**.
  - `injects`: lo programado en el escenario (`ExerciseInjects`). `truth`: la verdad hasta el instante actual. `stream` (SSE, mismos ids y reanudación): `FaultInjected`, `FaultCleared`, `InstructorCommand`, `ExerciseInjects` e `InteractiveModeChanged`, con el mismo formato propio.
- **La verdad del ejercicio no sale nunca por los endpoints de los assets:** ni los fallos, ni los comandos, ni lo programado, ni el estado interno del dron. Un asset da lo que mediría ese asset, con su ruido.

## 7. Despliegue
Host y puerto de la plataforma configurables (`--host`/`--port` y `POC_PLATFORM_HOST`/`POC_PLATFORM_PORT`; por defecto `127.0.0.1:8100`), los orígenes permitidos de la web con `POC_WEB_ORIGINS`, y la web llama a `NEXT_PUBLIC_PLATFORM_URL` (por defecto `http://127.0.0.1:8100`). Nada de esto cambia el comportamiento por defecto.

## 8. Equivalencia con el bus
Un adaptador que lea esta API reconstruye los eventos del bus con `poc_contracts.topics` (`topic_for`, `source_for`, `asset_for`): el `type` da el topic; la fuente, el `asset` del sobre y el prefijo del `id` salen del `type`.

| `type` | Fuente del sobre | `asset` del sobre | Prefijo de `id` |
|---|---|---|---|
| `PositionUpdated` · `GnssStatus` · `AutopilotStatus` · `BatteryStatus` · misión | `d1-gps` · `d1-gnss` · `d1-autopilot` · `d1-bat` · `d1-mission` | `d1` | `gps` · `gns` · `apl` · `bat` · `mis` |
| `TrackUpdated` | `radar-1` | `d1` | `rad` |
| `WindReported` | `meteo-1` | `zone1` | `met` |
| `LinkStatus` | `d1-link` | `d1` | `lnk` |
| `RunStarted` · `RunReset` · `RunFinished` | `platform-player` | `null` | `SimulationStarted` · `SimulationReset` · `SimulationFinished` |

Lo que no se puede reconstruir desde los assets (`seq` y `ingestion_time` del bus) lo pone quien publique en el bus.

## 9. Decisiones tomadas
1. **Estación de tierra como asset propio** (`gcs-1`, dueña de `LinkStatus`).
2. **SSE y no un segundo WebSocket** para el flujo; el control va por REST. El WebSocket `/ws` sigue siendo el bus de la plataforma.
3. **`asset_id` y `subject`** separados en cada mensaje (quién publica y de quién habla).
4. **Ciclo de vida por cada asset**, sin nombre de escenario.
5. **`seq` por asset que no se reinicia**, para que un cursor no se confunda tras un reinicio.
6. **Retención:** hasta 200 000 mensajes por asset y solo la ejecución actual y la anterior.
7. **`config` del inventario:** los valores del §2; el σ del GPS es el del escenario (1,5 m), no el 1,53 medido que hoy usa el monitor.

## 10. Arrancar un worker antes de que haya ejercicio
Un worker puede arrancar antes de que se cargue un escenario. Mientras no lo hay:
- `GET /assets` da `200` con `{"scenario_loaded": false, "assets": []}`.
- `GET /assets/{id}` da **`404` con `{"detail": "no scenario is loaded"}`** (la ficha sale del escenario). Un asset que no existe también es 404, pero con `{"detail": "unknown asset: 'x'"}`.
- `GET /assets/{id}/stream` y `/messages` **sí funcionan**: el flujo solo manda `heartbeat` (con `run_id: null`) hasta que llega `RunStarted`.
- Las órdenes de control (`play`, `pause`, `step`, `reset`, `speed`) y los *injects* dan **`409` con `no scenario is loaded`**.

El worker debe **reintentar la ficha (`GET /assets/{id}`) con espera creciente (0,5 s, 1 s, 2 s… hasta 5 s) mientras el `detail` sea `no scenario is loaded`**, y no reintentar ante «unknown asset». Después abre el flujo. `tools/sim_api/consume.py` lo hace así (`fetch_asset`) y escribe la ficha como primera línea de cada asset.

## 11. Consumidor de referencia
`tools/sim_api/consume.py` (solo la biblioteca estándar): se suscribe a uno o varios assets, reconecta con `Last-Event-ID` sin repetir mensajes y escribe JSON Lines.
```
python tools/sim_api/consume.py --all                       # inventario completo (espera al escenario)
python tools/sim_api/consume.py --assets d1,radar-1 --types PositionUpdated,TrackUpdated --since -1
uv run --project contracts/python python tools/sim_api/consume.py --all --as-bus   # eventos del bus reconstruidos
```
`tools/sim_api/adapter.py` es lo que hará el mediador: mezcla los flujos con las marcas de agua de los `heartbeat` y reconstruye los eventos del bus.

## 12. Ejemplos con `curl`
Con la plataforma en el 8100 (`API=http://127.0.0.1:8100/api/v1`). Salidas recortadas.
```bash
# Cargar y arrancar a 4× (devuelven el estado del ejercicio)
curl -X POST $API/exercise/load -H 'Content-Type: application/json' -d '{"scenario":"demo"}'
# {"status":"idle","scenario":"demo","run_id":"20261126-150723","sim_time":0.0,"speed":1.0,
#  "interactive":false,"active_faults":[],"cursor":0,"total_events":2094}
curl -X PUT  $API/exercise/speed -H 'Content-Type: application/json' -d '{"value":4}'
curl -X POST $API/exercise/play

# Inventario y ficha de un asset
curl $API/assets/radar-1
# {"id":"radar-1","type":"radar","name":"Radar 1","subject":"d1","message_types":["TrackUpdated"],
#  "config":{"x":0.0,"y":0.0,"period_s":2.0,"sigma_m":5.0,"sigma_per_km_m":2.0,"max_range_m":6000.0}}

# Histórico paginado: las dos primeras páginas del enlace (cursor = `next`)
curl "$API/assets/gcs-1/messages?since=-1&limit=3"
# {"asset_id":"gcs-1","messages":[{"seq":1,"type":"RunStarted",...},{"seq":2,...},{"seq":3,...}],
#  "next":3,"has_more":true}
curl "$API/assets/gcs-1/messages?since=3&limit=2&types=LinkStatus"

# Flujo en directo; reanudar tras un corte con Last-Event-ID (repite seq > 2)
curl -N $API/assets/meteo-1/stream
# event: heartbeat
# data: {"run_id":"20261126-150620","status":"running","sim_time":56.4,"speed":4.0}
#
# event: message
# id: 7
# data: {"seq":7,"run_id":"20261126-150620","asset_id":"meteo-1","subject":"zone1","type":"WindReported",
#        "id":"met-0006","sim_time":60.0,"time_utc":"2026-10-20T10:01:00Z",
#        "received_utc":"2026-11-26T14:06:35.378Z","data":{"speed_mps":1.1,"from_deg":300.9}}
curl -N -H 'Last-Event-ID: 2' $API/assets/meteo-1/stream

# Parte del instructor: modo interactivo y pérdida de GPS
curl -X PUT  $API/exercise/interactive -H 'Content-Type: application/json' -d '{"value":true}'
curl -X POST $API/instructor/faults -H 'Content-Type: application/json' \
     -d '{"source":"gps","mode":"loss","active":true}'
# {"status":"running",...,"interactive":true,"active_faults":[{"source":"gps","mode":"loss","origin":"manual"}],...}
curl -X POST $API/instructor/commands -H 'Content-Type: application/json' \
     -d '{"command":"set_wind","params":{"from_deg":0,"speed_mps":12,"ramp_s":10,"duration_s":60},"issued_by":"panel","text":null}'
curl $API/instructor/injects ; curl $API/instructor/truth
curl -N "$API/instructor/stream?since=-1"
```
Errores típicos:
| Petición | Respuesta |
|---|---|
| `POST /exercise/load {"scenario":"nope"}` | `404 {"detail":"unknown scenario: 'nope'"}` |
| `POST /exercise/play` sin escenario (o `pause`, `step`, `reset`, `speed`, `faults`, `commands`) | `409 {"detail":"no scenario is loaded"}` |
| `POST /instructor/faults` con el modo interactivo apagado | `409 {"detail":"interactive mode is off: turn it on to inject faults"}` |
| `PUT /exercise/speed {"value":3}` | `422` (velocidades: 0,5 · 1 · 2 · 4 · 8 · 16) |
| `POST /instructor/faults {"source":"radar","mode":"loss",...}` | `422` (`loss` solo existe para el GPS) |
| `GET /assets/nope/messages` · `?types=Nope` | `404 unknown asset` · `422 unknown message types` |
