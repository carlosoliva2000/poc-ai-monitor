# Fase 14.3 · Correcciones de la 14.2, margen de iteraciones y gpt-oss ×3 (05/11/2026)

Escrito para: Carlos, que decide qué se queda de la 14.3 y qué modelo es el de por defecto (con la rúbrica, sobre `experiments/e14-3-textos.md`). Perfil `actual` (Qwen3-14B-AWQ sin razonamiento, T=0). Base: `experiments/e14-2-informe/` (huella de `agent-assets` `4dc777667d2fd8a5`). **Contrato: un cambio aditivo (v0.15, el campo `now.gps_fix`).** `agent-assets-v13/` no se ha tocado (`git diff` vacío). No se arrancó ningún híbrido; vLLM, plataforma y módulo quedaron parados (puertos 8000 y 8100 libres, GPU a 0 MiB). Git solo de lectura. **No se ha cambiado el modelo por defecto.**

**Huella final de `agent-assets`: `d358e3d292c769e0`.** Pruebas: módulo de IA 541 (504 al empezar), plataforma 230 (225), contratos 130 (+1 omitida); `ruff check` y `ruff format --check` limpios. La web no se ha tocado (el cambio de contrato es aditivo y la web no usa `now`). El agente `revisor-contratos` pasó sobre la v0.15 sin incumplimientos (ver «Revisor de contratos»).

## Resumen

| Paso | Qué se cambió | Huella | Evaluación frente a su base | Medida del paso (contador propio) | Decisión |
|---|---|---|---|---|---|
| 0 · medidas | columna de iteraciones en `compare.py`; `now_window_mix` y las cifras aceptan «meters»/«metres» y «disagree (distance N m)» | – | – | mezcla del 32B 0 → 1 y errores 2 → 3 con la definición nueva; `actual` y gpt-oss no cambian | hecho |
| 1 · `now` sin fix | contrato v0.15 (`gps_fix`; sin fix, distancia, «coinciden» y desviación del GPS a `null`); frase en `source-discrepancy` | `1e30ccc46cb541a1` | 6/6 (F3 incluida), todo a 0, 3 recuperaciones con fase | `agree_without_fix` 1 → 0 | **adoptado** (variante c, tras 3 variantes) |
| 1b · estado como dato | `state_line: recovery_data` (el módulo da el salto en el estado) | `8bdc63bfdedb15f6` | igual | rechazos 19 → 20; iteraciones máx. de `spoofing` 7 → 9 y `faults` 8 → 9; fugas 3 → 6 | **no adoptado** (revertido; el estilo queda disponible, apagado) |
| 2 · severidad y cierres | criterio de severidad de la recuperación en `monitor_output.md`; cierre según la causa y enlace en el cierre de un secuestro | `a6569814240d40e7` | 6/6, todo a 0 | `close_without_cause_source` 2 → 0 | **adoptado** (variante b, tras una variante con recuperación sin fase) |
| 3 · informe | horas de recuperación y cierre por separado, desviación y salto con nombres distintos, recomendaciones solo con respaldo | `d358e3d292c769e0` | 6/6, todo a 0 | `recovery_time_mismatch` 1 → 0 (14.2: 2); `unsupported_figures` 0 → 1 (muestra suelta) | **adoptado** |

## Para decidir

1. **Modelo por defecto** (no se ha tocado). En `e14-3-textos.md` tienes `demo` y `faults` (r1) de `actual` y gpt-oss con su antes de la 14.2, para la rúbrica. Datos duros con ×3: `actual` 3/3 en todas las etiquetas (F3 incluida) y gpt-oss con 1 fallo en 18 (F1 en la r3: el radar mudo como `UNKNOWN`). Tabla final más abajo.
2. **Una propuesta que no he hecho (cambia un guardrail): que el módulo rellene `checks.link_anomalous`.** El modelo mira el enlace y aun así declara `null`; el guardrail lo rechaza («does not match the link events you requested (false)») y eso son **19 de los 52 rechazos de `actual`** (9 en las 9 recuperaciones, uno por recuperación, y 10 en otras alertas: el viento, un silencio del GPS…) y 5 de los 19 de gpt-oss: un rechazo y una iteración cada vez. El módulo ya calcula el valor esperado; si lo rellenara cuando el modelo miró el enlace (como ya hace con los ids), desaparecería. Lo he anotado en `docs/mejoras_futuras.md`.
3. **El texto de la skill `route-deviation` mueve la ventana de la recuperación.** El criterio de la fase depende de la ventana que pide el modelo (`gps_max_step_m` ≥ 30). Con la ventana de la skill («detección − 30») nunca falló (0 de 13 recuperaciones medidas); **cada vez que cambié el texto de esa skill** (paso 1 variante a: 3 de 3; paso 2 variante a: 1 de 1) el 14B pidió `since` = el instante de la detección, la ventana no vio el salto y la recuperación se quedó sin fase (`window_without_jump`). Lo resolví **no tocando esa skill** (ver pasos 1 y 2), pero es frágil: la opción robusta sería que el guardrail usara el salto que calcula el módulo (lo que midió el 1b) y eso es un cambio de decisión que no he hecho.
4. **Un efecto secundario del paso 1 que no he corregido:** con `now` a `null` por el GPS sin fix, la primera alerta de F2 dejó de decir «GPS and radar agree now» pero dice «**The radar is unavailable**, so we cannot confirm the actual position of the drone» (falso: el radar estaba bien). Ninguna medida lo ve. Está en `mejoras_futuras.md`.
5. **La `low` de la recuperación (Revisión §7.2) no se reproduce** con los assets de partida del paso 2: `demo` A2 ya salía `medium` en `e14-3-now-c` y sale `medium` en las 3 repeticiones finales de `actual` y de gpt-oss. No puedo atribuir al criterio nuevo que sea `medium`; el criterio es coherente con lo que sale (74 m de la ruta → `medium`), pero no está probado con un caso en el que antes saliera `low`.
6. **gpt-oss:** 293 caracteres U+2011 en su texto libre, **63 dentro de ids** (`AgentReply` 28, `ReportGenerated` 31, `AlertClosed` 3, `AnomalyDetected` 1); `actual` ninguno. Sin normalizar, como pediste. Ninguno de sus 19 rechazos es de la fase ni del veto.

