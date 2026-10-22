# Fase 3 · agentes (monitor, informe, chats, guardrails, trazas y evaluación)

Fecha: 21/10/2026. Estado: **terminada y congelada, pendiente de tu revisión**. Contrato v0.8. Configuración final: ronda **R9**, con `agent-assets/` y `agents.yaml` **congelados** (huella `8e2376c580bab74b`: `find agent-assets -type f | sort | xargs sha256sum | sha256sum`, comprobada antes y después de `fallos`, `nominal` y los chats).

Resultado en una línea: con el LLM real, **`demo` sale 3/3 en las tres ejecuciones** (viento `WIND`, spoofing `GPS_SPOOFING` y su recuperación en la misma cadena, secuestro `HIJACK`; 0 fallbacks, 0 alertas abiertas al final), y también `spoofing` y `viento` por separado; `nominal` ✅ (0 alertas). Lo que sigue fallando está en el apartado 14: `fallos` queda en 2/3 (F3, el GPS callado dentro de la cadena del jamming, y alertas abiertas al final) y los chats con tools escriben las llamadas como texto. Tienes la historia completa de las rondas y las trazas.

## 1. Qué se hizo
- **Contrato v0.8** (`contracts/eventos.md`, modelos, 56 esquemas): `DetectionAcknowledged` y la tool `acknowledge_detection` (tabla de respuestas y fallbacks de §4); `get_track_metrics` con el viento de la ventana y **hechos calculados** (`wind.notable`, `wind.with_drift`, `gps_radar.disagreed`, `gps_max_step_m`); `checks` en `publish_alert` (obligatorio, antes de `cause`) y opcional en `AnomalyDetected`; `alerts_by_cause` cuenta cadenas; `detection_ids`/`alert_id` opcionales en las tools que responden (v0.8).
- **Plataforma:** volcado incremental del timeline (lo que llega tras `SimulationFinished` se añade a `timeline.jsonl`); `run.py` con `--wait-agent`, `--evaluate`, `--ask` (con streaming), `--detector-only` y `--llm-url`, espera a `ReportGenerated` y a todas las respuestas del chat, escribe `run_meta.json`.
- **Módulo de IA** (`ai-module-py`, SDK `openai` 3.35.1): `agent/` (assets, cliente, motor, tools, guardrails, trazas), `monitor.py` y `monitor_state.py`, `report.py`, `chat.py`, `recovery.py`, `evaluate.py`, `llm_check.py`.
- **Motor y monitor:** un trabajador con lotes; cada aviso del detector recibe respuesta (alerta, `supersedes`, `acknowledge_detection`, cierre) y, si el agente no concluye, el módulo la publica (fallback); los `Cleared` que no cambian nada se responden sin LLM; al modelo solo se le enseña el `detection_id`; `publish_alert` solo acepta detecciones pendientes del lote y la alerta lleva el `causation_id` de la detección a la que responde.
- **Ronda R9 (última):** la recuperación del GPS tras un engaño es **excluyente** en el guardrail (la única causa aceptada es la de la alerta del GPS reciente, con `supersedes` a ella) y la línea del estado lo anticipa; `detection_ids` y `alert_id` los rellena el módulo cuando no hay nada que elegir (contrato v0.8); si el modelo repite por segunda vez una llamada ya rechazada, el motor corta la invocación y aplica el fallback; interruptor `chat.tools_enabled` (apagado en la demo: los chats llevan el estado, las alertas con su razonamiento y los últimos hechos en el sistema).
- **Ronda R8:** `load_skill` repetido no reenvía la skill; el estado lleva una línea fija «Alerta del GPS reciente»; `evidence_event_ids` pasa detrás de `confidence` en el esquema; rechazos en español y accionables, con aviso si se repite la misma llamada; el monitor tiene 12 iteraciones; el informe no usa tools (el módulo le inyecta el resumen del vuelo, las alertas con sus cadenas y las detecciones) y los chats reciben el estado actual en el sistema.
- **Interruptores de las ayudas** (`monitor.*` en `agents.yaml`, todo activado): `tool_choice`, `final_iteration_response_tools_only`, `require_checks`, `coherence_guardrail`, `computed_facts`; `eval.md` anota en su cabecera cuáles estaban activas. Una prueba por interruptor.
- **Documentación:** `CLAUDE.md` (reglas 4 y 6), `docs/01_definicion.md` §5 y §7, `ai-module-py/CLAUDE.md`, `platform/CLAUDE.md`, `web/CLAUDE.md`, `docs/mejoras_futuras.md` (nueva sección «Liberar al agente»).

## 2. Cómo se ejecuta
```bash
uv run --project platform python -m platform_app.run --scenario demo --speed 16 --wait-agent --evaluate   # con vLLM en marcha
uv run --project platform python -m platform_app.run --scenario demo --speed 1 --evaluate                  # sin esperar al agente
uv run --project platform python -m platform_app.run --scenario viento --speed 16 --wait-agent \
    --ask "monitor:150:¿Por qué crees que es viento?" --ask "report:end:¿Qué pasó?"                      # chats
uv run --project platform python -m platform_app.run --scenario demo --speed 16 --detector-only           # sin LLM
uv run --project ai-module-py python -m ai_module.evaluate runs/<escenario>/<run_id>
uv run --project ai-module-py python -m ai_module.llm_check [--latency runs/<esc>/<run_id> …]
(cd contracts/python && uv run pytest -q)   # 127 passed, 1 skipped
(cd platform && uv run pytest -q)           # 203 passed
(cd ai-module-py && uv run pytest -q)       # 270 passed (incluye la e2e, ≈ 40 s)
ruff check . && ruff format --check .       # limpio
```

## 3. Resultados con el LLM (configuración final R9, congelada)

| Escenario | Resultado | Cómo |
|---|---|---|
| `demo` 16× (3 ejecuciones) | ✅ 3/3 las tres | viento `WIND`; spoofing `GPS_SPOOFING` (alta) y su recuperación `GPS_SPOOFING` (media) **con `supersedes`: una sola cadena**; secuestro `HIJACK`; 0 fallbacks, 0 alertas abiertas al final |
| `spoofing` | ✅ | igual que en `demo`, una cadena |
| `viento` (ejecución de los chats) | ✅ | `WIND`, 0 fallbacks |
| `nominal` | ✅ | 0 detecciones, 0 alertas |
| `fallos` | ❌ 2/3 | F1 radar ✅; F2 pérdida de GPS ✅ pero en **2 cadenas** (la discrepancia abre otra alerta en vez de reconocerse); F3 GPS callado ❌ (`GPS_JAMMING` en vez de `SENSOR_FAULT`); 2 alertas abiertas al final (cierres reconocidos con `acknowledge_detection`) |
| `secuestro` y `demo` 1× | (R8 / R7, no se repitieron al congelar) | `secuestro` ✅ en R8; `demo` 1× igual que a 16× en R7 |
Siempre: 0 detecciones sin respuesta, 0 esperas agotadas, 0 fallbacks en la configuración congelada. Los `eval.md` completos:

### demo (R9, 16×, esperando al agente; primera de las tres ejecuciones)
#### Evaluación · demo · 20261021-215855

**✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final**

- Modelo: `Qwen/Qwen2.5-14B-Instruct-AWQ` · temperature 0.0 · top_p 1.0 · top_k -1 · repetition_penalty 1.05 · max_tokens 800
- `guided_mode`: False · esperar al agente: True · velocidad: 16.0× · duración en reloj: 102 s
- Ayudas al modelo: tool_choice = required · última iteración solo con las respuestas: sí · checks obligatorios: sí · guardrail de coherencia: sí · hechos calculados: sí

##### 1. Anomalías y fallos

| Etiqueta | Tipo | Ventana | Primera detección | Retraso detección | Primera alerta aceptada (conf.) | Retraso diagnóstico (sim / reloj) | Cadenas | Veredicto |
|---|---|---|---|---|---|---|---|---|
| A1 | wind | T+01:35–T+02:30 | ROUTE_DEVIATION T+01:46 | 11,0 s | WIND T+01:46 (0.85) | 0,3 s / 14,9 s | 1 | ✅ |
| A2 | gps_spoofing | T+02:48–T+03:42 | SOURCE_DISCREPANCY T+03:12 | 24,0 s | GPS_SPOOFING T+03:12 (0.85) | 0,3 s / 10,2 s | 1 | ✅ |
| A3 | hijack | T+05:35–T+06:20 | ROUTE_DEVIATION T+05:38 | 3,0 s | HIJACK T+05:38 (0.85) | 0,2 s / 16,8 s | 1 | ✅ |

##### 2. Respuesta a cada detección

| T+ | Aviso | Regla | Fuente | Detección | Respuesta | Causa atribuida | ✔ | Latencia (reloj) | Nota |
|---|---|---|---|---|---|---|---|---|---|
| T+01:46 | R | ROUTE_DEVIATION | — | det-0001 | alerta ai-0002 | WIND | ✅ | 14,9 s |  |
| T+02:36 | C | ROUTE_DEVIATION | — | det-0001 | cierre ai-0002 | — | ✅ | 3,8 s |  |
| T+03:12 | R | SOURCE_DISCREPANCY | — | det-0003 | alerta ai-0008 | GPS_SPOOFING | ✅ | 10,2 s |  |
| T+03:42 | R | ROUTE_DEVIATION | — | det-0004 | alerta ai-0011 (sustituye) | GPS_SPOOFING | ✅ | 14,6 s |  |
| T+03:52 | C | SOURCE_DISCREPANCY | — | det-0003 | ack → ai-0011 · determinista | — | ✅ | 0,0 s |  |
| T+03:54 | C | ROUTE_DEVIATION | — | det-0004 | cierre ai-0011 | — | ✅ | 3,4 s |  |
| T+05:38 | R | ROUTE_DEVIATION | — | det-0007 | alerta ai-0018 | HIJACK | ✅ | 16,8 s | no tratado como recuperación ✅ |
| T+05:41 | U | ROUTE_DEVIATION | — | det-0007 | ack → ai-0018 | HIJACK | ✅ | 10,7 s |  |
| T+07:21 | C | ROUTE_DEVIATION | — | det-0007 | cierre ai-0018 | — | ✅ | 2,4 s |  |

