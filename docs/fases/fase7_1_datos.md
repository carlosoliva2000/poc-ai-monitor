# Fase 7.1 · E3 parte A: ejecución y datos (27/10/2026)

Solo datos, sin conclusiones. Perfil `qwen3-14b-think` únicamente (no se ha ejecutado el 30B con razonamiento ni E2). Repositorio en `a17a835`; único cambio: tiempos de `model-profiles/qwen3-14b-think.yaml` (§2). Prompts, skills, `agents.yaml`, código, contratos y demás perfiles, sin tocar. Huella de `agent-assets` `e28d071e856efb09` (igual que en e0e1).

## Ejecuciones
```
run_matrix.py --profiles qwen3-14b-think --scenarios demo --reps 1 --id e3-medida --keep-server
run_matrix.py --profiles qwen3-14b-think --scenarios demo,faults,spoofing --reps 3 --id e3
```
- `e3-medida`: 1/1 `ok`, 354,7 s de reloj. `e3`: 9/9 `ok` (demo 386/314/367 s, faults 247/243/308 s, spoofing 121/191/163 s). Sin cuelgues de Windows, WSL ni vLLM, sin reintentos.
- Desviación de la orden: `e3-medida` se lanzó con `--keep-server` para que `e3` reutilizara el servidor (misma sección `server`; el lanzador lo reconoció, «already running»). `e3` no lo lleva y paró el servidor al terminar.
- Estado final: puerto 8000 libre, `nvidia-smi` 0 MiB.
- Ninguna condición de parada del paso 2 se cumplió: reloj 354,7 s (< 25 min), ninguna invocación llegó a `max_invocation_s` (máx. 65,4 s frente a 300 s), 0 cortes por longitud y 0 fallbacks en `e3-medida`.

## 1. Cómo se trata el razonamiento (comprobación sin el modelo)
- **Petición:** el perfil lleva `sampling.reasoning: true`; `agent/assets.py` lo envía en cada petición como `extra_body.chat_template_kwargs.enable_thinking = true` (visible en `sampling` de cada invocación de `llm_trace.jsonl`). `top_k`, `repetition_penalty` también en `extra_body`; temperatura, `top_p`, `presence_penalty` y `max_tokens` explícitos.
- **Lectura:** `agent/llm.py` lee `reasoning` (o `reasoning_content`) del mensaje (`reasoning_of`) y `usage.completion_tokens_details.reasoning_tokens`. En streaming el razonamiento no se entrega a `on_delta`.
- **Dentro del bucle de tools:** `LlmResponse.assistant_message()` añade el razonamiento al mensaje del asistente que se reenvía, con el campo `reasoning_content` (`REASONING_INPUT_FIELD`; en la fase 6 se comprobó que vLLM 0.31 lo pasa a la plantilla). Un mensaje de asistente con tool call conserva su razonamiento en `messages`.
- **Recordatorio (`engine.py`, líneas ~172-178):** si la respuesta es solo texto y `is_done()` es falso, y aún no se ha recordado, se incrementa `trace.reminders`, **no se guarda** ese intento en `messages` (queda solo en `calls` de la traza) y se añade un mensaje con `role: "user"`. La plantilla de Qwen3 solo muestra el razonamiento de los turnos posteriores al último mensaje de usuario, así que tras el recordatorio el razonamiento de las llamadas anteriores de esa invocación deja de verse (fase 6: +0 tokens).
- **Condición de espera:** `max_invocation_s` del monitor + 15 < espera de la plataforma: con los valores nuevos 99 + 15 = 114 < 330 (cumple; con los provisionales, 300 + 15 = 315 < 330). `agent/profiles.py` la valida al cargar el perfil.

## 2. Tiempos del perfil
Medidos en `e3-medida` (demo ×1; `experiments/e3-medida/runs/qwen3-14b-think/demo/r1/llm_trace.jsonl`):

