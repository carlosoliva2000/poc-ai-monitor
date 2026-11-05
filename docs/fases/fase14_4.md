# Fase 14.4 · `link_anomalous`, salto del módulo para la fase y cierre de la Fase 14 (05/11/2026)

Escrito para: Carlos, que decide qué se queda de la 14.4 y si cierra la Fase 14. Perfil `actual` (Qwen3-14B-AWQ sin razonamiento, T=0) y, en la comparación final, `gpt-oss-20b-low`. Base: `experiments/e14-3-informe/` (huella de `agent-assets` `d358e3d292c769e0`) y, para el ruido, `experiments/e14-3-final/` (×3). **Contrato: sin cambios** (la 14.4 no toca ningún evento ni la API de tools; el módulo llama a `get_track_metrics`, que ya existía). `agent-assets-v13/` no se ha tocado (`git diff` vacío). No se arrancó ningún híbrido; vLLM, plataforma y módulo quedaron parados (puertos 8000 y 8100 libres, GPU a 0 MiB, la cifra de reposo de `serve.sh` en esta sesión). Git solo de lectura. **No se ha cambiado el modelo por defecto.**

**Huella final de `agent-assets`: `d71cd7ec17440056`.** Pruebas: módulo de IA 578 (541 al empezar la fase), plataforma y contratos sin cambios; `ruff check` y `ruff format --check` limpios.

## Resumen

| Paso | Qué se cambió | Huella | Evaluación frente a su base | Medida del paso (contador propio) | Decisión |
|---|---|---|---|---|---|
| 1 · `link_anomalous` | `monitor.fill_link_anomalous`: si el modelo miró el enlace y deja `checks.link_anomalous` a `null` (o lo omite), lo pone el módulo | `c3c3cda7ad4e7292` | 6/6 (F3 incluida), todo a 0 | rechazos por `link_anomalous = null` **6 → 0**; rechazos totales 17 → 10; iteraciones máx. `faults` 9 → 7 y `demo` 9 → 8 | **adoptado** |
| 2 · fase con el salto del módulo | `monitor.recovery_jump_from_module`: el módulo pide `get_track_metrics` con una ventana fija y el guardrail decide con ese salto | `c80af17bd4138725` | 6/6, todo a 0, 3 recuperaciones con fase | **robustez:** con la skill de la 14.3 que rompía la fase, `spoofing` ×3 → **3 de 3 `recovering`** (control sin el interruptor: 3 de 3 sin fase) | **adoptado** |
| 3 · sin fix, el radar no falla | `source-discrepancy` paso 1: no acortar la ventana y qué significa `radar_available: false` | `d71cd7ec17440056` (la variante a, `28b396ede6504958`, no) | 6/6 y `faults` ×3 con F3 3/3 | `false_radar_unavailable`: **5 de 5** ventanas cortas con la frase falsa antes → **0 de 7** después | **adoptado** (variante b, tras la a) |

## Para decidir

1. **Cerrar la Fase 14.** Con `actual` ×3: 27/27 etiquetas (F3 3/3), 0 recuperaciones sin fase, 0 fallbacks, 0 `checks≠tools`, rechazos 46 → 40, iteraciones 4/8/9 (como la 14.3), pico de prompt del monitor 9 587 → 8 605. Resumen de la Fase 14 al final de este informe.
2. **El paso 3 no quita la ventana corta, solo la frase falsa.** En la serie final el 14B pidió en la primera alerta de F2 una ventana de 0–1 s (`since` = la detección) en **3 de 3** (en la 14.3 final, 0 de 3; en la base de este paso, 1 de 3; con las dos variantes del paso, 4 de 4 y 3 de 4): no es efecto de la skill (el texto del prompt de esa alerta es el mismo que en la base) sino variación del muestreo. Con esa ventana la plataforma no tiene muestras de radar y de viento, y el modelo declara un viento notable que luego el guardrail rechaza: **8 rechazos `checks≠tools` en `actual` (0 en la 14.3 final)**, y la alerta de recuperación de F2 dice «GPS and radar disagree (distance 5.1 m)» con `now` diciendo que coinciden (`now_window_mix` 0 → 1,3 en la media de las tres repeticiones). Lo corrige otra decisión tuya, no una skill: que el módulo corrija el `since` de una consulta de `GPS_DEGRADED` (sería otra ayuda con interruptor, y dejaría las skills como están) o que `radar_available` mire la última muestra y no la ventana (cambia el contrato). Está en `mejoras_futuras.md`.
3. **gpt-oss llegó a 12 iteraciones** (el tope) **en una invocación**: `faults` r3, `inv-0009`, el cierre del silencio del GPS (F3) a T+05:12. Reconoció y cerró con ids de otras detecciones y alertas (`det-0004`, `det-0006`; `ai-0006` en lugar de `ai-0008`) y el módulo se los rechazó 10 veces; acabó bien en la última iteración (que solo ofrece las tres tools de respuesta), **sin fallback** y en 45 s. No tiene relación con los cambios de la 14.4 (no hay `ROUTE_DEVIATION` ni enlace en ese aviso) y no afecta al 14B (su máximo es 9), pero conviene saberlo porque la condición que pusiste era «el 14B llega a 12»: el 14B no llegó, gpt-oss sí. Sus rechazos de «id equivocado» pasan de 3 (14.3) a 14.
4. **Modelo por defecto** (no se ha tocado). En `experiments/e14-4-textos.md` tienes `demo` y `faults` (r1) de `actual` y gpt-oss con su antes de la 14.3.
5. **F1 de `actual` baja de confianza 0,7 a 0,6** (las tres repeticiones; F3 0,7 → 0,6 en una): no la he podido atribuir a ningún paso (el paso 3 es el único que toca una skill que carga F1). La severidad no cambia.