##### 3. Falsas alarmas

Ninguna.

##### 4. Agente

###### monitor
- Invocaciones: 9 (8 con LLM, 1 deterministas) · iteraciones: 39 · llamadas al LLM: 39
- Tokens: prompt 236961, completion 3698 · **máximo de prompt en una llamada: 9178**
- Latencia por llamada: media 1,9 s, p50 1,0 s, máx. 6,4 s
- Llamadas por tool: acknowledge_detection: 1, close_alert: 3, get_events: 6, get_track_metrics: 11, load_skill: 10, publish_alert: 8
- Skills cargadas por el modelo: 7 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 4 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'done': 8, 'deterministic': 1}
###### report
- Invocaciones: 1 (1 con LLM, 0 deterministas) · iteraciones: 1 · llamadas al LLM: 1
- Tokens: prompt 1613, completion 998 · **máximo de prompt en una llamada: 1613**
- Latencia por llamada: media 17,0 s, p50 17,0 s, máx. 17,0 s
- Llamadas por tool: ninguna
- Skills cargadas por el modelo: 0 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 0 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'final': 1}

##### 5. Esperas al agente

5 esperas · media 13,4 s · máxima 16,8 s · 0 agotadas (≥ 89 s).

| T+ | Espera (reloj) | Chat en curso |
|---|---|---|
| T+01:46 | 14,9 s | no |
| T+03:12 | 10,2 s | no |
| T+03:42 | 14,6 s | no |
| T+05:38 | 16,8 s | no |
| T+05:41 | 10,7 s | no |

##### Alertas abiertas al final

Ninguna.

### spoofing (R9)
#### Evaluación · spoofing · 20261021-215707

**✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final**

- Modelo: `Qwen/Qwen2.5-14B-Instruct-AWQ` · temperature 0.0 · top_p 1.0 · top_k -1 · repetition_penalty 1.05 · max_tokens 800
- `guided_mode`: False · esperar al agente: True · velocidad: 16.0× · duración en reloj: 55 s
- Ayudas al modelo: tool_choice = required · última iteración solo con las respuestas: sí · checks obligatorios: sí · guardrail de coherencia: sí · hechos calculados: sí

##### 1. Anomalías y fallos

| Etiqueta | Tipo | Ventana | Primera detección | Retraso detección | Primera alerta aceptada (conf.) | Retraso diagnóstico (sim / reloj) | Cadenas | Veredicto |
|---|---|---|---|---|---|---|---|---|
| A1 | gps_spoofing | T+02:48–T+03:42 | SOURCE_DISCREPANCY T+03:12 | 24,0 s | GPS_SPOOFING T+03:12 (0.8) | 0,4 s / 9,6 s | 1 | ✅ |

##### 2. Respuesta a cada detección

| T+ | Aviso | Regla | Fuente | Detección | Respuesta | Causa atribuida | ✔ | Latencia (reloj) | Nota |
|---|---|---|---|---|---|---|---|---|---|
| T+03:12 | R | SOURCE_DISCREPANCY | — | det-0001 | alerta ai-0002 | GPS_SPOOFING | ✅ | 9,6 s |  |
| T+03:42 | R | ROUTE_DEVIATION | — | det-0002 | alerta ai-0005 (sustituye) | GPS_SPOOFING | ✅ | 17,1 s |  |
| T+03:52 | C | SOURCE_DISCREPANCY | — | det-0001 | ack → ai-0005 · determinista | — | ✅ | 0,0 s |  |
| T+04:01 | C | ROUTE_DEVIATION | — | det-0002 | cierre ai-0005 | — | ✅ | 2,3 s |  |

##### 3. Falsas alarmas

Ninguna.

##### 4. Agente

###### monitor
- Invocaciones: 4 (3 con LLM, 1 deterministas) · iteraciones: 14 · llamadas al LLM: 14
- Tokens: prompt 85483, completion 1393 · **máximo de prompt en una llamada: 8507**
- Latencia por llamada: media 2,1 s, p50 1,0 s, máx. 6,5 s
- Llamadas por tool: close_alert: 1, get_events: 2, get_track_metrics: 4, load_skill: 3, publish_alert: 4
- Skills cargadas por el modelo: 3 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 2 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'done': 3, 'deterministic': 1}
###### report
- Invocaciones: 1 (1 con LLM, 0 deterministas) · iteraciones: 1 · llamadas al LLM: 1
- Tokens: prompt 1390, completion 599 · **máximo de prompt en una llamada: 1390**
- Latencia por llamada: media 10,0 s, p50 10,0 s, máx. 10,0 s
- Llamadas por tool: ninguna
- Skills cargadas por el modelo: 0 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 0 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'final': 1}

##### 5. Esperas al agente

2 esperas · media 13,3 s · máxima 17,1 s · 0 agotadas (≥ 89 s).

| T+ | Espera (reloj) | Chat en curso |
|---|---|---|
| T+03:12 | 9,6 s | no |
| T+03:42 | 17,1 s | no |

##### Alertas abiertas al final

Ninguna.

### viento (R9, ejecución de los chats)
#### Evaluación · viento · 20261021-220740

**✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final**

- Modelo: `Qwen/Qwen2.5-14B-Instruct-AWQ` · temperature 0.0 · top_p 1.0 · top_k -1 · repetition_penalty 1.05 · max_tokens 800
- `guided_mode`: False · esperar al agente: True · velocidad: 16.0× · duración en reloj: 43 s
- Ayudas al modelo: tool_choice = required · última iteración solo con las respuestas: sí · checks obligatorios: sí · guardrail de coherencia: sí · hechos calculados: sí

##### 1. Anomalías y fallos

| Etiqueta | Tipo | Ventana | Primera detección | Retraso detección | Primera alerta aceptada (conf.) | Retraso diagnóstico (sim / reloj) | Cadenas | Veredicto |
|---|---|---|---|---|---|---|---|---|
| A1 | wind | T+01:35–T+02:30 | ROUTE_DEVIATION T+01:46 | 11,0 s | WIND T+01:46 (0.85) | 0,3 s / 13,8 s | 1 | ✅ |

##### 2. Respuesta a cada detección

| T+ | Aviso | Regla | Fuente | Detección | Respuesta | Causa atribuida | ✔ | Latencia (reloj) | Nota |
|---|---|---|---|---|---|---|---|---|---|
| T+01:46 | R | ROUTE_DEVIATION | — | det-0001 | alerta ai-0002 | WIND | ✅ | 13,8 s |  |
| T+02:36 | C | ROUTE_DEVIATION | — | det-0001 | cierre ai-0002 | — | ✅ | 4,1 s |  |

##### 3. Falsas alarmas

Ninguna.

##### 4. Agente

###### chat-monitor
- Invocaciones: 2 (2 con LLM, 0 deterministas) · iteraciones: 2 · llamadas al LLM: 2
- Tokens: prompt 2025, completion 132 · **máximo de prompt en una llamada: 1045**
- Latencia por llamada: media 1,6 s, p50 1,3 s, máx. 1,9 s
- Llamadas por tool: ninguna
- Skills cargadas por el modelo: 0 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 0 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'final': 2}
###### chat-report
- Invocaciones: 2 (2 con LLM, 0 deterministas) · iteraciones: 2 · llamadas al LLM: 2
- Tokens: prompt 3077, completion 268 · **máximo de prompt en una llamada: 1637**
- Latencia por llamada: media 2,5 s, p50 1,5 s, máx. 3,4 s
- Llamadas por tool: ninguna
- Skills cargadas por el modelo: 0 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 0 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'final': 2}
###### monitor
- Invocaciones: 2 (2 con LLM, 0 deterministas) · iteraciones: 7 · llamadas al LLM: 7
- Tokens: prompt 35776, completion 980 · **máximo de prompt en una llamada: 6335**
- Latencia por llamada: media 2,5 s, p50 0,8 s, máx. 6,1 s
- Llamadas por tool: close_alert: 1, get_events: 1, get_track_metrics: 2, load_skill: 1, publish_alert: 2
- Skills cargadas por el modelo: 1 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 1 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'done': 2}
###### report
- Invocaciones: 1 (1 con LLM, 0 deterministas) · iteraciones: 1 · llamadas al LLM: 1
- Tokens: prompt 1305, completion 595 · **máximo de prompt en una llamada: 1305**
- Latencia por llamada: media 9,7 s, p50 9,7 s, máx. 9,7 s
- Llamadas por tool: ninguna
- Skills cargadas por el modelo: 0 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 0 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'final': 1}

##### 5. Esperas al agente

1 esperas · media 13,8 s · máxima 13,8 s · 0 agotadas (≥ 89 s).

| T+ | Espera (reloj) | Chat en curso |
|---|---|---|
| T+01:46 | 13,8 s | no |

##### Alertas abiertas al final

Ninguna.

### nominal (R9)
#### Evaluación · nominal · 20261021-220504

**✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final**

- Modelo: `n/d` · temperature n/d · top_p n/d · top_k n/d · repetition_penalty n/d · max_tokens n/d
- `guided_mode`: n/d · esperar al agente: True · velocidad: 16.0× · duración en reloj: 28 s
- Ayudas al modelo: n/d

##### 1. Anomalías y fallos

| Etiqueta | Tipo | Ventana | Primera detección | Retraso detección | Primera alerta aceptada (conf.) | Retraso diagnóstico (sim / reloj) | Cadenas | Veredicto |
|---|---|---|---|---|---|---|---|---|
| — | sin anomalías ni fallos | | | | | | | |

##### 2. Respuesta a cada detección