## Cómo se ejecuta
- Matriz: `uv run --project ai-module-py python tools/experiments/run_matrix.py --profiles actual,gpt-oss-20b-low --scenarios nominal,wind,spoofing,hijack,faults,demo --reps 3 --id e14-3-final`; comparar: `uv run --project ai-module-py python -m ai_module.compare experiments/<id>` (ahora con la columna «Iteraciones monitor p50 / p95 / máx»).
- Medida de textos: `uv run --project ai-module-py python tools/experiments/text_metrics.py nombre=experiments/<id>:<perfil> … --out experiments/<nombre>.md` (`--rep N`). Textos para leer: `tools/experiments/texts.py` (`experiments/e14-3-textos.md`).
- Copias exactas de cada paso, fuera de git: `~/poc-backups/fase14_3/{base,paso0,paso1,paso1c,paso1b,paso1b-codigo,paso2-previo,paso2,paso3-previo,paso3}/`.
- Cada matriz de seis escenarios ×1 tarda ~9 minutos de pared (los seis escenarios suman ~524 s), más 1–2 de carga del modelo; la final (36 ejecuciones) ~55 minutos.

## Paso 0 · Medidas sin tocar el agente

**Margen de iteraciones** (trazas de las invocaciones del monitor con LLM; `max_iterations: 12`, `max_invocation_s: 60`):

| Serie | Invocaciones | Iteraciones p50/p95/máx | Tiempo p50/p95/máx (s) | ≥ 9 iteraciones |
|---|---|---|---|---|
| Fase 8 (B0) | – | 4 / – / 7 | 7,2 / 12,9 (p50/p95) | 0 |
| 14.1 (`e14-1-informe`, ×1) | 25 | 4 / 6 / 6 | 7,4 / 13,8 / 16,7 | 0 |
| **14.2 `actual` ×3** | 75 | 4 / 10 / **11** | 7,6 / 25,9 / 28,6 | **4** |
| 14.2 qwen3-32b ×1 | 25 | 4 / 7 / 7 | 15,2 / 37,5 / 46,0 | 0 |
| 14.2 gpt-oss ×1 | 25 | 4 / 5 / 5 | 8,3 / 15,9 / 17,3 | 0 |
| 14.3 `actual` ×3 (final) | 75 | 4 / 8 / 9 | 7,4 / 20,9 / 25,7 | 3 |
| 14.3 gpt-oss ×3 (final) | 75 | 3 / 7 / 8 | 7,8 / 17,6 / 26,5 | 0 |

Por escenario, `actual` ×3 de la 14.2: `wind` 2/5/5, `spoofing` 4/**11**/11, `hijack` 4/6/6, `faults` 4/8/8, `demo` 4/10/10 (la tabla completa, por serie y escenario, sale de `compare.md`). **Las 4 invocaciones de 9 o más iteraciones eran todas la recuperación de T+03:42** (`spoofing` r1 y r2 con 11 y 6 rechazos; `demo` r2 y r3 con 10 y 3), con la misma secuencia: `load_skill → get_track_metrics → get_events → publish_alert` rechazado («ai-0001 (GPS_SPOOFING) is open: use supersedes…») `→ acknowledge_detection` vetado `→ publish_alert` rechazado por `link_anomalous = null` `→ publish_alert`. Con 12 iteraciones de tope, la de `spoofing` dejaba **una sola de margen**. El tiempo no era el límite (máximo 28,6 s frente a 60 s). En la 14.3 el máximo de `actual` baja a 9 (3 invocaciones, todas la recuperación de `demo`).

**`now_window_mix` no veía el caso del 32B.** Causa: las expresiones de la medida solo aceptaban la unidad «m» (`m\b(?!/)`), y el 32B escribe «9.9 **meters**»: con «m» el contador sí salta, con «meters» no. Arreglado con una unidad común (`METRES`: `m`, `meter(s)`, `metre(s)`, sin «m/s»), que afecta también a `DISAGREE_RE`, `DIST_RE` (`gps_radar_distance`) y `DEV_RE` (`deviation`): **los errores de cifra del 32B también estaban subestimados**. Con el test de esa frase y de «meters»/«metres». Más adelante (paso 1) amplié `DISAGREE_RE` a «disagree (distance N m)», la forma que escribió `actual` en una recuperación de F2.

**Todas las tablas de la 14.2 remedidas con la definición final** (`experiments/e14-3-remedida-*.md`): `actual` ×3 no cambia (no escribe «meters»); gpt-oss no cambia en fugas, errores ni mezcla; el **32B pasa de 0 a 1 en mezcla ahora/ventana y de 2 a 3 en errores** (la frase de `demo` A2 «GPS and radar disagree by 9.9 meters, suggesting the GPS position is unreliable»). Las columnas nuevas (`close_without_cause_source`, `recovery_time_mismatch`, `unsupported_figures`, `agree_without_fix`) también se midieron sobre las series de la 14.2 para tener su «antes».