| Agente | Llamada máx. | Invocación p95 | Tokens de razonamiento por llamada p50 / p95 / máx. |
|---|---|---|---|
| monitor (33 llamadas, 9 invocaciones) | 24,4 s | 65,4 s (según `compare`; 63,2 s con interpolación lineal) | 430 / 837 / 1115 |
| chat del monitor (2) | 7,1 s | 7,1 s | 228 / 239 / 240 |
| informe (1) | 16,0 s | 16,0 s | 290 |
| chat del informe (1) | 8,8 s | 8,8 s | 250 |

Latencia por llamada del monitor p50 / p95 / máx. = 8,9 / 15,9 / 24,4 s; por invocación p50 / p95 / máx. = 35,3 / 63,2 / 65,4 s. Cortes por longitud 0, timeouts 0, fallbacks 0, recordatorios 5 (inv-0001, 0004, 0005, 0008 y 0009, uno cada una), reloj 354,7 s.

| Parámetro | Provisional | Cálculo | Nuevo |
|---|---|---|---|
| `monitor.llm_timeout_s` | 90 | 24,4 × 1,5 = 36,6 | **37** |
| `monitor.max_invocation_s` | 300 | 65,4 × 1,5 = 98,1 | **99** |
| `chat_monitor.llm_timeout_s` / `max_invocation_s` | 120 / 240 | 7,1 × 1,5 = 10,7 | **11 / 11** |
| `chat_report.llm_timeout_s` / `max_invocation_s` | 120 / 240 | 8,8 × 1,5 = 13,2 | **14 / 14** |
| `report.llm_timeout_s` / `max_invocation_s` | 240 / 300 | 16,0 × 1,5 = 24 | **24 / 24** |
| `max_tokens` | 4000 (informe 6000) | sin cortes | sin cambio |
| `platform.wait_agent_timeout_s` | 330 | 99 + 15 < 330 | sin cambio |

Los nuevos se aplicaron a los cuatro agentes con la misma fórmula (la orden la da para «una llamada» y «la invocación»; en los agentes de una sola llamada la invocación es la llamada). Las ejecuciones de `e3` se hicieron con estos valores. Nota de margen, solo como dato: en `e3` la llamada máxima del monitor fue 28,5 s (tope 37), la del informe 24,0 s (tope 24; terminó `final`), la del chat del informe 13,0 s (tope 14) y la del chat del monitor 7,9 s (tope 11). Tiempos de `e3-medida` con los valores provisionales; los de `e3`, con los nuevos.

## 3. Think frente a t0
`qwen3-14b-t0` sale de `experiments/e0e1/` (mismas ejecuciones de la fase 7: demo, faults y spoofing × 3); `qwen3-14b-think` de `experiments/e3/`. Los dos se pasaron por `ai_module.compare` en una carpeta temporal que junta ambos manifiestos (copia: `experiments/think_vs_t0_compare.md` en la carpeta de resultados). Contadores = sumas de 3 repeticiones; tokens = media por ejecución.