| T+ | Aviso | Regla | Fuente | Detección | Respuesta | Causa atribuida | ✔ | Latencia (reloj) | Nota |
|---|---|---|---|---|---|---|---|---|---|
| — | sin detecciones | | | | | | | | |

##### 3. Falsas alarmas

Ninguna.

##### 4. Agente

###### report
- Invocaciones: 1 (1 con LLM, 0 deterministas) · iteraciones: 1 · llamadas al LLM: 1
- Tokens: prompt 1214, completion 439 · **máximo de prompt en una llamada: 1214**
- Latencia por llamada: media 7,2 s, p50 7,2 s, máx. 7,2 s
- Llamadas por tool: ninguna
- Skills cargadas por el modelo: 0 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 0 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'final': 1}

##### 5. Esperas al agente

Ninguna (el reproductor no esperó al agente).

##### Alertas abiertas al final

Ninguna.

### fallos (R9)
#### Evaluación · fallos · 20261021-220542

**❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 2 alertas abiertas al final**

- Modelo: `Qwen/Qwen2.5-14B-Instruct-AWQ` · temperature 0.0 · top_p 1.0 · top_k -1 · repetition_penalty 1.05 · max_tokens 800
- `guided_mode`: False · esperar al agente: True · velocidad: 16.0× · duración en reloj: 102 s
- Ayudas al modelo: tool_choice = required · última iteración solo con las respuestas: sí · checks obligatorios: sí · guardrail de coherencia: sí · hechos calculados: sí

##### 1. Anomalías y fallos

| Etiqueta | Tipo | Ventana | Primera detección | Retraso detección | Primera alerta aceptada (conf.) | Retraso diagnóstico (sim / reloj) | Cadenas | Veredicto |
|---|---|---|---|---|---|---|---|---|
| F1 | source_silent radar | T+02:00–T+03:00 | SOURCE_SILENT T+02:05 | 5,0 s | SENSOR_FAULT T+02:05 (0.6) | 0,2 s / 8,0 s | 1 | ✅ |
| F2 | gps_loss gps | T+04:05–T+04:50 | GPS_DEGRADED T+04:05 | 0,0 s | GPS_JAMMING T+04:05 (0.8) | 0,1 s / 8,6 s | 2 | ✅ |
| F3 | source_silent gps | T+05:00–T+05:12 | SOURCE_SILENT T+05:04 | 4,0 s | — | — / — | 1 | ❌ |
|  |  |  | ↳ det-0008 SOURCE_SILENT T+05:04 atribuido a **GPS_JAMMING** (esperado: SENSOR_FAULT) | | | | | ❌ |

##### 2. Respuesta a cada detección

| T+ | Aviso | Regla | Fuente | Detección | Respuesta | Causa atribuida | ✔ | Latencia (reloj) | Nota |
|---|---|---|---|---|---|---|---|---|---|
| T+02:05 | R | SOURCE_SILENT | radar | det-0001 | alerta ai-0002 | SENSOR_FAULT | ✅ | 8,0 s |  |
| T+03:00 | C | SOURCE_SILENT | — | det-0001 | cierre ai-0002 | — | ✅ | 2,2 s |  |
| T+04:05 | R | GPS_DEGRADED | gps | det-0003 | alerta ai-0008 | GPS_JAMMING | ✅ | 8,6 s |  |
| T+04:18 | R | SOURCE_DISCREPANCY | — | det-0004 | alerta ai-0011 | GPS_JAMMING | ✅ | 8,7 s |  |
| T+04:48 | U | SOURCE_DISCREPANCY | — | det-0004 | ack → ai-0011 | GPS_JAMMING | ✅ | 9,8 s |  |
| T+04:50 | R | ROUTE_DEVIATION | — | det-0006 | alerta ai-0017 (sustituye) | GPS_JAMMING | ✅ | 22,0 s |  |
| T+04:55 | C | GPS_DEGRADED | — | det-0003 | ack → ai-0017 · determinista | — | ✅ | 0,0 s |  |
| T+05:04 | R | SOURCE_SILENT | gps | det-0008 | alerta ai-0021 | GPS_JAMMING | ❌ | 16,8 s |  |
| T+05:12 | C | SOURCE_SILENT | — | det-0008 | cierre ai-0021 | — | ✅ | 3,0 s |  |
| T+05:17 | C | ROUTE_DEVIATION | — | det-0006 | ack → ai-0017 | — | ✅ | 7,1 s |  |
| T+05:20 | C | SOURCE_DISCREPANCY | — | det-0004 | ack → ai-0011 | — | ✅ | 5,6 s |  |

##### 3. Falsas alarmas

Ninguna.

##### 4. Agente

###### monitor
- Invocaciones: 10 (9 con LLM, 1 deterministas) · iteraciones: 40 · llamadas al LLM: 40
- Tokens: prompt 236323, completion 4102 · **máximo de prompt en una llamada: 8441**
- Latencia por llamada: media 2,1 s, p50 1,0 s, máx. 6,7 s
- Llamadas por tool: acknowledge_detection: 3, close_alert: 2, get_events: 9, get_track_metrics: 10, load_skill: 7, publish_alert: 9
- Skills cargadas por el modelo: 7 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 4 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'done': 9, 'deterministic': 1}
###### report
- Invocaciones: 1 (1 con LLM, 0 deterministas) · iteraciones: 1 · llamadas al LLM: 1
- Tokens: prompt 1738, completion 790 · **máximo de prompt en una llamada: 1738**
- Latencia por llamada: media 13,5 s, p50 13,5 s, máx. 13,5 s
- Llamadas por tool: ninguna
- Skills cargadas por el modelo: 0 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 0 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'final': 1}

##### 5. Esperas al agente

6 esperas · media 12,3 s · máxima 22,0 s · 0 agotadas (≥ 89 s).

| T+ | Espera (reloj) | Chat en curso |
|---|---|---|
| T+02:05 | 8,0 s | no |
| T+04:05 | 8,6 s | no |
| T+04:18 | 8,7 s | no |
| T+04:48 | 9,8 s | no |
| T+04:50 | 22,0 s | no |
| T+05:04 | 16,8 s | no |

##### Alertas abiertas al final

- ai-0011 GPS_JAMMING (high) de T+04:18: El GPS del dron ha perdido el fix y el dron se desvía de la ruta planificada.
- ai-0017 GPS_JAMMING (medium) de T+04:50: El GPS del dron ha recuperado el fix y el dron está volviendo a la ruta planificada.

### secuestro (R8; previa a R9)
#### Evaluación · secuestro · 20261021-212836

**✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final**

- Modelo: `Qwen/Qwen2.5-14B-Instruct-AWQ` · temperature 0.0 · top_p 1.0 · top_k -1 · repetition_penalty 1.05 · max_tokens 800
- `guided_mode`: False · esperar al agente: True · velocidad: 16.0× · duración en reloj: 50 s
- Ayudas al modelo: tool_choice = required · última iteración solo con las respuestas: sí · checks obligatorios: sí · guardrail de coherencia: sí · hechos calculados: sí

##### 1. Anomalías y fallos

| Etiqueta | Tipo | Ventana | Primera detección | Retraso detección | Primera alerta aceptada (conf.) | Retraso diagnóstico (sim / reloj) | Cadenas | Veredicto |
|---|---|---|---|---|---|---|---|---|
| A1 | hijack | T+05:35–T+06:20 | ROUTE_DEVIATION T+05:38 | 3,0 s | HIJACK T+05:38 (0.8) | 0,7 s / 7,5 s | 1 | ✅ |

##### 2. Respuesta a cada detección

| T+ | Aviso | Regla | Fuente | Detección | Respuesta | Causa atribuida | ✔ | Latencia (reloj) | Nota |
|---|---|---|---|---|---|---|---|---|---|
| T+05:38 | R | ROUTE_DEVIATION | — | det-0001 | alerta ai-0002 | HIJACK | ✅ | 7,5 s | no tratado como recuperación ✅ |
| T+05:41 | U | ROUTE_DEVIATION | — | det-0001 | ack → ai-0002 | HIJACK | ✅ | 8,0 s |  |
| T+07:21 | C | ROUTE_DEVIATION | — | det-0001 | cierre ai-0002 | — | ✅ | 3,9 s |  |

##### 3. Falsas alarmas

Ninguna.

##### 4. Agente

###### monitor
- Invocaciones: 3 (3 con LLM, 0 deterministas) · iteraciones: 11 · llamadas al LLM: 11
- Tokens: prompt 55649, completion 981 · **máximo de prompt en una llamada: 6221**
- Latencia por llamada: media 1,8 s, p50 1,0 s, máx. 4,9 s
- Llamadas por tool: acknowledge_detection: 1, close_alert: 1, get_events: 2, get_track_metrics: 3, load_skill: 2, publish_alert: 2
- Skills cargadas por el modelo: 2 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 1 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'done': 3}
###### report
- Invocaciones: 1 (1 con LLM, 0 deterministas) · iteraciones: 1 · llamadas al LLM: 1
- Tokens: prompt 1317, completion 649 · **máximo de prompt en una llamada: 1317**
- Latencia por llamada: media 10,9 s, p50 10,9 s, máx. 10,9 s
- Llamadas por tool: ninguna
- Skills cargadas por el modelo: 0 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 0 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'final': 1}

##### 5. Esperas al agente

2 esperas · media 7,8 s · máxima 8,0 s · 0 agotadas (≥ 89 s).

| T+ | Espera (reloj) | Chat en curso |
|---|---|---|
| T+05:38 | 7,5 s | no |
| T+05:41 | 8,0 s | no |

##### Alertas abiertas al final

Ninguna.

### demo a 1× (R7; previa a R8 y R9; sin esperar al agente; informativa)
#### Evaluación · demo · 20261021-204734

**⚠️ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 1 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final**

