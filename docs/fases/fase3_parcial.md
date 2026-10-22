# Fase 3 · informe parcial (segunda parada)

> Histórico: lo que sigue es el informe de las dos paradas intermedias (rondas R1–R6). El cierre de la fase, con la configuración final (R7), está en `fase3.md`.

Estado: **parada por la regla «formato bien, diagnóstico mal tras 2 rondas»**. Con la decisión A aplicada (apartado 0) el formato de las tool calls queda estable (0 fallbacks en las rondas 5 y 6), pero el 14B sigue sin ejecutar el árbol de decisión de la skill: acierta `viento` y la discrepancia del spoofing, y falla la recuperación del spoofing y el secuestro (concluye `WIND` en los dos). No he activado `guided_mode`. Los apartados 1–8 son el informe de la primera parada (siguen vigentes salvo lo que corrige el apartado 0).

## 0. Después de la decisión A

### 0.1 Lo que se ha hecho (puntos 1–6 de tu mensaje)
1. **`tool_choice: required` solo para el monitor** (`agents.yaml`; informe y chats siguen en `auto`). Regla 6 de `CLAUDE.md` y `docs/01_definicion.md` §7.5 actualizados, con la nota para el módulo Java. `llm_check` lo confirma contra el vLLM real: con `required` y una pregunta que no pide nada, devuelve `tool_calls=1`, `content=''`, `finish_reason='tool_calls'`.
2. **Última iteración:** el motor ofrece solo `final_tools` (`publish_alert`, `acknowledge_detection`, `close_alert`), sin forzar ninguna por nombre (`engine._tools_for`, `agents.yaml`, campo `restricted_tools` en la traza). Pruebas: `test_last_iteration_offers_only_the_final_tools_without_forcing_one` y `test_agents_without_final_tools_keep_offering_everything_to_the_end`.
3. **Muestreo:** `repetition_penalty` 1,05 en todos los agentes; `top_k` −1 en el monitor y 20 en informe y chats, todo explícito en `agents.yaml` con nota. Pruebas del muestreo actualizadas (incluida la e2e, que mira cada petición que llega al servidor falso).
4. **Historial:** un intento fallido que es solo texto y al que sigue un recordatorio no se guarda en los `messages`; lo sustituye el recordatorio; en la traza (`calls`) queda. Prueba: `test_a_failed_text_attempt_is_not_kept_but_the_next_tool_call_is`. ⚠️ **Matiz:** hoy solo el monitor tiene recordatorio; en el informe y en los chats un texto sin tool calls **es** la respuesta final, así que la mecánica no actúa allí. No he inventado un recordatorio para ellos (habría que decidir cuándo un texto cuenta como «intento fallido» sin mirar el contenido).
5. **`get_track_metrics` con el viento de la ventana** (contrato, regla 2: `eventos.md` §7, modelo `WindStat`, esquemas, herramienta de la plataforma y sus pruebas, `tools.json`): `wind` = `{mean_speed_mps, max_gust_mps, from_deg, wind_to_deg, drift_vs_wind_deg, samples, last_event_id}` o `null` si no hay `WindReported` en la ventana. Dirección: media vectorial ponderada por la velocidad. Pruebas: viento (a favor, ≤ 45°), secuestro (viento flojo), `null` sin meteo y la diferencia de ángulos 0–180. La skill `route-deviation` usa esos campos (notable = media ≥ 5 o racha ≥ 8, y `drift_vs_wind_deg` ≤ 45 → `WIND`; si no, mira `LinkStatus` antes de concluir).
6. Criterio de recuperación «entre dos muestras consecutivas»: ya estaba.

### 0.2 Banco de reproducciones (32 puntos de decisión guardados de las rondas 3 y 4, temperatura 0)
| Configuración | Llamada real (`tool_calls`) | Qué llama |
|---|---|---|
| A · `auto`, `repetition_penalty` 1,0 (antes) | **10 / 32** | 6 `publish_alert`, 2 ack, 1 `close_alert`, 1 `get_track_metrics` |
| B · `auto`, 1,05 | 10 / 32 | 5 `publish_alert`, 3 ack, 2 `get_events` |
| C · `required`, 1,05, todas las tools | **32 / 32** | 12 `get_events`, 5 `get_track_metrics`, 2 `load_skill` (no cierra), 7 `publish_alert`, 4 ack, 2 `close_alert` |
| D · `required`, 1,05, solo las 3 tools finales (última iteración) | **32 / 32** | 20 `publish_alert`, 8 ack, 4 `close_alert` |
El formato queda estable con `required`. (`repetition_penalty` 1,05 no cambia el formato con `auto`: el bucle de repetición era otra cosa.)

