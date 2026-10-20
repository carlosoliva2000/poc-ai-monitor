# Fase 1 · generador, controlador y gráficas

Fecha: 20/10/2026. Estado: **terminada, pendiente de tu revisión de las gráficas** (la Fase 2 no se ha empezado).

## 1. Qué se hizo

### 1.1 Generador (`platform/src/platform_app/`)
| Módulo | Contenido |
|---|---|
| `geometry.py` | Rumbos, diferencia de ángulos, distancia a segmento y a polilínea (la desviación de ruta; la reutilizarán `get_track_metrics` y el detector) |
| `generator/disturbances.py` | Viento en cada instante (rampa de `ramp_s`), desfase del GPS (spoofing) y ventana de secuestro |
| `generator/controller.py` | La física de `ref/simcheck_controlador.py` con paso de 0,1 s y contador entero (sin acumular floats): punto de mira sobre el tramo, giro y aceleración limitados, viento sumado a la velocidad, secuestro, spoofing. `fly(config, perturbed)`: con `perturbed=False` es el plan (sin viento, spoofing ni secuestro) |
| `generator/sensors.py` | Muestreo y ruido de GPS, radar, meteo, enlace y batería (§4.3). Un único `random.Random(seed)` |
| `generator/build.py` | Eventos (`EventDraft` validados), fallos programados, `plan.json`, `truth.json`, `labels.json` y escritura en `runs/<escenario>/` |
| `generator/scenario_io.py`, `__main__.py` | Lectura del YAML y comando de generación |
| `scenario_metrics.py` | Mide los criterios de `scenarios/README.md` sobre `runs/<escenario>/`. **Lee `truth.json`**: está fuera de `tools/` y nada de lo que usarán las tools lo importa (regla 4; lo dice su docstring) |
| `plot_scenario.py` | Las tres figuras de §4.5 |

Se genera **todo** con la misma secuencia de ruido y después se filtran los fallos programados: con la misma semilla, `fallos` tiene exactamente los eventos de `nominal` menos los silenciados (comprobado por una prueba).

### 1.2 Contrato v0.4 (lo que dejaste para el final de la fase)
- `contracts/python/src/poc_contracts/scenario.py` (`ScenarioConfig` y subestructuras) y `run_files.py` (`PlanFile`, `TruthFile`, `LabelsFile`, `Label`); `LabelType` en `enums.py`. `extra="forbid"` en todos.
- `contracts/eventos.md` **v0.4**: sección nueva **§8 «Ficheros del generador»** (YAML con ejemplo completo, `plan.json`, `truth.json`, `labels.json`, `events.jsonl` con reglas de ids y de fallos), y dos precisiones en §4 y §6 (ver 3.2).
- `contracts/schemas/files/` (4 esquemas nuevos; **52** en total) exportados con el script de siempre. `poc-contracts` pasa a 0.4.0 (y `pyyaml` como dependencia de desarrollo, solo para validar el ejemplo YAML del documento).
- La prueba de ejemplos del documento valida ahora también los 3 JSON nuevos y el bloque YAML.

## 2. Cómo se ejecuta
```bash
uv run --project platform python -m platform_app.generator --all          # runs/<escenario>/ (los seis)
uv run --project platform python -m platform_app.plot_scenario --all      # los 18 PNG  (--only plan|xy|time)
uv run --project platform python -m platform_app.scenario_metrics         # tabla de criterios
uv run --project contracts/python python -m poc_contracts.export_schemas  # esquemas JSON
(cd contracts/python && uv run pytest -q)   # 112 passed, 1 skipped
(cd platform         && uv run pytest -q)   # 83 passed
(cd ai-module-py     && uv run pytest -q)   # 1 passed
ruff check . && ruff format --check .       # limpio
```
La salida son 1 063 (demo), 807 (fallos), 845 (nominal), 1 056 (secuestro), 854 (spoofing) y 886 (viento) eventos.

## 3. Decisiones (confírmame las que no te gusten)