- Modelo: `Qwen/Qwen2.5-14B-Instruct-AWQ` · temperature 0.0 · top_p 1.0 · top_k -1 · repetition_penalty 1.05 · max_tokens 800
- `guided_mode`: False · esperar al agente: False · velocidad: 1.0× · duración en reloj: 556 s
- Ayudas al modelo: tool_choice = required · última iteración solo con las respuestas: sí · checks obligatorios: sí · guardrail de coherencia: sí · hechos calculados: sí

##### 1. Anomalías y fallos

| Etiqueta | Tipo | Ventana | Primera detección | Retraso detección | Primera alerta aceptada (conf.) | Retraso diagnóstico (sim / reloj) | Cadenas | Veredicto |
|---|---|---|---|---|---|---|---|---|
| A1 | wind | T+01:35–T+02:30 | ROUTE_DEVIATION T+01:46 | 11,0 s | WIND T+01:53 (0.85) | 7,8 s / 8,0 s | 1 | ✅ |
| A2 | gps_spoofing | T+02:48–T+03:42 | SOURCE_DISCREPANCY T+03:12 | 24,0 s | GPS_SPOOFING T+03:21 (0.85) | 9,4 s / 9,4 s | 1 | ⚠️ |
|  |  |  | ↳ det-0004 ROUTE_DEVIATION T+03:42 atribuido a **sin diagnóstico** (esperado: GPS_SPOOFING) | | | | | ❌ |
| A3 | hijack | T+05:35–T+06:20 | ROUTE_DEVIATION T+05:38 | 3,0 s | HIJACK T+05:45 (0.8) | 7,0 s / 7,1 s | 1 | ✅ |

##### 2. Respuesta a cada detección

| T+ | Aviso | Regla | Fuente | Detección | Respuesta | Causa atribuida | ✔ | Latencia (reloj) | Nota |
|---|---|---|---|---|---|---|---|---|---|
| T+01:46 | R | ROUTE_DEVIATION | — | det-0001 | alerta ai-0002 | WIND | ✅ | 8,0 s |  |
| T+02:36 | C | ROUTE_DEVIATION | — | det-0001 | cierre ai-0002 | — | ✅ | 2,8 s |  |
| T+03:12 | R | SOURCE_DISCREPANCY | — | det-0003 | alerta ai-0008 | GPS_SPOOFING | ✅ | 9,4 s |  |
| T+03:42 | R | ROUTE_DEVIATION | — | det-0004 | ack → sin alerta · fallback | sin diagnóstico | ❌ | 13,1 s |  |
| T+03:52 | C | SOURCE_DISCREPANCY | — | det-0003 | cierre ai-0008 | — | ✅ | 5,3 s |  |
| T+03:54 | C | ROUTE_DEVIATION | — | det-0004 | ack → sin alerta | — | ✅ | 1,1 s |  |
| T+05:38 | R | ROUTE_DEVIATION | — | det-0007 | alerta ai-0018 | HIJACK | ✅ | 7,1 s | no tratado como recuperación ✅ |
| T+05:41 | U | ROUTE_DEVIATION | — | det-0007 | ack → ai-0018 | HIJACK | ✅ | 16,6 s |  |
| T+07:21 | C | ROUTE_DEVIATION | — | det-0007 | cierre ai-0018 | — | ✅ | 2,4 s |  |

##### 3. Falsas alarmas

Ninguna.

##### 4. Agente

###### monitor
- Invocaciones: 8 (8 con LLM, 0 deterministas) · iteraciones: 32 · llamadas al LLM: 32
- Tokens: prompt 178342, completion 2645 · **máximo de prompt en una llamada: 9301**
- Latencia por llamada: media 1,8 s, p50 1,0 s, máx. 8,0 s
- Llamadas por tool: acknowledge_detection: 1, close_alert: 3, get_events: 7, get_track_metrics: 9, load_skill: 7, publish_alert: 5
- Skills cargadas por el modelo: 7 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 2 · recordatorios: 0 · fallbacks: 1 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'done': 7, 'max_iterations': 1}
###### report
- Invocaciones: 1 (1 con LLM, 0 deterministas) · iteraciones: 1 · llamadas al LLM: 1
- Tokens: prompt 1699, completion 79 · **máximo de prompt en una llamada: 1699**
- Latencia por llamada: media 1,4 s, p50 1,4 s, máx. 1,4 s
- Llamadas por tool: ninguna
- Skills cargadas por el modelo: 0 · precargadas por el modo guiado: 0
- JSON inválido: 0 · rechazos de guardrails: 0 · recordatorios: 0 · fallbacks: 0 · cierres de fallback: 0 · evidencias no vistas: 0
- Cómo terminaron: {'final': 1}

##### 5. Esperas al agente

Ninguna (el reproductor no esperó al agente).

##### 6. Sin esperar al agente

- Latencia de respuesta en tiempo simulado: media 10,7 s, máxima 16,5 s
- Cola máxima al empezar una invocación: 0 · lotes de más de una detección: 1 · detecciones llegadas durante invocaciones: 0
- Desfase (`sim_time` al publicar − `as_of`): media 6,2 s, máximo 13,0 s

##### Alertas abiertas al final

Ninguna.

## 4. Informe y chats

### Informe de `demo` (R9, primera ejecución, tal cual lo generó el agente)
```
# Informe de la misión MSN-DEMO

**Escenario:** Demo · **Duración:** 09:16 · **Misión completada:** sí (regreso a base)

## Resumen
La simulación demo se completó satisfactoriamente en T+09:16. Se registraron tres anomalías significativas: desviación de ruta por viento, spoofing del GPS y secuestro del dron. Todas fueron identificadas y resueltas por el monitor.

## Cronología
| Tiempo | Fuente | Qué pasó |
|---|---|---|
| T+00:00 | Despegue | Inicio de la misión |
| T+01:46 | Detector | Desviación de ruta por viento (det-0001) |
| T+03:12 | Detector | Discrepancia de fuente (det-0003) |
| T+03:42 | Detector | Desviación de ruta (det-0004) |
| T+05:38 | Detector | Secuestro del dron (det-0007) |
| T+03:12 | Monitor | Alerta de viento (ai-0002) |
| T+03:12 | Monitor | Alerta de spoofing del GPS (ai-0011) |
| T+05:38 | Monitor | Alerta de secuestro del dron (ai-0018) |
| T+03:12 | Monitor | Cierre de alerta de viento (ai-0002) |
| T+04:48 | Monitor | Cierre de alerta de spoofing del GPS (ai-0011) |
| T+07:59 | Monitor | Cierre de alerta de secuestro del dron (ai-0018) |

## Anomalías
### Viento (baja, confianza 0.85)
- **Cuándo:** detección a T+01:46, alerta a T+03:12 (retraso de diagnóstico: 1 min 26 s).
- **Qué se vio:** Desviación de ruta detectada por el detector de reglas (det-0001).
- **Evidencias:** det-0001.
- **Estado:** cerrada a T+03:12.

### Spoofing del GPS (media, confianza 0.85)
- **Cuándo:** detección a T+03:12, alerta a T+03:12 (retraso de diagnóstico: 0 s).
- **Qué se vio:** Discrepancia de fuente detectada por el detector de reglas (det-0003) y desviación de ruta (det-0004).
- **Evidencias:** det-0003, det-0004.
- **Estado:** cerrada a T+04:48.

### Secuestro del dron (alta, confianza 0.85)
- **Cuándo:** detección a T+05:38, alerta a T+05:38 (retraso de diagnóstico: 0 s).
- **Qué se vio:** Desviación de ruta detectada por el detector de reglas (det-0007).
- **Evidencias:** det-0007.
- **Estado:** cerrada a T+07:59.

## Valoración del monitor
Las alertas emitidas por el monitor estuvieron bien fundamentadas por los datos observados. La alerta de viento fue la única que tuvo un retraso de diagnóstico, pero aún así fue identificada y resuelta correctamente. Las demás alertas fueron emitidas casi inmediatamente después de las detecciones correspondientes.

## Recomendaciones
1. Mejorar la velocidad de respuesta del monitor ante las detecciones de desviación de ruta para reducir el retraso de diagnóstico.
2. Realizar pruebas adicionales para asegurar que el monitor pueda manejar múltiples tipos de anomalías simultáneamente.

## Limitaciones
Los datos son simulados y el monitor solo tenía acceso a la información disponible hasta cada instante de tiempo. No se pudieron verificar todas las condiciones externas durante la simulación.
```
El informe no usa tools (el módulo le inyecta el resumen del vuelo, las alertas con sus cadenas y las detecciones) y sale con la estructura de la skill en 10–17 s. Sigue siendo **poco crítico**: valora al monitor sin dudas. El informe de `viento` (misma configuración):
```
```markdown
# Informe de la misión MSN-VIENTO

**Escenario:** Viento · **Duración:** 07:43 · **Misión completada:** sí (regreso a base)

## Resumen
El dron completó su misión de vuelo en condiciones de viento, alcanzando cuatro waypoints planificados. Se registró una desviación de ruta debido al viento, pero el monitor identificó y alertó oportunamente sobre esta anomalía.

## Cronología
| Tiempo | Fuente | Qué pasó |
|---|---|---|
| T+00:00 | Misión | Despegue desde la base |
| T+01:46 | Detector | Detección de desviación de ruta (ROUTED_DEVIATION) |
| T+01:46 | Monitor | Alerta por viento (WIND) |
| T+03:40 | Monitor | Cierre de la alerta por viento |
| T+07:43 | Misión | Regreso a la base |

## Anomalías
### Desviación de ruta por viento (low, confianza 0.85)
- **Cuándo:** Detección a T+01:46, alerta a T+01:46 (retraso de diagnóstico: 0 s).
- **Qué se vio:** El dron experimentó una desviación de ruta entre T+01:46 y T+02:36, que fue detectada por el sistema de detección.
- **Evidencias:** Id principal: det-0001.
- **Estado:** Cerrada a T+03:40.