### 0.3 Rondas con `required` (viento / spoofing / secuestro)
| Ronda | Cambios | viento | spoofing | secuestro |
|---|---|---|---|---|
| 5 | A + punto 3 + punto 5 (campo `wind`) | ✅ `WIND` low 0,8 | ⚠️ SD → `GPS_SPOOFING` ✅; RD de recuperación → `WIND` ❌ | ❌ `WIND` |
| 6 | skill `route-deviation` reordenada (métricas primero, recuperación observable, umbrales con ejemplos numéricos, «no concluyas WIND si…»), `monitor_system.md` «paso a paso y sin saltarte ninguno» | ✅ `WIND` | ⚠️ igual | ❌ `WIND` |
0 fallbacks, 0 recordatorios en las dos rondas. Invocaciones del monitor: media 7,3 s, p95 11,4 s (antes 19,5 y 37,5), prompt máximo 6.571 tokens.

### 0.4 Qué muestran las trazas (en `results/trazas/`: `*_R5_*`, `*_R6_*`)
- **Secuestro (R6, inv-0001):** carga la skill, pide `get_track_metrics` y recibe `wind: {mean_speed_mps 1.9, max_gust_mps 4.1, drift_vs_wind_deg 62.1}` y `gps_radar_distance_m.max 12.4`. Pide los `WindReported` y **publica `WIND`** (0,7) con la explicación «viento constante… 1,9 m/s… La deriva del dron (62,1°) va contra el viento»: cita los números que descartan el viento y concluye lo contrario. No llega a mirar el enlace (`LinkStatus`), que es lo que delata `HIJACK`.
- **Spoofing, RD de recuperación (R6, inv-0002):** `gps_radar_distance_m` media 55,6 y máxima 79,1 (discrepaban hasta ahora), alerta `GPS_SPOOFING` abierta en el estado (las dos condiciones del paso 2), `wind.mean_speed_mps` 1,7 y `drift_vs_wind_deg` 101,6. Publica `WIND`: «hay **viento notable** (media 1,7 m/s, racha 4,2 m/s)… empuja contra la deriva (101,6°)». Llama «notable» a 1,7 m/s y no ejecuta el paso 2.
- Patrón común: ejecuta los dos o tres primeros pasos (cargar skill, métricas, meteo) y salta a `publish_alert` con `WIND`, ignorando las comparaciones numéricas que la skill le pide y que el resultado ya trae resueltas. Es un fallo de ejecución del árbol de decisión, no de formato ni de datos.

### 0.5 Decisiones que necesito (no las he tomado)
- **(E) Veredictos ya calculados en los resultados de las tools** (más contrato): p. ej. en `wind` un booleano `notable` (media ≥ 5 o racha ≥ 8) y, en el resultado, `gps_radar_disagreed` (máx. ≥ 25 m) y el salto máximo del GPS entre muestras consecutivas (`gps_max_step_m`: el criterio de `recovery.py`, que el modelo no puede calcular con `x, y`). Quita al modelo las comparaciones, que es donde falla, y deja la elección de causa a la skill. Es lo que más probabilidad tiene de funcionar.
- **(F) Partir `route-deviation` en skills de una sola decisión** (`gps-recovery`, `wind-check`, `hijack-check`) que la skill principal encadena una a una con una pregunta de sí/no cada vez; más tools de ida y vuelta (≈ +3 llamadas, +6 s).
- **(G) Aceptar el fallo documentado** para `secuestro` y la recuperación del spoofing y cerrar la fase (criterio de la fase: «o el fallo documentado»).
Recomiendo E; si no, F.

### 0.6 Cambios en la skill respecto al criterio de recuperación aprobado
La condición 2 de `recovery.py` (salto de < 15 m a > 30 m entre dos muestras consecutivas) no la puede calcular el modelo (`get_events` da `x, y`, no desviaciones). En la skill uso, de momento, un **proxy observable** con los datos de `get_track_metrics`: GPS y radar discrepaban en la ventana (`gps_radar_distance_m.max` ≥ 25 m) y hay una alerta del GPS abierta o de ≤ 60 s. `recovery.py` y su prueba no cambian (siguen siendo el criterio de referencia). Avísame si prefieres que la skill use el salto real (necesita `gps_max_step_m`, opción E).