## Cómo se ejecuta
- Matriz: `uv run --project ai-module-py python tools/experiments/run_matrix.py --profiles actual,gpt-oss-20b-low --scenarios nominal,wind,spoofing,hijack,faults,demo --reps 3 --id e14-4-final`; comparar: `uv run --project ai-module-py python -m ai_module.compare experiments/<id>`.
- Medida de textos (`--rep N` para cada repetición): `uv run --project ai-module-py python tools/experiments/text_metrics.py nombre=experiments/<id>:<perfil> … --out experiments/<nombre>.md`. Textos para leer: `tools/experiments/texts.py` (`experiments/e14-4-textos.md`).
- Copias exactas de cada paso, fuera de git: `~/poc-backups/fase14_4/{base,paso1,paso2,paso3-previo,paso3-a,paso3}/`.
- Perfil nuevo `model-profiles/actual-sin-salto-modulo.yaml`: igual que `actual` con `monitor.recovery_jump_from_module` apagado (el control de la prueba de robustez).

## Paso 1 · El módulo rellena `checks.link_anomalous`

**Qué se cambió.**
- `agent-assets/agents.yaml`: `monitor.fill_link_anomalous: true` (sin la clave, apagado: los assets congelados no la tienen). Entra en `AID_KEYS` de `profiles.py` (y por tanto en `ALLOWED`), en `aids()` de `AgentConfig` y en la cabecera de `eval.md`.
- `guardrails.fill_link_anomalous(raw, facts)` (función pura) y su uso al principio de `Monitor._publish_alert`. **Antes:** `checks.link_anomalous = null` tras haber mirado el enlace → rechazo «checks.link_anomalous = null does not match the link events you requested (false)». **Después:** si `facts.link_events is not None` y el campo es `null` o falta, el módulo pone el valor que ya calculaba (`link_is_anomalous`), sin rechazo; la traza guarda `module_filled` (`tool`, `field`, `value`).
- **No cambia:** un valor distinto del esperado se sigue rechazando; sin haber mirado el enlace no se rellena nada; `link_checked = true` sin haberlo mirado se sigue rechazando, y `link_checked = false` tras mirarlo también (aunque `link_anomalous` se rellene). Tampoco rellena si no hay `checks`.
- `evaluate.py` y `compare.py`: columna «Rechazos link=null / rellenos».
- Tests nuevos (`test_link_fill.py`, 12): null y omitido con enlace normal y anómalo, valor declarado distinto, sin mirar el enlace, sin `checks`, la llamada original no se modifica, y con el monitor entero (interruptor encendido y apagado, valor equivocado, `link_checked` mal), la cuenta de `eval`, y que los assets congelados lo tienen apagado.

**Evaluación (`e14-4-link`, ×1, frente a `e14-3-informe`).** 6/6 (F3 incluida), 0 falsas alarmas, 0 fallbacks, 0 frases que contradicen, 0 `checks≠tools`, 0 recuperaciones sin fase, mismos veto (1 en `faults`, 1 en `demo`).

| | `wind` | `spoofing` | `hijack` | `faults` | `demo` | total |
|---|---|---|---|---|---|---|
| Rechazos (base → paso) | 1 → 0 | 1 → 1 | 2 → 2 | 8 → 4 | 5 → 3 | **17 → 10** |
| Rellenos por el módulo | 1 | 2 | 0 | 3 | 3 | 9 |
| Iteraciones p50 / p95 / máx (base → paso) | 2/5/5 → 2/4/4 | 4/5/5 → 4/5/5 | 4/5/5 → 4/5/5 | 5/9/9 → 4/7/7 | 4/9/9 → 4/8/8 | |

Rechazos por `link_anomalous = null`: **6 → 0** (`wind` 1, `spoofing` 1, `faults` 2, `demo` 2 → 0). Los 9 rellenos son 9 rechazos y 9 iteraciones que ya no ocurren; con los rechazos de otros tipos (los cuatro de siempre: «ai-XXXX (CAUSA) is open: use supersedes…», «Nothing changes…», el veto del reconocimiento, «detection… already in the open alert») la serie no cambia.

**Medida de textos (`e14-4-link-textos-medida.md`, base → paso):** fugas 5 → 8 (alertas 3 → 4, informe 1 → 2, cierres 1 → 2; el paso no toca textos y el informe va a 0,7), errores 2 → 0. **Decisión: adoptado.** Huella `c3c3cda7ad4e7292`.

## Paso 2 · La fase se decide con el salto que calcula el módulo