## Valoración del monitor
El monitor identificó correctamente la desviación de ruta causada por el viento y generó una alerta apropiada. La alerta fue emitida inmediatamente después de la detección, lo que demuestra una rápida reacción del sistema.

## Recomendaciones
1. Continuar monitoreando las condiciones meteorológicas antes de iniciar misiones para anticipar posibles desvíos de ruta.
2. Realizar evaluaciones periódicas de la precisión de las herramientas de detección y corrección de ruta.

## Limitaciones
Los datos utilizados son de simulación, por lo que la validez práctica puede variar. Además, el monitor solo tenía acceso a los datos disponibles hasta cada momento, lo que limita su capacidad de anticipación.
```

Este informe resume la misión, describe la anomalía detectada y valorada por el monitor, y proporciona recomendaciones basadas en los datos observados durante la simulación.
```

### Chats (`--ask`, ejecución `viento/20261021-220740`, con `chat.tools_enabled: false`)
```

== viento (a 16×) ==
T+01:46  RAISED   ROUTE_DEVIATION     -        30.5/30 m      [medium] La posición del GPS se aleja 30,5 m de la ruta planificada
T+01:46  ALERTA   ai-0002 WIND low conf 0.85 ← det-0001: Desviación de ruta por viento

[T+02:30] 👤 monitor: ¿Por qué crees que es viento? Resume en tres frases.
T+02:36  CLEARED  ROUTE_DEVIATION     -        det-0001
🤖 monitor: El GPS y el radar muestran una desviación de la ruta planificada. La velocidad media del viento es de 3.9 m/s con una racha máxima de 9.7 m/s. Esta condición meteorológica está empujando al dron en la dirección de la deriva, lo cual coincide con la desviación observada.
   (sin tools)

[T+03:20] 👤 monitor: ¿Qué alertas hay abiertas ahora mismo?
🤖 monitor: Hay una alerta abierta:
- ai-0002 WIND (low, confianza 0.85) a T+01:46, abierta: «Desviación de ruta por viento».T+03:40  CIERRE   ai-0002 ← det-0002: La desviación del dron respecto a la ruta planificada ha disminuido y GPS y radar coinciden. GPS_deviation_from_plan_m: {'mean': 40.0, 'max': 53.0, 'trend': 'decreasing'}. Radar_deviation_from_plan_m: {'mean': 40.3, 'max': 60.7, 'trend': 'decreasing'}. GPS_radar_distance_m: {'mean': 6.8, 'max': 13.4, 'trend': 'stable'}. GPS_radar: {'disagreed': False}

   (sin tools)
T+07:43  INFORME  1970 caracteres, 1 alertas

[T+07:43] 👤 report: ¿Qué pasó en esta misión y cómo lo hizo el monitor?

[T+07:43] 👤 report: ¿Hubo alguna alerta dudosa?
🤖 report: En esta misión, el dron completó su vuelo en condiciones de viento, alcanzando los waypoints planificados. Durante la misión, se registró una desviación de ruta debido al viento, pero el monitor identificó y alertó oportunamente sobre esta anomalía:

- A las T+01:46, el monitor detectó una desviación de ruta y generó una alerta por viento (WIND) debido a las condiciones meteorológicas notables.
- La alerta fue mantenida hasta T+03:40, cuando se confirmó que la situación había normalizado y la alerta fue cerrada.

El monitor actuó rápidamente y de manera precisa en la identificación de la anomalía, lo que permitió mantener la seguridad y eficacia de la misión.
   (sin tools)
🤖 report: No hubo ninguna alerta dudosa en esta misión. La única alerta generada fue la ai-0002 WIND (alerta por viento), la cual fue abierta y cerrada de manera adecuada y sin dudas. El monitor identificó correctamente la desviación de ruta causada por el viento y generó la alerta apropiadamente sin generar falsos positivos.
   (sin tools)
✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final
→ /home/coliva/poc-ai-monitor/runs/viento/20261021-220740/eval.md
-- viento: 1 detecciones abiertas (43 s de reloj)
```
- Sin tools, los chats contestan en 1–3 s con datos correctos: el del monitor da la velocidad media y la racha del viento y la alerta abierta tal como están en el sistema; el del informe resume la misión y valora al monitor con lo que lleva en el prompt. (En la consola de `run.py` las respuestas se entrelazan con los avisos de la simulación porque corren en paralelo.)
- Límites: solo saben lo que llevan en el prompt (alertas con su razonamiento y los últimos hechos de `get_track_metrics`); no pueden consultar eventos. Con `chat.tools_enabled: true` (R8) podían, pero a veces escribían la llamada como texto y contestaban sin consultar.

## 5. Repetibilidad de `demo` (3 ejecuciones a 16× con la configuración final, congelada)
| Ejecución | Alertas (T+ · causa · tipo) |
|---|---|
| 1 (`20261021-215855`) ✅ 3/3 anomalías y fallos diagnosticados | T+01:46 WIND (nueva); T+03:12 GPS_SPOOFING (nueva); T+03:42 GPS_SPOOFING (sustituye); T+05:38 HIJACK (nueva) |
| 2 (`20261021-220057`) ✅ 3/3 anomalías y fallos diagnosticados | T+01:46 WIND (nueva); T+03:12 GPS_SPOOFING (nueva); T+03:42 GPS_SPOOFING (sustituye); T+05:38 HIJACK (nueva); T+05:41 HIJACK (sustituye) |
| 3 (`20261021-220252`) ✅ 3/3 anomalías y fallos diagnosticados | T+01:46 WIND (nueva); T+03:12 GPS_SPOOFING (nueva); T+03:42 GPS_SPOOFING (sustituye); T+05:38 HIJACK (nueva); T+05:41 HIJACK (sustituye) |
- **Mismas causas y mismas cadenas en las tres** (una cadena por anomalía, sin fallbacks, sin alertas abiertas al final). **Mismos T+ de las alertas** (T+01:46, T+03:12, T+03:42, T+05:38); difieren **los T+ de los cierres** (el cierre del spoofing a T+04:28–04:48 y el del secuestro a T+07:59–08:08, por el tiempo de reloj que tarda el modelo en responder mientras el reproductor sigue) y **cómo se responde a la actualización del secuestro**: la ejecución 1 la reconoce (`acknowledge_detection` a `ai-0018`) y las 2 y 3 publican una `HIJACK` que sustituye a la anterior (`supersedes`); en los dos casos sigue habiendo una sola cadena.
- Comparado con las tres de R7 (una con el viento en fallback) y las tres de R8 (siempre mal la recuperación), R9 es estable. La regla excluyente de la recuperación es lo que lo hizo: ya no depende de que el modelo elija bien la causa.

## 6. Dos trazas resumidas
(Las trazas completas están en `results/trazas/` junto a este informe.)

**Recuperación del spoofing (`demo/20261021-215855`, inv-0004, T+03:42, `ROUTE_DEVIATION` det-0004):** el estado trae la línea «Alerta del GPS reciente… sí — ai-0008 GPS_SPOOFING (abierta). Si este aviso es la recuperación del GPS: causa GPS_SPOOFING, supersedes ai-0008». El modelo carga `route-deviation`, pide `get_track_metrics` (`gps_radar.disagreed` true, `gps_max_step_m` 67,9), salta a `source-discrepancy` (dos `load_skill`; el segundo contesta «Ya tienes cargada…»), vuelve a mirar el enlace y publica `GPS_SPOOFING` severidad *alta* sin `supersedes` con `checks.link_anomalous: null`. **El guardrail lo rechaza con dos frases**: «`checks.link_anomalous = null` no coincide con los eventos de enlace que has pedido (false)» y «Es la recuperación del GPS_SPOOFING de ai-0008: publica cause GPS_SPOOFING, severity medium y supersedes ai-0008». El modelo corrige las dos cosas en la llamada siguiente y la alerta sale (`ai-0011`, una cadena). 9 iteraciones, 14,6 s, ningún fallback. En R8 (sin la regla excluyente) el mismo punto salía mal en las tres ejecuciones.

**F2 de `fallos` (pérdida de GPS, `fallos/20261021-220542`, configuración congelada):** `GD → SD → SD actualizado → RD`. `GPS_DEGRADED` → `GPS_JAMMING` ✅ (`ai-0008`, 8,6 s); la discrepancia posterior → `GPS_JAMMING` ✅ pero como **alerta nueva** (`ai-0011`, sin `supersedes`: no hay regla que lo exija para `SOURCE_DISCREPANCY`); la actualización se reconoce con `acknowledge_detection`; el `ROUTE_DEVIATION` de la recuperación (T+04:50) → `GPS_JAMMING` media con `supersedes ai-0008` ✅ (la regla excluyente toma la primera alerta del GPS abierta, `ai-0008`, y deja `ai-0011` como una **segunda cadena**: F2 sale ✅ pero con 2 cadenas). `SOURCE_SILENT` del GPS (F3) → `GPS_JAMMING` alta en vez de `SENSOR_FAULT` (primer intento rechazado por dos checks mal declarados, corregido al segundo) ❌. Al cerrarse la discrepancia y el RD en un mismo lote (T+06:48 y T+07:11), el modelo contesta con `acknowledge_detection` a las dos (el texto dice «la situación se ha normalizado») y por diseño se respeta: **quedan 2 alertas abiertas al final**.