| | demo t0 | demo think | faults t0 | faults think | spoofing t0 | spoofing think |
|---|---|---|---|---|---|---|
| Aciertos por etiqueta | A1 3 · A2 3 · A3 3 | A1 3 · **A2 1** · A3 2 | F1 3 · F2 3 · F3 0 | F1 3 · F2 3 · F3 0 | A1 3 | **A1 2** |
| Etiquetas con una sola cadena | 3/3 en las tres | A1 3 · **A2 1** · A3 3 | 3/3 en las tres | F1 3 · F2 3 · F3 3 | 3 | 3 |
| Falsas alarmas | 0 | 0 | 0 | 0 | 0 | 0 |
| Fallbacks | 0 | **1** (r1) | 0 | 0 | 0 | 0 |
| Alertas abiertas al final | 0 | **1** (r3) | 0 | **2** (r1, r3) | 0 | 0 |
| Frases que contradicen | 0 | 0 | 0 | 0 | 0 | 0 |
| No latinos (monitor / informe / chats) | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| Rechazos (llamadas) | 9 | 8 | 9 | 2 | 3 | 0 |
| Estabilidad | estable 3/3 | 1/3 iguales | estable 3/3 | 2/3 iguales | estable 3/3 | 2/3 iguales |
| Llamada del monitor p50 / p95 | 0,9 / 5,7 s | 8,6 / 18,3 s | 0,9 / 5,4 s | 8,7 / 16,9 s | 0,7 / 5,7 s | 9,2 / 18,2 s |
| Invocación p50 / p95 | 5,5 / 13,9 s | 30,3 / 66,0 s | 6,6 / 12,8 s | 19,4 / 62,0 s | 7,5 / 13,2 s | 37,7 / 72,9 s |
| Iteraciones por invocación p50 / p95 / máx. | 4 / 5 / 5 | 4 / 5 / 6 | 5 / 5 / 5 | 2,5 / 5 / 6 | 4 / 5 / 5 | 3 / 5,6 / 6 |
| Tokens prompt / respuesta / razonamiento | 143 944 / 3 791 / 0 | 167 293 / 19 118 / 14 889 | 169 311 / 3 750 / 0 | 120 817 / 13 576 / 10 853 | 56 996 / 1 886 / 0 | 55 821 / 7 400 / 5 939 |
| Tiempo de reloj por ejecución (media) | 102 s | 356 s | 101 s | 266 s | 63 s | 158 s |

Globales de `e3` (9 ejecuciones): timeouts 0; cortes por longitud 0; fallbacks 1; recordatorios 29; llamada del monitor p50 / p95 / máx. = 8,8 / 18,0 / 28,5 s (196 llamadas); invocación del monitor 19,6 / 63,8 / 72,9 s (72); tokens de razonamiento por llamada del monitor p50 / p95 / máx. = 421 / 940 / 1565; informe: llamada máx. 24,0 s, razonamiento p50 / máx. 452 / 611; chats: llamada máx. 13,0 s. Las latencias de t0 son las de `compare.md` de e0e1; la fila de iteraciones y el reloj salen de las trazas y de `manifest.json` (sin deterministas).

### Rechazos por tipo de mensaje (recuento por mensaje de error, como fase7.md §5)
| Mensaje | demo t0 | demo think | faults t0 | faults think | spoofing t0 | spoofing think |
|---|---|---|---|---|---|---|
| `link_anomalous = null` aunque pidió el enlace | 6 | 1 | 3 | 1 | 3 | 0 |
| «Nothing changes… use acknowledge_detection» | 3 | 0 | 6 | 0 | 0 | 0 |
| «This is the recovery from the GPS_… publish… supersedes» | 3 | 0 | 3 | 1 | 3 | 0 |
| «This invocation handles det-N, not det-M» (ids de otra detección) | 0 | 4 | 0 | 0 | 0 | 0 |
| `wind_notable` / `wind_with_drift` no coinciden con `get_track_metrics` | 0 | 2 | 0 | 0 | 0 | 0 |
| «WIND requires notable wind…» | 0 | 1 | 0 | 0 | 0 | 0 |
| «same call as before» / «repeats a rejected call for the second time» | 0 | 2 | 0 | 0 | 0 | 0 |
| «detection … is already in the open alert …» | 0 | 1 | 0 | 0 | 0 | 0 |
| Llamadas rechazadas (de `acknowledge_detection`) | 9 (0) | 8 (2) | 9 (0) | 2 (0) | 3 (0) | 0 |

