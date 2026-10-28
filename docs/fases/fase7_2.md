# Fase 7.2 · Arreglar F3 (GPS callado durante una pérdida de GPS) (28/10/2026)

Perfil: solo `qwen3-14b-t0` (determinista; 1 repetición por escenario). Matrices: `experiments/e72a/` (paso A) y `experiments/e72b/` (paso B), frente a `qwen3-14b-t0` de `experiments/e0e1/` (3 repeticiones). Contratos sin cambios (v0.10). No se arrancó ningún modelo híbrido.

**Resumen:** el paso A (una frase en el prompt) **no cambia nada**: el modelo hace exactamente lo mismo en inv-0008 y F3 sigue ❌. Se deja la frase y se aplica el paso B (regla en el guardrail, con interruptor): **F3 ✅** (alerta propia `SENSOR_FAULT`, cerrada al final) **sin ninguna regresión** en los seis escenarios. Ya tiene alerta propia, con un rechazo previo.

## 1. Paso A · una frase en el prompt (`e72a`)
Fichero: `agent-assets/prompts/monitor_objective.md`, sección `## raised` (es donde está la regla general de `acknowledge_detection` de cada aviso nuevo; el resto de menciones, en `monitor_system.md` y `monitor_output.md`, son descripciones generales y no se tocan).

Antes:
```
- If an open alert already explains it and nothing changes: `acknowledge_detection` with its `alert_id`.
- If it belongs to an open alert but changes the cause or the severity: ...
```
Después:
```
- If an open alert already explains it and nothing changes: `acknowledge_detection` with its `alert_id`.
  Exception: a `SOURCE_SILENT` detection is always a different fault and gets its own alert (`publish_alert`, without `supersedes`), even if another alert is open.
- If it belongs to an open alert but changes the cause or the severity: ...
```
Resultado: 6/6 `ok`; todo igual que `e0e1`: F3 ❌ (`GPS_JAMMING`, 0 cierres). En inv-0008 de `faults` la secuencia de tools es **idéntica** a la de `e0e1` (carga `source-silence`, que no existe → carga `source-discrepancy` → `get_events gps` → `get_track_metrics` de 5 s → `publish_alert` `GPS_JAMMING`, `severity: high`, `supersedes: ai-0006`, `link_checked: false`), con la frase ya en el prompt del usuario. Sin regresiones, pero sin efecto: el modelo no lee la excepción, o la lee y la skill no se lo contradice (la sigue pese a ella). Criterio: «F3 sigue fallando sin regresiones» → se deja la frase y se pasa al B.

## 2. Paso B · regla en el guardrail (`e72b`)
Código (`ai-module-py/src/ai_module/agent/guardrails.py`, interruptor en `agents.yaml` `monitor.source_silent_own_alert: true`, cableado en `assets.py`, `profiles.py` (clave permitida en perfiles), `monitor.py`, `report_facts.py` y `evaluate.py` (cabecera de `eval.md` e informe), y `ai-module-py/CLAUDE.md`):
- Se aplica a una detección `SOURCE_SILENT` **nueva**, es decir, que todavía no está en ninguna alerta.
- `acknowledge_detection` sobre ella: rechazado, «a SOURCE_SILENT warning is always a different fault and gets its own alert: publish_alert with cause SENSOR_FAULT and without supersedes».
- `publish_alert` con `supersedes` hacia una alerta abierta de causa distinta de `SENSOR_FAULT`: rechazado, «a SOURCE_SILENT warning is a different fault from ai-0006 (GPS_JAMMING) and gets its own alert: publish_alert with cause SENSOR_FAULT and without supersedes».
- No cambia: el radar mudo (F1, no hay alerta abierta), un `DetectionUpdated` de un silencio que ya tiene alerta propia (se reconoce como siempre), `supersedes` hacia una alerta `SENSOR_FAULT`, ni el resto de reglas. La regla **no impone la causa**: solo dice cuál publicar (el skill permite `UNKNOWN` si callan varias fuentes).
- Pruebas (`tests/test_guardrails.py`, 6 nuevas): reconocer rechazado; sustituir una alerta `GPS_JAMMING` rechazado; alerta propia aceptada; radar mudo de F1 sin cambio (con `medium` y `high`); reconocer un silencio ya alertado aceptado; otras reglas intactas; interruptor apagado = comportamiento anterior. Se ajustaron dos pruebas existentes: la lista de ayudas de la traza (`test_coherence.py`) y el LLM falso `publisher` de `test_monitor_scenarios.py`, que reconocía el silencio dentro de la alerta abierta (justo lo que ahora se rechaza) y ahora publica alerta propia.
- Contratos: no cambia ningún evento, topic, WebSocket ni tool; no hace falta revisor de contratos. Sí cambia la huella de `agent-assets` (`agents.yaml`): **`5627cd4750f82906`** en `e72b` frente a `3116b1702762394d` en `e72a` (la frase del paso A sola; `e0e1` y la 7.1, `e28d071e856efb09`, no llevan la frase).