## 7. Tabla de cambios en prompts, skills y herramientas (fichero · cambio · por qué · efecto)
Rondas: R0 prompts de la Fase 2; R1–R4 con `tool_choice: auto`; R5–R6 con `required`; R7 con hechos calculados, `checks` y guardrail de coherencia.
| Fichero | Cambio (ronda) | Por qué | Efecto |
|---|---|---|---|
| `monitor_objective.md` | Secciones `batch`/`raised`/`updated`/`cleared`/`reminder` y marcador `<<open_detections>>` (R0) | Contrato v0.6: cada aviso tiene respuesta | El modelo conoce las cuatro respuestas |
| `monitor_objective.md` | Recordatorio «un texto no cuenta como respuesta» (R1–R2; una versión que citaba «un JSON escrito dentro de tu mensaje» empeoraba el formato) | Que llame a la tool tras un texto | Sin efecto (con `required` ya no hace falta) |
| `monitor_objective.md` | La detección en una línea, sin bloque ```` ```json ```` (R3) | El bloque cebaba respuestas en ```` ```json ```` | Banco, con el prefijo del sistema: primer paso 5/8 → 7/8 |
| `monitor_objective.md` | Sin `event_id` en el JSON de la detección (R7) | El modelo confundió `det-0002` con `det-0001` (secuestro R6, inv-0002) | Persisten confusiones de ids (fallos inv-0010) |
| `monitor_objective.md` | Sección `cleared`: ventana desde el inicio de la detección hasta ahora y una sola `get_track_metrics` (R7) | Pedía `since = until` (secuestro R6, inv-0003) | Funciona (fallos inv-0010/0011) |
| `monitor_system.md` | Reglas 7–8 (`acknowledge`, un problema una alerta); regla 10 «actúa llamando a las tools» y el prefijo «Cada paso de tu trabajo es una llamada a una tool» (R1–R3); «paso a paso, sin saltarte ninguno» (R6); nota de ids `det-…` (R7) | Estabilizar formato y orden | Mejora marginal con `auto`; con `required` irrelevante |
| `monitor_output.md` | Reescrito en prosa, sin lista de campos ni sintaxis `f(a, b)` (R3); línea sobre `checks` (R7) | La sección larga de campos empujaba a escribir el JSON en el texto (banco: decisión 0/3 con ella, 3/3 sin ella) | Con ella quitada, R3 viento ✅ por primera vez |
| `route-deviation/SKILL.md` | Recuperación del GPS, umbral de viento «notable» (R1); campo `wind` (R5); reordenada, proxy observable y ejemplos numéricos (R6); **reescrita corta sobre hechos y `checks`** (R7) | Plan §2; el modelo comparaba números mal («viento notable» con 1,7 m/s; «va contra el viento»…) | Ver apartados 3 y 6 |
| `source-discrepancy/SKILL.md` | Paso 0 (alerta del GPS ya abierta), mirar el fix antes de concluir spoofing, `SOURCE_SILENT` siempre aparte (R1); sin sintaxis `f(source="…")` (R4); **reescrita corta** (R7) | Plan §2; la sintaxis cebaba la llamada como texto | Sin efecto medible en R4 |
| `tools.json` | `acknowledge_detection`; `get_track_metrics` describe el viento; **`publish_alert.checks`** antes de `cause` (R7) | Contrato v0.6/v0.7 | vLLM genera las propiedades **en el orden del esquema** con `required` (5/5 en el banco: `detection_ids`, `checks`, `cause`…) |
| `agents.yaml` | `repetition_penalty` 1,05 y `top_k` (−1 monitor, 20 resto) explícitos; `tool_choice: required` solo en el monitor (R5); `final_tools`; interruptores (R7); tiempos 45/30 s | Ver apartado 8 | Ver «Ayudas» |
| Motor | El resultado de `load_skill` se entrega como texto y no como JSON entrecomillado (R2) | Error mío | No cambió el fallo |
| `monitor_objective.md` y las skills | Línea fija «Alerta del GPS reciente (…): sí — ai-XXXX CAUSA» / «no» en el estado; `route-deviation` (paso 2) y la regla de `checks.gps_alert_recent` remiten a ella (R8) | R7: el modelo declaraba `gps_alert_recent: false` con la alerta abierta (demo inv-0004) | Los checks se declaran bien en R8 (no hay rechazos por esto); el fallo de la recuperación sigue |
| `tools.json` | `evidence_event_ids` justo detrás de `confidence`; su descripción dice dónde van y cuántos (R8) | Con `required`, vLLM respeta el orden pero no obliga a incluir los campos obligatorios: R7 `viento/205814` (inv-0001) tuvo 5 rechazos idénticos por `evidence_event_ids` ausente, al final del objeto | R8: 1 rechazo en `secuestro`, ninguno por este campo en `viento` |
| Guardrails (`guardrails.py`) | Mensajes de rechazo en español y accionables («Falta `evidence_event_ids`: pon ahí, no en la explicación, de 2 a 6 ids…»); «Es la misma llamada que antes…» si repite; `publish_alert` solo con detecciones del lote pendiente (R8) | El 14B repetía llamadas idénticas; confundía ids | Los mensajes se entienden; no cambian al modelo cuando se atasca (spoofing inv-0003) |
| Motor / `Toolbox` | `load_skill` repetido devuelve «Ya tienes cargada la skill X (más arriba)…» (R8) | R7: tres `load_skill` seguidos de la misma skill (demo inv-0004) | Menos iteraciones desperdiciadas |
| `agents.yaml` | `max_iterations: 12` (R8); `max_invocation_s: 60` | 5 de los 6 fallbacks de R7 eran por agotar las 8 iteraciones de forma evitable | 0 fallbacks en las 3 `demo` de R8 |
| Informe y chats | Informe **sin tools** con los datos inyectados (`report_system.md`, `report_objective.md`); estado actual en el sistema de los chats (R8) | R7: informe ilegible con `auto`; chat que contesta sin mirar las alertas | Informe legible; chat acierta las alertas abiertas |
| `route-deviation/SKILL.md` | Paso 2 «manda sobre todo lo demás»: la causa válida es la que dice la línea del estado; la rama `HIJACK` por rumbo frente al waypoint solo si no hay alerta del GPS reciente (R9) | En R8 la recuperación salía como `GPS_JAMMING`/`HIJACK` pese a la línea del estado | Con la regla excluyente del guardrail, `demo` 3/3 en las tres ejecuciones |
| `monitor_objective.md` | La línea del estado añade «Si este aviso es la recuperación del GPS: causa X, supersedes ai-XXXX» (R9) | Que el modelo vea qué publicar antes de equivocarse | El rechazo del guardrail dice lo mismo; el modelo corrige en una llamada |
| `tools.json` | `detection_ids` (publish_alert, acknowledge_detection) y `alert_id` (close_alert) dejan de ser obligatorios (R9) | El modelo confundía ids de detecciones abiertas con las pendientes (spoofing R8 inv-0003) | Sin rechazos por ids en R9 |
| Guardrails y motor | Recuperación excluyente; ids que rellena el módulo con rechazo que indica el correcto; corte tras la segunda repetición de una llamada rechazada (R9) | R8: diez llamadas idénticas rechazadas hasta agotar las 12 iteraciones | El corte no se ha activado nunca con el LLM real en R9; está probado con el falso |
| `agents.yaml` y chats | `chat.tools_enabled: false`; prompts `chat_*_system_notools.md` (R9) | Con tools y `auto` los chats escribían la llamada como texto | Chats de 1–3 s sin llamadas fallidas |

## 8. Tiempos, muestreo y vLLM
- **Tiempos (`monitor`), configuración congelada (12 iteraciones):** `max_invocation_s: 60`, `llm_timeout_s: 30`. Medidos con 38 invocaciones del monitor con LLM (spoofing, tres `demo`, `fallos` y `viento`): media 8,9 s, p50 8,6 s, **p95 17,1 s**, máx. 22,0 s; por llamada: media 2,1 s, máx. 6,7 s; hasta 10 iteraciones (la media es 4,3). Con R8 (36 invocaciones): p95 16,6 s, máx. 21,1 s; con R7 (8 iteraciones, 51 invocaciones): p95 17,7 s, máx. 34,0 s. Condición del plan: `max_invocation_s + 15 < WAIT_AGENT_TIMEOUT_S` (60 + 15 = 75 < 90 ✓, no hizo falta tocar la plataforma). Informe: 7–17 s (una llamada, 440–1.000 tokens generados; `max_invocation_s: 240`). Chats sin tools: 1–3 s. Medido con las invocaciones de varios escenarios, no con la misma petición repetida.
- **Muestreo (explícito en cada petición):** monitor `temperature 0`, `top_p 1.0`, `top_k −1`, `repetition_penalty 1.05`, `max_tokens 800`, `tool_choice required`; informe y chats `temperature 0.7`, `top_p 0.8`, `top_k 20`, `repetition_penalty 1.05` (sin tools no se envía `tool_choice`). `repetition_penalty` 1,0 con temperatura 0 (decodificación voraz) dio un bucle de repetición (spoofing R4, inv-0001); 1,05 es el valor del `generation_config.json` del modelo. Confirmado en ese fichero (`~/.cache/huggingface/hub/models--Qwen--Qwen2.5-14B-Instruct-AWQ`): `temperature` 0,7, `top_p` 0,8, `top_k` 20, `repetition_penalty` 1,05.
- **vLLM (no tocado):** RTX PRO 5000 Blackwell de 24 GB; caché de prefijo activa (3.920 de 3.929 tokens acertados en la 2.ª petición); 63.312 tokens de caché KV (concurrencia máxima de 1,93 a 32.768 tokens); sin `--enforce-eager` ni `--quantization`; `VLLM_USE_FLASHINFER_SAMPLER=0`. Prompt máximo medido en R9: 9.178 tokens.