## 4. Recordatorios
29 invocaciones del monitor con recordatorio en `e3` (todas 1 recordatorio), más 5 de `e3-medida` (demo r1: inv-0001, 0004, 0005, 0008 y 0009; mismo patrón). En 28 de las 29 de `e3`, el intento que lo provoca es la **iteración 2** (en `faults/r2 inv-0001` es la 4); es una respuesta con `content` que empieza por `<tool_call><tool_call>\n{"name": …` (etiqueta duplicada, JSON con una llamada válida en el texto), `tool_calls` vacío, `reasoning_tokens` = 1 y `finish_reason: tool_calls`. Ninguna terminó en `timeout`: las 29 acabaron en `done` (la única `repeated_rejection` es `demo/r1 inv-0006`, sin recordatorio).

En 22 de 29 el primer tool call tras el recordatorio es el mismo que había escrito el texto fallido; en 7 es otro (`faults` r1 inv-0003 y inv-0005, r2 inv-0003 y inv-0005, r3 inv-0003 y inv-0005, `spoofing` r3 inv-0002). **Llamadas de lectura ya hechas que se repiten después del recordatorio (misma tool y mismos argumentos que antes del intento fallido): 0 de 29.**

| Ejecución | Invocaciones con recordatorio (iteración 2 salvo indicación) |
|---|---|
| demo r1 | inv-0001, inv-0004, inv-0008, inv-0009 |
| demo r2 | inv-0001, inv-0004, inv-0005, inv-0008, inv-0009 |
| demo r3 | inv-0001, inv-0004, inv-0008, inv-0009 |
| faults r1 | inv-0001, inv-0003, inv-0004, inv-0005 |
| faults r2 | inv-0001 (**iteración 4**, texto = `publish_alert`), inv-0003, inv-0005 |
| faults r3 | inv-0001, inv-0003, inv-0004, inv-0005, inv-0006 |
| spoofing r1 | inv-0001 |
| spoofing r2 | inv-0002 |
| spoofing r3 | inv-0001, inv-0002 |

Primera tool del intento fallido, de todas: `get_track_metrics` (la mayoría), `get_events` (faults inv-0001/0003) y `publish_alert` (faults r2 inv-0001). Rutas: `experiments/e3/runs/qwen3-14b-think/<escenario>/r<k>/llm_trace.jsonl`.

## 5. Caracteres no latinos en el razonamiento
Contados sobre el campo `reasoning` de todas las llamadas de las 9 ejecuciones (cualquier carácter fuera de Latin, signos de puntuación, flechas, matemáticas y símbolos habituales):

| Ejecución | demo r1 | r2 | r3 | faults r1 | r2 | r3 | spoofing r1 | r2 | r3 |
|---|---|---|---|---|---|---|---|---|---|
| Caracteres no latinos en el razonamiento | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

(Resumido por escenario en la ejecución de comprobación: 0 en demo, 0 en faults, 0 en spoofing; igual que la métrica de salida, 0 / 0 / 0.) El razonamiento de `e0e1` no existe (t0).

## 6. Índice de trazas para el análisis
Ruta base `experiments/e3/runs/qwen3-14b-think/<escenario>/r<k>/llm_trace.jsonl` (copiadas en `trazas/fase7_1/`). T+ = tiempo de simulación de la invocación.