### 3.1 Desviación respecto a lo que pediste — ⚠️ léelo
**`radar.sigma_m` queda en 5,0, no en 6,0.** Tu regla de reserva (bajar a 6,0 si la media móvil GPS–radar no quedaba < 20 m) se ejecutó y **no bastó**; la causa es una cola de ruido de la semilla 42 (un par de medidas seguidas del radar a ~4σ), que escala con σ. El README del escenario permite ajustar parámetros del YAML (no la física), así que probé 5,0 y cumple. Máximo de la media móvil de 3 (GPS interpolado al instante del radar, fuera de las ventanas de `labels.json` más 6 s de margen de la propia media):

| σ del radar | nominal | fallos | viento | spoofing | secuestro | demo |
|---|---|---|---|---|---|---|
| 8,0 (antes) | 26,7 | 26,7 | 26,9 | 28,1 | 18,3 | 17,4 |
| 6,0 (tu regla) | 20,1 | 20,1 | 20,2 | **21,4** | 14,0 | 13,0 |
| **5,0 (ahora)** | 16,8 | 16,8 | 16,9 | 18,0 | 11,9 | 10,9 |

Con 8,0 `nominal` habría disparado `SOURCE_DISCREPANCY` (abre en 25 m). Cambiado en los seis YAML y en la tabla de fuentes de `docs/01_definicion.md` (σ ≈ 5 m). Si prefieres conservar 6,0, la alternativa es otra semilla, no otro σ.

### 3.2 Decisiones nuevas del contrato
1. **`MissionPlanned.waypoints` incluye la vuelta**: `BASE, WP1…WP4, BASE`. El detector necesita la polilínea completa para medir la desviación en el último tramo, y el índice de `WaypointReached` es la posición en esa lista (la llegada final a la base lleva índice 5). Consecuencia para la Fase 2: `get_flight_summary.waypoints_planned` debe **filtrar `BASE`** (el ejemplo del contrato es `[WP1…WP4]`).
2. **Numeración `sim-`**: los fallos programados ocupan `sim-0001…`; el reproductor debe continuar tras el último `sim-` de `events.jsonl`.
3. **`expected_rules` del spoofing = `SOURCE_DISCREPANCY` y `ROUTE_DEVIATION`**: al acabar el engaño el GPS salta a la verdad (~80 m de la ruta) y la regla de ruta salta con razón. Semántica: basta con una de las esperadas. Si el evaluador debe tratarlo como falsa alarma, se quita de `labels.json`.
4. `labels.json` lleva siempre `source` (null salvo en fallos); un secuestro sin `end_s` se etiqueta hasta el fin de la misión; la ventana de fallo es semiabierta `[start_s, end_s)`.
5. `return_to_base: false` no está soportado (error explícito): ningún escenario lo usa y el contrato de `MissionCompleted` solo tiene `returned_to_base` | `timeout`.

### 3.3 Decisiones del generador
- **Ruido** (constantes con nombre en `sensors.py`; σ del YAML cuando existe): altitud GPS 0,5 m; velocidad/rumbo del GPS 0,2 m/s / 1° (**la velocidad y el rumbo del GPS incluyen la deriva del engaño**, como los de un receptor real); radar: velocidad 0,5 m/s, rumbo 3°, `quality` 0,85–0,95; enlace: RSSI 1,5 dB, latencia 5 ms; batería lineal con σ 0,1 % y voltaje 6S (21,0–25,2 V).
- **Las rachas no entran en la física** (solo el viento medio, como en la referencia); sí se reportan en `WindReported` y se ven en `truth.json`.
- El controlador usa el GPS **sin ruido** (verdad + desfase): el ruido solo está en lo que se reporta.
- Los umbrales numéricos de varios criterios de §3 de `scenarios/README.md` los he fijado yo porque el README dice «cientos de metros», «salta», «recupera»: salto del GPS al acabar el engaño > 40 m; secuestro > 300 m; el radar ve lo mismo que la verdad (media de los últimos 10 s, ±8 m); «recupera la ruta» = verdad a < 15 m hasta la siguiente anomalía (o el fin del vuelo).
- **`scenario_metrics` mide con la verdad a 1 Hz**, que infravalora los picos de las esquinas (nominal: 11,2 m a 1 Hz frente a 12,8 m a 0,1 s; el controlador a 0,1 s da exactamente los 12,8 m de la referencia, ver 4.2).