## 9. Ayudas al modelo añadidas en esta fase
Cada ayuda tiene un interruptor en `agents.yaml` (`monitor.*`, todos activados). `eval.md` anota las activas en su cabecera. «Qué medir» = qué comparar en los `eval.md` de los seis escenarios al apagarla.
| Ayuda | Problema que resolvía (ronda y traza) | Interruptor | Qué medir para poder quitarla |
|---|---|---|---|
| `tool_choice: required` en el monitor | Con `auto` el 14B escribía la llamada a `publish_alert` como texto en un bloque ```` ```json ```` (R1–R4: de 16 invocaciones, 11 acabaron en texto y fallback; trazas `viento_R4`, `spoofing_R4`). Banco: 10/32 llamadas reales con `auto`, 32/32 con `required` | `monitor.tool_choice` (`required` \| `auto`) | Invocaciones que acaban en `text` y fallbacks; llamadas escritas como texto en `calls[].content` de la traza |
| Última iteración solo con las tres respuestas | Con `required` el modelo encadena tools de datos hasta el tope (banco: 12 `get_events`, 5 `get_track_metrics` en 32 puntos de decisión; fallbacks `max_iterations`) | `monitor.final_iteration_response_tools_only` | Invocaciones que acaban en `max_iterations` |
| Hechos calculados en `get_track_metrics` | R5–R6: el modelo llamaba «notable» a un viento de 1,7 m/s, decía que la deriva «va contra el viento» y concluía `WIND` (trazas `secuestro_R6` inv-0001, `spoofing_R6` inv-0002) | `monitor.computed_facts` | Aciertos de causa sin `notable`/`with_drift`/`disagreed`/`gps_max_step_m` (el módulo quita esos campos al modelo, pero los conserva para los checks) |
| `checks` obligatorios en `publish_alert` | R5–R6: el modelo se saltaba los pasos de la skill (no miraba el enlace, ni la recuperación). Declararlos antes de `cause` le obliga a pasar por cada comprobación | `monitor.require_checks` | Tasa de rechazos por checks y causas correctas sin la obligación (con ella apagada, `checks` es opcional en el esquema) |
| Guardrail de coherencia (incluida la **recuperación excluyente**, R9) | Rechaza checks que no coinciden con las tools y causas incoherentes (`WIND` sin viento notable, `HIJACK` sin mirar el enlace) y, desde R9, exige para la recuperación del GPS tras un engaño **la causa de la alerta del GPS reciente con `supersedes`** (R8: la recuperación salía mal en las tres `demo`; R9: bien en las tres, con el rechazo explícito corrigiéndolo en una llamada; traza `demo/20261021-215855` inv-0004). Antes ya funcionaba: corrigió `wind_with_drift` en `fallos` (inv-0003, 0004, 0006) y rechazó un `GPS_SPOOFING` con `gps_alert_recent` falso en `demo` (inv-0004) | `monitor.coherence_guardrail` | Rechazos por coherencia en la traza y causas erróneas publicadas sin él |
| Chats sin tools (`chat.tools_enabled: false`) | R8: con `auto` los chats escribían las llamadas como texto (```` ```json {"name": "get_events"…} ````) y contestaban sin consultar nada (traza `viento_R8_20261021-213737`); sin tools y con el estado, las alertas con su razonamiento y los últimos hechos en el sistema contestan bien en 1–3 s | `chat.tools_enabled` en `agents.yaml` (`true` = con tools) | Respuestas correctas de los chats con tools y `auto` (o con `required` y una tool de respuesta final) frente a las de sin tools; preguntas que necesitan un dato que no está en el prompt |
| Ids que rellena el módulo (R9) | El modelo confundía ids de detecciones abiertas con las pendientes y repetía la llamada (spoofing R8 inv-0003: 11 rechazos) | (sin interruptor: es contrato v0.8; el módulo solo rellena cuando no hay nada que elegir) | Rechazos por ids en la traza al volver a pedirlos |
| Informe sin tools (datos inyectados por el módulo) | R7: con `auto` el informe de `demo` salió ilegible (etiquetas `<tool_call>` como texto, traza `demo/20261021-204444`, agente `report`) | (sin interruptor: `tools`/`skills` del informe en `agents.yaml` y `report_*.md`; las versiones anteriores están en git) | Informe legible con tools y `required`, o con tools y `auto` en un modelo mejor; calidad del informe contra los `eval.md` |
| Línea «Alerta del GPS reciente» y estado en el sistema de los chats | El modelo declaraba mal `gps_alert_recent` y el chat no sabía qué había abierto | (sin interruptor: es parte del prompt de objetivo/sistema) | `gps_alert_recent` mal declarado en la traza al quitar la línea |
| Reescritura de prompts y skills para este modelo | Skills largas con pasos en pseudocódigo (`get_events(source=…)`) que cebaban llamadas como texto; umbrales que el modelo no aplicaba | (no tiene interruptor; en git están las originales) | Aciertos con las skills originales (último paso de «Liberar al agente») |

**No son ayudas** (se quedan con cualquier modelo): el corte de la invocación tras la segunda repetición de una llamada rechazada, los mensajes de rechazo accionables y el aviso de llamada repetida, `load_skill` que no reenvía una skill ya cargada, solo detecciones pendientes en `publish_alert`, `alerts_by_cause` por cadenas, el cierre determinista de los `DetectionCleared` que no cambian nada, que al modelo solo se le enseñe el `detection_id` (la correspondencia con los eventos la hace el módulo), `repetition_penalty` 1,05 y `top_k` explícitos, la garantía de respuesta y los fallbacks, las ventanas temporales del objetivo (`cleared`), el corte `until = as_of`, el índice local de evidencias y la entrega de las skills como texto.

## 10. Conclusiones para la extensión de IA del worker
**Qué falló con prompts y skills.** Con `Qwen2.5-14B-Instruct-AWQ` y `auto`, lo primero que falla no es el razonamiento sino el *formato*: en el paso de decisión el modelo escribe la llamada como texto y `message.tool_calls` llega vacío. Cuatro rondas de prompts y skills no lo arreglaron: cambios mínimos del texto voltean el resultado de contextos distintos de forma caótica (banco de reproducciones: 5/8 → 7/8 en el primer paso con variantes casi iguales; 0/3 → 3/3 en la decisión al quitar una sección del prompt), de modo que el ajuste fino de redacción es una lotería. Lo que sí ayudó, pero poco: quitar del prompt las listas de campos y la sintaxis `f(a, b)`, no citar el fallo («no escribas el JSON en tu texto» lo cebaba) y dar los resultados de las skills como texto.

**Qué arregló `required`.** Fijó el formato por completo (32/32 frente a 10/32 en el banco; 0 fallbacks por formato desde R5) y acortó las invocaciones (media 6–9 s frente a 19,5 s; p95 17 s frente a 37,5 s: sin 800 tokens de prosa antes de la llamada). Es la ayuda que más rinde por esfuerzo y la única imprescindible: sin ella, el monitor no es usable con este modelo. Necesita la restricción de la última iteración, o encadena tools de datos hasta el tope. ⚠️ **Con `required` no se garantizan los campos obligatorios**: vLLM respeta el orden de las propiedades del esquema pero no obliga a incluir todas (R7 `viento/205814`: cinco llamadas seguidas sin `evidence_event_ids`), de ahí que el esquema ponga los campos que el modelo se salta justo detrás de `confidence` y que los guardrails rechacen con mensajes que dicen qué falta. Y **solo sirve para agentes cuya respuesta es siempre una tool call**: el informe y los chats, en `auto`, seguían con el fallo; el informe se resolvió quitándole las tools (el módulo le entrega los datos) y los chats de la demo, también.

**Qué arreglaron los hechos calculados, los checks y los guardrails.** Los hechos calculados sacaron de la cabeza del modelo la aritmética de ángulos y las comparaciones con umbrales (el 14B llamaba «notable» a 1,7 m/s). Los checks le obligan a pasar por cada comprobación antes de elegir la causa, y el guardrail de coherencia las convierte en algo verificable: **detecta y corrige** declaraciones falsas y permite al operador ver por qué se decidió (`AnomalyDetected.checks`). Cerraron los errores de *datos*.

**Qué arregló la última pieza: mover la decisión al código.** El 14B no ejecuta de forma fiable un árbol de decisión de cinco o seis pasos aunque tenga todos los números delante: en la recuperación del GPS tras el spoofing tenía la alerta reciente, los hechos y los checks bien declarados y publicaba otra causa y sin `supersedes` (tres de tres en R8). Lo que lo arregló no fue otra redacción de la skill sino una **regla en el guardrail** que, cuando los hechos verificados dicen «recuperación», deja una sola causa válida y dice cuál: rechazo de una frase («Es la recuperación del GPS_SPOOFING de ai-0002: publica cause GPS_SPOOFING, severity medium y supersedes ai-0002»), corrección en la llamada siguiente y `demo` 3/3 en las tres ejecuciones. Es el patrón más rentable de toda la fase: **donde la decisión es mecánica, que la tome el código y el modelo solo redacte**; el guardrail enseña al modelo con el mensaje de rechazo, no hace falta que lo sepa de antemano.

**Qué no se arregló.** (1) `fallos`: el `SOURCE_SILENT` del GPS dentro de una cadena de jamming se diagnostica como `GPS_JAMMING` (F3), la discrepancia posterior a un `GPS_DEGRADED` abre otra alerta en vez de unirse a la cadena (2 cadenas en F2) y, cuando dos cierres llegan en un lote, el modelo contesta con `acknowledge_detection` aunque su texto diga que la situación se ha normalizado (quedan 2 alertas abiertas); son tres decisiones también mecánicas a las que les falta una regla como la de la recuperación. (2) Los chats con tools y `auto`, que escriben las llamadas como texto. (3) El informe valora al monitor sin espíritu crítico. (4) Hay variación entre ejecuciones idénticas (en la respuesta a las actualizaciones y en los T+ de los cierres; las causas y las cadenas de `demo` no varían).

**Qué haría falta.** (1) Seguir moviendo decisiones mecánicas al código (cadena única por episodio de GPS, `SOURCE_SILENT` con alerta del GPS abierta, cierre de una alerta cuando se cierran todas sus detecciones y el problema se ha normalizado) y reducir cada skill a una pregunta de sí/no por paso. (2) Un modelo que siga mejor instrucciones largas (ver «Liberar al agente» en `mejoras_futuras.md`: Qwen3 instruct; ⚠️ memoria y parser sin confirmar en 24 GB), quitando las ayudas de la más a la menos intrusiva y comparando los `eval.md`. (3) Para los chats con tools: `required` con una tool de «respuesta final», o un modelo mejor. (4) Mantener lo que no depende del modelo: contrato claro, respuesta garantizada a cada aviso, trazas completas y una evaluación contra etiquetas; fueron lo que permitió ver y medir todo lo anterior.

