# Plan · Fase 3 (agentes)

## Contexto
Las fases 0–2 están aprobadas: simulador en directo, bus, tools de datos con corte temporal y detector de cuatro reglas. Falta la IA que diagnostica: motor de agente, monitor, informe, dos chats en streaming, guardrails, trazas y `evaluate.py`. Criterio de la fase (§9): `demo.yaml` diagnosticado con la causa correcta en las tres anomalías, o el fallo documentado.

vLLM responde en `127.0.0.1:8000` con **`Qwen/Qwen2.5-14B-Instruct-AWQ`** (`max_model_len` 32768). Comprobado.

Lo que hay en el código y condiciona el diseño:
- `platform_app/player.py:367-385`. Con «esperar al agente», cada `DetectionRaised`/`DetectionUpdated` pausa el reproductor. Se reanuda con **cualquier** evento de `source: ai-monitor` cuyo `causation_id` sea el `event_id` de la detección.
  - Ojo: un `DetectionUpdated` tiene su propio `event_id`, distinto de su `detection_id`.
  - `DetectionCleared` no pausa.
  - `WAIT_AGENT_TIMEOUT_S = 90`.
- `timeline.py`/`player._dump_timeline` vuelcan el timeline una sola vez, en `SimulationFinished`. Lo que llega después (últimas respuestas, `ReportGenerated`, chats) se perdería.
- Se reutilizan:
  - `bus_client.py` (WebSocket, y `_post_tool` por HTTP);
  - `Detector`;
  - `poc_contracts` (`EVENT_SPECS`, `PAYLOAD_MODELS`);
  - el patrón de streaming con tool calls de `~/spike1/py/openai/chat_f.py`.

## 1. Respuesta a cada detección (contrato v0.6, regla 2)
`AnomalyDetected` + `supersedes` **no basta**:
- no puede decir «no hace falta alerta» sin crear una alerta falsa;
- no puede decir «pertenece a la alerta abierta» sin republicarla;
- en un lote, cada detección necesita su propio `causation_id`.

Hacen falta un evento nuevo y una tool nueva.

**Evento `DetectionAcknowledged`.** Topic `citadel.pub.evt.ai.d1.DetectionAcknowledged.v1`, id `ai-`, `source: ai-monitor`, `asset: d1`, `causation_id` = `event_id` de la detección:
```json
{ "detection_id": "det-0002", "alert_id": "ai-0003", "reason": "…", "as_of_sim_time": 258.0, "fallback": false }
```

**Tool `acknowledge_detection(detection_ids, alert_id?, reason)`.** El monitor pasa a tener 8 tools.

| Caso | Publica |
|---|---|
| Alerta nueva | `AnomalyDetected` |
| Pertenece a una alerta abierta y cambia la causa o la severidad: el RD de recuperación del spoofing o de la pérdida (severidad `medium`, «el GPS ha vuelto»), o el SD que confirma la pérdida sobre una alerta `SENSOR_FAULT` | `AnomalyDetected` con `supersedes` (sigue siendo una sola cadena) |
| Pertenece a una alerta abierta y no cambia nada: SD/RD tras `GPS_DEGRADED` con la alerta ya en `GPS_JAMMING`, o el `DetectionUpdated` del secuestro | `DetectionAcknowledged` con `alert_id` |
| El agente decide que no hace falta alerta | `DetectionAcknowledged` con `alert_id: null` |
| El agente no concluye (texto final tras un recordatorio, tope de 8 iteraciones, tiempo agotado o error del LLM) en un `DetectionRaised` **sin ninguna alerta abierta** | `AnomalyDetected` `UNKNOWN`, `fallback: true` |
| El agente no concluye en cualquier otro caso | `DetectionAcknowledged`, `fallback: true`, `alert_id: null` |
| `DetectionCleared` y a la alerta le quedan detecciones abiertas, o no tiene alerta, o ya está cerrada | `DetectionAcknowledged` determinista, sin LLM (`deterministic: true` en la traza) |
| `DetectionCleared` de la última detección abierta de una alerta | Se invoca al LLM: `close_alert`, o `acknowledge_detection` si cree que sigue el problema (se respeta). Si acaba en fallback, el módulo publica él mismo un `AlertClosed` con `reason` «todas sus detecciones se han cerrado» (`fallback: true` en la traza) |

