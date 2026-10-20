# Fase 2 · plataforma en directo, detector, visor y contrato v0.5

Fecha: 20/10/2026. Estado: **terminada, pendiente de tu revisión** (la Fase 3 no se ha empezado).

Resultado en una línea: el reproductor ya **simula en directo** (un solo motor para el generador y la plataforma); con el modo interactivo apagado publica exactamente `runs/<escenario>/events.jsonl`; con él encendido se pueden inyectar fallos `mute` y `loss` (pérdida de GPS con navegación a estima); el detector de cuatro reglas dispara lo esperado en los seis escenarios, **también en directo por WebSocket**, y hay un visor en directo con ventana.

## 1. Qué se hizo

### 1.1 Contrato v0.5 (`contracts/eventos.md`, `contracts/python`, `contracts/schemas/`, **54** esquemas)
- Tipo de fallo `mode` (`mute` | `loss`; `loss` solo GPS) en `control` → `fault` (`{source, mode, active}`), en `FaultInjected`/`FaultCleared` y en `faults` del YAML.
- Modo interactivo: control `interactive`, campo `interactive` en `state`, evento `InteractiveModeChanged` (dominio `sim`, el agente no lo ve). `state` lleva `active_faults` (`{source, mode, origin}`) en lugar de `muted_sources`.
- Regla `GPS_DEGRADED` (`source: gps`, `value` = hdop, `unit: hdop`); causa `GPS_JAMMING` (activa; `REPLAY` sigue reservada); `PositionUpdated` en pérdida: `fix: none`, `sats: 0`, `hdop: 99.9`.
- Etiquetas: tipo `gps_loss` (`expected_rules` `GPS_DEGRADED`, `SOURCE_DISCREPANCY`, `ROUTE_DEVIATION`; `expected_cause` `GPS_JAMMING`) y campo nuevo `also_accepted_causes` (`["SENSOR_FAULT"]` en la pérdida, vacío en el resto). El `ROUTE_DEVIATION` que salta al acabar el spoofing (o la pérdida) queda documentado en §8.4: acierto si el monitor lo atribuye a la causa de esa anomalía, fallo de diagnóstico si lo atribuye a otra (decisión tuya).
- §6: `GET /api/truth` = verdad de la simulación en curso; `GET /api/timeline` con modelo propio (`TimelineResponse`: `events` + `truncated`) y esquema exportado; §8.5: `events.jsonl` = salida del simulador sin intervenciones.
- Los cuatro CLAUDE.md (raíz, `platform/`, `ai-module-py/`, `web/`), `docs/01_definicion.md` (§2, §3, §4.1, §4.4, §5, §6, §8, §9), `scenarios/README.md` y `docs/mejoras_futuras.md` (alertas del monitor en el visor; inyectar viento, secuestro o spoofing en directo) puestos al día.
- `agent-assets/`: `GPS_JAMMING` en `tools.json` y en el prompt de salida; `GPS_DEGRADED` en el prompt del monitor y en `guided_skill_by_rule`; skill `source-discrepancy` (paso 7 de `GPS_DEGRADED`: jamming por fix/sats/hdop frente a spoofing, `SENSOR_FAULT` si solo está degradado, caso de un `SOURCE_SILENT` simultáneo de otra fuente; el radar pasa de «unos 8 m» a «unos 5 m», que ya era el valor desde la Fase 1) y skill `route-deviation` (paso 0 ampliado a la recuperación tras una pérdida de GPS; paso 3: viento de más de 30 s → `UNKNOWN`, o `WIND` con confianza ≤ 0,5).