## 11. Decisiones nuevas y notas del revisor
**Decisiones mías (confírmame las que no te gusten):**
1. `gps_radar` es un objeto `{disagreed}` (y `null` si falta una fuente) y `gps_max_step_m` va en el primer nivel; `wind` calcula la dirección con la media vectorial ponderada por la velocidad.
2. `gps_max_step_m`: mayor *aumento* de la desviación del GPS entre dos muestras consecutivas a ≤ 1,5 s (el criterio de `recovery.py` mide «de < 15 a > 30»; el real es el aumento, que en las recuperaciones vale 68–90 m y en el secuestro 15,5 m).
3. `link_anomalous` lo calcula el módulo sobre los eventos de enlace que el modelo pidió: más de un `controller_id`, RSSI que varía más de 10 dB o latencia máxima > 2,5 × la mínima (en vuelo normal: ≤ 5,7 dB y ≤ 1,7 ×). Si todos los eventos son ya posteriores al cambio, no se detecta.
4. `gps_alert_recent` mira alertas en vigor de cada cadena: `GPS_SPOOFING`, `GPS_JAMMING`, o `SENSOR_FAULT` cuyas detecciones son del GPS (`GPS_DEGRADED`, `SOURCE_DISCREPANCY` o `SOURCE_SILENT` del GPS).
5. Mecánica del punto 4 de tu mensaje (el intento de solo texto no se guarda): solo actúa en agentes con recordatorio (el monitor). En el informe y los chats un texto sin tool calls es la respuesta final; no he inventado un recordatorio para ellos.
6. La skill `route-deviation` usa `gps_radar.disagreed` o `gps_max_step_m ≥ 30` en el paso de recuperación (el criterio de `recovery.py` aprobado se mantiene como referencia y en su prueba).
7. `recent_gps_alert` devuelve la primera alerta del GPS abierta; con dos cadenas del GPS abiertas a la vez (F2 de `fallos`), la regla excluyente apunta a la primera y deja la otra como segunda cadena.

**Revisor de contratos:** sin bloqueantes. Arreglado en R7: ids de eventos efímeros ya no valen como evidencia; `until` como texto («200») también se topa en `as_of`; la nota de `wind` nulo en calma total; el comentario de `agents.yaml` que citaba un fichero de `docs/` (regla 16); el docstring de `bus_client.py` y `ai-module-py/CLAUDE.md` sobre las suscripciones. **Notas del revisor atendidas en R8:** (a) `publish_alert` solo acepta `detection_ids` del lote pendiente (con al menos una sin respuesta) y la alerta lleva el `causation_id` de la detección a la que responde; (b) la regla 4 de `CLAUDE.md` y la definición precisan que el LLM nunca ve el dominio `sim` y que el módulo puede usar `SimulationStarted`/`SimulationReset`/`SimulationFinished` para reiniciarse y lanzar el informe; (c) `alerts_by_cause` cuenta cadenas (`eventos.md` §7 y prueba). **Siguen abiertas** (no pedidas): el informe y el chat del informe no topan `until` en `as_of` (razonable: la simulación ha terminado); un monitor lento a 16× sin esperar ve datos posteriores a su `as_of` en `get_my_alerts`/`get_mission_plan`; si el módulo arranca o reconecta a mitad de una ejecución, desconoce los ids anteriores y rechaza evidencias válidas.

## 12. Problemas (error literal) y ⚠️
- vLLM con `tool_choice: auto`: `message.tool_calls` vacío, `finish_reason: stop` y contenido ```` ```json\n{"name": "publish_alert", "arguments": {…}} ```` (traza `viento_R4` inv-0001, llamada 6).
- (R7, resuelto en R8 quitando las tools al informe) Informe de `demo` con `auto`: contenido `<tool_call>\n{"name": "load_skill", "arguments": {"name": "report-format"}}\n</tool_call> …` (traza `demo/20261021-204444`, agente `report`).
- Mi primer volcado del timeline en el reproductor se hacía una sola vez (`SimulationFinished`): perdía las últimas respuestas; ahora es incremental.
- `run.py` cortaba la segunda pregunta de un chat si la primera acababa antes (`--ask report:end`); ahora espera a todas las respuestas.
- Nada se atascó más de 30 minutos, salvo el fallo de formato del apartado 10 (varias horas de rondas de prompts, documentadas en `fase3_parcial.md`).
- ⚠️ **No confirmado en la documentación** (verificado ejecutando `llm_check`): streaming de tool calls con `hermes`, `finish_reason`, `top_k` −1/0, `timeout` de `AsyncOpenAI`, `extra_body`, `stream_options.include_usage`, `max_tokens`/`max_completion_tokens`, que con `required` el `content` quede vacío; y que vLLM genere las propiedades en el **orden del esquema** (probado en el banco: 5/5).
- ⚠️ **Con `tool_choice: required` vLLM no garantiza los campos obligatorios del esquema** (`viento/20261021-205814`, inv-0001: 5 llamadas seguidas a `publish_alert` sin `evidence_event_ids`, «Field required»): la documentación solo promete «una o más tool calls» cuyo formato «sigue el esquema»; en la práctica respeta el orden de las propiedades pero omite campos.
- R9: al aplicar «ids opcionales» a `acknowledge_detection` en un aviso de cierre, `alert_id` omitido se rellena con la alerta del cierre; eso significa que un `acknowledge_detection` en un cierre **siempre mantiene abierta esa alerta** (por diseño «se respeta»): el modelo lo usa a veces cuando quería cerrar (`fallos`, 2 alertas abiertas al final).

## 13. URLs consultadas (regla 8)
- vLLM, tool calling (flags de `hermes`, `tool_choice` `auto`/`required`/`none`): https://docs.vllm.ai/en/latest/features/tool_calling/ — sobre `required`: «`vLLM supports the tool_choice='required' option`» (`vllm>=0.8.3`); «it also uses structured outputs, so this is enabled by default and will work with any supported model»; «the model is guaranteed to generate one or more tool calls based on the specified tool list»; «the output format strictly follows the schema defined in the `tools` parameter». Con `auto`: «vLLM extracts tool calls from raw text, so arguments may occasionally be malformed».
- vLLM, structured outputs: https://docs.vllm.ai/en/latest/features/structured_outputs/ (backends `xgrammar` y `guidance`, por defecto `auto`; la relación con `required` está en la página de tool calling; latencia de compilación del autómata la primera vez).
- vLLM, `--generation-config` y parámetros extra de muestreo: https://docs.vllm.ai/en/latest/cli/serve/ y https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/
- SDK `openai` (Python 3.35.1): https://github.com/openai/openai-python
- Qwen3 y vLLM (para «Liberar al agente»): https://qwenlm.github.io/blog/qwen3/, https://huggingface.co/Qwen/Qwen3-14B-AWQ, https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507, https://qwen.readthedocs.io/en/latest/deployment/vllm.html, https://qwen.readthedocs.io/en/latest/framework/function_call.html, https://qwen.readthedocs.io/en/latest/getting_started/speed_benchmark.html

## 14. Pendientes documentados y qué queda
- **F3 de `fallos`** (`SOURCE_SILENT` del GPS dentro de la cadena del jamming): sale `GPS_JAMMING` en vez de `SENSOR_FAULT`. Pendiente documentado (decisión mecánica candidata a regla).
- **Dos cadenas en F2 de `fallos`** y **2 alertas abiertas al final** (cierres reconocidos con `acknowledge_detection`): pendientes; son decisiones mecánicas candidatas a regla.
- **Chats con tools** (`chat.tools_enabled: true`): escriben las llamadas como texto; la demo los usa sin tools.
- **El informe** es poco crítico con el monitor.
- **Notas del revisor sin atender:** el informe y el chat del informe no topan `until` en `as_of`; un monitor lento a 16× sin esperar ve datos posteriores a su `as_of` en `get_my_alerts`/`get_mission_plan`; si el módulo arranca o reconecta a mitad de una ejecución, desconoce los ids anteriores.
- **No repetidos con la configuración congelada:** `secuestro` suelto (R8 ✅; en `demo` ✅ ×3) y `demo` a 1× (R7).
- Fase 4 (web): `web/CLAUDE.md` describe ya la consola con `DetectionAcknowledged`, `AgentActivity` y el chat en streaming.
- Cualquier cambio a `agent-assets/` o `agents.yaml` rompe la huella de congelado: pregúntame antes.

## 15. Copias (reglas 13 y 15)
`docs/fases/`, los PNG de `runs/*/`, los `eval.md`/`eval.json`/`informe.md` de las ejecuciones y las trazas representativas (`results/trazas/`) en `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`; instantánea del código en `snapshots/fase3/` y la limpia en `snapshots-limpias/fase3/`, con las dos comprobaciones de la regla 15 vacías.

## 16. Mensaje de commit propuesto
```
feat: phase 3 - agents, guardrails, traces, evaluation and contracts v0.8

- contracts v0.8: DetectionAcknowledged, acknowledge_detection, computed facts in
  get_track_metrics (wind, gps_radar, gps_max_step_m), checks in publish_alert/AnomalyDetected and
  optional ids that the module fills in
- ai-module-py: agent engine (Chat Completions, hand-written tool loop), monitor with guaranteed
  response per detection, report, streaming chats, guardrails (evidence, coherence, exclusive GPS
  recovery), traces and evaluate.py; switches for every model aid in agents.yaml
- platform: incremental timeline dump; run.py with --wait-agent, --ask, --evaluate
- agent-assets: prompts and skills rewritten for the local model, tool_choice required for the
  monitor, report without tools (data injected by the module), sampling parameters explicit
- docs: phase report with conclusions for the worker AI extension; future work to free the agent
```
