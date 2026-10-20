# Fase 0 · preparación

Fecha: 20/10/2026. Estado: **terminada, pendiente de tu revisión** (la Fase 1 no se ha empezado).

## 1. Entorno (salida literal)
```
$ uname -a && pwd && git status
Linux 11LAP5CG60715WR 6.18.54.1-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Tue Oct  6 19:13:07 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
/home/coliva/poc-ai-monitor
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

| Herramienta | Resultado |
|---|---|
| `python3` | 3.12.3 |
| `uv` | 0.13.0 |
| `git` | 2.43.0 |
| `ruff` | 0.17.0 (herramienta global de uv, `~/.local/bin/ruff`) |
| `node` | ❌ **no instalado** |
| `pnpm` | ❌ **no instalado** |
| vLLM | ✅ responde en `http://127.0.0.1:8000/v1/models`: `Qwen/Qwen2.5-14B-Instruct-AWQ`, `max_model_len: 32768`. No lo he tocado |

Dependencias resueltas por `uv sync`: pydantic 2.14.1 (pydantic-core 2.50.1), pytest 9.1.1.

## 2. Qué se hizo

### 2.1 Contrato `contracts/eventos.md` → versión 0.3
Los cambios que pediste (1–5) más uno que he encontrado yo (6). **Revisa el 6 y los de la sección 2.3.**

1. **`get_flight_summary`** (§7): campos y ejemplo JSON definidos (`mission_id`, `duration_s`, `mission_completed`, `completion_reason`, `distance_m`, `waypoints_planned`, `waypoints_reached`, `detections_by_rule`, `alerts_by_cause`, `alerts_open`, `alerts_closed`); siempre todas las claves; nunca información del dominio `sim`.
2. **`source` y `asset` del sobre** (§2) y correspondencia con el parámetro `source` de `get_events` (§7).
3. **`fix`** de `PositionUpdated`: `none` | `2d` | `3d`; `sats` entero, `hdop` decimal (§4).
4. **`GET /api/scenarios`** (§6): `{"scenarios": [{name, description, generated, duration_s}]}`; `load` de un escenario no generado lo genera antes (§5 y §6).
5. **`get_track_metrics` sin datos de una fuente** (§7): `gps_available`, `radar_available`, `last_seen_sim_time`; nulls según fuente; `trend` null con < 3 muestras; `samples` reales; ventana parcial. Ejemplo actualizado.
6. **⚠️ Corrección que no me pediste.** §3 recomendaba suscribirse con `citadel.pub.evt.ai.d1.*`, pero los topics tienen **siete** segmentos (el último es `v1`) y `*` es un solo segmento, así que **ese patrón no casa con ningún topic**. Lo detectó la prueba de comodines. Ahora dice `citadel.pub.evt.ai.d1.>` (o `citadel.pub.evt.ai.d1.*.v1`) y avisa del error. Ningún componente existente lo usaba.

También: `agent-assets/skills/source-discrepancy/SKILL.md` lleva la línea sobre `radar_available: false` (Paso 1).

### 2.2 Estructura y proyectos uv
```
contracts/python/        poc-contracts   (pydantic) · src/poc_contracts/ · tests/
contracts/schemas/       48 JSON Schema exportados (generados, se versionan)
platform/                poc-platform    · src/platform_app/ · tests/   (depende de poc-contracts por ruta, editable)
ai-module-py/            poc-ai-module   · src/ai_module/    · tests/   (idem)
runs/.gitkeep            (runs/* ignorado salvo el .gitkeep)
docs/fases/  tools/hook_py.sh  ruff.toml  .claude/settings.json
```
- `uv init --lib` crea los paquetes como `poc_platform` y `poc_ai_module`; los renombré a `platform_app` y `ai_module` (nombres de los `CLAUDE.md`; `platform` choca con la biblioteca estándar) y fijé `[tool.uv.build-backend] module-name`.
- Dependencia local: `[tool.uv.sources] poc-contracts = { path = "../contracts/python", editable = true }`.
- `platform` y `ai-module-py` solo tienen una prueba de humo (importan el paquete y `poc_contracts`). FastAPI, `openai`, etc. se añaden en su fase.
- Quité `authors` del `pyproject.toml` que genera `uv init` (traía un correo sacado de la configuración de git).