### 1.2 Simulador incremental (`platform/src/platform_app/generator/simulator.py`)
- `Simulator`: estado + `step()` de 0,1 s; lo usan el reproductor y `build.py` (que ya no tiene un bucle propio). `controller.py` queda con el guiado puro; `sensors.py`, con una función por lectura; `events.py`, con los sobres.
- **Ruido por instante:** un único `random.Random(seed)`; en cada instante cada fuente que toca saca siempre los mismos números, esté silenciada o en pérdida. Un `mute` no cambia nada del resto; un `loss` cambia la trayectoria y, desde ahí, GPS y radar.
- **`loss`:** la estima arranca donde el dron cree estar, integra solo su velocidad respecto al aire (sin viento), el controlador sigue el plan con ella (y acepta waypoints con ella) y al terminar vuelve al GPS real.
- Reglas de fallos: una fuente solo tiene un fallo a la vez; uno programado que empieza con uno manual activo se omite; un programado acaba solo (no se puede terminar a mano); un fallo que sigue activo al acabar la misión se cierra en ese instante.
- **Física intacta:** `plan.json` y `truth.json` de los seis escenarios salen **idénticos byte a byte** a los de la Fase 1 (salvo `truth.json` de `fallos`, que incluye ya la pérdida); el número de eventos coincide (845, 886, 854, 1056, 1063; `fallos` 807 → 814).
- Con la semilla 42 **todos los criterios de ruido se siguen cumpliendo**: no hizo falta probar otras semillas (GPS–radar fuera de ventanas: 13,3 m en `nominal`, 13,2 en `viento`, `spoofing` y `secuestro`, 11,4 en `demo`; el máximo admitido es 20).

### 1.3 `scenarios/fallos.yaml` y `runs/`
- Pérdida de GPS de **45 s (T+04:05 a T+04:50)** en el tramo WP3→WP4 (viento de base de 2 m/s casi de costado), junto al radar silenciado (T+02:00–03:00) y al GPS silenciado (T+05:00–05:12). Gráficas: la verdad se desvía hasta **≈ 90 m** mientras el GPS (la estima, círculos huecos) sigue a 3 m de la ruta; el radar ve la desviación; al volver, el GPS salta 93 m; el dron recupera la ruta 10 s después.
- **Ficheros de `runs/` que cambian (24):** `events.jsonl` de los seis (el ruido sale por instante y no por fuente); `labels.json` de `demo`, `fallos`, `secuestro`, `spoofing` y `viento` (campo `also_accepted_causes`; `nominal` no tiene etiquetas); `truth.json` de `fallos` (la pérdida); y los PNG `scenario_xy.png` y `scenario_time.png` de los seis. **No cambian** `plan.json`, `truth.json` (resto) ni `plan_xy.png`. Se regeneran con `generator --all` y `plot_scenario --all`.
- Gráficas: los puntos de GPS sin fix se pintan huecos y la etiqueta de cada tramo ya no se sale de los ejes.
- `scenario_metrics.py`: 52 criterios (antes 45), **52 ✅ y 0 ❌**; añade los de la pérdida de GPS (marcas `mode loss`, `fix none` solo durante ella, estima a < 15 m del plan, verdad > 40 m, radar ±8 m, salto > 40 m, recuperación) y «igual que `nominal` hasta T+245 s».

### 1.4 Plataforma (`platform/`, subagente; yo integré)
`bus.py` (comodines `*` y `>` con las funciones del contrato, `seq` e `ingestion_time`), `timeline.py` (índices por fuente, tipo e id; volcado a `runs/<escenario>/<run_id>/timeline.jsonl`), `player.py` (reloj asyncio sobre una lógica síncrona `advance()`/`run_to_end()`; paso = un evento; esperar al agente; modo interactivo; `fault` rechazado con el mensaje `el modo interactivo está apagado: actívalo para inyectar fallos`), `tools/` (las cinco tools con corte temporal en un único punto, `ToolContext.events()`, que además descarta el dominio `sim`) y `app.py` (REST + `/ws`, CORS para `:3000`).

### 1.5 Módulo de IA (`ai-module-py/`, subagente)
`bus_client.py` (asíncrono, `hello` como `ai-module`, reconexión con espera creciente, bootstrap del plan por `POST /api/tools/get_mission_plan` si arranca con la simulación ya en marcha), `detector.py` (cuatro reglas con histéresis, determinista, umbrales en `config/detector.yaml`), `detect_file.py` y `__main__.py`. **No importa nada de `platform/`.**

