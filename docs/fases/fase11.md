# Fase 11 · Agente: modo guiado y memoria A (29/10/2026)

Escrito para: Carlos, que revisa la fase y decide los valores por defecto. Contratos **sin cambios**. Ningún valor por defecto cambia: los dos interruptores nuevos están apagados (`guided_skills: false`, `memory: per_detection`).

## Resumen

| | Modo guiado | Memoria A |
|---|---|---|
| Regresión frente a e10 | **ninguna** | **sí**: 1 alerta abierta al final de `faults`, en las 3 repeticiones extra |
| Tokens de prompt (6 vuelos) | −11 % | ×2,2 (1,01 M frente a 0,46 M) |
| Iteraciones p50 | 4 → 3 | 4 → 4 |
| Recomendación | activarlo es seguro; ganancia pequeña | **no activarla** tal como está |

Por la regla del plan (paso 3 solo si los pasos 1 y 2 salen sin regresión), **no se ejecutó `e11-juntas`**. Tampoco el subexperimento de YaRN: en la memoria A el pico de contexto fue 24,5 k de 32 768 y no hubo ninguna compactación (la primera versión compactó una vez, nivel A, con pico de 25,8 k).

## Paso 1 · Modo guiado

### 1.1 Medida previa (sin ejecutar nada): `experiments/e11-skills-previo.md`
Sobre las trazas de e10, e8-base y, como contraste, e0e1/actual (Qwen2.5). Hecha con `python -m ai_module.monitor_usage`.
- En e10 y e8-base el modelo carga la skill que toca el **100 %** de las veces y siempre **antes de decidir**. En Qwen2.5 (e0e1) el 96–100 %. No hay margen para que el modo guiado mejore la carga.
- La única petición de una skill inexistente (`source-silence`) aparece en 1 de cada 6 invocaciones de `faults` (e10 y e8-base). No es un fallo de la tabla regla→skill: `source-discrepancy` ya cubre las tres reglas.
- El único desacuerdo real entre decisión y skill es `GPS_DEGRADED` en `faults`: el modelo publica `GPS_JAMMING` donde el paso 4 de la skill dice `SENSOR_FAULT`. Observación: ese fallo del GPS es una pérdida de señal (`gps_loss`), así que la skill y la verdad del escenario no coinciden del todo; el modo guiado no puede cambiarlo y no se toca la skill.
- Rechazos de e10 por tipo: `link_anomalous` 6, `nothing_changes` 4, `source_silent` 1.

### 1.2 Diseño
- `monitor.guided_skills` (octava ayuda, en `AID_KEYS`, `aids()`, `eval.md` y el informe). La traza conserva `guided_mode` con el mismo valor.
- El módulo añade al primer mensaje de usuario una sección propia, `## guided_skill` (al final de `monitor_objective.md`), con la skill de la regla de cada aviso `raised` o `updated`, sin repetir. Para `cleared` no se añade nada. `load_skill` sigue disponible; la traza registra la skill con `by: "guided"`.
- **Se retira la variante antigua** (`guided_mode` con una llamada falsa a `load_skill`, `Monitor._preload_skill`) a favor de la sección en el mensaje. **No se han comparado las dos.**

### 1.3 Resultado (`e11-guiado`, `experiments/e11-guiado-vs-e10.md`, `e11-guiado-uso.md`)
- Etiquetas, cadenas, falsas alarmas, fallbacks, alertas abiertas, frases que contradicen y checks≠tools: **idénticos a e10**. Causa, severidad y `supersedes` de cada alerta, idénticos.
- Un check cambia: F3 `link_anomalous` pasa de nulo a falso.
- Iteraciones p50 4 → 3; tokens de prompt 460 034 → 408 999 (−11 %); latencia de invocación p50 7,2 → 6,1 s; pico de prompt 6 411 → 6 822. Rechazos: 11 en ambos (desaparece el de `source_silent`).
- **Lectura:** funciona y ahorra una iteración, pero el modelo ya hacía lo mismo por sí solo; es una red de seguridad barata para modelos más flojos.

## Paso 2 · Memoria A