### 2.3 Paquete `poc_contracts` (`contracts/python/src/poc_contracts/`)
| Módulo | Contenido |
|---|---|
| `enums.py` | Todos los enumerados cerrados (`EventType`, `Cause`, `Rule`, `Severity`, `SensorSource`, `ToolSource`, `GpsFix`…) |
| `topics.py` | Tabla tipo → dominio/routing/prefijo de id/`source`/efímero; `topic_for`, `asset_for`, `source_for`, `topic_matches` (comodines `*` y `>`), `validate_pattern`, dominios que puede publicar cada cliente, mapa de `get_events.source` → `source` del sobre |
| `payloads.py` | Un modelo por payload de §4 y `PAYLOAD_MODELS`. `extra="forbid"` en todos |
| `envelope.py` | `EventDraft` (sin `seq`/`ingestion_time`: lo que escribe el generador y lo que se publica) y `Envelope` (con ellos). Valida que payload, topic, `source`, `asset`, prefijo de id y `ephemeral` cuadran con `type` |
| `ws.py` | Mensajes del WebSocket: unión discriminada por `op` y, dentro de `control`, por `action` |
| `api.py` | `ScenariosResponse`, `ToolOk`, `ToolError` |
| `tools.py` | Argumentos y resultados de las tools, y `TOOL_MODELS` |
| `export_schemas.py` | `contracts/schemas/**/*.json`, determinista; borra los que sobran |

Decisiones de implementación que **no estaban en el documento** (dímelo si alguna no te gusta):
- `GET /api/state` devuelve lo mismo que el mensaje `state`, **incluido `op: "state"`** (lectura literal de «como el mensaje `state`»).
- `wait_agent.value` y `fault.value.muted` son booleanos JSON **estrictos** (`"yes"` se rechaza; lo vio una prueba).
- `speed` solo admite 0.5/1/2/4/8/16.
- `get_events.last_n` se **recorta** a 1–50 en vez de dar error (más amable con un 14B); el resto de argumentos no válidos sí son error.
- `summary` ≤ 160 caracteres en `AnomalyDetected` y en `publish_alert` (lo dice `tools.json`); `evidence_event_ids` y `detection_ids` de `publish_alert` con al menos 1 elemento.
- `get_events.type` es un `EventType` (un tipo inventado da error en vez de devolver una lista vacía que despistaría al modelo).
- `event_time` e `ingestion_time` son cadenas ISO 8601 UTC con `Z` (patrón), no `datetime`, para que la serialización sea idéntica en todos los componentes.
- Los resultados de `close_alert` y `load_skill` **no están definidos en el contrato** (son locales del módulo de IA y no cruzan componentes), así que no tienen modelo. `publish_alert` sí (ok / errors).