## Paso 1 · `now` con el GPS sin fix

**Lo que dijo la traza** (`faults` r1, `e14-2-final-actual`; GPS con `fix: none` de 245 a 290 s):

| Invocación | `now` (14.2) | Qué dijo el texto | De dónde viene |
|---|---|---|---|
| T+04:05 (245,8 s), alerta | distancia 2,8 m, `agree: true`, desviación del GPS 2,5 m | «GPS and radar agree now, but the GPS is degraded» | **`now` mentía**: posición estimada frente al radar; la ventana (40 s antes de la pérdida) tampoco discrepaba |
| T+04:18 (258,8 s), reconocimiento | `now`: 34,0 m, `agree: false` | «GPS and radar differ by 26.2 m» | **no viene de `now`**: es el mensaje del detector (media de 3 medidas) |
| T+05:20 (320 s), cierre | `now` con fix: 8,8 m | «distance 0 m» | **no viene de `now`**: lo escribió mal el modelo (`now` daba 8,8 m, ya con fix) |

Así que `_now_facts` calculaba `gps_radar_distance_m` y `gps_radar_agree` con la última `PositionUpdated` sin mirar el `fix`, como decía la Revisión; pero **solo la primera de las tres frases salía de ahí**. (La posición que publica el GPS sin fix es la estimación a estima: `fix: none`, 0 satélites, hdop 99,9.)

**Contrato v0.15 (aditivo, `eventos.md`, `NowFacts`, esquemas, `tools.json`, plataforma y tests en el mismo cambio):** `now.gps_fix` (`none`|`2d`|`3d`|`null`). **Sin fix en la última posición:** `gps_radar_distance_m`, `gps_radar_agree` y `gps_deviation_from_plan_m` salen `null` (la del radar se queda, decisión tuya) y, al interpolar el GPS para comparar con el radar, se descartan las posiciones sin fix. Cinco tests nuevos en `platform/tests/test_tools.py` (con fix; sin fix; vuelve el fix; los agregados de la ventana no dependen del fix; GPS mudo).

**Lo que encontré del GPS sin fix en la ventana (descrito, no cambiado).** Los agregados de la ventana usan **todas** las posiciones, también las estimadas: `gps_radar.disagreed`, `gps_max_step_m`, `drift_direction_deg`, `course_deg` y las medias de desviación. En F2 (`as_of` 258,8 s) la ventana dice `disagreed: true` (34 m) y una desviación del GPS media de 3,2 m y máxima de 8,0 m con el radar a 33–86 m: es la desviación de una posición estimada. Efecto en la recuperación de F2 (el salto de 90 m): **`gps_max_step_m` = 90,0 es la diferencia entre la desviación estimada (0,6 m) y la real (90,2 m) cuando el GPS vuelve de golpe**, y de él salen la fase `recovering`, el veto y la causa impuesta por el guardrail. Si la ventana descartara las posiciones sin fix, `_max_step` (que solo compara muestras a ≤ 1,5 s) no tendría pareja que comparar a través de un hueco de 45 s y daría `null`: **la recuperación de F2 perdería la fase y el veto**. No lo he probado ni lo he cambiado; lo decides tú.

**Matriz (cuatro, no una):**

| Matriz | Cambio | Resultado |
|---|---|---|
| `e14-3-now` (`11230dc56ed275d3`) | contrato + frase «sin fix» en las dos skills | 6/6 pero **`spoofing`: 1 recuperación sin fase** (`window_without_jump`): el 14B pidió `since=222.0` en vez de «detección − 30» |
| `e14-3-now-spoof3` (misma huella, ×3) | repetir `spoofing` | **3 de 3 sin fase** (`since=222.0` las tres): no es ruido; con fix `3d` en `spoofing`, `now` es idéntico salvo el campo nuevo, así que la causa es el texto añadido |
| `e14-3-now-b` (`fbcbd5c12e44ac47`) | sin la frase en las skills | recuperaciones bien, pero **F3 ❌** (`GPS_JAMMING` en vez de `SENSOR_FAULT`, el fallo conocido de la 14.2 r1) y el contador propio sigue en 1 |
| `e14-3-now-c` (`1e30ccc46cb541a1`) | frase **solo en `source-discrepancy`** | **6/6 con F3, todo a 0, 3 recuperaciones con fase**; rechazos 1/3/2/7/6 (19, frente a 21 en la base); iteraciones máx. 5/7/6/8/9 |

**Antes y después de los textos de F2** (`faults` r1; base `e14-2-informe`):
- Alerta T+04:05. *Antes:* «The GPS has lost its fix (hdop 99.9, 0 satellites) at T+04:05. The wind is blowing from NW (301°)… **GPS and radar agree now, but the GPS is degraded.**» *Después (`now-c`):* «At T+04:05, the GPS reported a high hdop of 99.9 with no satellite fix, indicating a loss of GPS signal. **The radar is unavailable, so we cannot confirm the actual position of the drone.**» (el «agree now» desaparece; aparece el falso «radar unavailable», ver «Para decidir» 4).
- Reconocimiento T+04:18: *antes y después* repite el mensaje del detector («GPS and radar differ by 26.2 m (mean of the last 3 measurements)…»): no era de `now`.
- Cierre T+05:20. *Antes:* «GPS and radar now agree (**distance 0 m**)…». *Después (`now-c`):* «GPS signal has fully recovered; GPS and radar now agree (distance 8.8 m)…» (la cifra coincide con `now`; es un acierto de esa repetición, no del código).