### 1.6 Visor en directo (`platform/src/platform_app/viewer.py` y `viewer_state.py`; sesión principal)
Cliente del WebSocket como `web` (solo publica `control`). Ventana de matplotlib (~10 fps): ruta y waypoints (`GET /api/plan`), estela y punto del GPS (hueco si no hay fix), puntos del radar, dron con su rumbo, viento (flecha y texto del último `WindReported`), verdad opcional (`GET /api/truth`, apagada), detecciones abiertas (lista en rojo, estela resaltada desde su inicio y aro rojo en el dron) y línea de estado (escenario, `sim_time`, velocidad, estado, esperar al agente, **interactivo** y fallos activos, más los avisos de error). Teclas: espacio, `n`, `+`/`-`, `0`, `w`, `t`, `i`, `1`–`5` (silenciar/reactivar), `g` (pérdida de GPS), `l` (pide el nombre por consola); los fallos solo con el modo interactivo (si no, aviso). La lógica de estado está separada (`viewer_state.py`, 22 pruebas sin ventana) y el pintado se prueba con Agg.
- **Backend:** TkAgg (`python3-tk` ya instalado). **Probado con ventana real en WSLg contra la plataforma real** (backend `TkAgg`; cargar `fallos`, subir a 16×, activar el modo interactivo, silenciar el radar y pérdida de GPS con las teclas; estado y captura correctos). Si no hay pantalla o Tk, cae a `--png RUTA` (PNG que se refresca cada segundo; sin teclado).
- Ejecutar: `uv run --project platform python -m platform_app.viewer [--platform URL] [--png ruta.png]` (con la plataforma en marcha).
- Limitación: un visor que se conecta a mitad de ejecución no recibe el historial (empieza a pintar desde ahí).

## 2. Cómo se ejecuta
```bash
# Todo sin LLM, escenario de principio a fin a 16× (arranca la plataforma y el módulo de IA como procesos aparte)
uv run --project platform python -m platform_app.run --scenario demo --speed 16
uv run --project platform python -m platform_app.run --all --check            # los seis, comparando con labels.json (≈ 3 min)
uv run --project platform python -m platform_app.run --scenario nominal \
    --fault radar:mute:150:200 --fault gps:loss:240:285                         # fallos manuales por WebSocket (activa el modo interactivo)

# Por separado
uv run --project platform python -m platform_app.app [--port 8100]             # plataforma (API + /ws)
uv run --project ai-module-py python -m ai_module --platform http://127.0.0.1:8100 --detector-only
uv run --project ai-module-py python -m ai_module.detect_file runs/fallos/events.jsonl   # detector sobre un fichero
uv run --project platform python -m platform_app.viewer                         # visor (ventana)

# Generador y comprobaciones
uv run --project platform python -m platform_app.generator --all && uv run --project platform python -m platform_app.plot_scenario --all
uv run --project platform python -m platform_app.scenario_metrics
(cd contracts/python && uv run pytest -q)   # 125 passed, 1 skipped
(cd platform && uv run pytest -q)           # 192 passed
(cd ai-module-py && uv run pytest -q)       # 68 passed
uv run --project platform ruff check . && uv run --project platform ruff format --check .   # limpio
```
⚠️ **«Esperar al agente»**: en esta fase no hay monitor. El comando e2e **no** lo activa; si lo activas a mano (`w` en el visor o `control`), el reproductor se pausa en cada `DetectionRaised`/`DetectionUpdated` y **espera 90 s de reloj de pared por detección** (no llega ningún evento del monitor).

## 3. Resultados

### 3.1 Escenario → detecciones (en directo por WebSocket, a 16×, `run --all --check`; `sim_time` en s y T+mm:ss)
Los resultados coinciden con los del detector sobre `events.jsonl` (misma tabla). R = `DetectionRaised`, U = `DetectionUpdated`, C = `DetectionCleared`.

| Escenario | Regla (source) | R | U | C | Comentario |
|---|---|---|---|---|---|
| `nominal` | — | | | | **ninguna detección** |
| `viento` | `ROUTE_DEVIATION` | 106 (T+01:46) 30,5 m | | 156 | anomalía 95–150 s |
| `spoofing` | `SOURCE_DISCREPANCY` | 192 (T+03:12) 31,2 m | | 232 | engaño 168–222 s |
| `spoofing` | `ROUTE_DEVIATION` | 222 (T+03:42) 55,6 m | | 241 | recuperación al acabar el engaño (esperada) |
| `secuestro` | `ROUTE_DEVIATION` | 338 (T+05:38) 36,6 m | 341 (83,7 m, `high`) | 441 | una vez por episodio |
| `fallos` | `SOURCE_SILENT` (radar) | 125 (T+02:05) 7 s | | 180 | silencio 120–180 s |
| `fallos` | `GPS_DEGRADED` (gps) | **245 (T+04:05)** hdop 99,9, `high` | | 295 | **primer segundo** de la pérdida (245–290 s) |
| `fallos` | `SOURCE_DISCREPANCY` | 258 (T+04:18) 26,2 m | 288 (80,6 m) | 320 | después de `GPS_DEGRADED` |
| `fallos` | `ROUTE_DEVIATION` | 290 (T+04:50) 90,2 m, `high` | | 317 | recuperación tras la pérdida (esperada) |
| `fallos` | `SOURCE_SILENT` (gps) | 304 (T+05:04) 5 s | | 312 | silencio 300–312 s |
| `demo` | `ROUTE_DEVIATION` (viento) | 106 (T+01:46) | | 156 | |
| `demo` | `SOURCE_DISCREPANCY` (spoofing) | 192 (T+03:12) | | 232 | |
| `demo` | `ROUTE_DEVIATION` (recuperación) | 222 (T+03:42) 73,9 m | | 234 | |
| `demo` | `ROUTE_DEVIATION` (secuestro) | 338 (T+05:38) | 341 (84,5 m) | 441 | |