### 2.1 Diseño
- `monitor.memory: per_detection | per_run` (no es una ayuda: va aparte, `MEMORY_KEYS`). Parámetros `memory_budget_tokens: 26000` y `memory_target_tokens: 18000`; el perfil valida que `budget + max_tokens + 4000 ≤ max_model_len`. Textos en `agent-assets/prompts/monitor_memory.md`.
- Con `per_run`, una sola conversación por simulación (`reset()` la vacía). Cada turno nuevo empieza con un mensaje que dice que lo anterior ya está respondido, que el estado de abajo es el vigente y que los datos antiguos **no valen como evidencia**.
- **Corte temporal:** sin cambios; las tools cortan en el `as_of` de cada invocación.
- **Guardrails por invocación (decidido):** las evidencias válidas son solo los ids pedidos en la invocación en curso; si el modelo cita un id del historial, el rechazo le dice que lo vuelva a pedir (tipo propio `history_evidence` en `monitor_usage`). Los `checks` también se calculan solo con las tools de la invocación.
- **Compactación** por bloques (de 26 000 a 18 000 tokens estimados): nivel A (resultados de tools de datos, objetivos antiguos y recordatorios) y nivel B (un turno antiguo en una línea). Nunca se toca el sistema, el turno en curso ni el anterior (que solo admite nivel A). Las llamadas cortadas se cierran con `aborted_call`.
- Traza: `messages` guarda copia; campo `memory` (turno, tokens antes y después, compactaciones). `cached_tokens` por llamada si vLLM lo da (**no lo da**: `n/d`); `run_matrix` guarda `vllm_metrics.json` con los contadores de la caché de prefijos de **toda la ejecución** (monitor, informe y chats).

### 2.2 Primera versión (`e11-memoria`) y un fallo mío
Regresión en `faults`: F2 ❌, 1 fallback, 1 alerta abierta, 8 rechazos frente a 5. Causa (traza inv-0006): el modelo publicó bien `GPS_JAMMING` con `supersedes: ai-0003` pero con severidad `high`. El rechazo por evidencia del historial cortaba el resto de comprobaciones, incluida la de recuperación (exige `medium`). El modelo repitió la llamada con las evidencias corregidas, `_reject` le devolvió el error viejo (el de las evidencias) y la tercera repetición abortó la invocación → fallback. Que el error oculto era la severidad **se infiere del código, no se leyó en la traza**.
- Arreglo: el error de evidencia del historial se añade al final y ya no corta las demás comprobaciones (`guardrails.py`, test nuevo `test_evidence_from_the_history_does_not_hide_the_other_rejections`).
- Debilidad que **no se toca**: `_reject` repite los errores del primer rechazo cuando se repite la llamada, aunque ya no sean los vigentes. Queda anotada.
- Se conserva `e11-memoria` como resultado de la primera versión.

### 2.3 Resultado tras el arreglo (`e11-memoria-v2`, `e11-memoria-v2-vs-e10.md`, `e11-memoria-v2-uso.md`)
- Etiquetas, cadenas, falsas alarmas, fallbacks y checks≠tools: **iguales a e10** en los seis vuelos.
- **Regresión:** `faults` termina con **1 alerta abierta** (ai-0006, la de recuperación del GPS). En el último aviso apagado (det-0004, inv-0011) el modelo llama a `get_track_metrics` y **reconoce** en vez de cerrar: «the discrepancy has decreased, but the GPS is still degraded (hdop 99.9)…». En e10, la misma invocación cierra. Son los máximos de toda la ventana desde 258 s los que lo confunden; con memoria, además, ya había reconocido esa alerta dos veces en turnos anteriores. Lo segundo es una hipótesis: la traza no permite separar las dos causas.
- `faults` ×3 (`e11-memoria-faults3`): etiquetas 3/3 y 0 fallbacks, pero **la alerta abierta aparece en las 3 repeticiones**: es sistemática, no ruido.
- Rechazos 10 (frente a 11): `recovery` 3, `nothing_changes` 3, `link_anomalous` 2, `duplicate_cause` 1, `source_silent` 1. En v2 no hubo rechazos `history_evidence`; en la primera versión fueron 4, todos en `faults`.