### 0.7 Documentación de vLLM sobre `required` (regla 8)
- https://docs.vllm.ai/en/latest/features/tool_calling/ : «`vLLM supports the tool_choice='required' option`» (`vllm>=0.8.3`); «it also uses structured outputs, so this is enabled by default and will work with any supported model»; «the model is guaranteed to generate one or more tool calls based on the specified tool list»; «the output format strictly follows the schema defined in the `tools` parameter». Con `auto` la llamada se extrae del texto («vLLM extracts tool calls from raw text, so arguments may occasionally be malformed»).
- https://docs.vllm.ai/en/latest/features/structured_outputs/ : backends `xgrammar` o `guidance` (por defecto `auto`); la relación con `required` está en la página de tool calling, no en esta. Aviso de latencia de compilación del autómata en la primera petición con tools nuevas (se nota solo la primera vez).
- ⚠️ **No confirmado en la documentación:** que el `content` quede vacío y qué `finish_reason` devuelve con `required`; verificado ejecutando `llm_check` (`content=''`, `finish_reason='tool_calls'`). Tampoco aparece el rendimiento ni el soporte en streaming (el monitor no usa streaming).

## 1. Qué está hecho (y probado sin LLM)
- **Contrato v0.6** (`contracts/eventos.md` §3, §4 y §7; modelos, esquemas regenerados —56—, ejemplo validado): evento `DetectionAcknowledged`, tool `acknowledge_detection` (el monitor tiene 8 tools), tabla de respuestas y fallbacks, `alerts_count` = cadenas. `agent-assets/tools.json` con la tool nueva (insertada, el resto del fichero intacto).
- **Plataforma:** volcado incremental del timeline (lo que llega después de `SimulationFinished` se añade a `timeline.jsonl`), prueba de que el reproductor se reanuda con `DetectionAcknowledged` (y espera por el `event_id` de cada aviso, no por el `detection_id`), `get_my_alerts`/`get_flight_summary` lo ignoran (prueba). `run.py`: `--wait-agent`, `--evaluate`, `--ask conversación:cuándo:texto` (con streaming), `--detector-only`, `--llm-url`; espera a `ReportGenerated` y escribe `run_meta.json`.
- **Módulo de IA** (`ai-module-py`, `openai` 3.35.1 añadido con `uv add`): `agent/` (assets, cliente LLM, motor, tools, guardrails, trazas), `monitor.py` + `monitor_state.py` (un trabajador, lotes, garantía de respuesta, cierre determinista y de fallback, `AgentActivity`), `report.py` (informe mínimo marcado si falla), `chat.py` (una tarea por conversación, historial de 12, sistema rehecho en cada pregunta, texto fijo antes del informe), `recovery.py`, `evaluate.py` (`eval.md` + `eval.json`), `llm_check.py` (comprobación previa y latencias), `module.py`/`__main__.py`.
- **Pruebas:** contratos 127 passed (1 skipped); plataforma 200 passed; módulo de IA 212 passed, incluida la e2e (`run.py --scenario demo --wait-agent --speed 16 --ask … --evaluate` con un servidor LLM falso de la biblioteca estándar: 0 esperas agotadas, 0 detecciones sin respuesta, informe y chats con streaming, timeline que sigue creciendo tras `SimulationFinished`). Los seis `events.jsonl` pasan por el detector y el monitor con LLM falsos que publican bien, solo contestan texto, devuelven basura, lanzan excepciones o se pasan de tiempo: **cada Raised/Updated/Cleared recibe respuesta con su `causation_id` dentro del tope**. `ruff check` y `ruff format --check` limpios.
- **Comprobación previa** (`python -m ai_module.llm_check`, vLLM real): ✅ tool calls con y sin streaming (deltas por `index`; en streaming los argumentos llegan completos y `usage` con `include_usage`), ✅ `timeout` por petición (`APITimeoutError`), ✅ `extra_body` con `top_k` −1 y 0 y `repetition_penalty`, ✅ `max_tokens` y `max_completion_tokens`, ✅ temperatura 0 con `top_k −1` da la misma respuesta 3 de 3 veces.

## 2. Lo que falla: el monitor no responde bien con el LLM

Resultados por ronda (viento / spoofing / secuestro; ✅ causa correcta, ❌ no; «fb» = respuesta de fallback del módulo):

