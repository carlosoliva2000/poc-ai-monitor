# platform/

La plataforma hace el papel de MDO: **el mundo**. Simula, publica eventos, guarda el historial y ofrece servicios de datos. No razona ni diagnostica nada.

## Qué contiene
- **Generador y controlador** (`generator/`): lee `scenarios/<nombre>.yaml` y escribe `runs/<nombre>/` (`plan.json`, `truth.json`, `events.jsonl`, `labels.json`). Física en `docs/01_definicion.md` §4 y referencia comprobada en `ref/simcheck_controlador.py`: el generador debe dar los mismos órdenes de magnitud (con ruido de sensores encima). Determinista con la semilla (`random.Random(seed)` o `numpy.random.default_rng(seed)`, uno solo para todo).
- **Gráficas** (`plot_scenario.py`): las tres figuras de §4.5 de la definición, con matplotlib. Las flechas con `quiver` (comprueba su firma en la documentación oficial antes de usarla), coloreadas por velocidad, con barra de color. Fondo claro, ejes iguales (`set_aspect("equal")`), leyenda, título con el escenario.
- **Reproductor** (`player.py`): reloj simulado con `asyncio`; publica los eventos cuyo `sim_time` ≤ reloj; velocidades, pausa, paso, reinicio y «esperar al agente» (§5). **Fallos manuales:** lista de fuentes silenciadas (`control` → `fault`); descarta al publicar los eventos de esas fuentes y publica `FaultInjected`/`FaultCleared` con `origin: manual`. Se vacía al reiniciar o cargar otro escenario.
- **Fallos programados** (`faults` del YAML): los aplica el generador al escribir `events.jsonl` (quita los eventos de la fuente en la ventana e inserta `FaultInjected`/`FaultCleared` con `origin: scenario`) y los añade a `labels.json`.
- **Bus** (`bus.py`): en memoria, `publish`/`subscribe` con comodines `*` y `>`; pone `seq` e `ingestion_time`; los no efímeros van al timeline.
- **Timeline** (`timeline.py`): lista en memoria con índices por fuente y tipo; volcado a `runs/<escenario>/<run_id>/timeline.jsonl` al terminar.
- **Tools de datos** (`tools/`): nunca devuelven eventos del dominio `sim`. `get_events`, `get_mission_plan`, `get_track_metrics`, `get_my_alerts`, `get_flight_summary`, con los resultados de `contracts/eventos.md` §7. **Corte temporal obligatorio** (`until` efectivo = mín(pedido, `sim_time` actual)). No leen `truth.json` ni `labels.json`.
- **API** (`app.py`, FastAPI + uvicorn, `127.0.0.1:8100`): REST de §6 y WebSocket `/ws` de §5 de los contratos.

## Notas
- Un solo proceso; un `run_id` por cada `load` (`AAAAMMDD-HHMMSS`).
- `get_track_metrics`: la desviación respecto al plan es la distancia a la polilínea de waypoints; `drift_direction_deg` es el rumbo del vector que va del punto más cercano de la ruta a la posición GPS (media del tramo); `course_deg` sale de posiciones consecutivas; `trend` compara la media del primer y del último tercio del intervalo (umbral ±20 %).
- Pruebas (`pytest`): comodines del bus, orden por `sim_time`, corte temporal de las tools, que ninguna tool devuelve campos de la verdad ni eventos `sim`, que un fallo manual descarta los eventos de esa fuente, determinismo del generador (misma semilla → mismos eventos) y criterios de `scenarios/README.md`.
- Comando de ejecución sin web: `uv run python -m platform_app.run --scenario demo --speed 16` (o el nombre que elijas; documéntalo en `docs/fases/fase2.md`). Ojo: no llames al paquete `platform`, que choca con el módulo estándar de Python.