§7.5 de la definición se reescribe para que diga exactamente las dos filas de fallback.

**Garantía en código.** Cada invocación lleva sus eventos de detección pendientes. Al terminar, el módulo publica la respuesta de cada uno que siga sin ella:
- si una alerta publicada en la invocación la incluye en `detection_ids`, un acknowledge enlazado a esa alerta;
- si no, el fallback de la tabla.

**Fin del bucle.** El bucle termina en cuanto todas las detecciones del lote tienen respuesta. Así no hay una llamada de más y no se anota dos veces (lo que pasó en el spike 1).

**Tiempos.** Se miden en el paso 0 (§5):
- `max_invocation_s` = p95 de una invocación típica más un margen;
- `llm_timeout_s` acorde;
- condición: `max_invocation_s + 15 < WAIT_AGENT_TIMEOUT_S`. Si no cabe, subo `WAIT_AGENT_TIMEOUT_S` en la plataforma y lo anoto.

Los valores y su porqué van a `fase3.md`.

**Cambios en el mismo commit:**
- `contracts/eventos.md` (§3, §4 y §7; versión 0.6);
- `poc_contracts` (modelo, `EventType`, `EVENT_SPECS`, `PAYLOAD_MODELS`) y los esquemas regenerados con el ejemplo validado;
- `agent-assets/tools.json`, `agents.yaml`, prompts y skills;
- plataforma: compruebo que `get_my_alerts` y `get_flight_summary` lo ignoran; prueba de que el reproductor se reanuda con `DetectionAcknowledged`;
- `web/CLAUDE.md`, `ai-module-py/CLAUDE.md` y `docs/01_definicion.md` §7 (8 tools, fallbacks, cierre determinista).

Te lo cuento en `fase3.md`.

**Guardrails.** Un rechazo vuelve al modelo como resultado de la tool y cuenta como iteración.
- `publish_alert`:
  - validación Pydantic (`AnomalyDetected`: causas y severidades cerradas, `confidence` entre 0 y 1, `summary` ≤ 160);
  - cada evidencia existe y tiene `sim_time` ≤ `as_of`. Se mira en un índice local de los eventos `air`/`env`/`ai`/`ops` recibidos por el WebSocket, no en `/api/timeline`, que trae el dominio `sim`. Los ids que existen pero no ha visto el modelo se cuentan en la traza;
  - las `detection_ids` existen;
  - `supersedes` apunta a una alerta abierta;
  - sin `supersedes`, se rechaza si una de las detecciones ya está en una alerta abierta.
- `acknowledge_detection`: el `alert_id` existe y está abierto; cada detección es del lote y aún no tiene respuesta.
- `close_alert`: la alerta existe, está abierta y no le quedan detecciones abiertas.
- Tools de datos del monitor: el módulo pone `until = as_of` (el `sim_time` al empezar la invocación) si falta o si es mayor.

## 2. Un episodio, una alerta, y `GPS_JAMMING` frente a `GPS_SPOOFING`
**Estado (opción B).** Lo lleva `monitor_state.py`, puro y probado:
- las alertas y sus cadenas de `supersedes`;
- qué detecciones pertenecen a cada alerta (las de toda la cadena más las enlazadas con acknowledge);
- las detecciones abiertas;
- las últimas 3 decisiones.

En el objetivo se inyectan:
- las alertas abiertas, con sus detecciones abiertas y cerradas;
- `<<open_detections>>`, un marcador nuevo;
- las últimas decisiones;
- `related_alerts`, siguiendo la cadena hasta la alerta en vigor.

**Prompts.**
- Sistema: terminar siempre con `publish_alert`, `acknowledge_detection` o `close_alert`.
- `raised`: si una alerta abierta ya lo explica, acknowledge, o `supersedes` si cambia la causa o la severidad.
- `updated`: si no cambia nada, acknowledge.
- Sección nueva `reminder`.