**Qué se cambió.**
- `agents.yaml`: `monitor.recovery_jump_from_module: true` (sin la clave, apagado; en `AID_KEYS`, `aids()` y la cabecera de `eval.md`).
- `Monitor._module_jump(inv)` (antes de `_state_metrics`, sin LLM, fuera de las iteraciones, dentro de `duration_s`): ante un `ROUTE_DEVIATION` `raised` o `updated` con una alerta del GPS reciente (abierta o cerrada hace ≤ 60 s), el módulo pide `get_track_metrics` a la plataforma por la API de tools (corte temporal incluido) con **`since` = max(inicio de la detección − 30, hora de publicación de la primera alerta de la cadena del GPS, 0)** y `until` = `as_of`. Tu ajuste: un salto anterior a la alerta no es la vuelta del GPS, y así un engaño que empiece con un salto brusco no deja ese salto en la ventana durante toda la detección. La primera alerta de la cadena (`MonitorState.chain_root`) y no la cabeza: si la cabeza ya es la `recovering` (publicada después del salto), un `updated` posterior perdería el salto.
- El resultado va a `InvocationFacts.module_jump` y **`guardrails.gps_step` lo usa en lugar de la ventana del modelo** para: la fase esperada (`recovering`), el veto de `high`, y el veto del reconocimiento. El rechazo `recovery_ack_no_metrics` **se quita con el interruptor encendido y la llamada bien** (ya se sabe si hay salto: con salto, veto; sin salto, se puede reconocer); sin dato del módulo sigue como hoy.
- **«Es del GPS» (causa y `supersedes`)**, mi propuesta justificada: alerta del GPS reciente y (`disagreed` de la ventana del modelo o salto), con el **salto del módulo cuando lo hay** y no el del modelo. Una sola fuente del salto evita el estado incoherente «`jump` sí y `gps_related` no» (pediría `recovering` sin imponer causa ni `supersedes`), y si la ventana del modelo ve un salto que la del módulo no, es anterior a la alerta o a la detección − 30 y no es de esta recuperación.
- Si la llamada del módulo falla: el guardrail vuelve al criterio de hoy (ventana del modelo, y el rechazo sin métricas) y la traza guarda `recovery_jump.error`.
- Traza `recovery_jump` (`since`, `until`, `gps_max_step_m`, `jump`, `error`, `model_view`: `jump`, `window_without_jump` o `no_metrics`). `eval.md` y `compare.md` cuentan los saltos del módulo, los que la ventana del modelo no veía y las llamadas que fallaron; `recovery_misses` usa el salto del módulo (con él no puede dar `window_without_jump`). `report_facts.recovery_jump_m` y `text_metrics` lo usan también (el rechazo se lo dice al modelo y la cifra es válida).
- Tests nuevos (`test_module_jump.py`, 16): veto con el salto del módulo y sin métricas del modelo, el salto del módulo manda sobre la ventana del modelo en los dos sentidos, `chain_root`, la ventana enviada a la plataforma, ventana del modelo sin el salto → `recovering`, `high` y `active` rechazados, **salto anterior a la alerta y un `updated` posterior → no es recuperación (`active`, reconocer vale)**, caso normal (salto posterior a la alerta) → `recovering` también en un `updated`, cabeza ya `recovering` sigue viendo el salto, llamada que falla (ventana del modelo y rechazo sin métricas, con la traza), interruptor apagado = hoy, sin alerta del GPS reciente u otra regla = sin llamada, y los assets congelados lo tienen apagado. Más 4 tests en `evaluate`, `compare`, `report_facts` y `text_metrics`.

**Los tres saltos con la ventana nueva (comprobado antes de la matriz, con la función de la plataforma sobre las líneas temporales reales y la alerta publicada lo más tarde posible):** `spoofing` 49,6 m (`since` 192,1–192,9), `demo` 67,9 m (192,3–192,9), F2 90,0 m (260,0). Los tres siguen dentro.

**Evaluación (`e14-4-salto`, ×1, frente a `e14-4-link`).** 6/6, todo a 0, 3 recuperaciones con fase; rechazos 0/1/2/4/3 (igual); iteraciones máx. 4/5/5/7/8 (igual); saltos del módulo 49,6 (`spoofing`, `since` 192,7), 67,9 (`demo`, 192,4) y 90,0 (F2, 260,0), con la ventana del modelo viéndolos en las tres (no había nada que arreglar con estos assets, como se esperaba).

**Prueba de robustez (lo que justifica el paso).** `e14-4-salto-robustez`: `spoofing` ×3 con el `route-deviation/SKILL.md` de `~/poc-backups/fase14_3/paso1/` (la variante a del paso 1 de la 14.3, la que rompía la fase; el resto, los assets adoptados; huella de esa variante `013399329716e0f8`), con el interruptor encendido (`actual`) y apagado (`actual-sin-salto-modulo`, el control):

| | `actual` (interruptor encendido) | `actual-sin-salto-modulo` (control) |
|---|---|---|
| Ventana que pidió el modelo | `since=222.0` las 3 (sin salto: `gps_max_step_m` `null`) | `since=222.0` las 3 |
| Salto del módulo | 49,6 m las 3 (`since` 192,2–192,7) | – |
| Alerta de recuperación | **3 de 3 `recovering`, `medium`**, con `supersedes` | **ninguna** (el modelo reconoce): 3 de 3 `window_without_jump` |
| Etiqueta A1 | 3/3 ✅ | 3/3 ✅ |
| Rechazos / iteraciones máx. | 9 / 10 | 6 / 10 |

Texto de la recuperación de la r1 con la ventana vacía: «GPS spoofing detected; GPS is recovering and aligning with radar. … the GPS has jumped by 49.6 m, indicating a possible recovery … GPS and radar now agree (distance 9.9 m) …» (la cifra del salto es la del rechazo del guardrail, que ahora trae la del módulo). Después de la prueba se restauró la skill adoptada (`sha256` `4918f40a…`, `diff -rq` con la copia del paso 2 vacío, huella `c80af17bd4138725`). La iteración máxima fue 10 (no 12).