### 3.4 Gráficas
Fondo claro, ejes iguales, leyenda, título con el escenario; colores de la paleta categórica validada con el script de la skill (los tres primeros huecos —verdad azul, GPS naranja, radar aguamarina— pasan todos los pares; el aguamarina queda a 2,74:1 de contraste sobre claro, así que va siempre con leyenda y marcador propio: rombos; la estación meteo, magenta `#d55181`, pasa los cinco controles con la verdad). Velocidad: rampa secuencial de un solo tono azul.
- En `scenario_time.png` el panel de desviación usa escala **simétrica logarítmica** (lineal hasta 100 m) solo cuando hay un pico de más de 200 m (secuestro y demo); si no, el viento y el spoofing (50–75 m) quedarían aplastados por los 700 m. El eje lo dice.
- Dibujan los umbrales de las reglas de §6 (30/15 m y 25/12 m) para ver a qué altura caen las medidas.
- Las flechas son de longitud fija (no representan velocidad), una cada 8 s.

## 4. Resultados

### 4.1 Escenario → criterio → valor medido
Salida literal de `python -m platform_app.scenario_metrics` (**45 criterios, 45 ✅, 0 ❌**).

| Escenario | Criterio | Valor medido | OK |
|---|---|---|---|
| `demo` | A1 viento: desviación máx. de la verdad (episodio + 30 s), 40–120 m | 51.8 m | ✅ |
| `demo` | A1 viento: GPS y radar coinciden en el episodio (< 20 m) | 9.8 m | ✅ |
| `demo` | A1: recupera la ruta (< 15 m) antes de la siguiente | T+151 s (1 s tras el fin) | ✅ |
| `demo` | A2 spoofing: GPS a < 15 m del plan durante el engaño | 9.0 m | ✅ |
| `demo` | A2 spoofing: la verdad se aleja 70–90 m al final del engaño | 74.3 m | ✅ |
| `demo` | A2 spoofing: el radar ve lo mismo que la verdad (media 10 s, ±8 m) | radar 66.9 m, verdad 67.5 m | ✅ |
| `demo` | A2 spoofing: el GPS salta al terminar el engaño (> 40 m) | 84.3 m | ✅ |
| `demo` | A2: recupera la ruta (< 15 m) antes de la siguiente | T+229 s (7 s tras el fin) | ✅ |
| `demo` | A3 secuestro: la verdad se aleja cientos de metros (> 300 m) | 717.2 m | ✅ |
| `demo` | A3 secuestro: el GPS lo acompaña (> 300 m) | 715.5 m | ✅ |
| `demo` | A3 secuestro: LinkStatus cambia de controlador solo durante el secuestro | 9 eventos, T+335–375 s | ✅ |
| `demo` | A3: recupera la ruta (< 15 m) antes de la siguiente | T+436 s (56 s tras el fin) | ✅ |
| `demo` | anomalías en orden viento → spoofing → secuestro, sin solaparse | wind → gps_spoofing → hijack; huecos 18 s, 113 s | ✅ |
| `demo` | GPS–radar (media móvil de 3) fuera de las ventanas < 20 m | 10.9 m | ✅ |
| `demo` | la misión se completa | returned_to_base a T+556 s | ✅ |
| `fallos` | desviación de la verdad respecto al plan < 15 m | 11.2 m | ✅ |
| `fallos` | desviación del GPS respecto al plan < 15 m | 10.9 m | ✅ |
| `fallos` | F1 fallo: sin TrackUpdated en [120, 180) y con FaultInjected/Cleared | 0 eventos dentro; marcas en [120.0, 180.0] | ✅ |
| `fallos` | F2 fallo: sin PositionUpdated en [300, 312) y con FaultInjected/Cleared | 0 eventos dentro; marcas en [300.0, 312.0] | ✅ |
| `fallos` | trayectoria idéntica a nominal (truth.json) | idéntica | ✅ |
| `fallos` | resto de eventos de fuentes idéntico a nominal (solo faltan los silenciados) | 42 silenciados | ✅ |
| `fallos` | GPS–radar (media móvil de 3) fuera de las ventanas < 20 m | 16.8 m | ✅ |
| `fallos` | la misión se completa | returned_to_base a T+441 s | ✅ |
| `nominal` | desviación de la verdad respecto al plan < 15 m | 11.2 m | ✅ |
| `nominal` | desviación del GPS respecto al plan < 15 m | 10.9 m | ✅ |
| `nominal` | GPS–radar (media móvil de 3) fuera de las ventanas < 20 m | 16.8 m | ✅ |
| `nominal` | la misión se completa | returned_to_base a T+441 s | ✅ |
| `secuestro` | A1 secuestro: la verdad se aleja cientos de metros (> 300 m) | 713.1 m | ✅ |
| `secuestro` | A1 secuestro: el GPS lo acompaña (> 300 m) | 711.3 m | ✅ |
| `secuestro` | A1 secuestro: LinkStatus cambia de controlador solo durante el secuestro | 9 eventos, T+335–375 s | ✅ |
| `secuestro` | A1: recupera la ruta (< 15 m) antes de la siguiente | T+436 s (56 s tras el fin) | ✅ |
| `secuestro` | GPS–radar (media móvil de 3) fuera de las ventanas < 20 m | 11.9 m | ✅ |
| `secuestro` | la misión se completa | returned_to_base a T+552 s | ✅ |
| `spoofing` | A1 spoofing: GPS a < 15 m del plan durante el engaño | 9.0 m | ✅ |
| `spoofing` | A1 spoofing: la verdad se aleja 70–90 m al final del engaño | 73.3 m | ✅ |
| `spoofing` | A1 spoofing: el radar ve lo mismo que la verdad (media 10 s, ±8 m) | radar 65.8 m, verdad 67.4 m | ✅ |
| `spoofing` | A1 spoofing: el GPS salta al terminar el engaño (> 40 m) | 84.3 m | ✅ |
| `spoofing` | A1: recupera la ruta (< 15 m) antes de la siguiente | T+236 s (14 s tras el fin) | ✅ |
| `spoofing` | GPS–radar (media móvil de 3) fuera de las ventanas < 20 m | 18.0 m | ✅ |
| `spoofing` | la misión se completa | returned_to_base a T+447 s | ✅ |
| `viento` | A1 viento: desviación máx. de la verdad (episodio + 30 s), 40–120 m | 51.8 m | ✅ |
| `viento` | A1 viento: GPS y radar coinciden en el episodio (< 20 m) | 9.2 m | ✅ |
| `viento` | A1: recupera la ruta (< 15 m) antes de la siguiente | T+151 s (1 s tras el fin) | ✅ |
| `viento` | GPS–radar (media móvil de 3) fuera de las ventanas < 20 m | 16.9 m | ✅ |
| `viento` | la misión se completa | returned_to_base a T+463 s | ✅ |