`--check`: **todo ✅** (cada regla esperada, una vez por episodio, dentro de su `eval_window`; `SOURCE_SILENT` solo de la fuente silenciada; `GPS_DEGRADED` en el primer segundo y `SOURCE_DISCREPANCY` después; **0 detecciones fuera de las ventanas**). Duración: ≈ 35 s de reloj por escenario a 16×.

### 3.2 Fallo manual por WebSocket (`nominal` con `--fault radar:mute:150:200 --fault gps:loss:240:285 --fault meteo:mute:60:100`)
`SOURCE_SILENT` meteo (T+01:31) y radar (T+02:37); `GPS_DEGRADED` (T+04:01), `SOURCE_DISCREPANCY` (T+04:16, `UPDATED` T+04:44), `ROUTE_DEVIATION` de recuperación (T+04:46) y sus cierres. Con el modo interactivo **apagado** el `fault` se rechaza con el mensaje exacto; con él encendido, `loss` en el radar se rechaza por el esquema, un fallo duplicado también, el timeline recoge `InteractiveModeChanged` (`plr-0002`) y `FaultInjected` (`sim-0001`, `origin: manual`), `state.active_faults` lo muestra y `GET /api/truth` no pasa del instante actual.

### 3.3 Pruebas
- **En directo y sin intervenciones, los eventos son idénticos a `runs/<escenario>/events.jsonl` en los seis escenarios** (todo menos `plr-`, `seq` e `ingestion_time`); `cursor == total_events`.
- Plataforma: bus (comodines, orden), reproductor (pausa, paso, reinicio, `fault`, esperar al agente con un monitor falso), tools (corte temporal con `until` enorme, sin dominio `sim` ni verdad), WebSocket y REST, simulador (`mute` no cambia el ruido de las demás; `loss` ignora el viento: la estima se separa `viento · tiempo`), visor y comprobaciones del comando e2e.
- Módulo de IA: detector sobre los seis `events.jsonl`, unitarias con eventos sintéticos, cliente del bus contra un servidor WebSocket falso.

## 4. Decisiones nuevas (confírmame las que no te gusten)
1. **Ids del estado del reproductor: `plr-`** (`SimulationStarted`… y `InteractiveModeChanged`); `sim-` queda solo para `FaultInjected/Cleared`, numerados por el simulador. Era necesario para que el directo sea idéntico a `events.jsonl` (si no, el primer `SimulationStarted` se llevaba `sim-0001`). Sustituye a la regla de la Fase 1 («el reproductor continúa tras el último `sim-`»).
2. `Label.also_accepted_causes` (campo nuevo, obligatorio, casi siempre vacío) para «`GPS_JAMMING` o `SENSOR_FAULT`».
3. `GPS_DEGRADED.value` = el `hdop` del último `PositionUpdated` (umbral 3,0); el `message` dice qué falla (fix, satélites o hdop).
4. Un fallo programado no se puede terminar a mano; uno manual sobre una fuente con fallo se rechaza.
5. `GET /api/timeline` devuelve `events` + `truncated` (el contrato no lo fijaba; ya está en §6 y como `TimelineResponse`). `waypoints_planned` y `waypoints_reached` sin `BASE`. `trend`: ±20 % y al menos 2 m.
6. Detector: severidades (`ROUTE_DEVIATION`/`SOURCE_DISCREPANCY` `medium` y `high` al empeorar; `SOURCE_SILENT` `medium` para GPS y radar, `low` para el resto; `GPS_DEGRADED` `high` con `fix: none`); los ids `det-` comparten un contador con los `Updated`/`Cleared` (los `detection_id` no son contiguos); al acabar la misión los episodios abiertos se dejan abiertos (en los seis escenarios no queda ninguno); `SOURCE_SILENT` se evalúa solo al llegar eventos (por eso el GPS mudo desde T+300 salta en T+304).
7. `SimulationStarted.duration_s`/`total_events` son los de la ejecución **sin intervenciones**; `cursor` cuenta los eventos del simulador publicados (sin `plr-`).
8. Si el modo interactivo está encendido al cargar, se publica `InteractiveModeChanged{true}` justo tras `SimulationStarted`, para que el timeline nuevo lo registre.