**Medida de textos (`e14-4-salto-textos-medida.md`, paso 1 → paso 2):** fugas 8 → 6, errores 0 → 0, sin acción 8 → 9, cifras sin respaldo 1 → 2 (ruido). **Decisión: adoptado.** Huella `c80af17bd4138725`.

## Paso 3 · Sin fix: no inventar que el radar falla

**Por qué lo decía (la traza, no la frase del GPS sin fix).** En F2 (`faults`, primera alerta, T+04:05) `now` trae `radar_deviation_from_plan_m` = 8,4 m y `get_events` del radar da `rad-000122`; el modelo no lo ve porque **pide `since` = la detección** (0,2–0,8 s) y la plataforma devuelve `radar_available: false` (el radar publica cada 2 s y esa ventana no tiene muestras). El paso 1 de `source-discrepancy` dice «If `radar_available` is `false`, you cannot check the GPS: say so». Medido: con ventana corta, 5 de 5 series dicen que el radar no está (`e14-3-now`, `now-c`, `textos-b`, `informe` y la r3 de la base de este paso); con ventana de 40 s, 0 de 10 (todas las de `e14-2-final-actual` y `e14-3-final`, y gpt-oss).

**Qué se cambió (solo `source-discrepancy`, sin tocar `route-deviation`).** Paso 1, antes: *«Call `get_track_metrics` with `since` = sim_time of the detection − 40 and `until` = now. If `radar_available` is `false`, you cannot check the GPS: say so.»* Después (variante b): *«…and `until` = now; do not shorten the window, because the radar reports every 2 seconds and a window of a second or two may hold no sample of it. `radar_available: false` only says that this window has no radar sample: the radar is silent only if its deviation in `now` is missing as well and its last events (`get_events`, `source` `radar`) are old. If the radar really is silent, you cannot check the GPS: say so.»*

**Variante a (no adoptada).** La a añadía además a la frase de «Window or now» *«…but the radar still reports and is the reference: say where it places the drone now (its deviation from the route in `now`)»*. Resultado (`e14-4-sinfix`, `-faults3`, huella `28b396ede6504958`): 6/6, F3 3/3, contador 0, pero **errores 0 → 3** (seis escenarios) y 1 → 3 (`faults` ×3), `now_window_mix` 0 → 3, genéricas 2 → 6, sin acción 9 → 12: la recuperación decía «GPS and radar disagree (distance 5.1 / 9.9 m)». Fuera del ruido (±1 error). Copia en `paso3-a`.

**Contador `false_radar_unavailable`** (`text_metrics.py`, con 3 tests): frases en presente que dicen que el radar no está o no informa («the radar is unavailable», «no radar data», «without radar confirmation»…) cuando el radar publicó una pista en los 6 s anteriores a la invocación (`radar_reporting_at`); el pasado («was silent for 7 s») y un radar callado de verdad (F1) no cuentan. Remedido sobre las series anteriores: 1 en `e14-3-informe`, `e14-3-now-c` y la r3 de la base.

**Matrices.** Base: `e14-4-sinfix-antes` (`faults` ×3, huella `c80af17bd4138725`, la del paso 2): F2 con ventana corta en la r3 → «**The radar is unavailable, so we cannot confirm the drone's actual position.**» (contador 1; r1 y r2, ventana de 40 s, 0); F3 2/3 (r2: `GPS_JAMMING`, el fallo conocido). Variante b: `e14-4-sinfix-b` (6/6, rechazos 0/2/2/7/3, iteraciones máx. 4/6/5/9/7) y `e14-4-sinfix-b-faults3` (F1, F2 y F3 3/3, rechazos 19, máx. 9): **ventana corta en 4 de 4 primeras alertas de F2, y en las 4 el modelo pide también `get_events` del radar y el contador sale 0**. Con la serie final, 3 de 3 ventanas cortas y 0 frases falsas: **0 de 7 con ventana corta después, frente a 5 de 5 antes**.

**Antes y después, primera alerta de F2** (`faults`, `actual`, ventana corta en ambas):
- *Antes (`e14-4-sinfix-antes` r3):* «At T+04:05, the GPS reported a high hdop of 99.9 and no fix… **The radar is unavailable, so we cannot confirm the drone's actual position.** The wind is blowing from the northwest, pushing southeast, which could contribute to the drone drifting off course.» Recomendación: «…Monitor the radar for updates on the drone's actual position.»
- *Después (`e14-4-sinfix-b-faults3` r3):* «At T+04:05, GPS reported no fix (hdop 99.9). **Radar data shows the drone is 8.4 m off the planned route**, indicating a possible GPS jamming or loss. Wind is from NW (301°), pushing SE, but it is not sufficient to explain the deviation.» Recomendación: «Verify GPS signal integrity and consider switching to radar-based navigation until GPS is restored.»
- *Después (r1 y r2):* «The GPS has lost its fix (hdop 99.9, 0 satellites) at T+04:05. The radar shows the drone at T+04:04 (rad-000122) at x=2269.1, y=519.5, while the GPS shows x=2257.2, y=508.8 …».