### 4.2 Contra la referencia (física sin sensores ni ruido, 0,1 s)
| Escenario | Referencia (la de `ref/`) | Generador (`fly` a 0,1 s) |
|---|---|---|
| nominal | verdad = GPS = 12,8 m; fin 441,1 s | 12,8 m; 441,1 s |
| viento | 51,8 m; fin 463,2 s | 51,8 m; 463,2 s |
| spoofing | verdad 74,1 m; GPS < 10 m durante el engaño (5,1 m); fin 446,8 s | 74,1 m; GPS < 10 m; fin 446,6 s |
| secuestro | 713,2 m; fin 552,0 s | 713,2 m; 552,0 s |
| demo | 717,3 m; fin 556,3 s | 717,2 m; 556,3 s |

La única diferencia (0,2 s en el spoofing, 0,1 m en la demo) es que la referencia acumula `t += 0.1` en float y el generador usa un contador entero: el instante exacto en que acaba el engaño cae un paso antes o después.

### 4.3 Ajustes de los YAML
Solo `radar.sigma_m` (8,0 → 5,0; ver 3.1). Ningún criterio exigió tocar la física ni otros parámetros.

## 5. Gráficas (revísalas)
Tres por escenario, en `runs/<escenario>/` (se pisan al regenerar). **18 PNG**:

