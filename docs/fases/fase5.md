# Fase 5 · interfaz y mensajes en inglés (23/10/2026)

Petición de Francesco: la interfaz y todos los mensajes en inglés para poder enseñarlo fuera. **Solo se ha traducido y se ha comprobado que no hay errores de ejecución. No se ha ejecutado nada con el LLM real** (ni `demo`, ni escenarios, ni chats): el comportamiento del modelo en inglés **no está evaluado** (ver «Pendiente de validar»). Contrato sin cambios de campos (v0.10); en `contracts/eventos.md` solo cambian los textos de los ejemplos y de los errores citados.

## 1. Qué se ha traducido
| Zona | Qué | Dónde |
|---|---|---|
| **Web** | Todos los textos: cabecera y estado, controles (escenario, Start/Pause/Resume/Step/Restart, velocidad, «Wait for the agent», «Interactive mode»), aviso de espera («Waiting for the monitor: analysing det-XXXX…»), panel de fallos, capas, telemetría, timeline y sus filtros, consola del agente (pestañas Monitor/Report, tarjetas de alerta, checks, cierres, reconocimientos), preguntas sugeridas de los chats, errores, nombres de causas, severidades y checks. Números con punto decimal (`toFixed`; no había `toLocale*`). `<html lang="en">` y título. | `web/components/`, `web/lib/format.ts`, `web/hooks/use-platform.ts`, `web/app/layout.tsx`, `web/scripts/capture.mjs` (selectores y preguntas) |
| **Lo que lee el modelo** | Los 9 prompts, las 3 skills, las descripciones de `tools.json` y `no_report_reply` de `agents.yaml`. Traducción fiel, mismos pasos, umbrales y orden; solo se añaden las peticiones expresas de escribir en inglés (`monitor_output.md`, último punto de `monitor_system.md`, «in English» en los dos chats y en el informe). `monitor_output.md` conserva lo de la 4.3 (sin la frase del castellano llano). Los títulos del informe pasan a «Summary», «What was seen», «Monitor assessment», «Recommendations». | `agent-assets/` |
| **Textos que genera el código** | Mensajes del detector; rechazos de los guardrails (los lee el modelo) y ayudas de campo; fallbacks y reconocimientos deterministas; estado del monitor para el prompt (`monitor_state.py`: «yes — ai-0008 GPS_SPOOFING (open). If this warning is the GPS recovery: …»); `chat_facts.py`; `report_facts.py` (cabecera, cronología, estados, cifras del monitor, datos para valorar, limitaciones); errores de tools y de plataforma al cliente (WebSocket y API), del reproductor, del simulador y de los modelos de `contracts/python`; descripciones de los 6 escenarios (YAML); gráficas (`plot_scenario.py`) y visor (`viewer.py`, `viewer_state.py`). Cifras con punto decimal. | `ai-module-py/src/`, `platform/src/`, `contracts/python/src/`, `scenarios/*.yaml` |
| **Métrica de contradicciones** | `evaluate.py` añade patrones en inglés (`against`/`opposite`/`contrary` a menos de 60 caracteres de `drift*`/`wind` con `wind_with_drift = sí`; `disagree by <cifra>` y «discrepancy … is <cifra>» sin `slightly` ni negación con `gps_radar_disagreed = no`) y sus excepciones (`contrary/against/to the (planned) route`; negación `no`/`not`/`never`/`n't`). **Los de castellano se conservan** para las ejecuciones antiguas. | `ai-module-py/src/ai_module/evaluate.py` |
| **Parser del informe** | `parse_narrative` acepta los títulos en inglés y, para informes antiguos, también los de castellano. | `report_facts.py` |
| **Contrato** | Ejemplos de payloads y errores citados en `contracts/eventos.md` en inglés; esquemas JSON sin cambios (regenerados: idénticos). | `contracts/eventos.md` |
| **Documentación** | Regla 14 de `CLAUDE.md`, `web/CLAUDE.md`, `ai-module-py/CLAUDE.md`, `docs/quien_decide_que.md` y las preguntas del guion (§4 de `fase4.md`) en inglés. | |