## 5. Problemas
- **Marcador del dron:** el marcador de tupla `(3, 0, ángulo)` de matplotlib dibuja mal los ángulos que no son múltiplos de 90° (con rumbo 208° apuntaba al este). Lo sustituí por un marcador propio (`Path` + `Affine2D`), comprobado a ojo con rumbos 0°, 30°, 90°, 208° y 300°.
- Mi primera captura de la ventana Tk salió corrupta por guardar la figura desde un hilo distinto del de la GUI (era mi script de prueba, no el visor); repetida desde el hilo de la GUI.
- Pulsar `+` varias veces seguidas enviaba siempre la misma velocidad (el `state` tarda en confirmarla); ahora la velocidad se actualiza de forma optimista (con prueba).
- El hook de formato avisó varias veces de errores `E501` en ficheros de otro subagente mientras trabajaban en paralelo (ya corregidos al terminar).
- Mi primer corte de `build.py` borró de más (`F821 Undefined name '_plan_flight'`); reescrito entero sobre el simulador.
- Al cerrar la plataforma el visor registra `received 1012 (service restart)`: es el cierre normal de uvicorn, inofensivo.
- Nada se atascó más de 30 minutos.

## 6. URLs consultadas (regla 8)
- matplotlib 3.11.2: backends https://matplotlib.org/stable/users/explain/figure/backends.html · atajos y `keymap.*` https://matplotlib.org/stable/users/explain/figure/interactive.html y https://matplotlib.org/stable/users/explain/customizing.html · eventos de teclado https://matplotlib.org/stable/users/explain/figure/event_handling.html · `new_timer`, `KeyEvent` https://matplotlib.org/stable/api/backend_bases_api.html · `Axes.set_aspect` https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.set_aspect.html · marcadores https://matplotlib.org/stable/api/markers_api.html
- websockets (cliente síncrono) https://websockets.readthedocs.io/en/stable/reference/sync/client.html · (asyncio) https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html y https://websockets.readthedocs.io/en/stable/reference/asyncio/server.html
- Python `urllib.request` https://docs.python.org/3/library/urllib.request.html
- FastAPI https://fastapi.tiangolo.com/advanced/websockets/ y https://fastapi.tiangolo.com/advanced/events/ · Starlette `TestClient` https://starlette.dev/testclient/ · uvicorn https://uvicorn.dev/

⚠️ **Sin confirmar en la documentación** (verificado solo ejecutándolo): (1) que `rcParams["keymap.grid"] = []` (y `yscale`, `xscale`, `grid_minor`) desactive el atajo: la plantilla de matplotlib habla de dejar el campo vacío en `matplotlibrc`; en código funciona (la `g` y la `l` llegan al visor); (2) cómo llegan al `key_press_event` el espacio, `+` y `-` (la página no los nombra): el visor acepta `" "`/`space`, `+`/`plus`/`add`/`=` y `-`/`minus`/`subtract`/`_`; probado con eventos simulados, no con el teclado físico; (3) el sentido del ángulo del marcador de tupla (no documentado; por eso uso `Affine2D`); (4) que `websockets.sync` se introdujo en la 11.0 (resumen del registro de cambios, no leído literalmente) y si `send` y `recv` pueden llamarse desde hilos distintos (solo se documenta que dos hilos no pueden llamar a `recv` a la vez; el visor envía con un cerrojo y recibe en un único hilo); (5) que `uvicorn.run(app, host, port)` acepte el objeto de la app y el extra `[standard]` (lo comprobé arrancando el servidor); (6) que `port=0` elija un puerto libre en `websockets.serve` (funciona en las pruebas); (7) `www.starlette.io` no resolvió: usé `starlette.dev`. `python3-tk` es el paquete de Ubuntu; matplotlib solo dice `python-tk` «o similar». Versiones salidas de `uv`: fastapi 0.152.0, uvicorn 0.54.0, websockets 17.3, httpx2 2.15.1 (dev; Starlette 1.9 marca `httpx` como obsoleto para `TestClient`), pyyaml 6.0.3.