**Medida de textos (variante b frente a `e14-4-salto`, ×1):** fugas 6 → 7, errores 0 → 1, mezcla ahora/ventana 0 → 1 (dentro del ruido ±1), sin acción 9 → 11, genéricas 2 → 3. En `faults` ×3 por repetición (base → variante b): errores 0/0/1 → 1/1/2 y mezcla 0/0/1 → 1/1/1; los errores y la mezcla son la frase de recuperación de F2 «GPS and radar disagree (distance 5.1 m)» (`ai-0006`), que sale cuando la primera alerta de F2 usó la ventana corta (también en la r3 de la base): no es del texto de la skill sino de esa ventana. **Decisión: adoptado la variante b.** Huella `d71cd7ec17440056`.

## Comparación final (`e14-4-final`, huella `d71cd7ec17440056`; seis escenarios ×3)

**Evaluación** (suma de las tres repeticiones; entre paréntesis, la 14.3 final):

| | `actual` | gpt-oss-20b-low |
|---|---|---|
| Etiquetas ✅ | **27 de 27** (27) | 26 de 27 (26) · F1 ❌ en la r1: `UNKNOWN`, «radar mudo» |
| F3 (silencio del GPS) | 3 de 3 | 3 de 3 |
| Falsas alarmas / fallbacks / abiertas / contradicciones / `checks≠tools` | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| Recuperaciones sin fase | 0 | 0 |
| Saltos del módulo (ventana del modelo sin verlos) | 9 (0) | 9 (0) |
| `link_anomalous = null` rechazos / rellenos | 0 / 34 (19 / 0) | 0 / 4 (5 / 0) |
| Veto del reconocimiento | 9 (6) | 0 (0) |
| Rechazos (llamadas) | **40** (46) · 13,3 por serie (13–14; 15,3) | **24** (17) · 8,0 por serie (5–13; 5,7) |
| Iteraciones p50 / p95 / máx | 4 / 8 / **9** (4 / 8 / 9) | 3 / 5 / **12** (3 / 6,3 / 8) |
| Pico de prompt (monitor / informe), tokens | 8 605 / 3 522 (9 587 / 3 477) | 7 032 / 3 473 (7 517 / 3 454) |
| Tokens de prompt por ejecución (media) | 115 775 (112 990) | 79 408 (82 818) |
| Estabilidad entre repeticiones | estable (3/3) en los seis | estable salvo `faults` (F1 `UNKNOWN` en la r1) |

**Rechazos por tipo (errores).** `actual` 45 en 40 llamadas (14.3: 52 en 46): «ai-XXXX (CAUSA) is open: use supersedes…» 13; «Nothing changes…» 9; veto del reconocimiento 9; **`checks≠tools` 8 (14.3: 0; son los de las ventanas cortas de F2: `wind_notable` y `wind_with_drift` declarados sin viento en la ventana)**; reconocer un `SOURCE_SILENT` 3; «detection… already in the open alert» 3; ninguno de `link_anomalous = null` (14.3: 19), de la severidad `high` ni de la fase. **gpt-oss** 26 en 24 llamadas (14.3: 18 en 17): **id equivocado de detección o de alerta 14 (14.3: 3; 10 de ellos en la invocación de 12 iteraciones)**, causa de la recuperación 5, reconocer un `SOURCE_SILENT` 3, `WIND` sin viento notable 2, un argumento que no existe 2; ninguno de `link_anomalous` (14.3: 5) ni de la fase.

**Textos con la definición final** (media y rango entre las tres repeticiones; `experiments/e14-4-final-r{1,2,3}-textos-medida.md`):