## 2. Huella de congelado de `agent-assets`
`find agent-assets -type f | sort | xargs sha256sum | sha256sum` → **`e28d071e856efb09`** (completa: `e28d071e856efb09e8b75bde8a465b93eb7cc46b94dafa2d8c42007d0537642b`). Anteriores: `cd2925fe198331cc` (4.3), `9df401059abcaff2` (4.2), `3b066bf7a0d69baa` (4.1), `40e5049dbf83198c` (4). Cambian los 14 ficheros de `agent-assets/` (todos traducidos).

## 3. Comprobaciones (sin LLM real)
| Comprobación | Resultado |
|---|---|
| `contracts/python` pytest | **128 passed, 1 skipped** (igual que la 4.3) |
| `platform` pytest | **206 passed** (igual) |
| `ai-module-py` pytest (incluye la e2e con el LLM falso) | **303 passed** (+2: patrones en inglés de la métrica y títulos del informe en inglés) |
| `ruff check` y `ruff format --check` en los tres | limpios |
| `pnpm typecheck` | correcto |
| `pnpm test` | **7 passed** (+1: `stripFieldValues` con texto en inglés) |
| `pnpm build` | correcto. **La primera ejecución falló** con `exit code 1` justo tras el aviso de Next «Your version of Next.js is affected by a known security vulnerability … Reference: https://registry.npmjs.org/-/npm/v1/security/advisories/bulk … [ELIFECYCLE] Command failed with exit code 1` (no se vio el error previo: solo la cola); la segunda, sin tocar nada, compiló y generó las páginas sin errores. No lo he investigado más. |
| Esquemas JSON (`export_schemas`) | 57 escritos, sin diferencias con git |
| `runs/<escenario>/` | `plot_scenario --all` regenerado: **solo cambian los 18 PNG** (`plan_xy`, `scenario_xy`, `scenario_time` de los 6 escenarios, con títulos, ejes y leyendas en inglés); `plan.json`, `truth.json`, `events.jsonl` y `labels.json` idénticos (el generador no se ha tocado; las descripciones de los YAML no salen en los ficheros). |

Las pruebas que comprobaban textos en castellano se han actualizado a los textos nuevos (guardrails, estado del monitor, chats, informe, plataforma, visor, modelos). La e2e usa un LLM falso que reconoce el prompt: sus expresiones regulares siguen los textos en inglés.

## 4. Búsqueda de texto en castellano que pueda ver el usuario o el modelo
- `agent-assets/`: `grep -P '[áéíóúñ¿¡«»]'` → **solo** el comentario HTML de `prompts/monitor_objective.md` (líneas 1–3) y comentarios de `agents.yaml`; `assets.py` quita los comentarios HTML antes de enviar el prompt, así que no llegan al modelo.
- `web/` (`app`, `components`, `hooks`, `lib`, `scripts`): sin cadenas en castellano; quedan **comentarios** (documentación en español, regla 14), los datos de prueba en castellano de `clean-text.test.ts` (verifican que la función sigue funcionando con prosa en castellano) y las notas de consola de `scripts/capture.mjs` (`note(...)`, para nosotros).
- Palabras como «alerta», «viento», «detección», «cerrada», «Esperando», «sí/no» en cadenas de `web/` y de `agent-assets/`: **ninguna**. «viento» y «secuestro» siguen apareciendo como **nombres de escenario** (`wind`, `hijack`: nombres de ficheros YAML y de carpetas de `runs/`, que no se cambian) y en la lista desplegable de escenarios.

**Lo que queda en castellano, y por qué:**
1. Documentación, `CLAUDE.md`, comentarios y docstrings (regla 14).
2. `eval.md`/`eval.json` (para nosotros) y los textos de `evaluate.py` que los generan; los patrones en castellano de la métrica y los títulos en castellano que acepta `parse_narrative` (compatibilidad con ejecuciones antiguas).
3. Salida de consola y ayuda de las **herramientas de desarrollo**: `platform_app/run.py` (resumen, `--help`), `scenario_metrics.py` (las comprobaciones de los escenarios), la ayuda de `generator`, `plot_scenario`, `viewer` y `export_schemas`, `llm_check.py`. No se ven en la web ni los lee el modelo; **pregunta abierta** abajo.
4. Datos de prueba en castellano dentro de `tests/` (p. ej. textos que simulan al modelo) donde la prueba no depende del idioma.
5. Comentarios del YAML de los escenarios.
6. Las trazas, `informe.md` y `timeline.jsonl` de las ejecuciones **antiguas** de `runs/<escenario>/<run_id>/` (no se versionan; no se han tocado).