### Coste
| | e10 | guiado | memoria v2 |
|---|---|---|---|
| Tokens de prompt (suma 6 vuelos) | 460 k¹ | 409 k¹ | 1 012 k¹ |
| Pico de prompt en una llamada | 6 411 | 6 822 | 24 530 |
| Compactaciones | — | — | 0 (v1: una, nivel A) |
| Invocación p50 / p95 | 7,2 / 13,2 s | 6,1 / 12,2 s | 7,0 / 15,1 s |
| Caché de prefijos (aciertos/consultas) | sin medida | 0,79 en `demo`, 0,85 en `faults` | 0,92 en `demo`, 0,95 en `faults` |

¹ Solo invocaciones con LLM del monitor. Los contadores de caché cubren toda la ejecución, informe y chats incluidos; e10 no tiene contadores, así que no hay base de comparación directa.
- La memoria triplica el prompt de `faults` (196 k → 523 k por ejecución), pero la latencia apenas cambia porque casi todo es prefijo en caché.
- Contexto por invocación en `faults` (primera llamada): 3,6 k, 6,7 k, 7,6 k, 10,6 k, 14,6 k, 15,8 k, 19,2 k, 23,1 k, 24,1 k. Crece ~1 k por invocación; con más de 12 avisos haría falta compactar.

## Recomendación (no se cambia ningún valor por defecto)
1. **Modo guiado:** se puede activar sin riesgo medido (0 regresiones), con una ganancia modesta. Mi voto: dejarlo apagado mientras el modelo actual cargue la skill el 100 %, y activarlo si se prueba un modelo menor.
2. **Memoria A:** no activarla. No aporta aciertos en estos vuelos, cuesta ×2,2 de prompt y degrada el cierre de la alerta de recuperación. Si se retoma, el primer paso es que el cierre use solo la ventana posterior a la última alerta y no desde el inicio de la detección; es una mejora de prompt, no de memoria.
3. **No se probó** YaRN ni la combinación de ambas.

## Límites
1 repetición por escenario (3 en `faults` con memoria), T=0, seis vuelos. Con T=0 hay variación residual por el procesamiento por lotes de vLLM. Los contadores de caché cubren toda la ejecución.

## Ficheros
Nuevos: `monitor_memory.py`, `monitor_usage.py`, `prompts/monitor_memory.md`, perfiles `actual-guiado`, `actual-memoria-a`, `actual-guiado-memoria-a`, tests de memoria y de uso. Modificados: `agents.yaml`, `monitor_objective.md` (sección nueva al final), `assets.py`, `profiles.py`, `monitor.py`, `guardrails.py`, `trace.py`, `llm.py`, `engine.py`, `evaluate.py`, `report_facts.py`, `run_matrix.py`, tests y `ai-module-py/CLAUDE.md`.

## Revisión de contratos
Sin incumplimientos de contratos, separación, corte temporal ni cliente LLM. Una desviación menor de la regla 7, **pendiente**: tres fragmentos de texto en inglés escritos en el código (`monitor_memory.py:172` «no recorded outcome»; `monitor.py:370-375` «supersedes», «acknowledged», «alert closed») forman la línea del nivel B de la memoria y deberían vivir en `monitor_memory.md`. No se movieron para no cambiar la huella de `agent-assets` respecto a las ejecuciones medidas, y el nivel B no se activó en ninguna ejecución de v2. Si se retoma la memoria A, se mueven entonces. Además, `monitor_usage.py` interpreta el texto del objetivo con expresiones regulares, así que depende de su formato.

## URLs consultadas
- `vllm serve --help=all` (0.31.0, local): no hay `--rope-scaling`; YaRN iría por `--hf-overrides`.
- Contadores `vllm:prefix_cache_queries_total` y `vllm:prefix_cache_hits_total` en `GET :8000/metrics` (local). ⚠️ No se consultó documentación web.

## Mensaje de commit propuesto
```
feat: phase 11 - guided skills switch and monitor memory A (both off by default)

Add monitor.guided_skills (skill of the detection's rule in the first user
message) and monitor.memory: per_run (one conversation per simulation with
block compaction). Both measured against e10; defaults unchanged. Memory A
leaves one alert open in faults, so it stays off.
```