| Escenario | `plan_xy.png` (solo lo planificado) | `scenario_xy.png` | `scenario_time.png` |
|---|---|---|---|
| `nominal` | `/home/coliva/poc-ai-monitor/runs/nominal/plan_xy.png` | `/home/coliva/poc-ai-monitor/runs/nominal/scenario_xy.png` | `/home/coliva/poc-ai-monitor/runs/nominal/scenario_time.png` |
| `viento` | `/home/coliva/poc-ai-monitor/runs/viento/plan_xy.png` | `/home/coliva/poc-ai-monitor/runs/viento/scenario_xy.png` | `/home/coliva/poc-ai-monitor/runs/viento/scenario_time.png` |
| `spoofing` | `/home/coliva/poc-ai-monitor/runs/spoofing/plan_xy.png` | `/home/coliva/poc-ai-monitor/runs/spoofing/scenario_xy.png` | `/home/coliva/poc-ai-monitor/runs/spoofing/scenario_time.png` |
| `secuestro` | `/home/coliva/poc-ai-monitor/runs/secuestro/plan_xy.png` | `/home/coliva/poc-ai-monitor/runs/secuestro/scenario_xy.png` | `/home/coliva/poc-ai-monitor/runs/secuestro/scenario_time.png` |
| `fallos` | `/home/coliva/poc-ai-monitor/runs/fallos/plan_xy.png` | `/home/coliva/poc-ai-monitor/runs/fallos/scenario_xy.png` | `/home/coliva/poc-ai-monitor/runs/fallos/scenario_time.png` |
| `demo` | `/home/coliva/poc-ai-monitor/runs/demo/plan_xy.png` | `/home/coliva/poc-ai-monitor/runs/demo/scenario_xy.png` | `/home/coliva/poc-ai-monitor/runs/demo/scenario_time.png` |

Qué mirar (tabla 4.4): en `viento` la verdad y el GPS se desvían juntos hacia el sur (viento del norte); en `spoofing` los puntos naranjas (GPS) siguen la ruta y el radar y la verdad se separan ~75 m hacia el suroeste y el GPS salta al terminar; en `secuestro` la verdad se va hacia el destino marcado (~710 m) y vuelve; en `fallos` faltan los rombos del radar entre T+02:00 y T+03:00 y los puntos del GPS en T+05:00–05:12; en `demo`, los tres episodios en orden y separados. Los `plan_xy.png` de los seis son iguales (misma ruta), con el título de cada uno.

## 6. Problemas
- **Radar σ = 6,0 no basta** (3.1). Salida: `A… GPS–radar (media móvil de 3) fuera de las ventanas etiquetadas < 20 m | 21.4 m | ❌` (spoofing, con σ = 6,0).
- Mi medidor dio al principio falsos ❌ que eran errores suyos, ya corregidos: la ventana de spoofing incluía el instante del salto (`GPS a < 15 m … 78.3 m`), la recuperación de cada anomalía se medía hasta el fin del vuelo en lugar de hasta la siguiente anomalía, y la comparación del radar exigía 70–90 m sobre una media de 10 s.
- `ruff check --fix` quitó imports que aún no usaba en un fichero a medio escribir y falló después con `NameError: name 'RunData' is not defined` (`plot_scenario.py`). Resuelto restituyéndolos.
- Primer intento de pruebas con `from tests.conftest import …`: `ModuleNotFoundError: No module named 'tests'`; resuelto con `tests/helpers.py` (mismo patrón que `contracts/python/tests/`).
- **Node no está instalado** (sigue igual desde la Fase 0): el validador de paleta de la skill es de JavaScript; usé su versión en Python (`validate_palette.py`), que da el mismo informe.
- Nada se atascó más de 30 minutos.