## 5. Pendiente de validar (**el comportamiento del modelo en inglés NO se ha evaluado**)
No se ha llamado a vLLM en toda la fase. Qwen2.5-14B-AWQ es muy sensible al texto del prompt, y las ayudas (guardrails, hechos calculados, `checks`) se diseñaron y se afinaron con el prompt en castellano. Puede haber cambios en causas, cadenas de `supersedes`, cierres, rechazos, cifras en las narrativas y frases que contradicen los checks. **Antes de enseñarlo en directo:**
1. `demo` ×3 a 16× con «esperar al agente» y comparar con la 4.3: causas (`ai-0001` WIND T+01:46 · `GPS_SPOOFING` alta T+03:12 → media T+03:42 con `supersedes` · `HIJACK` T+05:38), una cadena por anomalía, los tres cierres (T+02:36 · T+03:54 · T+07:21), un reconocimiento (T+05:41), 3/3, 0 fallbacks, 0 alertas abiertas, 0 esperas agotadas.
2. **Métrica «frases que contradicen los checks» a 0** en las tres (con los patrones en inglés, que **no se han visto sobre textos reales del modelo**: pueden tener falsos negativos).
3. Chats (las tres preguntas del guion, ahora en inglés), informe (títulos y `parse_narrative` con la respuesta real; si el modelo no respeta los títulos, el informe sale con «Not available») y que el modelo escribe de verdad en inglés.
4. Si algo empeora, **ajustar primero la traducción del prompt afectado** (no la lógica), y anotar qué cambia con una nueva huella.
5. Otras partes sin ver con datos reales: la web en directo con textos largos en inglés (anchos de las tarjetas) y las capturas de `scripts/capture.mjs` (selectores actualizados, no ejecutados).