## 7. Qué queda
- **Fase 3:** motor de agente, monitor, informe, chats, guardrails, trazas y `evaluate.py`; vLLM (no se ha tocado). La evaluación debe aplicar la regla del `ROUTE_DEVIATION` de recuperación (§4.4 de la definición).
- **Fase 4:** web (Node y pnpm siguen sin instalar); `web/CLAUDE.md` ya describe el panel de fallos con `mute`/`loss`, el interruptor interactivo y `active_faults`.
- El visor no recupera el historial si se conecta a mitad de ejecución (`GET /api/timeline` lo permitiría).
- `SOURCE_SILENT` podría afinarse con los `state` cada 0,5 s (propuesta del subagente del módulo de IA); no se hace porque el directo y el fichero dejarían de dar lo mismo.
- `viento` abre `ROUTE_DEVIATION` con 30,5 m (umbral 30): margen estrecho si cambia el generador.

## 8. Revisión de contratos y copias

### 8.1 `revisor-contratos` (solo lectura; sin shell, no ejecutó nada)
Conforme: separación (regla 3; el módulo de IA no importa `platform_app` y `run.py` lo lanza como subproceso), verdad (regla 4; las tools solo leen el timeline por `ToolContext.events`, que descarta el dominio `sim` también cuando se pide `type=FaultInjected`; `GET /api/truth` solo lo usan el visor y, luego, la web), corte temporal (regla 5; un único punto), WebSocket, ids (`plr-`, `sim-`, `det-`), payloads, `get_flight_summary` (4 reglas, 6 causas, sin `BASE`), `get_track_metrics` sin datos de una fuente, y regla 16 (sin menciones propias, de personas ni de ficheros excluidos en `platform/`, `ai-module-py/`, `contracts/`, `agent-assets/`, `scenarios/` y `runs/`). **Sin bloqueantes.** Puntos a corregir, **todos corregidos**:
1. El módulo de IA se suscribía a `citadel.pub.evt.>` y recibía `FaultInjected`/`FaultCleared`/`InteractiveModeChanged`, y guardaba `active_faults`/`interactive` del `state`. Ahora se suscribe a patrones explícitos (`air`, `env`, `ai`, `ops` y solo `SimulationStarted`/`Reset`/`Finished`) y del `state` solo guarda `sim_time`. Probado en directo (`fallos` y `nominal` siguen en ✅).
2. El detector usa del dominio `sim` el ciclo de vida (`Started`/`Reset` reinician, `Finished` para los silencios): escrito en su comentario y en `ai-module-py/CLAUDE.md`.
3. El `message` de `GPS_DEGRADED` no decía qué valor falla: ahora lista las condiciones que fallan («4 satélites (mínimo 6), hdop 4,2 (máximo 3)»), con prueba.
4. El detector no ignoraba el dominio `ops` (un `OperatorMessage` adelantaba el reloj y podía colarse en `trigger_event_ids`): ignorado, con prueba.
5. `docs/01_definicion.md` §7.3: las skills no citaban `GPS_DEGRADED` ni la recuperación tras una pérdida de GPS.
6. Comentarios obsoletos («fuentes silenciadas programadas») en cinco YAML (solo comentarios; `runs/` no cambia).
7. `scenarios/README.md`: el ejemplo de `labels.json` sin `also_accepted_causes`, un «(Fase 1)» y una referencia al informe de la fase (regla 16).
8. Fechas de versión en la cabecera de `contracts/eventos.md`: son fechas de revisión, no de reuniones; se dejan.

Notas atendidas: `hello` repetido con otro tipo de cliente se rechaza (con prueba); `muted_sources()` del visor pasa a `silenced_sources()`; una aserción tautológica de `test_api.py`; `TimelineResponse` en el contrato.