| Ronda | Cambios | viento | spoofing | secuestro |
|---|---|---|---|---|
| 0 | prompts de la Fase 2 | ❌ fb UNKNOWN | — | — |
| 1 | regla «actúa llamando a las tools»; umbral de viento «notable» (5 m/s o racha 8) en la skill; recordatorio reescrito | ❌ fb | ❌ fb | ❌ fb |
| 2 | quitada la frase que mencionaba «no escribas el JSON en tu texto»; cola «tu respuesta final es una llamada a una tool»; las skills se entregan como texto y no como JSON entrecomillado (fallo mío del motor) | ❌ fb | ❌ fb | ❌ fb |
| 3 | prompt de salida en prosa (sin lista de campos), detección en una línea sin ```` ```json ````, prefijo «Cada paso de tu trabajo es una llamada a una tool» | **✅ WIND** (conf 0,8) | ❌ fb | ❌ UNKNOWN fb y luego UNKNOWN |
| 4 | las skills dejan de usar `get_events(source="gps", last_n=5)` y pasan a «la tool `get_events` con `source` = …» | ❌ fb | ❌ fb | ❌ UNKNOWN (sin diagnóstico), 1 alerta abierta al final |

Nunca llegué a una ronda con los tres bien; el único acierto (viento, R3) no se repitió en R4 con prompts casi iguales.

### Qué muestran las trazas (`results/trazas/`, copiadas junto a este informe)
1. **Fallo de formato de la tool call (el principal).** En el paso de decisión (`publish_alert`) el modelo razona bien en prosa y luego **escribe la llamada como texto** en un bloque ```` ```json ```` con `{"name": "publish_alert", "arguments": {…}}` (a veces dos veces), o como `publish_alert(detection_ids=[…])`. `message.tool_calls` llega vacío, `finish_reason: stop`. Con el recordatorio, repite lo mismo. Pasa con el 14B + parser `hermes`: en el primer paso (`load_skill`) y en las tools de datos falla de vez en cuando (spoofing R3: ```` ```json {"name": "load_skill"…} ```` ya en la primera llamada), y casi siempre en la decisión final. `close_alert` (2 argumentos) y `get_*` funcionan casi siempre; `publish_alert` (8 argumentos largos), la mayoría de las veces no. **Cifras de R3 y R4** (6 ejecuciones, 16 invocaciones del monitor con LLM): 11 acabaron en texto (y por tanto en respuesta de fallback) y 5 en una tool call real (`done`); en esas 11 hubo 23 respuestas del modelo con la llamada escrita como texto. Con una conversación mínima (sistema de una línea) el mismo modelo llama bien a `publish_alert`, así que no es el esquema.
2. **Banco de reproducciones** (mismo contexto guardado, variantes del prompt, temperatura 0): cambios mínimos del texto voltean el resultado de contextos distintos de forma aparentemente caótica (p. ej. paso 1: 5/8, 6/8, 7/8 llamadas correctas según la variante; paso de decisión: 0/3 con casi todas, 3/3 con el prompt sin la sección «Formato de tu salida» y sin «Qué tienes», 1/3 con un sistema de una línea). No hay una redacción estable.
3. **Calidad del diagnóstico cuando sí llama bien:** en secuestro el modelo publica `WIND` (conf. 0,5) con viento de 1,7 m/s y una deriva a 186°, ignorando el umbral de la skill; en viento hace aritmética de ángulos y de «hace 10 minutos» equivocada, aunque llegue a la conclusión correcta. Rara vez sigue los pasos hasta el enlace (`LinkStatus`) que da `HIJACK`.
4. **Texto largo antes de la llamada:** 600–800 tokens de análisis en prosa (a veces `finish_reason: length`), 14 s por llamada; las invocaciones del monitor duran de 4 a 38 s (media 19,5, p95 37,5; prompt máximo 6.883 tokens).

### Qué he descartado
- `guided_mode` **no se ha activado** (como pediste). Además no atacaría el fallo principal: el modelo sí carga la skill por sí mismo (`skills_by_model` > 0 en todas las invocaciones); falla al formar la tool call.
- Cambiar de modelo (prohibido) ni tocar vLLM.

### Opciones que necesito que decidas (las dos tocan reglas del proyecto, por eso no las he aplicado)
- **(A) `tool_choice: "required"` solo para el monitor.** vLLM obliga entonces a producir una tool call válida en cada paso (comprobado fuera del bucle: siempre devuelve `tool_calls`). Contradice la regla 6 («`tool_choice: "auto"`, nada de forzar»), aunque no fuerza por nombre; el monitor no necesita texto final (siempre acaba en `publish_alert`, `acknowledge_detection` o `close_alert`). Riesgo: elige tools de datos en bucle hasta el tope de 8, y entonces entra el fallback.
- **(B) Recuperar la llamada del texto** cuando `tool_calls` viene vacío pero el contenido es un JSON `{"name", "arguments"}` válido de una tool ofrecida. Sigue sin mirar `finish_reason`, pero es un remedio del cliente al parser del servidor: el módulo Java tendría que replicarlo.
- **(C) Seguir con prompts/skills** (más rondas): cada ronda es una lotería con este modelo; no la recomiendo como única vía.
- **(D)** Aceptar el fallo documentado para `demo` (criterio de la fase: «o el fallo documentado») y cerrar la fase con lo que hay.
Mi recomendación: **A**, probada primero fuera del bucle con las tres anomalías y, si pasa, volver a las rondas con el bucle estable.

## 3. Tabla de cambios en prompts y skills (fichero · cambio · por qué · efecto)
| Fichero | Cambio | Por qué | Efecto |
|---|---|---|---|
| `monitor_objective.md` | Secciones `batch`, `raised`, `updated`, `cleared`, `reminder`; marcador `<<open_detections>>`; respuestas posibles (alerta, `supersedes`, `acknowledge_detection`, `close_alert`) | Contrato v0.6: cada aviso tiene respuesta | R1–: el modelo conoce las cuatro respuestas; sin efecto en el fallo de formato |
| `monitor_objective.md` | Recordatorio: «un texto no cuenta como respuesta»; primera versión mencionaba «un JSON escrito dentro de tu mensaje» | Que el modelo llame a la tool tras un texto | La versión que citaba el JSON lo empeoraba (cebaba el formato); la actual no lo arregla |
| `monitor_objective.md` | La detección sin bloque ```` ```json ```` | El bloque cebaba respuestas en ```` ```json ```` | Prueba en banco (junto con el prefijo del sistema): 5/8 → 7/8 en el primer paso; no cambia el paso de decisión |
| `monitor_system.md` | Regla 7 y 8 (acknowledge, un problema una alerta); regla 10 «actúa llamando a las tools»; prefijo «Cada paso de tu trabajo es una llamada a una tool.» | Estabilizar el formato | Mejora marginal del primer paso; ninguna en la decisión |
| `monitor_output.md` | Reescrito en prosa (sin «Formato de tu salida», sin lista de campos ni sintaxis `f(a, b)`); «Recuerda…» se quitó | La sección larga de campos empujaba a escribir el JSON en el texto (banco: decisión 0/3 con ella, 3/3 sin ella) | Con ella quitada, R3 viento ✅; no se repitió en R4 |
| `route-deviation/SKILL.md` | Paso 0 reescrito (recuperación = alerta del GPS abierta/≤ 60 s **y** salto de < 15 m a > 30 m entre dos muestras consecutivas); viento «notable» desde 5 m/s o racha 8 | Plan §2; con 12 m/s nominal el informe a los 100 s da 7,2/9,7 y el umbral antiguo (8/12) no lo veía | Viento llega a `WIND` cuando el modelo llama bien |
| `route-deviation/SKILL.md` y `source-discrepancy/SKILL.md` | `get_events(source="x", last_n=n)` → «la tool `get_events` con `source` = `x`…» | Cebaba la llamada como texto (R4) | Sin efecto medible (R4 ❌) |
| `source-discrepancy/SKILL.md` | Paso 0 nuevo (alerta del GPS abierta y `GPS_DEGRADED` abierta → consecuencia: acknowledge o `GPS_JAMMING` con `supersedes`); antes de concluir spoofing mirar el fix del GPS; un `SOURCE_SILENT` siempre lleva su propia alerta | Plan §2 (F2 de `fallos`) | Sin probar con el LLM (no se llegó a `fallos`) |
| `tools.json` | `acknowledge_detection` | Plan §1 | — |
| `agents.yaml` | `top_k: -1`, `repetition_penalty: 1.0` (explícitos), `max_invocation_s`, `llm_timeout_s`, `no_report_reply` | Plan §5 y §7 | Comprobado con `llm_check` |
| Motor | El resultado de `load_skill` se entrega como texto y no como JSON entrecomillado | Error mío: la skill llegaba como `"---\nname:…"` con `\n` escapados | Corregido en R2; no cambió el fallo |

## 4. Cosas que no cuadraban con el plan (decidir o confirmar)
1. **Criterio de recuperación del plan (§2), «salto de < 15 m a > 30 m en ≤ 2 s», no distingue el secuestro de `demo`:** la desviación del GPS en T+05:38 va 7,2 → 21,1 → 36,7 m en 2 s (el dron se aleja a ~15 m/s) y cumpliría el criterio, mientras que el plan decía que **no** lo cumple. En las recuperaciones reales el salto es de una muestra (5,6 → 73,9 m en `demo`; 1,3 → 90,2 m en `fallos`). **Lo he cambiado a «entre dos muestras consecutivas (1 s)»** en `recovery.py`, en la skill y en la prueba (que ahora comprueba los cinco casos de los cuatro escenarios: spoofing, fallos y demo sí; viento y secuestro no). Es el único cambio de plan que he hecho; dime si no te gusta.
2. `top_k: -1` para **todos** los agentes (también informe y chats), como dice el plan §5; la definición decía `top_k 20` para ellos. Lo dejo en −1 (parámetros del modelo anulados por igual).

## 5. Qué falta para cerrar la fase (cuando decidas A/B/C/D)
1. Tiempos finales (`max_invocation_s`/`llm_timeout_s`): hoy 60 s / 40 s, con p95 medido de 37,5 s (60 + 15 < 90 ✓); se medirán de nuevo con el bucle estable.
2. Los seis `eval.md` (viento, spoofing, secuestro, fallos, nominal, demo) a 16×, `demo` a 1× informativa y los chats (`--ask`).
3. `revisor-contratos`, informe de `demo`, dos trazas resumidas (F2 de `fallos` y el RD de recuperación del spoofing), `fase3.md` con el commit propuesto (sin `Co-Authored-By`) y las copias de las reglas 13 y 15.

## 6. Cómo se ejecuta
```bash
uv run --project platform python -m platform_app.run --scenario viento --speed 16 --wait-agent --evaluate   # con vLLM en marcha
uv run --project platform python -m platform_app.run --scenario demo --speed 16 --detector-only             # sin LLM
uv run --project ai-module-py python -m ai_module.llm_check [--latency runs/<esc>/<run_id> …]
uv run --project ai-module-py python -m ai_module.evaluate runs/<esc>/<run_id>
(cd ai-module-py && uv run pytest -q)    # 212 passed (incluye la e2e con el LLM falso, ≈ 40 s)
```

## 7. Documentación consultada (regla 8)
- vLLM, tool calling: https://docs.vllm.ai/en/latest/features/tool_calling/ (flags `--enable-auto-tool-choice` y `--tool-call-parser hermes`; `tool_choice` `auto`/`required`/`none`). ⚠️ **No confirmado en la documentación:** el formato de los deltas con streaming para `hermes` y qué `finish_reason` devuelve (verificados ejecutando `llm_check`: `tool_calls` en ambos modos).
- vLLM, `--generation-config` (por defecto `auto`; `vllm` desactiva el `generation_config.json` del modelo) y parámetros extra de muestreo vía `extra_body`: https://docs.vllm.ai/en/latest/cli/serve/ y https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/. ⚠️ **No confirmado:** qué valor de `top_k` desactiva el top-k (−1 o 0): `llm_check` muestra que el servidor acepta los dos.
- SDK `openai` (Python, 3.35.1): https://github.com/openai/openai-python. ⚠️ **No confirmado literalmente:** `timeout` de `AsyncOpenAI` y por petición, `extra_body`, `stream_options.include_usage` en Chat Completions y `max_tokens`/`max_completion_tokens` (el README no los muestra); todos comprobados ejecutando `llm_check` contra el vLLM real.
- Configuración de vLLM ya comprobada antes (no la he tocado): RTX PRO 5000 Blackwell de 24 GB; caché de prefijo activa; 63.312 tokens de caché KV (concurrencia máxima de 1,93 a 32.768 tokens); sin `--enforce-eager` ni `--quantization`; `VLLM_USE_FLASHINFER_SAMPLER=0`.

## 8. Copias (reglas 13 y 15)
Hechas al parar: `docs/fases/`, los PNG de `runs/*/`, los `eval.md`/`eval.json` de todas las ejecuciones de esta fase y las trazas representativas (`results/trazas/`: viento R3 —el único acierto— y viento, spoofing y secuestro de R4) en `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`; instantánea del código en `snapshots/fase3/` y la limpia en `snapshots-limpias/fase3/`, con las dos comprobaciones de la regla 15 vacías (en la primera encontró una referencia a `docs/` en el docstring de `evaluate.py`: corregida en el repo y recopiada). No hay mensaje de commit propuesto todavía (se escribirá en `fase3.md`).