**Medida** (`e14-3-now-textos-medida.md`, definición final): base `e14-2-informe` → adoptado `now-c`: fugas 4 → 3, errores 1 → 2, mezcla 0 → 1, **`agree_without_fix` 1 → 0**. Los errores y la mezcla suben por la misma frase («GPS and radar disagree (distance 5.1 m)» en la recuperación de F2, con `now` diciendo que coinciden), dentro del ruido medido en la 14.2 (±1 error, 0–1 de mezcla). **Decisión: adoptado** (variante c).

## Paso 1b · Estado de la recuperación como dato (no adoptado)

**Qué se hizo.** `state_line: recovery_data` (`monitor_state.describe_gps_alert`; `Monitor._state_metrics` en `monitor.py`): ante un `ROUTE_DEVIATION` (`raised`/`updated`) con la alerta del GPS abierta y activa, el módulo pide `get_track_metrics` a la plataforma antes de la primera llamada al modelo (ventana de la skill: `since` = hora del aviso − 30, `until` = `as_of`, con el corte temporal, sin LLM, fuera de las iteraciones y dentro de `duration_s`) y la línea dice solo datos: *«yes — ai-0001 GPS_SPOOFING (open, active); GPS jump 67.9 m; replaces ai-0001»* (sin umbral, sin nombres de campo, sin frases copiables; test con la lista de `text_metrics`). La traza guarda `state_metrics` (ventana, salto y, al acabar, `guardrail_view`: `jump`, `window_without_jump` o `no_metrics`); `eval.md` y `compare.md` cuentan aparte «estado con salto N, guardrail sin verlo M». **No cambia ningún guardrail.** Si falla la llamada, el estado sale sin salto y se anota. Tests nuevos en `test_state_recovery.py` (12), `test_evaluate.py` (2) y `test_compare.py` (1).

**Resultado (`e14-3-estado`, huella `8bdc63bfdedb15f6`), frente a `e14-3-now-c`:** evaluación 6/6, todo a 0, 3 recuperaciones con fase. **Saltos que el guardrail no veía: 0 de 3** (no hizo falta parar). **Pero el objetivo no se cumple:** rechazos 19 → 20 (`spoofing` 3 → 3, `demo` 6 → 6, `faults` 7 → 8), iteraciones máximas `spoofing` 7 → 9, `demo` 9 → 9, `faults` 8 → 9; fugas 3 → 6 (fuera del ruido ±2). **El 14B ignora la línea:** en las tres recuperaciones publica primero sin `supersedes` («ai-0001 (GPS_SPOOFING) is open: use supersedes…»), intenta reconocer (veto) y publica con `link_anomalous = null` (rechazo), exactamente la secuencia de antes. **Decisión: no adoptado**, `agents.yaml` restaurado a `state_line: phase` (huella `1e30ccc46cb541a1`); el estilo queda en el código, apagado y probado, como `data` en la 14.1.

## Paso 2 · Severidad de la recuperación y cierres según la causa

**Qué se cambió** (antes → después):
- `monitor_output.md`, párrafo «Phase»: *«…so in a recovery it is `low` or `medium`, never `high`.»* → *«…never `high`. In a recovery the severity is the risk now: while the drone is still far from the route there is something to watch (`medium`); when it is already close to the route and GPS and radar agree, watching is enough (`low`).»* **No se tocó la skill `route-deviation`** (la variante a sí, y rompió la ventana: ver abajo).
- `monitor_objective.md`, sección `cleared`: *«…close with `close_alert` and say what went back to normal and with which figure (the current ones); do not talk about sources that have nothing to do with the cause…»* → se añade *«If the alert was a hijacking, also look at the command link with `get_events` (`source` `link`, `last_n` 3)»* (hasta ahora el cierre solo pedía `get_track_metrics`, así que el modelo **no tenía datos del enlace** al cerrar un secuestro) y *«say what went back to normal **for the cause of the alert**, with its current figure: for a hijacking, the command link (whose controller is in charge again, latency and signal strength); for a GPS deception or loss, that GPS and radar agree and how far the drone is from the route; for a sensor fault, that the sensor reports again; for wind, the wind and the deviation»*.
- `text_metrics.py`: `close_without_cause_source` (solo `AlertClosed`, no reconocimientos): un `HIJACK` sin el enlace o el controlador, una causa del GPS sin GPS y radar, un `SENSOR_FAULT` sin que el sensor vuelve a informar; con tests.

**Matrices:** `e14-3-textos` (variante a, con la frase también en `route-deviation`, `0839c32e0fb3b5fc`): cierres bien (`close_without_cause_source` 2 → 0), pero **`spoofing`: 1 recuperación sin fase** (`since=222.0`, la segunda vez). `e14-3-textos-b` (**adoptada**, `a6569814240d40e7`): 6/6 con F3, todo a 0, 3 recuperaciones con fase; rechazos 1/1/2/6/5 (15, frente a 19); iteraciones máx. 5/5/5/8/9 (`spoofing` 7 → 5).

**Medida frente a `e14-3-now-c`:** **`close_without_cause_source` 2 → 0**; fugas 3 → 3; errores 2 → 0; mezcla 1 → 0; fuentes ajenas en el cierre 1 → 2 (ruido: 1–3 en la 14.2); genéricas 3 → 4; sin acción 9 → 10; jerga del monitor 0 → 2.

