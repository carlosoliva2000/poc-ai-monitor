# D1a · API del simulador

Informe de cierre. Referencia: especificación del núcleo v2 (v1.4, §2 y §10). Escrito para: Carlos, que revisa la fase y hace el commit.

## Qué se hizo
El simulador pasa a poder usarse como **plataforma externa** (como un ciber range): además del `/ws` y los `GET /api/*` de hoy (que **no cambian**, y siguen siendo lo que usan la web y los procesos de IA), expone una **API REST versionada `/api/v1`** con endpoints por asset, flujo en directo SSE reanudable, control del ejercicio e *injects* del instructor. Guía, ejemplos y OpenAPI: `contracts/api/` (`README.md` y `sim-api-v1.json`; el OpenAPI se sirve en `/api/v1/openapi.json` y `/docs`, y está exportado al repo con `python -m platform_app.sim_api.export_openapi`, vigilado por un test). Contrato del bus **sin cambios**; v1.5 aditiva solo de documento.

## Lo que se ve del simulador de David y qué se tomó
Solo lectura (no se arrancó ni se instaló nada): API FastAPI `/api/v1` con `drone/state`, `drone/stream` (SSE), vuelos grabados y mensajes paginados por cursor entero (`since`/`limit`/`types`, `next`, `has_more`); una instancia por dron y por puerto, sin el id en la ruta; un consumidor aparte (`dron-tui --dump`) que reconecta con `Last-Event-ID` y escribe JSON Lines; sin OpenAPI estático, sin CORS, sin autenticación, sin Docker. **Tomado:** `/api/v1` con etiquetas, SSE con `id` entero y `Last-Event-ID`, cursor `since`/`next`/`has_more`, `types`, keep-alive, `Cache-Control: no-cache`, un consumidor que no importa el servidor y escribe JSON Lines. **No tomado:** una instancia por dron (aquí hay 4 assets en un proceso, con id en la ruta), los vuelos grabados (nuestro histórico es el de la ejecución), los textos en español (aquí, inglés, regla 14). Se añade lo que él no tiene: el `heartbeat` con marca de agua, el `gap` y el OpenAPI exportado.

## Reparto entre ciber range y zona común
| Ciber range (lo expone la API) | Zona común (en la D1b la sustituye el bus/NATS) |
|---|---|
| generador, reproductor, escenarios, control del ejercicio, *injects*, verdad | el bus y el `/ws`, la línea temporal, lo que publican la IA (`ai.*`) y el operador (`ops.*`) |

La API solo expone la izquierda: `air`/`env` por asset, y `sim.*` y la verdad solo por `/api/v1/instructor/*`. Nada de `ai.*` ni `ops.*`.

## Inventario
`d1` (dron: GPS, receptor, autopiloto, batería, misión), `radar-1`, `meteo-1` y `gcs-1` (**estación de tierra, asset propio**: dueña de `LinkStatus`; decidido). Cada uno trae su ficha (`config`) con lo que el monitor lee hoy de `assets.yaml` (límites del dron, periodos, σ y C/N0 nominal del receptor, posición y alcance del radar); nunca viento, fallos, emisores ni nada de la verdad. Vacío mientras no hay escenario cargado.

## Formato de cada asset
Cabecera propia (`seq`, `run_id`, `asset_id`, `subject`, `type`, `id`, `sim_time`, `time_utc`, `received_utc`) y en `data` el payload del evento del contrato sin cambios. `asset_id` es quien publica y `subject` de quién habla. Ciclo de vida (`RunStarted`/`RunReset`/`RunFinished`) por cada asset, sin nombre de escenario. `seq` por asset que no se reinicia. No se pierde información: el topic y la fuente se reconstruyen con `poc_contracts.topics`.

## Endpoints y flujo
`/assets`, `/assets/{id}`, `/assets/{id}/state`, `/assets/{id}/messages`, `/assets/{id}/stream`; `/exercise/*` (load, play, pause, step, reset, speed, interactive, scenarios); `/instructor/*` (faults, commands, injects, truth, stream). Rutas por id y no por tipo (admite varios drones). SSE: `event: message` con `id` = `seq`, `heartbeat` cada segundo sin id (con el `sim_time` hasta el que ha llegado el ejercicio) y `gap` si lo pedido ya no se conserva; reanuda con `Last-Event-ID` o `since` (`-1` = todo). Lee de un registro por índice, sin cola por cliente: no se pierde ni se repite nada. Pausa: solo `heartbeat`; carga o reinicio: `RunReset` y `RunStarted`, el `seq` sigue; velocidad: solo el ritmo. Retención: 200 000 mensajes por asset y dos ejecuciones.