**Skills.**
- `source-discrepancy`, paso 0 nuevo: si hay una alerta del GPS abierta (`GPS_JAMMING`/`SENSOR_FAULT`) y `GPS_DEGRADED` sigue abierta, la discrepancia es la consecuencia de la pérdida.
  - Si la alerta es `SENSOR_FAULT`, se sustituye con `GPS_JAMMING`.
  - Si ya es `GPS_JAMMING`, acknowledge.
- `source-discrepancy`, paso 6: un `SOURCE_SILENT` es siempre un fallo distinto y lleva su propia alerta (F3).
- `route-deviation`, paso 0 reescrito. Es recuperación si se cumplen las dos:
  1. hay una alerta `GPS_SPOOFING`, `GPS_JAMMING` o `SENSOR_FAULT` del GPS abierta, o cerrada hace ≤ 60 s de tiempo simulado;
  2. **la desviación del GPS da un salto brusco: de < 15 m a > 30 m en ≤ 2 s**. Se comprueba con `get_events(gps, last_n=5)` o con `get_track_metrics` de los últimos segundos. El viento y el secuestro crecen poco a poco.

  El fix `3d` no se usa como criterio, porque es lo normal.

  Prueba sin LLM sobre `demo`: el contexto del RD de T+05:38 (secuestro) **no** cumple el criterio de recuperación. Se vigila también en el eval de `demo`.

**F2 esperado** (`fallos`):

| T+ | Detección | Respuesta |
|---|---|---|
| 04:05 | GD | `ai-A` (`SENSOR_FAULT` o `GPS_JAMMING`) |
| 04:18 | SD | `ai-B` `GPS_JAMMING`, sustituye a `ai-A`, o acknowledge |
| 04:48 | SD U | acknowledge |
| 04:50 | RD | `ai-C` `GPS_JAMMING` `medium`, «el GPS ha vuelto» (supersedes) |
| 04:55 | GD C | acknowledge determinista |
| 05:17 | RD C | acknowledge determinista |
| 05:20 | SD C | LLM: `close_alert` |

Queda una cadena, con una sola alerta abierta a la vez. El `SOURCE_SILENT` del GPS de T+05:04 lleva su propia alerta `SENSOR_FAULT`.

**Jamming frente a spoofing.**
1. Solo la pérdida dispara `GPS_DEGRADED`, y llega antes que la discrepancia; el estado la muestra abierta.
2. La skill obliga a mirar `get_events(gps, last_n=5)` **antes** de concluir spoofing:
   - `fix none`, `sats 0` o `hdop` 99,9 → `GPS_JAMMING`;
   - fix sano, GPS sobre el plan, radar fuera y distancia creciente → `GPS_SPOOFING`.

La geometría de los dos es igual; lo que los separa es la calidad del fix.

## 3. `evaluate.py` → `eval.md` (más `eval.json`)
Se ejecuta con `uv run --project ai-module-py python -m ai_module.evaluate runs/<esc>/<run_id>`.
- Lee `timeline.jsonl`, `llm_trace.jsonl` y `runs/<esc>/labels.json`.
- Es un módulo aislado: una prueba comprueba que el código del agente no lee `labels` ni `truth`.
- Los fallos manuales generan etiquetas sintéticas.

**Atribución.**
- Una detección va a la etiqueta cuya `eval_window` la contiene y cuyas `expected_rules` incluyen su regla. Si hay varias, a la de inicio más reciente.
- Su causa atribuida es la de su respuesta: la alerta, o la alerta a la que la enlaza el acknowledge. Si la respuesta es un fallback, queda «sin diagnóstico».
- Es acierto si la causa está en `{expected_cause} ∪ also_accepted_causes`. Así se aplica la regla del RD de recuperación de §4.4.