## 6. Decisiones mías que conviene revisar
- Causas y severidades en la web: «GPS loss/interference» y «No diagnosis» (antes «Pérdida/interferencia del GPS» y «Sin diagnóstico»).
- `eval.md` y `eval.json` siguen en castellano y con las mismas cabeceras (`NO_DIAGNOSIS = "sin diagnóstico"` es una etiqueta de `eval.md`), porque pediste que se queden como están.
- Los patrones en inglés de la métrica son un criterio mío (`against` también cuenta si no sigue «route»/«plan»/«path»; «n't» como negación).
- `contracts/eventos.md`: no he subido la versión (sigue en 0.10): solo cambian los textos de ejemplo; lo he anotado en la cabecera.

## 7. Cómo se ejecuta
Igual que en la Fase 4 (`docs/fases/fase4.md` §3). Comprobaciones: `(cd contracts/python && uv run pytest -q)` · `(cd platform && uv run pytest -q)` · `(cd ai-module-py && uv run pytest -q)` · `ruff check . && ruff format --check .` en los tres · `(cd web && pnpm typecheck && pnpm test && pnpm build)` · gráficas: `uv run --project platform python -m platform_app.plot_scenario --all`.

## 8. Qué queda
- Validar con el LLM real (apartado 5).
- Decidir si las herramientas de desarrollo (apartado 4, punto 3) también pasan a inglés.
- Pendientes de la Fase 4.3 sin cambios (texto no verificado del monitor, F2/F3 de `faults`, `pnpm exec next telemetry disable`).

## 9. Copias (reglas 13 y 15)
`docs/fases/`, los PNG de `runs/*/` (regenerados), los `eval.md` e `informe.md` existentes, `snapshots/fase5/` y `snapshots-limpias/fase5/` en `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`. Las dos comprobaciones de la regla 15 (palabras prohibidas y nombres propios) **salen vacías**; no ha hecho falta corregir nada.

## 10. Mensaje de commit propuesto
```
feat: phase 5 - interface and all messages in English

- web: every UI text, suggested chat questions, errors and number format in English
- agent-assets: prompts, skills, tool descriptions and fixed replies translated
  faithfully (same steps, thresholds and order); the model is asked to write in
  English (new freeze hash e28d071e856efb09)
- ai-module-py, platform, contracts: detector messages, guardrail rejections,
  fallbacks, monitor state, chat and report facts, API/WebSocket errors, scenario
  descriptions, plots and viewer in English; contradiction metric also matches
  English phrases (Spanish patterns kept for old runs); report parser accepts
  English titles
- docs: language rule, who-decides-what and demo script updated; plots in runs/
  regenerated (only the PNG files change)
- model behaviour in English is not yet evaluated
```

---

# Fase 5.1 · nombres y gráficas en inglés (23/10/2026)

Cierra lo que quedaba en castellano en lo visible: dos textos de las gráficas y los nombres de tres escenarios. **No se ha ejecutado nada con el LLM real.** Lo dicho en el apartado 4 sobre `viento` y `secuestro` («siguen apareciendo como nombres de escenario») ya no es cierto.

## 5.1.1 Textos de las gráficas
- `plot_scenario.py`: etiqueta de la base en `plan_xy.png` → `departure T+00:00` / `arrival T+07:15`; título de `scenario_xy.png` → `<name> · planned and real trajectory`.
- Búsqueda en `plot_scenario.py`, `viewer.py` y `viewer_state.py` (`salida`, `llegada`, `ruta`, `tramo`, `verdad`, `viento`, `trayectoria`, `planificad`, `desviaci`, `fallo`, `secuestro`, `esperar`, `alerta`, caracteres con tilde y palabras sueltas como `el/la/de/con/para/en`): **no queda ninguna cadena visible en castellano**; solo docstrings y comentarios (regla 14) y la ayuda de teclas del docstring de `viewer.py`.
- Revisados a ojo `hijack/plan_xy.png`, `faults/scenario_xy.png` y `demo/scenario_time.png`: todo en inglés.

## 5.1.2 Equivalencias de nombres
| Antes | Ahora | `mission.id` antes → ahora |
|---|---|---|
| `viento` | `wind` | `MSN-VIENTO` → `MSN-WIND` |
| `secuestro` | `hijack` | `MSN-SECUESTRO` → `MSN-HIJACK` |
| `fallos` | `faults` | `MSN-FALLOS` → `MSN-FAULTS` |
| `nominal`, `spoofing`, `demo` | sin cambios | sin cambios |

Cambia en: `scenarios/*.yaml` (`name`, `mission.id`; las descripciones ya estaban en inglés) y `scenarios/README.md`; carpetas de `runs/` (con sus ejecuciones antiguas dentro, movidas con la carpeta); código y pruebas de `platform/`, `ai-module-py/` y `contracts/python/` (nombres de escenario en cadenas, listas ordenadas de escenarios de las pruebas, ejemplos de `run.py`/`detect_file.py`); `web/scripts/capture.mjs` (la clave `hijack` y los ficheros `02_alert_wind`/`06_alert_hijack`); `CLAUDE.md`, `platform/CLAUDE.md`, `ai-module-py/CLAUDE.md`, `web/CLAUDE.md`, `docs/quien_decide_que.md`, `docs/mejoras_futuras.md`, `contracts/eventos.md` y este informe. El selector de la web lee la lista de la API (`GET /api/scenarios`), así que no hay nombres en el código de `web/` salvo `capture.mjs`. Los informes `fase0`–`fase4` (y `fase3_*`) y `01_definicion.md` no se han tocado.

## 5.1.3 `runs/` regenerado
`generator --all` y `plot_scenario --all`. Comparado con la versión de git (`HEAD`), sustituyendo antes en la antigua los nombres viejos por los nuevos:
- `truth.json`: **idéntico en los 6**.
- `events.jsonl` y `labels.json`: **idénticos en los 6** tras la sustitución (solo cambian el nombre del escenario y el id de la misión).
- `plan.json`: idéntico en `nominal`, `spoofing` y `demo`; en `wind`, `hijack` y `faults` **cambia únicamente `mission_id`** (el id de la misión va dentro del plan; no lo dije al pedirlo, pero es el mismo cambio del id). Tras la sustitución, idéntico.
- PNG: regenerados los 18 (cambian los dos textos y los nombres en títulos).
- Las ejecuciones antiguas de `runs/<escenario>/<run_id>/` están ahora bajo el nombre nuevo. Sus `run_meta.json`/`timeline.jsonl` siguen diciendo `viento`/`secuestro`/`fallos` por dentro (histórico, no tocado, ignorado por git).

## 5.1.4 Comprobaciones (sin LLM real)
| Comprobación | Resultado |
|---|---|
| `contracts/python` pytest | 128 passed, 1 skipped |
| `platform` pytest | 206 passed |
| `ai-module-py` pytest | 303 passed (la primera pasada falló una prueba, `test_report_chat`, porque comprobaba `**Scenario:** viento`; corregida) |
| `ruff check` y `ruff format --check` en los tres | limpios |
| `pnpm typecheck` · `pnpm test` | correcto · 7 passed |
| `pnpm build` | **la primera ejecución volvió a fallar** con `exit code 1` justo después del aviso de Next sobre la vulnerabilidad conocida (`Reference: https://registry.npmjs.org/-/npm/v1/security/advisories/bulk … [ELIFECYCLE] Command failed with exit code 1`); la segunda, sin tocar nada, compiló bien. Mismo síntoma que en la Fase 5; sigue sin investigarse (parece una consulta de red al registro). |

## 5.1.5 Lo que queda con `viento`, `secuestro` o `fallos` (fuera de `docs/`)
Búsqueda en todo el repo. **No queda ningún nombre de escenario ni `MSN-*` antiguo.** Lo que sigue apareciendo es castellano corriente, no un nombre de escenario:
- Docstrings y comentarios en castellano (regla 14): `simulator.py`, `controller.py`, `disturbances.py`, `player.py`, `viewer.py`, `viewer_state.py`, `plot_scenario.py`, `metrics.py`, `bus_client.py`, `recovery.py`, `evaluate.py`, `contracts/python/.../tools.py` y `payloads.py`, descripciones de los modelos y de `contracts/schemas/payloads/InteractiveModeChanged.json` (docstring exportado), comentarios del YAML (`faults: []  # fallos programados…`).
- Los `CLAUDE.md` y `contracts/eventos.md`: prosa en castellano («viento», «secuestro», «fallos» como palabras).
- `scenario_metrics.py` y `run.py`: la salida de consola de las herramientas de desarrollo sigue en castellano (`… viento: desviación máx. …`, `… secuestro: …`; pendiente abierto del apartado 8 de la Fase 5). La prueba `test_acceptance.py` busca esos prefijos.
- `evaluate.py`: patrones en castellano de la métrica (compatibilidad con ejecuciones antiguas).
- Datos de prueba en castellano en `tests/` (textos que simulan al modelo, p. ej. `test_evaluate.py`, `test_round9.py`, `test_chat_facts.py`) y `web/lib/clean-text.test.ts`.
- `scenarios/README.md`: prosa en castellano (el documento no es visible para el usuario final).
- `web/scripts/capture.mjs`: comentarios y notas de consola.

## 5.1.6 Copias (reglas 13 y 15)
Copiados a `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`: `docs/fases/`, PNG de `runs/*/` (con los nombres nuevos), `eval.md` e `informe.md` existentes, `snapshots/fase5_1/` y `snapshots-limpias/fase5_1/`. Las dos comprobaciones de la regla 15 **salen vacías**; no ha hecho falta corregir nada. `git ls-files` aún lista los ficheros antiguos (`scenarios/viento.yaml`, `secuestro.yaml`, `fallos.yaml`, que git ve como borrados hasta tu commit), y `cp` avisó de que no existen; es inofensivo: las copias contienen los nuevos.

**Para borrar a mano (yo no puedo):** en `results/runs/` siguen las carpetas con nombre en castellano de copias anteriores: `viento/`, `secuestro/` y `fallos/`. Las nuevas son `wind/`, `hijack/` y `faults/`.

## 5.1.7 Mensaje de commit propuesto
```
feat: phase 5.1 - scenario names and plot labels in English

- plot_scenario: base label (departure/arrival) and scenario_xy title in English
- rename scenarios: viento -> wind, secuestro -> hijack, fallos -> faults
  (mission ids MSN-WIND, MSN-HIJACK, MSN-FAULTS) across scenarios, runs/, code,
  tests, web capture script and current docs
- runs/ regenerated: truth.json identical; events.jsonl, labels.json and plan.json
  differ only in the scenario name and mission id
```