**Antes y después (`actual` r1):**
- **`demo` A2 (severidad y texto):** `medium` en las dos; *antes* «GPS has recovered from spoofing; GPS and radar now agree.» → *después* «GPS has jumped back to real position; GPS and radar now agree.» El criterio no cambió la severidad (ver «Para decidir» 5).
- **Cierre de A3 (secuestro, `demo`):** *antes* «…the deviation from the route has decreased to 3.2 m (GPS) and 4.9 m (radar), and GPS and radar now agree. The situation has returned to normal.» → *después* «…GPS and radar now agree (distance 3.4 m)… **The command link shows stable performance with controller_id GCS-1, RSSI -63.6 dBm, and latency 51.8 ms.** The hijacking alert is closed…» (nombra el enlace; filtra el campo `controller_id`, una fuga).
- **Cierre de A2 (`demo`):** *antes* «GPS has recovered from spoofing; GPS and radar now agree. Current GPS deviation is 2.9 m, and GPS and radar agree (distance 9.2 m).» → *después* «GPS has returned to real position; GPS and radar now agree. Current GPS deviation from route is 2.9 m, and GPS fix is 3D. **Wind is from NW (299°), pushing SE, but it is not notable.**» (el viento ajeno sigue colándose en un cierre de spoofing).
- **`hijack`:** *antes* «The GPS and radar now agree (distance 3.4 m), and the deviation… The situation has returned to normal.» → *después* «…**The command link shows stable performance with RSSI -63.6 dBm and latency 51.8 ms at T+07:20.** The hijacking alert can be closed…».
- **`spoofing`:** *antes* «GPS has recovered from spoofing; GPS and radar now agree. Current GPS deviation is 5.7 m, and GPS and radar agree (distance 9.2 m).» → *después* «GPS has recovered from spoofing; GPS and radar now agree, and the drone is 5.7 m off route.» (sin viento).

**Decisión: adoptado** (variante b).

## Paso 3 · Informe de misión: hechos y recomendaciones

**Qué recibía el agente de informe y qué faltaba.** `anomalies_for_llm(mission=True)` quita a propósito la hora de cada alerta (no hay retrasos que comentar) y daba solo «detection at T+03:12 … closed by the monitor at T+03:54»: **la hora de entrada en recuperación (T+03:42) no estaba en el prompt**, así que el modelo tomó la del cierre («entered recovery by T+03:54»). Tampoco recibía el salto del GPS (`gps_max_step_m`) con nombre propio; solo la desviación del detector.

**Qué se cambió:**
- `report_facts.py`: `Anomaly.recovery_at` (primera alerta `recovering` de la cadena), `Anomaly.max_route_deviation_m` (máximo de sus `ROUTE_DEVIATION`) y `recovery_jump_m(records, alert_id)` (el salto que vio el monitor al publicar la recuperación, de la traza; **sin tocar contratos**). `anomalies_for_llm(mission=True, records=…)` añade por anomalía: *«- Times: detected at T+03:12; entered recovery at T+03:42; closed at T+03:54.»*, *«- Largest distance from the planned route seen by the detector: 73.9 m.»* y *«- GPS position jump when the GPS came back: 67.9 m (how far the GPS position moved at once; it is not a distance from the route).»* El anexo (autoevaluación) no las recibe. Cuatro tests.
- `report_system.md`: regla 8 *«…Do not present the figures of an anomaly as the state of the drone at the end.»* → *«…Use the time the data gives for each event: entering recovery and closing are two different times. The jump of the GPS (how far its position moved at once when it came back) and the distance from the route are two different figures.»* Regla nueva 10: *«A recommendation may use only figures that appear in the data above or in the notes below, and may rely only on what the data of the flight or those notes support. Do not set thresholds, limits or deadlines of your own, and do not recommend checking or repairing something that nothing in the data points to.»* (criterio, sin ejemplos; de paso, la numeración repetida «8.» pasa a 10 y 11). `report_objective.md` y la skill `report-format`: la misma idea en una frase.
- `text_metrics.py`: `unsupported_figures` (cifras con unidad en las `Recommendations` que no están en lo que recibió la llamada del informe de misión; un entero tras «about/around…» vale si redondea una cifra recibida) y `recovery_time_mismatch` (en el Summary, la hora del cierre dada como entrada en recuperación). Con tests. **Lo que no ve:** acciones inventadas sin cifra («firmware», «encryption», «physical damage»): eso es de la rúbrica. Sobre los informes de la 14.2 el contador marca el «10 m» de gpt-oss en `demo` y un «120 m» en `nominal`; el «7 m/s» que citabas no salta (el dato ya traía una cifra igual).

**Un matiz a la Revisión.** «route deviation of 90.2 m» en `faults` **no es un error**: la desviación real era 90,2 m (el radar daba 93,1 m); lo que no es una desviación es el salto del GPS (90,0 m). Por eso doy las dos cifras con nombres distintos en vez de tratar los 90,2 m como un fallo.

**Matriz `e14-3-informe` (`d358e3d292c769e0`, frente a `e14-3-textos-b`):** 6/6 con F3, todo a 0, 3 recuperaciones con fase; rechazos 1/1/2/8/5 (17); iteraciones máx. 5/5/5/9/9.

**Medida (informe y alertas, `e14-3-informe-textos-medida.md`):** **`recovery_time_mismatch` 1 → 0** (14.2: 2); `unsupported_figures` 0 → 1 (un `nominal` donde el modelo resta los recorridos totales del GPS y del radar —«the difference of 120.5 meters»— y lo toma por una discrepancia: muestra suelta, 0 en las 18 de la 14.2); genéricas 4 → 2; sin acción 10 → 8; jerga del monitor 2 → 1; Summary sin tipo 0 → 0. Las fugas y errores del total suben (3 → 5 y 0 → 2) **en los textos de las alertas, que el paso no toca** (alertas 1 → 3 fugas, 0 → 2 errores; informe 1 → 1 y 0 → 0).