**Secciones de `eval.md`:**
1. **Cabecera y resumen en una línea.**
   - Cabecera: escenario, `run_id`, modelo, parámetros, `guided_mode`, esperar al agente, velocidad y duración en reloj.
   - Resumen: ✅/⚠️/❌, falsas alarmas, fallbacks, esperas agotadas, detecciones sin respuesta (debe ser 0) y **alertas abiertas al final de la simulación**.
2. **Anomalías y fallos.** Por etiqueta: primera detección (regla, T+), retraso de detección, primera alerta aceptada y su confianza, retraso de diagnóstico (en tiempo simulado y en reloj, por `ingestion_time`), número de cadenas de alerta (se espera 1) y veredicto:
   - ✅: todas las detecciones atribuidas a una causa aceptada;
   - ⚠️: hay una alerta correcta, pero alguna detección está mal atribuida;
   - ❌: ninguna alerta correcta.
3. **Respuesta a cada detección.** Tipo (alerta, supersedes, acknowledge, determinista o fallback), causa atribuida, ✅/❌ y latencia en reloj. Incluye la fila del RD del secuestro en `demo`, marcando que no se trató como recuperación.
4. **Falsas alarmas.**
5. **Agente**, por instancia:
   - invocaciones (LLM y deterministas), iteraciones y llamadas al LLM;
   - tokens: suma y **máximo de tokens de prompt por agente**, para ver cuánta concurrencia de la caché KV queda libre;
   - latencia por llamada (media, p50, máximo);
   - llamadas por tool;
   - **skills que carga el propio modelo** frente a las precargadas por el modo guiado;
   - JSON inválido, rechazos de guardrails, recordatorios, fallbacks, cierres de fallback y evidencias no vistas.
6. **Esperas al agente.** Cuántas, media, máximo y cuántas llegan al tope; para cada espera, si había un chat en curso.
7. **Solo sin esperar** (demo a 1×): latencia en tiempo simulado, cola máxima, lotes de más de una detección y desfase (`sim_time` al publicar − `as_of`, más las detecciones que llegan durante la invocación).

## 4. Trazas
- Van en `runs/<esc>/<run_id>/llm_trace.jsonl`, una línea por invocación. Cada línea lleva:
  - `invocation_id`, agente, `causation_ids`, `as_of`, `sim_time` final, cola y reloj;
  - los **parámetros enviados**, incluidos los de `extra_body`;
  - las tools ofrecidas;
  - los `messages` completos, una sola vez;
  - por cada llamada: latencia, tokens, `finish_reason` (solo como anotación), tool calls con argumentos, resultado, error y si se recortó;
  - skills cargadas (`by: model | guided`), rechazos, `deterministic`, `fallback` y eventos publicados.
- Tamaño: unos 15–30 KB por invocación del monitor y unos 40–60 KB por el informe, es decir, **0,3–0,6 MB por ejecución**.
- **No van al repo:** la regla `runs/*/*/` ya las ignora, así que **`.gitignore` no se toca**. Las dos trazas elegidas se copian a `results/` y se resumen en `fase3.md`.
- Timeline: después del primer volcado, los eventos nuevos **se añaden** al fichero. Con prueba.

## 5. Orden de pruebas con el LLM
**0. Comprobación previa.** El resultado va a `fase3.md`:
- Script contra vLLM:
  - tool calls con `stream=True`;
  - `stream_options.include_usage`;
  - `timeout` de `AsyncOpenAI`;
  - **latencia de una invocación típica del monitor** (`load_skill` + 2 tools de datos + `publish_alert`) para fijar los tiempos del §1. Se mide con **detecciones distintas**, al menos de viento, spoofing y secuestro, sacadas de sus `events.jsonl`. No se repite la misma petición, porque la caché de prefijo daría un p95 demasiado optimista. En `fase3.md` se anota con qué se midió.
- Documentación oficial con URL (regla 8): vLLM tool calling con el parser `hermes` y streaming; vLLM `--generation-config`; SDK `openai` (`AsyncOpenAI`, `timeout`, `extra_body`, `stream_options`).
- Parámetros de muestreo:
  - confirmar en `~/.cache/huggingface` el `generation_config.json` del modelo (temperature 0.7, top_p 0.8, top_k 20, repetition_penalty 1.05);
  - en `agents.yaml`, `repetition_penalty: 1.0` y `top_k: -1`, con la nota «explícitos para anular los valores por defecto del modelo»;
  - se envían en cada petición con `extra_body` y la traza los registra.