Notas que quedaron abiertas (resueltas en §10): (a) cualquier cliente, también `ai-module`, puede mandar `control`; el contrato no lo restringe (valorar limitarlo a `web`); (b) `detect_file.py` lee un `events.jsonl` por argumento: es una herramienta de desarrollo (no lee verdad ni etiquetas); (c) `step` desde `idle` pasa a pausa sin publicar `SimulationPaused` y el siguiente play publica `SimulationResumed`; (d) `load`/`reset` ejecutan `generate()` (≈ 60 ms) dentro del bucle asyncio; (e) `tools/summary.py` importa la constante `BASE` de `generator.controller`.

### 8.2 Copias (reglas 13 y 15)
Hechas al terminar la fase: `docs/fases/` y los 18 PNG de `runs/*/` en `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`; instantánea del código en `results/snapshots/fase2/` y la limpia en `results/snapshots-limpias/fase2/` (con las dos comprobaciones de la regla 15). No hay `eval.md` ni `informe.md` todavía (Fase 3).

## 9. Mensaje de commit propuesto
```
feat: phase 2 - live simulator, platform, detector, viewer and contracts v0.5

- platform: incremental simulator (single engine for runs/ and the live player), live player
  with interactive mode and mute/loss faults (GPS loss navigates on estimate), bus with
  wildcards, timeline, data tools with time cutoff, REST API and WebSocket
- platform: live matplotlib viewer (keys send control messages) and end-to-end run command
- ai-module-py: bus client and rule detector with four rules (GPS_DEGRADED added)
- contracts v0.5: fault mode, interactive mode, GPS_DEGRADED, GPS_JAMMING, gps_loss labels,
  plr- ids for player state, TimelineResponse; agent skills and prompts updated
- scenarios: fallos.yaml gets a 45 s GPS loss; runs/ regenerated (events, labels, fallos truth, PNGs)

```

## 10. Cambios tras tu revisión
Fase 2 **aprobada**; las decisiones 1–3 (`plr-`/`sim-`, `also_accepted_causes`, `TimelineResponse`) se mantienen. Cambios hechos:
- **`control` solo para clientes `web`** (nota (a) del revisor): si lo manda otro tipo de cliente (`ai-module`), la plataforma responde `error` («solo los clientes de tipo web pueden enviar control») y no hace nada. Anotado en `contracts/eventos.md` §5, con la indicación de que una señal del módulo de IA hacia el reproductor (p. ej. para «esperar al agente» en la Fase 3) se define como mensaje propio en el contrato y no como `control` genérico. Prueba: `test_only_web_clients_can_send_control` (play, interactive y load desde `ai-module` rechazados y sin efecto; `web` sigue funcionando). Dos pruebas antiguas que mandaban `control` como `ai-module` pasan a cliente `web`. El visor y `run.py` ya eran clientes `web`; el módulo de IA no manda `control`.
- **Paso desde `idle` publica `SimulationPaused`** (nota (c)): el primer `step` con la simulación sin arrancar publica el evento y, justo después, `SimulationPaused{user}`; el `play` siguiente publica `SimulationResumed`. Anotado en el contrato (§4, `SimulationPaused`). Pruebas: `test_a_step_from_idle_publishes_paused_so_that_play_resumes_coherently` (secuencia `plr-`: Started, Paused, Resumed; el segundo paso ya en pausa no repite el aviso) y `test_step_publishes_one_event_and_pauses` (ahora cuenta eventos del simulador con `cursor`); el test del WebSocket espera `MissionPlanned` + `SimulationPaused` en ese primer paso.
- **Se quedan como están** (b) `detect_file.py`, (d) `generate()` en el bucle asyncio y (e) `BASE` en `tools/summary.py`; esta última queda anotada como refactorización en `docs/mejoras_futuras.md` (mover `BASE` a `poc_contracts`).
- **`docs/mejoras_futuras.md`:** visor con historial desde `GET /api/timeline` (no se hace ahora) y la sección «Refactorización».
- **`CLAUDE.md`, regla 12:** el mensaje de commit propuesto en `docs/fases/faseN.md` no lleva línea `Co-Authored-By` ni mención de quién lo ha generado. Quitada del mensaje de la Fase 2 (`fase0.md` y `fase1.md` no se tocan).
- **Pruebas:** contratos 125 passed (1 skipped), plataforma **192 passed**, módulo de IA 68 passed; `ruff check` y `ruff format --check` limpios.
- **Copias:** `docs/fases/` y los PNG de `runs/*/` en `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`, e instantáneas `snapshots/fase2/` y `snapshots-limpias/fase2/` rehechas desde cero, con las dos comprobaciones de la regla 15 vacías.