**Antes y después, Summary y Recommendations (`demo` y `faults`, `actual` r1):**
- `demo`, Summary. *Antes (`e14-3-textos-b`):* «…a GPS spoofing incident (A2) starting at T+03:12, **ending in recovery by T+03:54**; and a potential hijacking (A3) detected at T+05:38, resolved by T+07:21…» *Después:* «…a GPS spoofing incident (A2) at T+03:12, **which entered recovery at T+03:42 and closed at T+03:54**; and a potential hijacking (A3) at T+05:38, resolved at T+07:21…»
- `demo`, Recommendations. *Antes:* «2. Confirm that GPS is functioning correctly following the spoofing incident, as the GPS position jumped significantly and then aligned with radar. Ensure the drone’s actual location matches the GPS reading to avoid future discrepancies.» *Después:* «2. Review the GPS recovery process after the spoofing incident (A2), as **the GPS position jumped 67.9 m when it returned**. Ensure that the drone’s navigation system can accurately reconcile such discrepancies with radar data.» (cifra correcta y con respaldo; sigue siendo una recomendación con poca acción).
- `faults`, Summary. *Antes:* «…A2 was GPS loss or interference, detected at T+04:05 and **resolved by T+05:20**, with a high severity during the episode…» *Después:* «…a GPS loss or interference (A2) starting at T+04:05, **entering recovery at T+04:50 and resolved by T+05:20**…» (T+04:50 es la entrada en recuperación y T+05:20 el cierre).
- `faults`, Recommendations. *Antes:* tres puntos («Verify the GPS signal integrity after the loss…», «Investigate the radar sensor fault in A1…», «Review the GPS update mechanism following A3… could indicate a delay or intermittent failure in the GPS communication system»). *Después:* dos («Verify the GPS signal stability and check for any interference or degradation, as GPS loss caused significant deviation…», «Confirm that the radar is functioning correctly, as it was the only reference during GPS outages…»): sin la causa técnica inventada de A3.

**Decisión: adoptado.**

## Comparación final (`e14-3-final`, huella `d358e3d292c769e0`; seis escenarios ×3)

**Evaluación** (suma de las tres repeticiones):

| | `actual` | gpt-oss-20b-low |
|---|---|---|
| Etiquetas ✅ | **27 de 27** | 26 de 27 (F1 ❌ en la r3: `UNKNOWN`, «Radar stopped reporting for 7 s, GPS still valid») |
| F3 (silencio del GPS) | 3 de 3 | 3 de 3 |
| Falsas alarmas / fallbacks / abiertas / contradicciones / checks≠tools | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| Recuperaciones sin fase | 0 | 0 |
| Veto del reconocimiento | 6 (3 `faults`, 3 `demo`) | 0 |
| Rechazos (llamadas) | **46** (15,3 por serie; 14.2: 23, 21 y 19) | **17** (5,7 por serie; 14.2: 8; E4a: 5) |
| Iteraciones p50 / p95 / máx | 4 / 8 / **9** (14.2: 4 / 10 / 11) | 3 / 7 / 8 |
| Tiempo por invocación p50 / p95 / máx (s) | 7,4 / 20,9 / 25,7 | 7,8 / 17,6 / 26,5 |
| Pico de prompt (monitor / informe), tokens | 9 587 / 3 477 (14.2: 9 548 / 3 090) | 7 517 / 3 454 |
| Estabilidad entre repeticiones | estable (3/3) en los seis | estable salvo `faults` (F1 `UNKNOWN` y F2 con otra confianza en la r3) |

**Rechazos por tipo.** `actual` (52 errores en 46 llamadas): `link_anomalous = null` 19; «Nothing changes… (same cause, severity and phase)» 9; «ai-XXXX (GPS_JAMMING/GPS_SPOOFING) is open: use supersedes…» 9; veto del reconocimiento de la recuperación 6; «detection… already in the open alert» 3; severidad `high` no cabe en la recuperación 3; fase equivocada («wrong phase… use recovering») 3. **gpt-oss** (19 errores en 17 llamadas; **ninguno es de la fase ni del veto**: 0 menciones a `phase` y 0 etiquetas de veto): `link_anomalous = null` 5; reconocer un `SOURCE_SILENT` («a SOURCE_SILENT warning is always a different fault and gets its own alert») 3; cierre con el `alert_id` de otra alerta 3; causa de la recuperación del GPS («expected cause X and supersedes Y») 4 (3 `GPS_SPOOFING`, 1 `GPS_JAMMING`: la regla de la recuperación de siempre, no la fase); «detection… already in the open alert» 1; `link_checked = true` sin haber mirado el enlace 1; llamada repetida 1; `WIND` sin viento notable 1.

**Textos con la definición final** (media y rango entre las tres repeticiones; el antes de `actual` es la 14.2 ×3 y el de gpt-oss la 14.2 ×1):