- Se anota la configuración de vLLM ya comprobada: RTX PRO 5000 Blackwell de 24 GB; caché de prefijo activa (3.920 de 3.929 tokens acertados en la 2.ª petición); 63.312 tokens de caché KV (concurrencia máxima de 1,93 a 32.768 tokens); sin `--enforce-eager` ni `--quantization`; `VLLM_USE_FLASHINFER_SAMPLER=0`.

**1. Escenarios con «esperar al agente» a 16×** (`run.py --wait-agent --evaluate`), en este orden: viento, spoofing, secuestro, fallos, nominal (0 alertas) y demo (el criterio de la fase).

**2. Demo sin esperar, a 1×**, una vez y solo informativa.

**3. Chats:** 2–3 preguntas a cada uno con `run.py --ask monitor:200:"…"` (cliente `web`, imprime el streaming).

**Si algo falla:**
- (a) ajustar prompts y skills en `agent-assets/`, cada cambio anotado en una tabla (fichero, cambio, por qué, efecto), y **repetir los escenarios anteriores**;
- (b) `guided_mode: true` si el modelo no carga skills o no mejora tras unas 3 rondas;
- (c) documentar y preguntarte.

**Nunca se cambia de modelo.** Lo que pase de 30 min se anota.

## 6. pytest (sin LLM) y evaluación con el LLM
Pruebas con pytest y un LLM falso guionizado:
- **Motor:**
  - en cada petición van `temperature`, `top_p`, `max_tokens`, `tool_choice: "auto"` y, en `extra_body`, `top_k: -1` y `repetition_penalty: 1.0`;
  - tools tal cual, filtradas y con `disabled_tools`;
  - las llamadas se detectan por `tool_calls`, también con `finish_reason: stop`;
  - JSON inválido o tool desconocida cuentan como iteración;
  - recorte a ~4000 caracteres;
  - tope de iteraciones, fin al responderlo todo, recordatorio, tiempo máximo y streaming con `tool_calls`.
- **Assets:** índice de skills, marcadores (no queda ningún `<<…>>`) y secciones.
- **Guardrails:** cada regla del §1, aceptada y rechazada.
- **`monitor_state`:** cadenas, pertenencia, detecciones abiertas y decisiones.
- **Respuesta a cada detección:**
  - se repiten los `events.jsonl` de los seis escenarios por el detector y el monitor, con LLM falsos que siempre publican, siempre responden texto, devuelven basura, lanzan excepciones o se pasan de tiempo;
  - para cada Raised/Updated/Cleared hay al menos una respuesta con su `causation_id`, dentro del tope;
  - la excepción de `UNKNOWN` sin alertas abiertas;
  - lotes de 3;
  - cierre determinista;
  - **cierre de fallback (`AlertClosed`) cuando la invocación del último Cleared acaba en fallback**;
  - el LLM mantiene abierta la alerta: se respeta y `evaluate` la cuenta.
- **Criterio de recuperación** (`recovery.py`, una función pura): sobre `demo`, el RD de T+05:38 no lo cumple y el de T+03:42 sí. La prueba comprueba que la skill está bien planteada sobre los datos.
  - Fuera de esta prueba, solo puede usarlo el modo guiado. El monitor no lo ejecuta para darle pistas al LLM: la recuperación la concluye el modelo con la skill y las tools.
  - `evaluate` no lo usa y **no importa nada del código del agente**. Si el RD del secuestro «se trató como recuperación» se decide por lo que publicó el agente (si sustituyó a una alerta de la cadena del spoofing o abrió una alerta nueva, y con qué causa), contrastado con `labels.json`.