**Control compartido.** `control.py::apply_control` despacha las órdenes del WebSocket y de REST: misma validación (modelos de `poc_contracts.ws`) y mismos errores (REST: 404 desconocido, 409 «la orden no procede», 422 cuerpo no válido). Una orden por REST llega a los clientes de `/ws` como si la hubiera dado la web (test). **Ajuste de la revisión:** sin escenario cargado, `play`, `pause`, `step`, `reset`, `speed`, `faults` y `commands` dan siempre «no scenario is loaded» (antes `speed` no daba error y `faults`/`commands` decían «interactive mode is off»); vale también para el WebSocket. `load` e `interactive` se salvan (el modo interactivo se apaga con cada carga).

**Un worker que arranca antes del ejercicio** reintenta `GET /assets/{id}` (404 «no scenario is loaded») con espera creciente; el flujo y el histórico sí funcionan sin escenario. Documentado en la guía y hecho en `tools/sim_api/consume.py` (`fetch_asset`, con test).

## Equivalencia
`tools/sim_api/adapter.py` (lo que hará el mediador) lee solo la API, mezcla los flujos con las marcas de agua de los `heartbeat` y reconstruye los eventos del bus. **En `demo`** (plataforma real, a 16×), `ai-module-py/tests/test_sim_api_equivalence.py`: los eventos del mundo reconstruidos son **idénticos y en el mismo orden** que los del timeline, y alimentando un monitor aparte con ellos salen los **mismos `IncidentUpdated`** (21 transiciones en `demo`) que el monitor real conectado al `/ws`. Además, sin servidor, `test_sim_api_adapter.py` lo repite en los **11 escenarios** de `runs/`, con los mensajes mezclados entre assets de forma distinta (3 semillas) y con un reinicio a mitad.

## Consumidor de referencia
`tools/sim_api/consume.py` (solo biblioteca estándar): `--all` o `--assets`, `--types`, `--since`, `--heartbeats`, `--as-bus`, `--max-seconds`; JSON Lines; reconecta con `Last-Event-ID` sin repetir. Ejemplos reales de cada endpoint y del flujo (puerto temporal 8199, ya liberado): `experiments/d1a/ejemplos.md` y `ejemplos.sh` (**solo en `results/`**: `experiments/**` está en `.gitignore`, que no se ha tocado); los que importan están en la guía.

## Despliegue configurable
`POC_PLATFORM_HOST`, `POC_PLATFORM_PORT`, `POC_WEB_ORIGINS` y `--host` (en `app` y `run`); la web, `NEXT_PUBLIC_PLATFORM_URL` (se fija al construir) y `WEB_HOST`/`WEB_PORT`. Los valores por defecto no cambian. Nada de Docker; la plataforma nunca escucha en `0.0.0.0` salvo que se le diga.

## Cambios de contrato
Ninguno en el bus (eventos, topics ni mensajes del WebSocket). `contracts/eventos.md` pasa a v1.5 (aditiva): §6 bis (API por asset) y la nota de que `control` sin escenario da «no scenario is loaded». Modelos nuevos en `poc_contracts.sim_api` (no se exportan a `contracts/schemas/`: los cubre el OpenAPI).

## Tests
Plataforma **336** (nuevos: `test_sim_api` 15, `test_sim_api_control` 13, `test_sim_api_adapter` 4, `test_sim_api_openapi` 1), contratos **139**, módulo de IA **234 + 2 e2e** (la nueva de equivalencia y la de ids compartidos, que siguen pasando con la plataforma cambiada), web **85** (typecheck bien). Los importantes: cada asset da solo lo suyo y la verdad no sale por los assets; el flujo sin pérdidas ni duplicados, también al reanudar y a través de un reinicio; lo que da la API es lo del bus; REST y `/ws` equivalentes. `ruff check` y `ruff format --check` limpios. Lo congelado (`check_freeze`, prompts) y `runs/` sin cambios. Un test existente se adaptó: el doble de `start_platform` de `test_run_checks.py` acepta ahora `host`.