| | Fugas | Errores | Genéricas | Sin acción | Mezcla ahora/ventana | Coinciden sin fix | Radar falso | Ajenas en el cierre | Cierre sin dato de la causa | Jerga del monitor | Cifras sin respaldo | Hora de recuperación ≠ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` 14.3 ×3 | 4,0 (2–5) | 0,3 (0–1) | 1,7 (1–2) | 8,3 (7–9) | 0 | 0 | 0 | 2,3 (1–3) | 0 | 1,3 (1–2) | 0,3 (0–1) | 0 |
| **`actual` 14.4 ×3** | 5,7 (4–7) | 0,7 (0–1) | 2,7 (1–4) | 9,3 (9–10) | **1,3 (0–2)** | 0 | **0** | **0,3 (0–1)** | 0 | 0,3 (0–1) | 0,7 (0–2) | 0,3 (0–1) |
| gpt-oss 14.3 ×3 | 8,7 (7–12) | 0 | 3,3 (3–4) | 9,3 (8–10) | 0 | 1,0 (1–1) | 0 | 1,7 (1–2) | 0 | 3,0 (3–3) | 0,7 (0–2) | 0 |
| **gpt-oss 14.4 ×3** | 6,0 (2–12) | 1,3 (1–2) | 3,0 (2–4) | 7,7 (6–9) | 0 | 0,3 (0–1) | 0 | 1,7 (0–5) | 0,7 (0–2) | 0,7 (0–2) | 0 | 0 |

`actual`: las fugas, los errores y las genéricas suben dentro del ruido (±2 y ±1) salvo la mezcla ahora/ventana (1,3; la frase de recuperación de F2 de la decisión 2) y mejoran las fuentes ajenas en el cierre (2,3 → 0,3, en el ruido de 1–3). gpt-oss: sin ningún efecto atribuible a los pasos (no usa ninguna de las dos ayudas nuevas más que en 4 rellenos y 9 saltos del módulo).

**Severidad, confianza, fase y sustituciones por etiqueta** (`e14-4-final-r{1,2,3}-textos-medida.md`): `actual` idéntico en las tres repeticiones y en las nueve etiquetas, salvo la confianza de F1 (0,7 → 0,6, las tres) y la de F3 en la r1 (0,6): viento `medium` 0,8; spoofing y pérdida de GPS `high` 0,8 → `medium` 0,8 `[recovering]` con 1 sustitución; secuestro `high` 0,7 sin sustituir; fallos de sensor `medium` 0,6–0,7. gpt-oss: mismas causas y recuperaciones `[recovering]` (`medium` en 8 de 9; `low` 2 veces: `spoofing` r2 y `demo` r3); **el secuestro empieza en `medium` y sube a `high` con una sustitución en 5 de 6**; F1 de la r1 `UNKNOWN` `medium` 0,6; F3 `high` 0,8 en la r1.

**Ids con U+2011 en el texto de gpt-oss** (sin normalizar, solo contados, con el mismo guion de la 14.3 sobre `timeline.jsonl`): 276 caracteres U+2011 en el texto libre (14.3: 293), 46 dentro de ids con la expresión de ids de `text_metrics` (con ese criterio la 14.3 da 37; la cifra de 63 del informe de la 14.3 no la he podido reproducir con otro criterio); por tipo: `ReportGenerated` 201, `AgentReply` 68, `AnomalyDetected` 5, `AlertClosed` 2. `actual`: ninguno.

**Textos para la rúbrica:** `experiments/e14-4-textos.md` (`demo` y `faults`, r1, de `actual` y gpt-oss con el antes de `e14-3-final`).

## Revisor de contratos
Una pasada, al cerrar el paso 3 (`revisor-contratos`; no tiene shell: no ejecutó pruebas ni leyó línea a línea `evaluate.py`, `compare.py`, `report_facts.py` ni `text_metrics.py`). **Sin incumplimientos.** Confirma: ningún import de `platform/` en `ai-module-py`; `_module_jump` habla con la plataforma solo por la API de tools (`until` = `as_of`, sin pasar por `Toolbox` y sin riesgo de corte); ninguna ruta nueva lleva la verdad, `labels.json` o el dominio `sim` al LLM; `recovery_jump` y `module_filled` solo se escriben en la traza y el LLM no ve nada nuevo salvo el salto en metros del mensaje de rechazo; los interruptores valen `False` sin la clave; y el contrato (eventos, modelos Pydantic, esquemas) no necesita cambios. **Una observación, sin incumplimiento:** si la llamada del módulo funciona pero la plataforma no puede calcular el salto en esa ventana (`gps_max_step_m` `null`), el guardrail no vuelve a la ventana del modelo (solo vuelve si la llamada falla). Es lo que se quiere: la ventana del módulo es la de la recuperación y un salto que solo ve la del modelo es anterior a la alerta o a la detección − 30.

## Problemas (con su error literal)
- `ERROR platform/tests - ModuleNotFoundError: No module named 'platform_app'` y `Interrupted: 1 error during collection`: lancé `pytest` desde la raíz con el proyecto del módulo; las pruebas del módulo se lanzan con `uv run pytest -q tests` dentro de `ai-module-py/`.
- `Blocked: sleep 60 followed by: tail …. To wait for a condition, use Monitor with an until-loop`: espera con `Monitor`.
- `Monitor expired after 30m with 21 events delivered. Re-arm it if you still need the watch.` en la comparación final (el máximo es 30 min): lo rearmé.
- Ruff del hook: `E501 Line too long (101 > 100)` en `trace.py`, `monitor.py` y `text_metrics.py`; corregidos.
- `ModuleNotFoundError: No module named 'poc_contracts'` al cargar `text_metrics.py` con el Python del sistema: va con `uv run --project ai-module-py`.
- Pruebas que fallaron por mi cambio, no por el código: `TypeError: dataclasses.replace() got multiple values for keyword argument 'recovery_jump_from_module'`, `TypeError: monitor_with() got an unexpected keyword argument 'recovery_jump_from_module'`, el diccionario exacto de `aids` de `test_coherence.py` (ahora con las dos claves nuevas) y `test_other_state_styles_do_not_call_the_platform_either` (ahora el módulo llama a la plataforma para la fase: la prueba es de la línea de estado y apaga esa ayuda), y mis propias expectativas del contador `radar_reporting_at` (6,5 s es silencio).
- `text_metrics.py` mide **una** repetición por llamada (`--rep`, por defecto 1): la primera medida de la base de `faults` ×3 miró solo la r1 y dio 0 en el contador falso; midiendo cada repetición sale 1 en la r3.
- Un contador de rechazos que mi script daba a 0 al principio porque las ejecuciones de `nominal` no tienen invocaciones del monitor (`KeyError: 'monitor'`): corregido en el script de tablas (no está en el repo).

## Límites
- n = 3 por escenario en la comparación final; las matrices de los pasos son ×1 (y ×3 solo `faults` para el paso 3). Con T=0 sigue habiendo variación (F3 falló 1 de 3 en la base del paso 3, y la ventana de F2 pasó de 0 de 3 a 3 de 3 cortas entre dos series con el mismo texto de prompt), así que la comparación 14.3 final → 14.4 final de los contadores de F2 (`checks≠tools`, mezcla ahora/ventana) mezcla el efecto de los pasos con esa variación.
- Cada paso se comparó con **una** repetición de su base, salvo el 3 (base ×3).
- La prueba de robustez usa una sola variante de skill (la a del paso 1 de la 14.3); la a del paso 2 (`e14-3-textos`, que también la rompió 1 de 1) no se ha repetido.
- Las medidas de texto son léxicas y en inglés; `false_radar_unavailable` solo ve frases en presente con las construcciones listadas.
- No probé el salto del módulo con la memoria A ni con el modo guiado, ni con el 32B.

## Qué queda
- **Tu decisión:** cerrar la Fase 14, el modelo por defecto (con la rúbrica) y la corrección de la ventana corta de la pérdida del GPS (decisión 2).
- `docs/mejoras_futuras.md`: el segundo salto brusco con el engaño en marcha, los chats que no ven el salto del módulo, la ventana corta de `GPS_DEGRADED`, la frase de recuperación de F2 con «ahora/ventana» (ya anotados) y los pendientes de la Fase 14 de abajo.
- E5 (modelo de Claude como juez con `docs/rubrica_textos.md`).

## Resumen de la Fase 14

**Tabla de `actual`, de la 14.1 a la 14.4** (todas las medidas de texto con la definición final de `text_metrics.py`, remedidas; 14.1 es ×1 y las demás ×3; entre paréntesis, el rango entre repeticiones):

| | 14.1 (×1, `e14-1-informe`) | 14.2 (×3, `e14-2-final-actual`) | 14.3 (×3, `e14-3-final`) | 14.4 (×3, `e14-4-final`) |
|---|---|---|---|---|
| Etiquetas ✅ | 9/9 | 26/27 (F3 2/3) | 27/27 | 27/27 |
| Rechazos (llamadas) | 11 | 63 (21,0 por serie) | 46 (15,3) | 40 (13,3) |
| Iteraciones p50 / p95 / máx | 4 / 6 / 6 | 4 / 8,6 / 11 | 4 / 8 / 9 | 4 / 8 / 9 |
| Pico de prompt monitor / informe | 7 537 / 2 498 | 9 548 / 3 090 | 9 587 / 3 477 | 8 605 / 3 522 |
| Prompt por ejecución (media) | 90 483 | 124 623 | 112 990 | 115 775 |
| Veto del reconocimiento | 0 | 11 | 6 | 9 |
| Recuperaciones sin fase | 0 | 0 | 0 | 0 |
| `checks≠tools` / contradicciones / falsas alarmas / fallbacks | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Fugas | 6 | 5,7 (5–7) | 4,0 (2–5) | 5,7 (4–7) |
| Errores | 5 | 1,7 (1–2) | 0,3 (0–1) | 0,7 (0–1) |
| Genéricas / sin acción | 5 / 14 | 2,0 / 9,3 | 1,7 / 8,3 | 2,7 / 9,3 |
| Mezcla ahora/ventana | 2 | 0,7 (0–1) | 0 | 1,3 (0–2) |
| Coinciden sin fix | 1 | 1,0 | 0 | 0 |
| Radar falso | 0 | 0 | 0 | 0 |
| Ajenas en el cierre | 4 | 2,0 (1–3) | 2,3 (1–3) | 0,3 (0–1) |
| Cierre sin dato de la causa | 2 | 2,0 | 0 | 0 |
| Jerga del monitor | 3 | 0,7 | 1,3 | 0,3 |
| Cifras sin respaldo / hora de recuperación ≠ | 0 / 0 | 0 / 0,7 | 0,3 / 0 | 0,7 / 0,3 |

(El «radar falso» de las series anteriores a la 14.4 se midió con el contador nuevo y sale 0 porque en esas series la repetición medida (r1) tenía ventana larga, salvo en `e14-3-informe`, donde sí lo da 1.)

**Qué ayudas y reglas nuevas quedaron en la Fase 14** (con su interruptor en `agents.yaml`; sin la clave, apagado, para los assets congelados `agent-assets-v13`):
- **14.1:** bloque `now` de `get_track_metrics` (`monitor.now_facts`); criterio de severidad y confianza en `monitor_output.md` y skills sin valores por rama (sin interruptor; en git); plantillas del monitor por criterio; informe de misión con anexo de autoevaluación (dos llamadas: `report.annex_*`); `state_line: data` medido y no adoptado.
- **14.2:** fase de la alerta (contrato v0.14, sin interruptor), `state_line: phase` (`monitor.state_line`), veto del reconocimiento de la recuperación (`monitor.recovery_ack_veto`), `operational_knowledge.md` (marcador, sin interruptor), el informe de misión nombra cada anomalía.
- **14.3:** `now.gps_fix` (contrato v0.15, sin interruptor), criterio de severidad de la recuperación y cierres según la causa (sin interruptor; en git), informe con las horas de entrada en recuperación y cierre por separado, `state_line: recovery_data` medido y **no adoptado** (apagado).
- **14.4:** `monitor.fill_link_anomalous`, `monitor.recovery_jump_from_module` y `source-discrepancy` paso 1 (sin interruptor; en git).

**Pasa a `docs/mejoras_futuras.md`** (ya anotado ahí o en `quien_decide_que.md`):
1. Un segundo salto brusco con el engaño en marcha, después de la alerta, se marca `recovering` (exigir `now.gps_radar_agree`).
2. Los chats no ven el salto del módulo (`last_metrics` es lo que pidió el modelo).
3. El 14B pide `since` = la detección en la primera alerta de la pérdida del GPS (intermitente, 3 de 3 en la serie final): corregirlo en el módulo o que `radar_available` mire la última muestra (cambia el contrato).
4. «GPS and radar disagree (distance 5.1 m)» en la recuperación de F2.
5. F3 (silencio del GPS) con la alerta de la pérdida en `recovering`: regla del guardrail para `SOURCE_SILENT` del GPS (falló 1 de 3 en la base del paso 3, 0 de 15 en el resto de la 14.4).
6. gpt-oss: ids equivocados al reconocer o cerrar (14 en la 14.4; 12 iteraciones en una invocación), el secuestro que empieza en `medium`, U+2011 en el texto libre.
7. Acciones inventadas sin cifra en las recomendaciones del informe y recomendaciones de la recuperación poco útiles (rúbrica).
8. Cierres de un spoofing que nombran el viento y cierres de otras causas con la frase genérica (resueltos en parte en la 14.3 y 14.4; falta ×3 con más escenarios).
9. Margen de contexto del 32B (pico del 14B 8 605, del 32B 7 843 frente a 10 240) y la memoria A con la ventana de 20 s ×3.

## Documentos actualizados
`docs/quien_decide_que.md` (cabecera, §1 guardrails, orquestación y evaluación, §2 recuperación, §3 tres ayudas nuevas, §6), `docs/mejoras_futuras.md` (dos entradas marcadas hechas y las nuevas) y `ai-module-py/CLAUDE.md`. Contrastado `quien_decide_que.md` con el código: **cambia quién decide la fase (con datos que pide el propio módulo) y el módulo rellena `link_anomalous`; no cambia quién decide la causa ni la severidad**.

## URLs consultadas
Ninguna (solo código y documentación locales).

## Ficheros
Nuevos: `ai-module-py/tests/test_link_fill.py`, `ai-module-py/tests/test_module_jump.py`, `model-profiles/actual-sin-salto-modulo.yaml`, `docs/fases/fase14_4.md`, `experiments/e14-4-*` (matrices, medidas y `e14-4-textos.md`; solo se versionan los `compare.md`). Modificados: `agent-assets/{agents.yaml,skills/source-discrepancy/SKILL.md}`, `ai-module-py/src/ai_module/{monitor,monitor_state,evaluate,compare,report_facts}.py`, `agent/{guardrails,assets,profiles,trace}.py` y sus tests, `tools/experiments/text_metrics.py`, `docs/quien_decide_que.md`, `docs/mejoras_futuras.md`, `ai-module-py/CLAUDE.md`. **Los ficheros de `runs/` no cambian** (no se tocó el generador ni los escenarios) y el contrato tampoco.

## Copias (reglas 13 y 15)
En `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`: `docs/fases/` (`diff -rq docs/fases results/docs/fases` sin diferencias), `docs/{quien_decide_que,mejoras_futuras,rubrica_textos}.md`, `experiments/` (`e14-4-textos.md`, las medidas `e14-4-*-textos-medida.{md,json}`, los `compare.md` y los 75 `eval.md` y 75 `informe.md` de las matrices de la fase, con su estructura de carpetas), los PNG de `runs/*/` (sin cambios), `snapshots/fase14_4/` (476 ficheros) y `snapshots-limpias/fase14_4/` (430 ficheros). **Quitado `results/docs/fases/quien_decide_que.md`** (copia vieja del 04/11 con el estado de la 14.2; la buena está en `results/docs/quien_decide_que.md`). No hay capturas nuevas: la web no cambia.

## Instantánea limpia
Las dos comprobaciones de la regla 15 (palabras prohibidas y nombres propios) **salen vacías a la primera**; no hubo que corregir ningún fichero.

## Estado al terminar
`serve.sh stop` ejecutado (y por `run_matrix` al final de cada matriz); puertos 8000 y 8100 libres, GPU a 0 MiB (la cifra de reposo de `serve.sh` es 0 MiB en esta sesión); ningún servidor lanzado por mí queda en marcha. Pruebas: módulo de IA 578 pasadas; `ruff check` y `ruff format --check` limpios; `git diff -- agent-assets-v13` vacío.

## Mensaje de commit propuesto
```
feat: phase 14.4 - link_anomalous filled by the module, recovery phase from the module's GPS jump

monitor.fill_link_anomalous: when the model has looked at the link and leaves
checks.link_anomalous null (or omits it), the module sets the expected value
instead of rejecting the call; a different declared value is still rejected and
nothing is filled without a look at the link.

monitor.recovery_jump_from_module: for a ROUTE_DEVIATION with a recent GPS alert
the module asks get_track_metrics itself, with a fixed window (30 s before the
detection, never before the first alert of the GPS chain), and the guardrail
decides the recovering phase, the severity limit and the acknowledgement veto
with that GPS jump instead of the window the model asked for; if the call
fails the previous criterion applies. Traces, eval.md and compare.md count the
module's jumps and the filled fields.

source-discrepancy step 1 no longer lets the model read radar_available: false
(a window without radar samples) as a silent radar; text_metrics counts
false_radar_unavailable. Phase 14 summary and final comparison against
gpt-oss-20b in docs/fases/fase14_4.md.
```
