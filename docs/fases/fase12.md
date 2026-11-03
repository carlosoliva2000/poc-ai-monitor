# Fase 12 · Correcciones antes de E4 (03/11/2026)

Escrito para: Carlos, que revisa la fase. Contratos **sin cambios**. Perfil `actual` (Qwen3-14B-AWQ sin razonamiento, T=0; modo guiado y memoria A apagados). Base: `experiments/e10/`. Tres cambios, uno cada vez, cada uno con los seis escenarios ×1 frente a la base anterior. **Los tres se adoptan: ninguna regresión.** No se arrancó ningún modelo híbrido. Al empezar, el puerto 8000 lo ocupaba otro servidor (una página «aTrain»): se paró y se esperó a que Carlos lo liberara; nada se mató.

## Resumen

| Experimento | Cambio | Base | Etiquetas | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Rechazos (demo/nom/wind/spoof/hijack/faults) | Decisión |
|---|---|---|---|---|---|---|---|---|---|---|
| `e12-reject` | `_reject` con errores vigentes | e10 | igual (6/6 vuelos ✅) | 0 | 0 | 0 | 0 | 0 | 3/0/1/1/1/**4** (e10: 3/0/1/1/1/5) | adoptado |
| `e12-skill` | skill `source-discrepancy` pasos 0 y 4 | e12-reject | igual | 0 | 0 | 0 | 0 | 0 | 3/0/1/1/1/**5** | adoptado |
| `e12-cierre` | ventana de 20 s en el cierre | e12-skill | igual | 0 | 0 | 0 | 0 | 0 | 3/0/1/1/1/5 | adoptado |
| `e12-cierre-memoria` | (informativo) `faults` con memoria A | e11-memoria-v2 | F1–F3 ✅ | 0 | 0 | **0** | 0 | 0 | 5 | no cambia la recomendación |

Comparaciones juntando manifiestos con `compare.py`: `experiments/e12-reject-vs-e10.md`, `e12-skill-vs-reject.md`, `e12-cierre-vs-skill.md` y `e12-cierre-memoria-vs-e11.md` (esta última frente a `e11-memoria-v2`, no frente a una base de la Fase 12).

## Cambio 1 · Errores vigentes al repetir una llamada rechazada (código)
- **Qué se tocó:** `Monitor._reject` (`monitor.py`). `Invocation.rejected` pasa de `dict[str, list[str]]` (llamada → errores del primer rechazo) a un `set` de llamadas. Si se repite una llamada idéntica, el rechazo es «This is the same call as before; change what I told you.» **más los errores de esa llamada** (`verdict.errors`). La detección de repetición (`AbortInvocation` en la segunda repetición) se mantiene y compara la llamada (herramienta + argumentos), no los errores.
- **Tests:** `test_a_repeated_call_gets_the_current_errors_not_the_first_ones` (`test_round8.py`): errores que cambian entre dos rechazos de la misma llamada → recibe los vigentes; la tercera repetición corta; otra llamada no lleva aviso. Los tests antiguos de repetición (`test_round8`, `test_round9`) pasan sin cambios.
- **Nota:** una llamada con argumentos *distintos* siempre fue una llamada nueva y recibía sus propios errores; el error de la Fase 11 solo aparecía con la misma llamada y errores distintos (p. ej. tras pedir una evidencia entremedias).
- **Resultado frente a e10:** igual en todo. **El camino de «misma llamada repetida» se activó 0 veces** (ni «same call as before» ni `repeated_rejection` en las trazas). Rechazos de `faults` 5 → 4: variación de vLLM, no efecto del cambio. Huella de `agent-assets`: `40d9cff3f1e110f3` (distinta de e10, `e41c4a68a68dfa93`, por los cambios de assets de la Fase 11; esta fase no tocó assets en este paso).
- **Adoptado.**

## Cambio 2 · Skill `source-discrepancy`, pasos 0 y 4
Fichero: `agent-assets/skills/source-discrepancy/SKILL.md`. El contexto de la skill no se toca (ya decía que una pérdida de GPS degrada el fix).

**Paso 0, antes:**
```
- `SENSOR_FAULT` alert: publish `GPS_JAMMING`, `severity: high`, with `supersedes` pointing to it.
- Alert already `GPS_JAMMING`: `acknowledge_detection` with its `alert_id`.
```
**Después:**
```
- `SENSOR_FAULT` alert: publish `GPS_JAMMING`, `severity: high`, with `supersedes` pointing to it.
- `GPS_JAMMING` alert with `severity: medium` and `gps_radar.disagreed` is now `true` (the drone already drifts): publish `GPS_JAMMING`, `severity: high`, with `supersedes` pointing to it.
- Alert already `GPS_JAMMING` with `severity: high`, or `medium` while `gps_radar.disagreed` is still `false`: `acknowledge_detection` with its `alert_id`.
```
**Paso 4, antes:**
```
- Bad fix/sats/hdop and `gps_radar.disagreed` `true`: **`GPS_JAMMING`**, `severity: high`, `confidence` 0.8–0.9 (the drone navigates by dead reckoning and drifts off). Recommendation: do not trust the GPS, radar as reference.
- Only degraded and `gps_radar.disagreed` `false`: **`SENSOR_FAULT`**, `severity: medium`, `confidence` 0.5–0.7.
```
**Después:**
```
- Bad fix (`fix: none`, `sats` 0 or `hdop` 20 or more): **`GPS_JAMMING`** (loss or interference of the GPS), `confidence` 0.8–0.9. `severity: high` if `gps_radar.disagreed` is `true` (the drone navigates by dead reckoning and drifts off), `medium` if it is not yet. Recommendation: do not trust the GPS, radar as reference.
- Only a somewhat high `hdop` or few satellites, with a fix and `gps_radar.disagreed` `false`: **`SENSOR_FAULT`**, `severity: medium`, `confidence` 0.5–0.7.
```
(El enunciado de la tarea describía el paso 4 antiguo con `SENSOR_FAULT` para un fix malo sin discrepancia; el fichero real ya mandaba `GPS_JAMMING` `high` con discrepancia, y lo que cambia es el caso sin discrepancia.)

- **Evaluación:** acepta `GPS_JAMMING` para F2 (`evaluate.py:101`, causa esperada `GPS_JAMMING` si el fallo es una pérdida); sin cambios.
- **Resultado frente a e12-reject:** igual en todas las métricas. F2 es **idéntico**: `GPS_JAMMING` `high` T+04:05 → `GPS_JAMMING` `medium` T+04:50, una cadena (ya empezaba en `GPS_JAMMING`, así que no había nada que mejorar).
- **Lo esperado y no visto:** «menos rechazos o iteraciones en `faults`». Hay **5 rechazos frente a 4** y la invocación inv-0008 (F3, `SOURCE_SILENT`, que no usa el paso 4) pasa de 6 a 8 iteraciones: el extra es `checks.gps_radar_disagreed = true does not match get_track_metrics (false)`. No puedo separar si es efecto de la skill o variación de vLLM (1 repetición).
- **Lo que el modelo no sigue:** en inv-0003 (T+04:05, `GPS_DEGRADED`) publica `GPS_JAMMING` `high` con `gps_radar_disagreed: false`; el paso 4 nuevo diría `medium`. El modelo no distingue la severidad por la discrepancia en ese primer aviso. No se pide al guardrail.
- **Adoptado** (ninguna regresión; mejora no demostrada). Huella: `da95583ecb33fca8`.

## Cambio 3 · Ventana del aviso de cierre
- **Qué se tocó:** `agent-assets/prompts/monitor_objective.md` (sección `cleared`) y `monitor.py`.
  - **Antes:** «call `get_track_metrics` **once** with `since` = <<detection_since>> and `until` = <<sim_time>> (from the start of the detection until now) and decide with that result.»
  - **Después:** «… with `since` = <<window_since>> and `until` = <<sim_time>> (the last 20 seconds) and decide with how things are now, not with how they were while the problem was going on.»
  - Código: marcador nuevo `window_since` (el viejo `detection_since` se retira: era el único uso) y función `closure_window_start(detection_since, as_of)`: `max(as_of − 20, 0)`, sin pasar por atrás del inicio de la detección (`CLOSURE_WINDOW_S = 20`).
- **Tests:** `test_closure_window_is_the_last_20_seconds_but_not_before_the_detection`, `test_the_closing_warning_asks_for_the_last_20_seconds` (`test_monitor.py`); `test_coherence.py` (antes «ventana desde el inicio de la detección», ahora la de 20 s: 106→136 con cierre a 156 s) y el marcador en `test_assets.py`. Batería de `ai-module-py`: 416 tests, `ruff` limpio.
- **Resultado frente a e12-skill:** **mismos cierres**: misma lista de eventos de cierre y de reconocimiento, a las mismas horas, en los cinco escenarios con anomalías; 0 alertas abiertas. Ningún cambio de cierre que citar. Tokens de prompt de `faults` 198 915 → 199 006.
- **Adoptado.** Huella: `293927dd0c038af5`.

### Comprobación informativa: `faults` con memoria A (`e12-cierre-memoria`, perfil `actual-memoria-a`)
- **La alerta de recuperación del GPS se cierra ahora**: `T+05:20 · cierre ai-0006`; **0 alertas abiertas** (la Fase 11 la dejaba abierta en 3 de 3 repeticiones). F1–F3 ✅, 0 fallbacks, 0 checks≠tools.
- Prompt: 609 545 tokens (frente a 199 006 sin memoria, ×3,1 en `faults`); invocación p95 26,1 s (la de F3, T+05:04).
- **Límite:** 1 repetición, no 3: no se demuestra que sea sistemático. Apoya la hipótesis de la Fase 11 de que eran los máximos de toda la ventana, pero no la separa de la otra (memoria con reconocimientos previos). **No cambia la recomendación**: memoria A apagada (coste ×3 de prompt).

## Base final para E4
- Último experimento adoptado: **`e12-cierre`** (huella de `agent-assets`: `293927dd0c038af5`; la memoria A y el modo guiado siguen apagados).
- Base de resultados para comparar: `experiments/e12-cierre/` (seis escenarios ×1, perfil `actual`: etiquetas 6/6, 0 falsas alarmas, 0 fallbacks, 0 alertas abiertas, 0 frases que contradicen, 0 checks≠tools; rechazos 11).

## Documentos actualizados
- `docs/quien_decide_que.md`: §2 «Pérdida de GPS» (la skill manda `GPS_JAMMING` ante fix malo, `high` con discrepancia y `medium` sin ella; el modelo no distingue la severidad en el primer aviso) y «Cierre» (ventana de 20 s); §1 orquestación (errores vigentes al repetir) y §3 (prompts y skills); §6 pendientes.
- `docs/mejoras_futuras.md`: «Memoria del monitor» con el resultado del cierre; nueva entrada sobre la severidad de `GPS_JAMMING` en el primer aviso.

## Límites
1 repetición por escenario, T=0, seis vuelos: con T=0 hay variación residual por el procesamiento por lotes de vLLM, y los cambios 2 y 3 no se pueden distinguir de ella cuando difieren en uno o dos rechazos.

## URLs consultadas
Ninguna (solo código y documentación locales).

## Ficheros
Modificados: `agent-assets/prompts/monitor_objective.md`, `agent-assets/skills/source-discrepancy/SKILL.md`, `ai-module-py/src/ai_module/monitor.py`, `ai-module-py/tests/{test_round8,test_monitor,test_coherence,test_assets}.py`, `docs/quien_decide_que.md`, `docs/mejoras_futuras.md`. Nuevos: `experiments/e12-*` y las comparaciones `experiments/e12-*-vs-*.md`.

## Mensaje de commit propuesto
```
feat: phase 12 - current errors on repeated rejected calls, GPS_JAMMING in source-discrepancy step 4, 20 s closing window

Monitor._reject returns the errors of the current call and compares calls, not
errors, to detect a repeat. The source-discrepancy skill maps a bad GPS fix to
GPS_JAMMING (high with GPS-radar disagreement, medium without). The closing
warning asks for the last 20 s of get_track_metrics. Each change measured on the
six scenarios against the previous one; no regressions.
```