## Problemas
- **`gap` falso con `since=-1`** (lo vieron los ejemplos reales, no los tests): «desde el principio» se leía como un cursor perdido. Corregido (`max(since + 1, 1)`) y con test.
- Mis primeras versiones de los tests de SSE se colgaban al pedir más mensajes de los que existían (los `heartbeat` impiden que salte el timeout del socket): el lector tiene ahora un plazo de 8 s.
- Un test de ejecuciones retenidas fallaba porque tres cargas en el mismo segundo repiten el `run_id` de la primera (el reproductor solo evita repetir el inmediatamente anterior): el test fija los ids. No es un fallo del reproductor en uso real.
- Nada pasó de 30 minutos.

## Lo pendiente para la D1b
Workers, mediadores y NATS (el adaptador es el esqueleto; falta el SDK, el registro de contratos y la cola de errores); **describir el flujo en AsyncAPI** (lo propuso el equipo de la taxonomía para los contratos): conviene decidirlo con la taxonomía delante, porque el OpenAPI y la guía ya cubren el REST y el SSE y AsyncAPI solo aportaría los eventos nativos; contenedores y configuración de la web en ejecución (las `NEXT_PUBLIC_*` se fijan al construir); dónde va el chat de IA; que el monitor lea el inventario (σ del GPS 1,5 frente al 1,53 de `assets.yaml`); el orden entre assets con NATS; autenticación y límites. Detalle en `docs/mejoras_futuras.md`.

## Lo que propongo cambiar en la especificación
- **§10:** el flujo es **SSE y no WebSocket** (el control va por REST; el `/ws` sigue siendo el bus de la plataforma); la estación de tierra es **asset propio** (`gcs-1`); el asset del evento se reparte en `asset_id` (quien publica) y `subject` (de quién habla), lo que contesta la pregunta abierta; los workers reintentan ante 404 hasta que haya escenario.
- **§9:** la D1a se hizo **antes** de la E8 (no toca lo congelado ni el simulador).
- **§12:** registrar la v1.5 aditiva (API del simulador) y esta fase.

## Reglas 13 y 15
`snapshots/d1a/` (664 ficheros) y `snapshots-limpias/d1a/` (606); las dos búsquedas de la regla 15 salieron vacías a la primera; copia de `docs/fases/`, `contracts/api/` y `experiments/d1a/` en `results/`. Puertos 8000, 8100 y 3000 como estaban (no se tocaron; el 8199 temporal quedó libre).

## URLs consultadas
Ninguna: no se afirmó nada nuevo sobre librerías. El SSE está escrito a mano (`text/event-stream` con `StreamingResponse`); lo único comprobado fue que el entorno trae FastAPI 0.152.0 y Starlette 1.9.0.

## Mensaje de commit propuesto
```
D1a: simulator REST API per asset (/api/v1), contract v1.5 (document only)

- /api/v1: inventory with each asset's configuration (d1, radar-1, meteo-1, gcs-1), state,
  paged history and a resumable SSE stream per asset in its own JSON format (own header plus the
  bus payload unchanged); exercise control and instructor injects; the ground truth only under
  /api/v1/instructor/*
- one registry per asset with a seq that never restarts; readers go by index, so a slow client
  loses and repeats nothing; heartbeat watermark and gap events
- control orders go through one function shared by the WebSocket and REST; without a loaded
  scenario they answer "no scenario is loaded"
- host, port and CORS origins configurable (POC_PLATFORM_HOST, POC_PLATFORM_PORT, POC_WEB_ORIGINS,
  --host); the web reads NEXT_PUBLIC_PLATFORM_URL
- OpenAPI exported to contracts/api/sim-api-v1.json, integration guide in contracts/api/README.md
- tools/sim_api: reference consumer (retries until a scenario exists) and the adapter that rebuilds
  the bus events from the API; equivalence tests on demo (same events and incidents as the bus)
  and on the 11 scenarios
```