## 7. URLs consultadas (regla 8)
- matplotlib 3.11.2 (la versión instalada, `uv pip list`; coincide con la de la documentación): `Axes.quiver` — firma `quiver([X, Y], U, V, [C], /, **kwargs)`, `angles='xy', scale_units='xy', scale=1` para vectores en coordenadas de datos, `pivot`, `width`, `headwidth`, color por `C` con `cmap`/`norm`/`clim` como kwargs: https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.quiver.html
- PyYAML: `safe_load` «recognizes only standard YAML tags and cannot construct an arbitrary Python object»: https://pyyaml.org/wiki/PyYAMLDocumentation (6.0.3 instalado)
- symlog (`linthresh`: rango lineal alrededor de 0; `linscale`: espacio visual de ese rango respecto a una década): https://matplotlib.org/stable/gallery/scales/symlog_demo.html
- `Figure.colorbar`, `pyplot.switch_backend`: https://matplotlib.org/stable/api/figure_api.html#matplotlib.figure.Figure.colorbar · https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.switch_backend.html
- uv, `uv add` y grupos de dependencias (consultada en la Fase 0): https://docs.astral.sh/uv/concepts/projects/dependencies/
- Paleta y validador de la skill de visualización (local, no es una URL): los cálculos de ΔE en espacio OKLab y CVD vienen de su script.

⚠️ **Sin confirmar en la documentación** (verificado solo ejecutándolo): (1) que `Figure.colorbar` acepte el objeto `Quiver` — la página dice que el argumento es un `ColorizingArtist` «(i.e., AxesImage, ContourSet, etc.)» sin nombrar `Quiver`; funciona con 3.11.2 (las 18 figuras llevan barra de color); (2) que `Agg` sea no interactivo y adecuado para PNG — la página de `switch_backend` no habla de `Agg`; (3) los valores por defecto de `linthresh`/`linscale`: los fijo explícitamente (100 y 1,0). Las versiones de las dependencias salen de `uv`; no se afirma nada sobre licencias.

## 8. Qué queda
- **Fase 2:** el reproductor continúa la numeración `sim-`; `get_flight_summary.waypoints_planned` sin `BASE`; el detector y `get_track_metrics` pueden importar la geometría ya escrita en `platform_app/geometry.py` (el módulo de IA, no: solo recibe datos por WebSocket/HTTP, así que tendrá su propia copia mínima). El detector debe leer la ruta de `MissionPlanned` (con la vuelta).
- Decidir si `ROUTE_DEVIATION` tras el fin del spoofing cuenta como acierto o falsa alarma (3.2, punto 3).
- Node y pnpm antes de la Fase 4.
- Opcional (no hecho): animación con `FuncAnimation` (§4.5).

## 9. Revisión de contratos y copias

### 9.1 `revisor-contratos` (solo lectura)
Conforme: eventos del generador frente a §2–§4 y §8 (topics, `source`, `asset`, prefijos y anchuras de id, payloads, orden), regla 3 (`ai-module-py` no importa `platform_app`) y regla 4 (solo `scenario_metrics.py` lee `truth.json` y `labels.json`; solo `plot_scenario.py` y las pruebas lo importan). Tres puntos señalados, **corregidos**:
1. §8.1 decía «todos los campos obligatorios» y `return_to_base` solo `true`, pero el modelo tenía valores por defecto: ahora `return_to_base: Literal[True]` y `wind.episodes` son obligatorios (el error ya sale al validar el YAML, no en el controlador).
2. El recorte de un fallo al fin de la misión no estaba en el contrato y solo se aplicaba a los fallos: ahora está en §8.5 y se aplica también a las etiquetas de viento, spoofing y secuestro; un fallo que empezaría después del fin no se escribe (2 pruebas nuevas).
3. `radar.id` y `meteo.id` van al payload mientras `source` del sobre está fijo: se fijan en el modelo a `radar-1` y `meteo-1` (1 prueba nueva).
Aviso para la Fase 2 (suyo): `scenario_metrics.load_run` es la vía más fácil para colar la verdad en las tools; las tools no deben importarlo ni leer esos ficheros.