### Diferencias de resultado frente a t0
| Traza | inv | Qué pasa (una línea) |
|---|---|---|
| demo/r1 | inv-0005 (T+223) | `SOURCE_DISCREPANCY` tras A2: intenta `WIND` (rechazada: `wind_notable` no coincide) y publica `UNKNOWN` media como alerta nueva (2.ª cadena en A2; t0: una). |
| demo/r1 | inv-0006 (T+232) | `repeated_rejection` → **fallback**: `acknowledge_detection` y 3 `publish_alert` `GPS_SPOOFING` supersedes ai-0005 con ids de det-0004 en la invocación de det-0005 («This invocation handles det-0005, not det-0004»; «repeats a rejected call»). |
| demo/r1 | inv-0008 (T+338) | A3: publica `UNKNOWN` media tras cargar `route-deviation`; `HIJACK` solo en inv-0009 (T+342, supersedes ai-0008). |
| demo/r3 | inv-0005 (T+222) | A2: publica `UNKNOWN` media dos veces (2.ª cadena). |
| demo/r3 | inv-0006 (T+232) | `acknowledge_detection` dos veces sobre ai-0004 (una rechazada: ids de otra detección); la alerta de A2 queda abierta al final (1 abierta). |
| demo/r3 | inv-0009 (T+342) | A3 escalada: `acknowledge_detection` sobre ai-0008 (en vez de publicar); A3 ✅ por inv-0008 (`HIJACK`). |
| demo/r2 | — | 3/3 ✅, 1 cadena por etiqueta (única demo igual que t0). |
| faults/r1 | inv-0003 y inv-0004 (T+246/259) | F2: `SENSOR_FAULT` media y luego `GPS_JAMMING` alta supersedes ai-0003 (t0: `GPS_JAMMING`×3); sin `close_alert` hasta el final (1 abierta). |
| faults/r3 | inv-0003 y inv-0004 | Igual que r1 (`SENSOR_FAULT` → `GPS_JAMMING`); 1 abierta. |
| faults/r2 | inv-0003 (T+246) | F2 con `GPS_JAMMING` de salida y 1 cadena (igual que t0). |
| spoofing/r2 | inv-0001 (T+192) | A1: publica `SENSOR_FAULT` (t0: `GPS_SPOOFING`); inv-0002 (T+222) carga `route-deviation` y `source-discrepancy` y solo hace `acknowledge_detection`; cierra en inv-0004. |

### F3 en las tres repeticiones (❌ también en t0)
| Traza | inv | Qué pasa |
|---|---|---|
| faults/r1 | inv-0005 (T+288) a inv-0008 (T+305) | Detecciones del GPS mudo: solo `acknowledge_detection` sobre ai-0004 (`GPS_JAMMING`); no se publica alerta propia. |
| faults/r2 | inv-0004 (T+259), inv-0005, inv-0006, inv-0008 | Igual: solo `acknowledge_detection` (ai-0004), sin alerta propia. |
| faults/r3 | inv-0006 (T+291) | Carga `route-deviation`, publica `GPS_JAMMING` media y luego `GPS_JAMMING` supersedes ai-0004; inv-0008 `acknowledge_detection` sobre ai-0006. |

### Otros fallos y casos a mirar
| Traza | inv | Qué pasa |
|---|---|---|
| demo/r1 | inv-0001, 0004, 0008, 0009 | Recordatorio en cada una (§4). |
| faults/r2 | inv-0001 (T+125) | Único recordatorio en iteración 4 (el texto fallido era un `publish_alert`) y 1 rechazo. |
| faults/r3 | inv-0006 | 1 rechazo y recordatorio (única invocación con ambas en faults). |
| spoofing/r3 | inv-0002 | Recordatorio y luego `acknowledge_detection` (primera tool distinta a la del texto fallido). |

Estabilidad, según `compare.md`: demo 1/3 iguales (r2 distinta de r1 y r3), faults 2/3 (r2 distinta: F2 solo `GPS_JAMMING`), spoofing 2/3 (r2 distinta).

## 7. Límites de lo anterior
- `e3-medida` es una sola ejecución; los tiempos del perfil son de ahí (n = 33 llamadas de monitor). En `e3` la llamada máxima del informe tocó su tope (24,0 de 24 s).
- t0 es determinista y se tomó de e0e1; think muestrea (temperatura 0,6), así que 3 repeticiones sí varían.
- «Caracteres no latinos» en el razonamiento se contó con un filtro propio (rango Unicode), distinto del de la métrica del evaluador, que solo mira la salida.
- Los números de iteraciones y de reloj de t0 se han calculado a mano de las trazas/manifiestos; el resto, de `compare.py`.
- Sin análisis, sin conclusiones ni recomendaciones (parte B).