### 2.4 Pruebas (`contracts/python/tests/`)
- `test_doc_examples.py`: extrae del documento **los 35 ejemplos JSON** (bloques ```` ```json ```` y spans en línea) y los valida; comprueba que el número coincide y que cada uno sigue empezando como espera (si cambias el documento sin actualizar la lista, falla). 34 validan; **1 se omite a propósito** (`{"ok": true, "result": …}` de §6: el `…` no es JSON y `result` depende de la tool). El sobre de §2 trae `"payload": { }`, así que se valida con el payload de `PositionUpdated` de §4.
  - El plan permitía recortar a los bloques ```` ```json ```` si los ejemplos en línea se complicaban (tope 30 min): **no hizo falta**, se validan todos.
- `test_models.py`: 12 sobres inválidos, `SOURCE_SILENT` sin `source`, límites de `AnomalyDetected`, 11 mensajes de cliente válidos y 11 inválidos, mensajes de servidor, `get_track_metrics` sin radar, etc.
- `test_topics.py`: comodines (incluido el contraejemplo `Detection*` y el patrón del punto 6), dominios por cliente.
- `test_tools_json.py`: nombres, propiedades, `required` y enumerados de los modelos de argumentos coinciden con `agent-assets/tools.json`.
- `test_schemas_up_to_date.py`: `contracts/schemas/` coincide con lo que generan los modelos (comprobado a mano que falla si se altera un esquema).

### 2.5 ruff y hook de formato
- `ruff.toml` en la raíz, copiado de `~/spike1/py/ruff.toml` (100 columnas, py312, `E W F I B UP SIM C4`); cambia `src` (tres proyectos) y excluye `.venv`, `.tools`, `web` y `ref/`. **`ref/simcheck_controlador.py` queda fuera a propósito**: es la referencia que me diste y daba 8 avisos de ruff (líneas largas y `open` sin `with`); no la he tocado.
- `tools/hook_py.sh`: el de `~/spike1/py/hook_py.sh` adaptado (mismo comportamiento: ficheros cambiados desde `.tools/format.stamp`, `ruff check --fix` → `ruff format` → `ruff check`, exit 2 si queda una violación, `stop_hook_active`), recorriendo `contracts/python`, `platform` y `ai-module-py` y saltándose `.venv`.
- `.claude/settings.json` registra el hook en `PostToolUse` (`Write|Edit|Bash`) y `Stop`. No modifiqué nada de `~/spike1`.
- Probado: sobre todo el código (formateó los 19 ficheros, exit 0); sobre un `.py` temporal con `import os` sin usar, dos sentencias en una línea y una línea de 126 columnas (exit 2 y `E501 … (126 > 100)` por stderr; el fichero se borró). Además, `.tools/hook.log` muestra ejecuciones que yo no lancé a mano tras llamadas a Bash, o sea que **se dispara solo en esta sesión** sin reiniciarla (la documentación dice que los cambios en `settings.json` se recogen automáticamente, aunque ese detalle viene de un resumen, no de texto literal).
- `.gitignore`: añadidos `runs/*`, `!runs/.gitkeep` y `.tools/`.

## 3. Cómo se ejecuta
```bash
# esquemas JSON (regenera contracts/schemas/)
uv run --project contracts/python python -m poc_contracts.export_schemas
# pruebas
(cd contracts/python && uv run pytest -q)      # 108 passed, 1 skipped
(cd platform         && uv run pytest -q)      # 1 passed
(cd ai-module-py     && uv run pytest -q)      # 1 passed
# estilo
ruff check . && ruff format --check .          # All checks passed! · 40 files already formatted
```

## 4. Resultados
| Comprobación | Resultado |
|---|---|
| Ejemplos de `contracts/eventos.md` | 34 validan, 1 omitido (ilustrativo, no es JSON) |
| `contracts/python` | 108 passed, 1 skipped |
| `platform`, `ai-module-py` | 1 passed cada uno |
| Esquemas exportados | 48 ficheros en `contracts/schemas/` (sobre, 26 payloads, WebSocket, API, tools) |
| `ruff check` / `ruff format --check` | limpio |
| Hook | exit 0 en limpio, exit 2 con violación, se dispara solo |

## 5. Problemas
- **Node y pnpm no están instalados** (`bash: node: command not found`, `bash: pnpm: command not found`). No hacen falta hasta la Fase 4. Los instalas tú (ver sección 6).
- El patrón de suscripción de §3 no casaba con nada (punto 6 de 2.1). Resuelto en el documento.
- `"yes"` se aceptaba como booleano en el WebSocket por la coerción laxa de Pydantic. Resuelto con `StrictBool`.
- Un fallo mío en un helper de las pruebas (parámetro duplicado). Resuelto.
- Nada se atascó más de 30 minutos.

## 6. Instalar Node y pnpm (los instalas tú; yo no he ejecutado nada de esto)
**Versión mínima:** la página de instalación de Next.js dice literalmente «Minimum Node.js version: 20.9» (https://nextjs.org/docs/app/getting-started/installation, actualizada el 02/10/2026). ⚠️ Esa página no liga el mínimo a «Next 16» por nombre ni da la última versión estable de Next; lo tomo como el mínimo de la documentación vigente. Recomiendo la **LTS actual** (≥ 22).

**A) nvm, sin sudo (recomendada)**
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh | bash   # nvm v0.40.8, última del README
exec bash                                  # o abre otra terminal
nvm install --lts && node --version        # debe ser >= 20.9
curl -fsSL https://get.pnpm.io/install.sh | sh -    # pnpm.io/installation, sin sudo
exec bash && pnpm --version
```

**B) NodeSource, con sudo + corepack**
```bash
sudo apt install -y curl
curl -fsSL https://deb.nodesource.com/setup_lts.x -o nodesource_setup.sh
sudo -E bash nodesource_setup.sh
sudo apt install -y nodejs
node --version                              # debe ser >= 20.9
sudo corepack enable pnpm && pnpm --version
```
⚠️ **Sin confirmar:** (1) la página oficial de pnpm que leí **no menciona corepack**, y no he podido confirmar que corepack venga incluido en el Node actual; si `corepack --version` falla, usa el instalador de pnpm de la opción A (sin sudo), que sí está documentado. (2) En el README de NodeSource el comando está en `DEV_README.md` y su encabezado dice «LTS (v22.x)», que puede estar desfasado; comprueba la versión con `node --version`.

## 7. URLs consultadas (regla 8)
- uv, dependencia por ruta editable (`[tool.uv.sources] … { path = "…", editable = true }`): https://docs.astral.sh/uv/concepts/projects/dependencies/
- uv, `uv init --lib` (layout `src/`, `py.typed`, backend `uv_build`): https://docs.astral.sh/uv/concepts/projects/init/
- Pydantic v2.14.1 (versión estable al consultar), uniones discriminadas y JSON Schema: https://pydantic.dev/docs/validation/latest/get-started/ · https://pydantic.dev/docs/validation/latest/concepts/unions/ · https://pydantic.dev/docs/validation/latest/concepts/json_schema/ (`docs.pydantic.dev/latest/` redirige ahí con 301)
- ruff, configuración (`line-length`, `target-version`, `exclude`/`extend-exclude`): https://docs.astral.sh/ruff/configuration/ — ⚠️ la clave `src` **no** figura en esa página (es de https://docs.astral.sh/ruff/settings/, que no se leyó); la heredé tal cual del `ruff.toml` del spike, donde ya funcionaba, y el hook la ejercita.
- Hooks de Claude Code (formato de `settings.json`, campos de stdin, exit 2): https://code.claude.com/docs/en/hooks — `stop_hook_active` y la recarga automática de `settings.json` salen de un resumen, no de texto literal.
- Next.js: https://nextjs.org/docs/app/getting-started/installation · pnpm: https://pnpm.io/installation · nvm: https://github.com/nvm-sh/nvm · NodeSource: https://github.com/nodesource/distributions y https://github.com/nodesource/distributions/blob/master/DEV_README.md

## 8. Qué queda
- **Fase 1** (generador): al terminar, **se definen en `poc_contracts` y en `contracts/eventos.md` (v0.4) los modelos de `plan.json`, `truth.json`, `labels.json` y del YAML de escenario**, junto con el generador y antes de paralelizar la Fase 2 (decidido por ti).
- Sin definir en el contrato y sin modelo: resultados de `close_alert` y `load_skill` (locales).
- `revisor-contratos` no se ha pasado: aún no hay componentes que revisar.
- Instalar Node/pnpm antes de la Fase 4.

## 9. Mensaje de commit propuesto
```
feat: phase 0 - contracts in code (v0.3), uv projects, JSON schemas and formatting hook

- contracts/eventos.md v0.3: envelope source/asset, GpsFix, GET /scenarios,
  get_flight_summary and get_track_metrics without a source; fix the ai.d1 subscription
  example (it matched no topic)
- contracts/python: Pydantic models (envelope, payloads, websocket, api, tools),
  schema exporter and tests that validate every JSON example of the document
- contracts/schemas: exported JSON Schema (48 files)
- platform/ and ai-module-py/: uv projects (platform_app, ai_module) depending on poc-contracts
- ruff.toml and tools/hook_py.sh (from spike1) with .claude/settings.json
- source-discrepancy skill: say it when radar_available is false

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
```