- **Informe:** si falla, informe mínimo marcado; menciona las alertas abiertas al final.
- **Chats:**
  - **en su propia tarea, sin pasar por la cola del monitor**: un chat lento no retrasa una detección;
  - historial de 12 mensajes y sistema rehecho en cada pregunta;
  - el chat del informe, antes de que exista el informe, contesta con un texto fijo de `agents.yaml`;
  - trozos efímeros y `AgentReply`.
- **`evaluate.py`:** atribución, RD de recuperación, `also_accepted_causes`, falsas alarmas, cadenas, alertas abiertas al final, esperas con o sin chat en curso.
- **e2e** (marca `e2e`): `run.py --scenario demo --wait-agent --speed 16` contra un servidor LLM falso compatible con OpenAI (stdlib, `--llm-url`). Comprueba 0 esperas agotadas y 0 detecciones sin respuesta.
- **Plataforma:** el reproductor se reanuda con `DetectionAcknowledged`; volcado incremental del timeline.

**Con el LLM se evalúa**, sin aserciones exactas: la causa por etiqueta, una cadena por episodio, las falsas alarmas, las latencias, los tokens, las tools y skills, y la calidad del informe y de los chats.

## 7. Piezas y ficheros
- `ai-module-py/src/ai_module/agent/`:
  - `assets.py`;
  - `llm.py` (`AsyncOpenAI`, Chat Completions, parámetros explícitos con `extra_body`, streaming);
  - `engine.py`;
  - `tools.py` (HTTP con `_post_tool` y tools locales);
  - `guardrails.py`;
  - `trace.py`.
- En `ai_module/`:
  - `monitor_state.py`;
  - `monitor.py` (un trabajador, lotes, garantía de respuesta, cierre determinista y de fallback, `AgentActivity`);
  - `recovery.py` (criterio de recuperación; solo para la prueba y, como mucho, el modo guiado);
  - `report.py`;
  - `chat.py` (tarea propia por conversación);
  - `ids.py`;
  - `evaluate.py`.
- `__main__.py`: detector y agentes por defecto, con `--detector-only` y `--llm-url`. La dependencia `openai` se añade con `uv add`.
- `agent-assets/agents.yaml`: `top_k`, `repetition_penalty`, `max_invocation_s`, `llm_timeout_s`, la respuesta fija del chat del informe y la tool nueva del monitor.
- `platform/`:
  - `run.py` (`--wait-agent`, `--evaluate`, `--ask`, `--detector-only`/`--llm-url` de paso, espera a `ReportGenerated`);
  - volcado incremental en `timeline.py`/`player.py`;
  - `WAIT_AGENT_TIMEOUT_S`, solo si hace falta.
- `docs/mejoras_futuras.md`: entrada «Uso exclusivo del LLM por configuración». Es un `llm_max_concurrency` global en `agents.yaml` con un semáforo compartido; los tiempos máximos cuentan desde que el monitor consigue el LLM; sin «esperar al agente», necesita un mensaje nuevo del módulo a la plataforma en el contrato. No se implementa ahora.
- Al cerrar la fase:
  - `revisor-contratos`;
  - `ruff`;
  - `docs/fases/fase3.md`, con: los `eval.md` de viento, spoofing, secuestro, fallos, nominal, demo y demo a 1×; el informe de demo; dos trazas resumidas (F2 de `fallos` y el RD de recuperación del spoofing); la tabla de cambios en prompts y skills; los tiempos elegidos; los parámetros de muestreo y la configuración de vLLM; las URLs; y el commit propuesto, sin `Co-Authored-By`;
  - las copias de las reglas 13 y 15, con sus comprobaciones;
  - **parada**.

## Verificación
- `uv run pytest -q` en `contracts/python`, `platform` y `ai-module-py` (incluida la e2e con el LLM falso); `ruff check` y `ruff format --check`.
- `run.py --scenario <esc> --speed 16 --wait-agent --evaluate` en los seis escenarios. En `eval.md`: 0 detecciones sin respuesta, 0 esperas agotadas, causas correctas, una cadena por episodio, 0 alertas en `nominal` y el RD del secuestro no tratado como recuperación.
- `run.py --scenario demo --speed 1 --evaluate`, solo informativo.