### 9.2 `runs/<escenario>/` pasa a versionarse (petición posterior a la revisión)
- `.gitignore`: se quitó `runs/*` y `!runs/.gitkeep`; ahora solo se ignora `runs/*/*/` (las carpetas de ejecución `runs/<escenario>/<run_id>/` de las fases siguientes). Comprobado con `git status --ignored`: aparecen los **6 escenarios con 7 ficheros cada uno (42)** —`plan.json`, `truth.json`, `events.jsonl`, `labels.json`, `plan_xy.png`, `scenario_xy.png`, `scenario_time.png`— y nada más de `runs/` (5,6 MB en total); `git check-ignore` confirma que `runs/nominal/20261020-120000/timeline.jsonl` y `runs/demo/20261020-120000/llm_trace.jsonl` quedan ignorados y que `plan.json` y `plan_xy.png` no. `runs/.gitkeep` sigue versionado (inofensivo).
- `CLAUDE.md`: descripción de `runs/` en «Estructura», paréntesis de la regla 13 (ya no excluye `runs/`, solo las carpetas de ejecución) y frase nueva en la regla 9: si cambias el generador o un YAML, regenera `runs/` y di en `faseN.md` qué ficheros cambian.
- Regenerar es estable: tras `generator --all` y `plot_scenario --all` los 42 ficheros salen **byte a byte idénticos** (md5 antes y después), PNG incluidos. En esta fase todos son nuevos; cuando una fase posterior cambie el generador o un YAML, aquí se listará qué ficheros cambian.

### 9.3 Copias
- Regla 13: `docs/fases/` y los 18 PNG de `runs/*/` en `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/` (`docs/fases/…` y `runs/<escenario>/*.png`) y la instantánea del código en `results/snapshots/fase1/`, ahora con `runs/<escenario>/` dentro. No hay `eval.md` ni `informe.md` todavía (Fase 3).
- Regla 15: `results/snapshots-limpias/fase1/`, rehecha desde cero (ahora incluye `runs/<escenario>/`: los JSON, el JSONL y los PNG pasan las mismas comprobaciones). Resultado de las dos comprobaciones en el mensaje de cierre de la fase; antes de copiar quité de un comentario de `plot_scenario.py` una referencia a un fichero de `docs/` (regla 16).

## 10. Mensaje de commit propuesto
```
feat: phase 1 - generator, controller, plots and contracts v0.4

- platform/generator: drone controller (same physics as the reference check), wind, hijack
  and GPS spoofing, source noise, scheduled faults, runs/<scenario>/ output (plan, truth,
  events, labels); deterministic with the scenario seed
- platform/plot_scenario.py: plan_xy, scenario_xy and scenario_time figures; scenario_metrics.py
  measures the acceptance criteria (reads truth.json, kept out of the tools)
- contracts v0.4: scenario YAML, plan/truth/labels models and schemas, eventos.md section 8,
  MissionPlanned route includes the return to base
- scenarios: radar sigma_m 8.0 -> 5.0 so the GPS-radar moving mean stays under 20 m
- tests: controller, determinism, output format and acceptance criteria for the six scenarios
- runs/<scenario>/ (generator output and figures, 42 files) is now versioned; .gitignore only
  ignores the run folders runs/*/*/. CLAUDE.md: runs/ description, rule 13 and a regeneration
  note in rule 9

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
```