Qué hace el modelo en inv-0008 de `faults` (e72b): la misma secuencia hasta el `publish_alert` `GPS_JAMMING` + `supersedes: ai-0006`, que **se rechaza** con el mensaje anterior, y en la segunda llamada publica `ai-0008` con `SENSOR_FAULT` y sin `supersedes`. Esa alerta se cierra con el `DetectionCleared`.

## 3. Resultados (tabla frente a e0e1)
Cada fila de `e0e1` son 3 repeticiones idénticas (estable 3/3); `e72a` y `e72b`, 1 repetición. (En la comparación conjunta los «k/3» de `e72a` y `e72b` salen así porque se fijó `reps` a 3 al juntar los manifiestos; en sus propios `compare.md` son 1/1.) Comparación de los tres: `experiments/e72-compare.md` en la carpeta de resultados (se juntaron los manifiestos en una carpeta temporal, como en la 7.1).

| Escenario | e0e1 (`qwen3-14b-t0`) | e72a (frase) | e72b (frase + regla) |
|---|---|---|---|
| demo | A1, A2, A3 ✅ · 1 cadena cada una · 0 abiertas | igual | igual |
| nominal | 0 falsas alarmas | igual | igual |
| wind | A1 ✅ | igual | igual |
| spoofing | A1 ✅ (`GPS_SPOOFING`) | igual | igual |
| hijack | A1 ✅ | igual | igual |
| faults | F1 ✅ · F2 ✅ (1 cadena `GPS_JAMMING`×3) · **F3 ❌** (`GPS_JAMMING`, 0 cierres) | F1 ✅ · F2 ✅ · **F3 ❌** (igual) | F1 ✅ · F2 ✅ · **F3 ✅** (`SENSOR_FAULT`, 1 cadena, 1 cierre) |

Contadores de las seis ejecuciones, en los tres: falsas alarmas 0, fallbacks 0, alertas abiertas al final 0, frases que contradicen 0, no latinos 0, cortes por longitud 0. Las cadenas y causas de los 6 escenarios coinciden con las de `e0e1` salvo F3 en `e72b`.

**Regresiones: ninguna** (aciertos, cadenas, abiertas, fallbacks, falsas alarmas y contradicciones iguales; F1 sigue con una cadena `SENSOR_FAULT`).

## 4. Rechazos de guardrails
Por ejecución, `faults`: `e0e1` 3 (9 en las 3 repeticiones), `e72a` 3, `e72b` **4**. Los cuatro de `e72b` en inv-0004 y inv-0005 («Nothing changes… use acknowledge_detection», decisión), inv-0006 (`link_anomalous = null` y recuperación del GPS, igual que antes) y **el nuevo, inv-0008 (fuente callada)**. Los demás escenarios: sin cambios (demo 3, wind 1, spoofing 1, hijack 1, nominal 0).

## 5. Límites
- 1 repetición por escenario y perfil determinista (temperatura 0): vale para decir «sin cambio» o «sin regresión» en estos seis vuelos; no mide variabilidad. El modelo es el mismo que en `e0e1`, así que las diferencias solo pueden venir del prompt (A) y de la regla (B). Las latencias de `compare.md` de e72a y e72b son solo de una repetición.
- La regla cubre `SOURCE_SILENT` nuevos de cualquier fuente: no hay ningún escenario con link, tiempo o batería callados, así que su efecto allí no está medido (sí está probada con pruebas unitarias).
- `tests/test_profiles.py::test_think_profiles_raise_max_tokens_and_times` falla (espera `max_invocation_s == 300` y el perfil `qwen3-14b-think` tiene 99, tiempos medidos en la 7.1). **No es de esta fase**: viene de la 7.1 y no se ha tocado; queda para quien decida si se actualiza la prueba. El resto de la batería: 351 pruebas ok.
- Con el paso B el modelo sigue proponiendo `GPS_JAMMING` primero: la regla le obliga a rectificar, no le hace decidir mejor; es un rechazo más (≈ 6 s por invocación).

## 6. `docs/quien_decide_que.md`
Actualizado: la frase nueva en «Prompts y skills reescritos»; el caso «Fuente callada» del §2 (la forma de la alerta la pone ahora el código; la causa, el modelo); la fila de ayuda `monitor.source_silent_own_alert` en el §3; y el pendiente de `faults` del §6 (F3 resuelto).

## 7. Mensaje de commit propuesto
```
feat: phase 7.2 - SOURCE_SILENT gets its own alert (fix for F3)

- agent-assets/prompts/monitor_objective.md: exception in the "raised" section
  (a SOURCE_SILENT detection always gets its own alert); alone it changes
  nothing (e72a identical to e0e1)
- guardrails: a new SOURCE_SILENT detection cannot be acknowledged nor
  supersede an alert of a cause other than SENSOR_FAULT; switch
  monitor.source_silent_own_alert (on by default) in agents.yaml
- tests for the rule (including the silent radar of F1); two existing tests
  adapted (aids list, scripted publisher)
- experiments/e72a/compare.md and experiments/e72b/compare.md: F3 now passes,
  no regressions on the six scenarios
- docs: phase 7.2 report and who-decides-what updated
```