| | Fugas | Errores | Genéricas | Sin acción | Mezcla ahora/ventana | Coinciden sin fix | Ajenas en el cierre | Cierre sin dato de la causa | Resumen sin tipo | Jerga del monitor | Cifras sin respaldo | Hora de recuperación ≠ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` 14.2 ×3 | 5,7 (5–7) | 1,7 (1–2) | 2,0 (0–4) | 9,3 (8–10) | 0,7 (0–1) | 1,0 (1–1) | 2,0 (1–3) | 2,0 (2–2) | 0 | 0,7 (0–1) | 0 | 0,7 (0–2) |
| **`actual` 14.3 ×3** | **4,0 (2–5)** | **0,3 (0–1)** | 1,7 (1–2) | 8,3 (7–9) | **0** | **0** | 2,3 (1–3) | **0** | 0 | 1,3 (1–2) | 0,3 (0–1) | **0** |
| gpt-oss 14.2 ×1 | 7 | 0 | 2 | 8 | 0 | 1 | 0 | 3 | 0 | 2 | 2 | 2 |
| **gpt-oss 14.3 ×3** | 8,7 (7–12) | 0 | 3,3 (3–4) | 9,3 (8–10) | 0 | 1,0 (1–1) | 1,7 (1–2) | **0** | 0 | 3,0 (3–3) | 0,7 (0–2) | **0** |

`actual` mejora en errores, mezcla, «coinciden sin fix» y los dos contadores de los pasos 2 y 3; no cambia en fuentes ajenas ni en la jerga del monitor (ruido). gpt-oss mejora los dos contadores de los pasos 2 y 3 pero **no** el de «coinciden sin fix» (1 en cada repetición: sigue afirmando que GPS y radar coinciden en F2 aunque `now` ya no lo dice) y su jerga del monitor en las recomendaciones es 3 en las tres repeticiones.

**Severidad, confianza, fase y sustituciones por etiqueta** (`e14-3-final-r{1,2,3}-textos-medida.md`): en `actual` las nueve etiquetas salen **idénticas en las tres repeticiones** (viento `medium` 0,8; spoofing y pérdida de GPS `high` 0,8 → `medium` 0,8 `[recovering]` con 1 sustitución; secuestro `high` 0,7 sin sustituir; fallos de sensor `medium` 0,7). gpt-oss: mismas causas y recuperaciones `[recovering]` `medium` (confianza 0,8–0,9); **el secuestro empieza en `medium` y sube a `high` con una sustitución** en 4 de 6 casos (`demo` A3 y `hijack`, r1 y r2); `faults` F1 de la r3, `UNKNOWN` `medium` 0,6.

**F3 (solo anotar):** no ha fallado en ninguna repetición, ni con `actual` ni con gpt-oss (3 de 3). La única etiqueta fallada de la fase con `actual` fue F3 en `e14-3-now-b` (una variante no adoptada, ×1): `GPS_JAMMING` en vez de `SENSOR_FAULT`; de las 10 ejecuciones de `faults` de `actual` de la fase (matrices de los pasos y final) falló 1, y en las 3 de la final no.

**Textos para la rúbrica:** `experiments/e14-3-textos.md` (`demo` y `faults`, r1, de `actual` y gpt-oss con el antes de `e14-2-final-*`).

## Revisor de contratos
Una pasada, al cerrar el paso 3 (`revisor-contratos`; no tiene shell, así que `git diff --stat -- agent-assets-v13` y las pruebas las comprobé yo). **Sin incumplimientos.** Confirma: la v0.15 es coherente entre `eventos.md`, `NowFacts`, el esquema, `tools.json`, la plataforma y sus tests; ningún import de `platform/` en `ai-module-py`; la web no usa `now`; la verdad, las etiquetas y el dominio `sim` no salen de la evaluación y la plataforma; el corte temporal sigue; `_state_metrics` solo habla con la plataforma por la API de tools, está apagado con `state_line: phase` y no cambia ningún guardrail. Observaciones menores (corregidas): una frase torpe del párrafo de `now` en `eventos.md` (separada), `gps_radar_agree` sin «o el GPS no tiene fix» en esa cláusula (añadido) y los `CLAUDE.md` de `platform/` y `ai-module-py/` sin la v0.15 (actualizados).

## Problemas (con su error literal)
- `sleep 540 followed by: tail …` → `Blocked: sleep 540 followed by: tail -3 …. To wait for a condition, use Monitor with an until-loop`: usé `Monitor` con un `until` sobre la salida de la matriz.
- Mi primer monitor de espera usaba `pgrep -f "run_matrix.py … --id e14-3-now"`, que **se detectaba a sí mismo** (su propia línea de comandos lleva el patrón) y nunca terminaba: lo paré con `TaskStop` y pasé a vigilar la salida de la matriz.
- Un aviso de «completada» del lanzador de la primera matriz era el del envoltorio (`nohup … &`); la matriz seguía corriendo. Lo comprobé con el manifiesto antes de analizar (todo salía `n/d`).
- `Monitor expired after 30m with no events delivered` en la comparación final (el máximo es 30 min): lo rearmé.
- Ruff del hook, varias veces: `E501 Line too long (120 > 100)` y `F821 Undefined name 'GpsFix'` en `contracts/python/src/poc_contracts/tools.py`; `I001 Import block is un-sorted`; `F821 Undefined name 'AlertStatus'` en `monitor.py`; `SIM102`; `C408 Unnecessary dict() call`; corregidos.
- Pruebas que fallaron por mi cambio, no por el código: `test_gps_alert_line_data_style_has_no_sentence_to_copy` y `test_the_prompt_carries_the_gps_alert_line` (esperaban el estilo por defecto), `KeyError: 'monitor'` en un test nuevo de `evaluate` sin trazas, y una aserción de negación que no miraba dentro de la frase (`GPS and radar do not agree.` contaba como «coinciden»).
- `run_matrix` con vLLM cargando 1–2 minutos en cada arranque: no es un fallo, pero hay que contarlo en los tiempos.

## Límites
- n = 3 por escenario con `actual` y gpt-oss; con T=0 sigue habiendo variación (F3 falló 1 de 3 en la 14.2 y 1 de 10 aquí): evidencia, no prueba. Las matrices de los pasos son ×1.
- Cada paso se comparó con **una** repetición de su base; el efecto de los pasos sobre los contadores de texto está dentro del ruido (±2 fugas, ±1 error) salvo donde lo digo.
- Las medidas de texto son léxicas y en inglés; los contadores nuevos (`agree_without_fix`, `close_without_cause_source`, `unsupported_figures`, `recovery_time_mismatch`) tienen falsos positivos y negativos que no he cuantificado más allá de leer los hallazgos. `unsupported_figures` no ve acciones inventadas sin cifra.
- No se repitió el 32B (como pediste): su pico de prompt de la 14.2 (7 843) y el del 14B (9 587 ahora) siguen sin caber en su contexto de 10 240 con margen; no lo he tocado.
- No probé `now` sin fix en los chats ni la memoria A o el modo guiado con v0.15.

## Qué queda
- **Tu decisión:** el modelo por defecto (con la rúbrica), y las propuestas de «Para decidir» 2 y 3 (rellenar `link_anomalous`; guardrail con el salto del módulo).
- `docs/mejoras_futuras.md`: `link_anomalous`, la ventana de la recuperación, la posición sin fix en la ventana, el «radar unavailable» y las acciones inventadas del informe.
- E5 (modelo de Claude como juez con `docs/rubrica_textos.md`).

## Documentos actualizados
`docs/quien_decide_que.md` (cabecera, §1 tools de datos e informe, §3 una ayuda nueva medida y no adoptada), `docs/mejoras_futuras.md`, `contracts/eventos.md`, y los `CLAUDE.md` de `platform/` y `ai-module-py/`. Contrastado `quien_decide_que.md` con el código: **no cambia quién decide la causa, la fase ni la severidad**; cambia lo que ven los agentes (`now` sin fix, los hechos del informe) y se añade la ayuda `state_line: recovery_data` (apagada).

## URLs consultadas
Ninguna (solo código y documentación locales).

## Ficheros
Nuevos: `ai-module-py/tests/test_state_recovery.py`, `docs/fases/fase14_3.md`, `experiments/e14-3-*` (matrices, medidas y `e14-3-textos.md`; solo se versionan los `compare.md`). Modificados: `agent-assets/{tools.json,prompts/{monitor_output,monitor_objective,report_system,report_objective}.md,skills/{source-discrepancy,report-format}/SKILL.md}`, `contracts/{eventos.md,python/src/poc_contracts/tools.py,schemas/tools/get_track_metrics.result.json}`, `platform/src/platform_app/tools/metrics.py` y `platform/tests/test_tools.py`, `ai-module-py/src/ai_module/{monitor,monitor_state,report,report_facts,evaluate,compare}.py`, `agent/{assets,trace}.py` y sus tests, `tools/experiments/text_metrics.py`. **Los ficheros de `runs/` no cambian** (no se tocó el generador ni los escenarios).

## Copias (reglas 13 y 15)
En `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`: `docs/fases/`, `docs/{quien_decide_que,mejoras_futuras,rubrica_textos}.md`, `experiments/` (`e14-3-textos.md`, las medidas `e14-3-*-textos-medida.{md,json}` y `e14-3-remedida-*`, los `compare.md` y los 81 `eval.md` y 81 `informe.md` de las matrices de la fase, con su estructura de carpetas), los PNG de `runs/*/` (sin cambios, el generador no se tocó), `snapshots/fase14_3/` (463 ficheros) y `snapshots-limpias/fase14_3/` (418 ficheros). No hay capturas nuevas: la web no cambia.
- `diff -rq docs/fases results/docs/fases` solo marca **un fichero de más que no es de esta fase**: `results/docs/fases/quien_decide_que.md` (copia del 04/11 19:53, con el estado de la 14.2, que quedó en esa carpeta en una fase anterior). No lo he borrado; la copia buena está en `results/docs/quien_decide_que.md`. Si quieres, lo quito.

## Instantánea limpia
`snapshots-limpias/fase14_3/` (418 ficheros). Las dos comprobaciones de la regla 15 (palabras prohibidas y nombres propios) **salen vacías a la primera**; no hubo que corregir ningún fichero.

## Estado al terminar
`serve.sh stop` ejecutado por `run_matrix` al final de cada matriz; puertos 8000 y 8100 libres y GPU a 0 MiB (la cifra de reposo de `serve.sh` es 0 MiB en esta sesión). Ningún servidor lanzado por mí queda en marcha.

## Mensaje de commit propuesto
```
feat: phase 14.3 - now without GPS fix, closings by cause, mission report times

get_track_metrics.now carries gps_fix (contract v0.15, additive). With no fix
on the last GPS position (a dead-reckoning estimate, not a measurement) the
GPS-radar distance, whether they agree and the GPS deviation are null, and the
estimated positions are left out of the interpolation; the window aggregates
are unchanged. The monitor closing says what went back to normal for the cause
of the alert (the command link for a hijacking, which it now looks at), and the
recovery severity has a criterion in monitor_output.md. The mission report
gets the time it entered recovery, the closing time, the largest distance from
the route and the GPS jump as separate facts, and its recommendations may only
use figures and actions that the data or the operational notes support.
compare.py adds the iterations per invocation (p50/p95/max); text_metrics
counts meters/metres, GPS-radar agreement with no fix, closings without the
cause's data, unsupported figures and wrong recovery times. A state line that
gives the GPS jump as data (state_line: recovery_data) is available and off:
it did not reduce the rejections or the iterations.
```
