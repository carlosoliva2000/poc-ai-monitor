# Fase 15.1 · Fuente de LINK_ANOMALY, estación callada y deslices de texto

Escrito para: Carlos. Perfil `actual` (Qwen3-14B-AWQ sin razonamiento, T=0), base `experiments/e15-final/` (×1). Mismo método que la Fase 15: un paso cada vez, copia exacta antes en `~/poc-backups/fase15_1/<paso>/`, interruptor en cada cambio de comportamiento, pruebas dirigidas y sin matrices. Git solo de lectura.

## Resumen

| Paso | Resultado | Interruptor |
|---|---|---|
| 1 · Fuente de `LINK_ANOMALY` | Corregido (7 tests fallaban antes) | dentro de `monitor.sensor_fault_per_source` |
| 2 · Estación callada (`demo-meteo`) | El monitor publica `UNKNOWN` para el viento, sin rechazos; no se toca nada. **Pendiente al final:** con la 15.1 el spoofing sale `SENSOR_FAULT` en este escenario | – |
| 3 · Tendencia de «ahora» (v0.17) | Adoptado **solo en la recuperación del secuestro** (en todas las invocaciones hacía fallar el spoofing de `demo-battery`: 3 de 8 ejecuciones frente a 0 de 6 sin ella) | `monitor.now_route_trend: link_recovery` |
| 4 · Textos del secuestro e informe | Adoptado; la hora de vuelta del enlace es la del primer `LinkStatus` con el controlador de la misión (T+06:20) | `report.link_back_time`, `chat.alert_phases` |
| 5 · Tiempos, «los últimos» y instante de partida (v0.17) | Adoptado; `demo` idéntica con y sin «esperar al agente», 0 eventos posteriores al `as_of` | `monitor.as_of_from_warning`, `chat.window_rules`, `chat.monitor_decisions` |

**Pendiente:** `demo-meteo` (ver al final). **Qué no se hizo:** no se separaron los esquemas de `tools.json` (el control, que comparte el `tools.json` nuevo, descartó esa causa).

## Paso 1 · La fuente de `LINK_ANOMALY`

**Antes (comprobado con tests que fallaban):** `fault_sources` no daba fuente a una `LINK_ANOMALY` y `foreign_sensor_fault` trataba cualquier regla que no fuera `SOURCE_SILENT` como de posición (el veto miraba `gps`, `radar` o `position`). Consecuencias: un `SENSOR_FAULT` del enlace (por `SOURCE_SILENT`) y una `LINK_ANOMALY` posterior se tomaban por problemas distintos, y un `SENSOR_FAULT` del radar, del GPS o de la discrepancia no vetaba absorber una `LINK_ANOMALY` (un secuestro con el radar callado). Siete de los nuevos tests fallaban con el código de la Fase 15.

**Después:** `LINK_ANOMALY` → fuente `link` en `fault_sources` (y por tanto en `describe_fault_sources` y en «SENSOR_FAULT of the command link»); en `foreign_sensor_fault` una `LINK_ANOMALY` es ajena si la fuente `link` no está entre las del `SENSOR_FAULT`. Queda dentro de `monitor.sensor_fault_per_source` (es la corrección de un fallo de esa misma ayuda; sin la clave, sin cambios). 4 líneas en `monitor_state.py`.

**Prueba:** 9 tests nuevos en `test_sensor_fault_source.py` (enlace mudo + `LINK_ANOMALY` = mismo problema y se puede reconocer; radar/GPS/batería/`GPS_DEGRADED`/discrepancia + `LINK_ANOMALY` = otro problema y `TAG_FOREIGN_FAULT`; un fallo del enlace es ajeno a la posición y a las demás fuentes; sin el interruptor, como antes) y los que ya había. Módulo de IA 638 pasan; `ruff check` y `ruff format --check` limpios. Sin matriz: no cambia ningún mensaje que vea el modelo en los escenarios (ninguno tiene un `SENSOR_FAULT` del enlace).

## Paso 2 · Estación meteorológica callada (`demo-meteo`)

**Escenario** `scenarios/demo-meteo.yaml` = `demo` + `faults: [{source: meteo, mode: mute, start_s: 25, end_s: 900}]` (recortado al fin del vuelo, T+556,3). Determinista (dos generaciones con el mismo sha256 `1638a3db…`); mismos eventos que `demo` salvo los `WindReported` desde T+25 s (test nuevo); etiquetas A1 viento, A2 spoofing, A3 secuestro y F1 `source_silent` meteo (T+25–556). Añadido a `scenarios/README.md` y a las listas de los tests de plataforma (242 pasan). Cambia solo `runs/demo-meteo/` (nuevo).

**Qué hace hoy el monitor** (`experiments/e15_1-paso2-meteo`, `demo-meteo` ×1, código del paso 1, sin cambiar nada más): **3/4 en la evaluación (A1 ❌, A2 ✅, A3 ✅, F1 ✅)**, 0 falsas alarmas, 0 fallbacks, 0 frases que contradicen, 0 checks≠tools, recuperaciones del GPS y del secuestro con `recovering`.

Traza de la racha de viento (T+01:46, `inv-0002`, `det-0002`, 4 iteraciones, 7,8 s):
1. `load_skill route-deviation`; `get_track_metrics` 76,1–106,1: `wind: null`, `now.wind: null` (no hay ningún `WindReported` desde T+00:20).
2. `get_events link last_n 6`: enlace normal (`GCS-1`).
3. `publish_alert`: causa **`UNKNOWN`**, `medium`, confianza 0,5, `checks` todo `false` (`link_anomalous` lo rellena el módulo). **Sin rechazos** (el guardrail de `WIND` no llegó a hacer falta). Resumen: «Drone is 30.5 m off route; GPS and radar agree.». Explicación: «…Wind data is not available. The command link is stable… The deviation is increasing, but no wind or link issues are evident.».

Resultado: el viento no se atribuye a otra cosa (ni `HIJACK` por el rumbo ni `SENSOR_FAULT`); acaba `UNKNOWN`, y el cierre llega a T+02:36. F1 (`SENSOR_FAULT` de la estación) a T+00:51, `medium`, abierta al final. El spoofing (`GPS_SPOOFING` high T+03:12 → recovering T+03:42) y el secuestro (`HIJACK` high T+05:35 → recovering T+06:25) salen como en `demo`. Los 5 rechazos de la ejecución son los de siempre (causa duplicada y veto del reconocimiento de la recuperación del GPS; «nothing changes» en el secuestro); ninguno es de la estación.

**Decisión: no se toca nada.** `UNKNOWN` con la falta de la estación dicha en el texto es lo correcto. Matices que veo y **no corrijo** (×1, el diagnóstico es bueno): (a) la confianza de 0,5 supera el «≤ 0,4» que pide la skill; (b) «no wind … issues are evident» da a entender que miró el viento (no hay datos); (c) el informe, con T=0,7, escribe en F1 «the drone showed a drift in favor of the wind» y en el anexo «drift in favor of the wind is noted»: es una invención del informe (no hay viento que contrastar). Si quieres atajarlo, el arreglo mínimo sería una frase de criterio en `route-deviation` (sin datos de viento en la ventana: `UNKNOWN`, confianza baja, decir que la estación no informa) y no dar a la narración del informe una «deriva a favor del viento» sin viento; lo dejo propuesto, sin aplicar.

**Cómo debería contarlo la evaluación (propuesta, sin aplicar; la etiqueta de A1 no se toca):** con la estación callada, `UNKNOWN` en un `ROUTE_DEVIATION` de viento es un acierto honesto. Opciones: (1) que el etiquetador ponga `also_accepted_causes: ["UNKNOWN"]` en un episodio de viento que coincide con un `mute` de `meteo` (regla en el contrato §8.4, cambia `runs/demo-meteo/labels.json`); (2) que `eval.md` lo cuente aparte («causa honesta por falta de datos», ni acierto ni fallo) para no mezclarlo con un diagnóstico equivocado. Recomiendo la 2: no regala un ✅ y separa «no sabe» de «se equivoca».

## Paso 3 · Tendencia de «ahora» (contrato v0.17, aditivo)

**Antes:** la recuperación del secuestro de `hijack` decía «The deviation trend is increasing, so the drone is not yet back on track» (`e15-final`, T+06:25) con la desviación ya bajando (710 m a T+06:23 → 686 m a T+06:26): el modelo leía el `trend` de la ventana de 30 s, que incluye el secuestro.

**Después:** `now` de `get_track_metrics` lleva `route_trend` (`approaching` | `moving_away` | `steady` | `null`), `route_change_m` (cambio estimado de la desviación en 10 s, negativo = se acerca) y `route_trend_source` (`gps` | `radar`). Cálculo (`platform_app/tools/metrics.py::_route_change`): pendiente de mínimos cuadrados × 10 s sobre el GPS con fix de los **últimos 4 s**, sin contar lo anterior al último salto de 30 m o más (el GPS que vuelve de golpe a la posición real no es «alejarse»); si el GPS discrepa del radar (puede mentir) o no tiene tres muestras y 3 s de tramo, sobre el radar de los últimos 10 s. `steady` si |cambio| < el mayor entre 5 m y 2 desviaciones típicas de la pendiente por el ruido de la fuente (GPS 1,5 m, radar 5 m). **Elección de la ventana, medida sobre los datos:** con 10 s la tendencia llega tarde en el giro (a T+06:25 aún «moving_away +87 m»); con 6 s, «+13 m» (dudoso); con 4 s ya «approaching −59 m». Coste: con 4 s el GPS parado a veces marca ±10 m en `nominal` en las curvas (8 de 141 instantes; es movimiento real, no ruido, y `steady` en el resto).

Contrato v0.17 (`eventos.md` §7 y cabecera, `NowFacts`, enum `RouteTrend`, esquema exportado). Interruptor `monitor.now_route_trend` (sin la clave, el módulo quita los tres campos de lo que ve el modelo; `agent-assets-v13` no lo lleva; los chats ven `now` entero). `tools.json`: una frase en la descripción de `get_track_metrics`. Skills: `route-deviation` (decir si se acerca, se aleja o se mantiene con `now`; la tendencia de la ventana lleva el pasado) y `link-anomaly` §4 (la recuperación del secuestro).

**Prueba:** 4 tests nuevos de plataforma (secuestro: `moving_away` a T+06:20, `approaching` a T+06:25 y T+06:28 mientras el `trend` de la ventana sigue `increasing`; `nominal` `steady`; recuperación del GPS: radar con el engaño en marcha y GPS después del salto; sin GPS: radar; sin muestras: `null`) y 1 del módulo; plataforma 246, contratos 132, módulo 639, `ruff` limpio. `demo` ×1 y `hijack` ×1 (`experiments/e15_1-paso3`):

| | Antes (`e15-final`) | Después |
|---|---|---|
| Secuestro (`demo`, ai-0012, T+06:25) | «The deviation trend is increasing, so monitoring is required» | «The drone is now approaching the route (route_trend: approaching, route_change_m: -86.1 m over 10 s)». Resumen: «…drone approaching route» (antes «drone still off route») |
| Secuestro (`hijack`, ai-0004) | «…the drone is not yet back on track» | «The drone is now approaching the route (route_trend: approaching, route_change_m: -83.3 m over 10 s)» |
| Recuperación del GPS (`demo`, ai-0005, T+03:42) | «GPS has recovered from spoofing; deviation is 73.9 m, GPS and radar agree now» | «GPS is recovering from spoofing; GPS and radar disagree by 9.9 m»; `now` dice `moving_away` (radar, +20 m: con el salto recién dado el GPS aún no tiene tres muestras); el texto no habla de la tendencia |
| Etiquetas / fases / rechazos | `demo` 3/3, `hijack` 1/1, 5 rechazos | `demo` 3/3, `hijack` 1/1, 5 rechazos; mismas fases (`recovering` T+03:42 y T+06:25) |
| Ventanas de `get_track_metrics` por invocación | `(as_of−30, as_of)`; la del GPS `(192.0, 222.1)` y la del cierre `(222, 234.3)` | las mismas con otro `as_of` (`(192.0, 222.5)`, `(222, 234.7)`): ninguna se movió |

**Lo que no se arregla aquí:** (a) el modelo copia los nombres de los campos al texto («route_trend: approaching, route_change_m: -86.1…», «now.gps_radar_agree: true»): es el paso 4. (b) La recuperación del GPS no cuenta la tendencia (y con el salto recién dado, `now` la saca del radar). (c) A T+06:25 el pico de la desviación fue 2 s antes: la tendencia es honesta pero un instante antes diría `moving_away`. **Decisión: adoptado.** La prueba de ventanas del monitor cumple lo pedido (tools.json único): se repetirá tras el paso 5.

## Paso 4 · Textos del secuestro e informe

**1. Nombres internos en la alerta del secuestro.** La skill `link-anomaly` se reescribió como las demás desde la 14.1: criterio y lectura de campos solo donde hace falta (los `checks` sí nombran sus campos), una sección «Writing» (palabras llanas, sin nombres de campos, herramientas ni `true`/`false`) y, en la recuperación, decir cuándo volvió el enlace (la hora del primer evento del enlace con el controlador de la misión, no la del aviso, que llega después) y si el dron se acerca, se aleja o se mantiene (la tendencia de «ahora»). **Pero el modelo no carga la skill en la recuperación**: lo que lee es la sección `link_recovered` de `monitor_objective.md`, que decía «(the `now` figures)» y hacía que copiara «now.gps_radar_agree: true». Se reescribió esa frase (la hora de vuelta, lo que está pasando ahora, «in plain words, without names of fields or tools»).

| `hijack` / `demo`, recuperación del secuestro (T+06:25) | Nombres de campo en el texto |
|---|---|
| `e15-final` | «(now.gps_radar_agree: true)», «(now.gps_deviation_from_plan_m: 0.7 m)» |
| Paso 3, antes de esta reescritura | «(route_trend: approaching, route_change_m: -86.1 m over 10 s)», «(now.gps_radar_agree: true)» |
| Con skill y objetivo nuevos (×1 en `demo` y en `hijack`) | «(route_trend: approaching)»: uno, el del nombre que lleva la descripción de la tool; el resto, en palabras («GPS and radar agree (rad-000192)», «The command link returned to GCS-1 at T+06:20 (lnk-0076) and remains stable») |

Queda **un** nombre de campo por alerta (de 2 a 1): el modelo copia el que aparece en el resultado de la tool y en su descripción. Las reglas de texto ya lo prohíben (`monitor_output.md`); la medida de fugas por matriz sigue en `tools/experiments/text_metrics.py`.

**2. Hora de vuelta del enlace en el informe** (`report.link_back_time`, sin la clave apagado). **Ajuste de Carlos: la hora de vuelta es la del primer `LinkStatus` con el controlador de la misión después de la anomalía (T+06:20, `lnk-0076`), no el cierre de la `LINK_ANOMALY` (T+06:25, que lleva los 5 s de espera del detector).** El módulo guarda, sin LLM, el controlador de la misión (el primero visto, como el detector) y los cambios de controlador (`link_log.py`, alimentado en `module.handle_event`, a cero con `SimulationStarted`/`SimulationReset`). `report_facts.Anomaly.link_back` = el primer cambio de vuelta al controlador de la misión tras el inicio de la `LINK_ANOMALY` de la cadena. El informe da las horas con nombres distintos: «detected at T+05:35; command link back to GCS-1 at T+06:20; entered recovery at T+06:25; closed at T+07:21» y la tabla de cronología lleva la fila `T+06:20 | Link | Command link back to GCS-1 (lnk-0076; A3)`. `tools/experiments/text_metrics.py::recovery_time_mismatch` cubre también la vuelta del enlace (`link_returns`, con la hora del timeline): marca «…until T+07:21, when the hijack was resolved and the link returned to GCS-1» y «the link returned at T+07:21», y no marca «the link returned at T+06:20» ni «hijack closed at T+07:21». **Resultado:** en `demo` ×2 y `hijack` ×2 el resumen ya no repite el error (dice «entered recovery at T+06:25 and closed at T+07:21», sin hora de vuelta del enlace o con la buena): el fallo del resumen no se reprodujo con el modelo vivo (T=0,7) y se prueba con tests (6 nuevos en `test_link_back_time.py`, 3 en `test_text_metrics.py`).

**3. Chat del informe con la fase de cada alerta** (`chat.alert_phases`, sin la clave apagado). Sección nueva `<<alert_phases_section>>` en los dos prompts del chat del informe (vacía si está apagado), escrita por el código (`report_facts.describe_alert_phases`): «A3 · GPS spoofing: active from T+03:12 (ai-0006, high); in recovery from T+03:42 (ai-0007, medium); closed at T+03:54», con la hora de vuelta del enlace en el secuestro, y una frase de criterio (una pregunta sobre un momento se contesta con la fase de entonces; lo que sigue a una recuperación no es la causa). **Prueba** (`demo-battery` ×1, guion de la Fase 15 + «What was happening to the GPS at T+03:42?»): la sección llega al prompt (comprobado en la traza). El chat **ya no atribuye** la desviación de 73,9 m al spoofing (`e15-final`: «73.9 m away from the route» del informe, con «GPS spoofing») y contesta con `get_events` «3D fix with 14 satellites, HDOP 0.8… the GPS was functioning normally»; **pero no dice que ese instante era la recuperación**: con tools tiende a describir lo que devuelve la consulta y no usa la fase. En `demo`, «most serious anomaly» sale bien (secuestro, 714,2 m); en `demo-battery`, el chat repitió el error del propio informe (T=0,7: «the most serious was the GPS spoofing») en una ejecución y acertó (secuestro, 714,2 m) en la repetición.

**Resultado de la ejecución completa** (`e15_1-paso4-b`, ×1 cada una): `demo` 3/3, `hijack` 1/1, `demo-battery` 4/4, 0 falsas alarmas, 0 fallbacks, 0 frases que contradicen, 0 checks≠tools, `recovering` en las dos recuperaciones. Módulo 652 tests, `ruff` limpio. **Decisión: adoptado** (`report.link_back_time` y `chat.alert_phases` encendidos). **Pendiente:** que el chat use la fase al contestar con tools (en `mejoras_futuras.md`); el nombre de campo que queda en el texto del secuestro.

## Paso 3, corrección posterior: la tendencia solo en la recuperación del secuestro

Con `monitor.now_route_trend` encendido para **todas** las invocaciones, `demo-battery` empezó a fallar en el spoofing de T+03:12 (el modelo publicó `SENSOR_FAULT` en vez de `GPS_SPOOFING`). Se aisló con series de 3 repeticiones (`demo-battery`, `--no-ask`):

| Configuración | A2 (spoofing) bien |
|---|---|
| Todo encendido (`actual`) | 3 fallos en las 5 ejecuciones de esta fase con la tendencia en todas las invocaciones (`bat-b`, `final`, una de `iso-sin-asof`) |
| Control con todas las ayudas de la 15.1 apagadas (`actual-sin-fase15-1`; mismo `tools.json` nuevo) | 3/3 |
| Solo la tendencia apagada (`actual-sin-tendencia`) | 3/3 |
| Solo `as_of_from_warning` apagado (tendencia encendida; `actual-sin-asof`) | 2/3 |
| **`now_route_trend: link_recovery`** (lo adoptado) | **3/3** (`e15_1-lr-bat`) |

Con la tendencia 3 fallos en 8 ejecuciones y 0 en 6 sin ella: consistente, no concluyente (n pequeño); el aumento del prompt (~8 %) o los campos nuevos en `now` mueven la decisión del 14B. **Sospecha descartada:** el `tools.json` único no es la causa (el control lo comparte y sale 3/3), así que **no se separaron los esquemas**; sí se quitó de la descripción de `get_track_metrics` la frase de `route_trend`. **Decisión:** `monitor.now_route_trend` tiene tres valores (`off`, `link_recovery`, `all`); `agents.yaml` usa `link_recovery` (el módulo solo deja `route_trend` en `now` cuando algún aviso del lote es la recuperación de un secuestro: `Monitor._shows_route_trend`). La indicación de usarla va en la sección `link_recovered` de `monitor_objective.md` (el modelo no carga la skill en esa invocación; sin la indicación repetía «the deviation is increasing»). Se retiraron de `route-deviation` las frases que mandaban usarla en la recuperación del GPS. Verificado: `hijack` ×2 y `demo` ×1 dicen «drone approaching route» (`e15_1-lr2-*`), con el nombre de campo «route_trend» todavía una vez en el texto.

## Paso 5 · Herramientas de datos: tiempos, «los últimos» y el instante de partida

**Antes (demo del 06/11, `runs/demo/20261106-103008`, comprobado en `llm_trace.jsonl`):** «between T+01:30 and T+01:50» → seis `get_events` con `since: 810, until: 850`, sin resultados y «no pasó nada»; «last battery status» → `since: 875, until: 916`; sin segundos explícitos el modelo concatenaba los dígitos. El `as_of` del monitor era el reloj del módulo (con «esperar al agente» llega 0,1–0,8 s tarde: det-0001 a 106,0 → `as_of` 106,5; sin pausa, decenas de segundos) y los chats con tools no tenían `as_of` el del informe.

**Qué se cambió (contrato v0.17, aditivo; `eventos.md` §7):**
1. **Tiempos por código** (`poc_contracts/times.py`): `since`/`until` como segundos o `T+mm:ss`, `mm:ss`, `T+h:mm:ss`; error con los formatos válidos si no. Plataforma y módulo usan el mismo parser (`Toolbox.prepare_window`).
2. **Mismo instante en toda la interacción:** `as_of` = `sim_time` del aviso (el del último del lote), con o sin «esperar al agente» (`monitor.as_of_from_warning`); los lotes solo juntan avisos del mismo instante; «cerrada hace 60 s» y la hora de la línea de últimas decisiones usan `as_of_sim_time` y no la de publicación (sin esto el prompt decía «decisiones a T+07:24» para un aviso de T+05:04: se vio en `faults` sin espera); los dos chats tienen `as_of` (`chat.window_rules`; con el ejercicio terminado, el último instante). Contador `events_after_as_of` por invocación (`eval.md`): **0 en todas las ejecuciones de la fase**.
3. **Ventanas futuras:** un `since` posterior al instante de partida se rechaza con ese instante («The start T+13:30 (810 s) is after the current time T+03:42 (222 s)…»); un `until` posterior se recorta y el resultado lleva `until_clipped_to` y `note`.
4. **`last_s`** (`60`, `"90s"`, `"1:30"`, `"1m30s"`) en `get_events` y `get_track_metrics`, y **5. `source: all`** (o sin `source`): todas las fuentes por tiempo, cada evento con `feed`, 3 por fuente por defecto y 60 en total. 3. Reglas de «los últimos» → `last_n` (el penúltimo: 2 y tomar el primero), `since`/`until`, `last_s` y `all`, en la descripción de `get_events` y en los prompts de los dos chats.
6. **Decisiones del monitor en su chat** (`chat.monitor_decisions`): por invocación, el aviso con las palabras del detector, qué miró y qué publicó, sacado de las trazas; el prompt dice que una pregunta sobre lo que hizo el monitor se contesta con eso.

**Prueba de equivalencia** (`tools/experiments/equivalence.py`, ×1, 16×, mismo código): «esperar al agente» frente a sin esperar.
- `demo`: **11 decisiones idénticas** (alerta con causa, severidad, fase, `supersedes`; cierres; reconocimientos; mismo `as_of`), 0 eventos posteriores al `as_of`, también tras la corrección de la línea de decisiones.
- `faults`: **10 de 11 iguales**. La que difiere es la del silencio del GPS (T+05:04): `SENSOR_FAULT` con espera, `GPS_JAMMING` sin ella. **No es de la pausa:** prompts, llamadas y resultados de las tools idénticos; el modelo muestrea distinto (en la primera llamada marca `gps_radar_disagreed` `true` o `false`). En la ejecución sin espera la alerta `GPS_JAMMING` pasó el guardrail de alerta propia que con otra muestra la rechazó (hueco anotado en `mejoras_futuras.md`).

**Guion de chat (`demo-battery`, preguntas de la demo del 06/11 en los mismos instantes, `e15_1-final2`)**

| Pregunta | Antes (06/11) | Después |
|---|---|---|
| «between T+01:30 and T+01:50» | 6 llamadas, `since 810–850`, «no pasó nada» | **1 llamada** `{source: all, since: "T+01:30", until: "T+01:50"}` con los eventos reales (viento, WP1, enlace…) |
| «last battery status» | `since 875, until 916` → vacío; luego `last_n 1` | `last_n 1` → T+00:20, 99,6 %, 25,21 V |
| «last 3 link events» | – | `last_n 3` → T+09:05, 09:10, 09:15 |
| «second-to-last GPS position» | – | `last_n 2` y toma el primero → T+09:15 (correcto) |
| «last 90 seconds» | – | `{source: all, last_s: "90"}` → T+08:16–09:16 |
| «general state of the exercise» | – | contesta con `get_flight_summary` (no usa `all`) |
| «Why did you look on the link?» (T+07:45) | `last_n 10` de enlace posteriores al secuestro: «todo bien» | **Mejora a medias:** a T+07:45 consulta el enlace y describe el presente en una ejecución; con el ejercicio terminado, y en la ejecución con el aviso del detector en las decisiones, explica el motivo correcto («detection det-0008… change of controller GCS-1 → UNK-4F2A at T+05:35… potential hijack») |
| Con el ejercicio terminado (chats) | – | sin errores de tools; `as_of` = T+09:16 |

**Límites (sin tapar):** a T+07:45 el chat del monitor aún lanza una consulta nueva en alguna ejecución y contesta con el presente; el informe, con T=0,7, afirmó en una ejecución que «la más grave fue el spoofing (73,9 m)» y el chat lo repitió (en `demo` y en otra ejecución de `demo-battery`, el secuestro, 714,2 m); «estado general» no usa `all`. **Decisión: adoptado** (`monitor.as_of_from_warning`, `chat.window_rules`, `chat.monitor_decisions`).

## Comparación final (`e15_1-final2`, ×1 cada uno, `actual`; guion de chat en `demo` y `demo-battery`)

| Escenario | Etiquetas e15-final → 15.1 | Fallbacks | Rechazos | Prompt máx. (tokens) | Llamada más larga (s) | Eventos tras `as_of` |
|---|---|---|---|---|---|---|
| `demo` | 3/3 → **3/3** | 0 → 0 | 4 → 4 | 7 593 → 7 998 | 6,1 → 6,4 | 0 |
| `hijack` | 1/1 → **1/1** | 0 → 0 | 2 → 3 | 7 258 → 7 741 | 5,6 → 6,0 | 0 |
| `faults` | 3/3 → **2/3** (F3: silencio del GPS → `GPS_JAMMING`) | 0 → 0 | 5 → 5 | 8 492 → 8 574 | 6,9 → 5,9 | 0 |
| `demo-battery` | 4/4 → **4/4** | 0 → 0 | 4 → 4 | 7 650 → 8 093 | 6,5 → 6,6 | 0 |
| `demo-meteo` | n/d → **2/4** (A1 `UNKNOWN`, A2 `SENSOR_FAULT`) | n/d → 0 | n/d → 5 | n/d → 8 400 | n/d → 6,2 | 0 |

0 frases que contradicen los checks, 0 checks≠tools y 0 recuperaciones sin `recovering` en todas. Textos de lo que cambió, antes y después: `experiments/e15_1-textos.md`. Prompt máximo +5 % por las descripciones nuevas de las tools. **Dos intermitencias del 14B, en escenarios con un `SENSOR_FAULT` de otra fuente abierto o con silencio del GPS** (spoofing → `SENSOR_FAULT`; silencio del GPS → `GPS_JAMMING`): las dos existían antes (Fase 15, paso 2; Fase 14.2). **`demo-meteo` es la excepción y queda pendiente (ver abajo).**

## Inconvenientes y por qué se alargó la fase

- **Alcance:** cinco pasos y unas 25 subtareas (contrato v0.17, plataforma, módulo, prompts, skills, escenario nuevo, herramientas de comparación). La suite del módulo tarda 3,5 min y cada ejecución con el modelo real 2–3 min (el servidor se reinicia al cambiar de perfil).
- **Una regresión real (el spoofing de `demo-battery` como `SENSOR_FAULT`)** obligó a aislarla: control, dos series de aislamiento de 3, verificación de la corrección y repetir la comparación final entera. Salió que la tendencia en todas las invocaciones del monitor la provocaba; ahora solo se da en la recuperación del secuestro.
- **Una divergencia de equivalencia** (`faults`, silencio del GPS) costó dos ejecuciones más; era variabilidad del modelo, no la pausa, y dejó dos hallazgos reales: la línea de últimas decisiones mostraba horas de publicación tardías sin pausa (corregido) y un hueco del guardrail de alerta propia (anotado).
- **Una sospecha mía equivocada:** achaqué el fallo al `tools.json` único sin haberlo aislado; el control (que comparte `tools.json`) la descartó. No se separaron los esquemas.
- **Errores míos de operación:** un YAML de perfil con `: ` sin comillas; un `pkill -f` que mató mi propio shell (el mismo tropiezo de la Fase 15); un servidor vLLM de otro perfil que bloqueaba la serie siguiente (`run_matrix` no cambia de perfil con un servidor vivo); un directorio de experimento ya existente; un lanzamiento solapado con otra tanda en curso (falló en 0,2 s sin dañar nada); la comparación final repetida porque la primera se hizo antes de la última corrección.
- **Cosas que no se resolvieron** (en `mejoras_futuras.md`): el nombre de campo que aún copia el texto del secuestro, el chat del informe que no usa la fase con tools, y las dos intermitencias del 14B.

## Quién decide qué (contrastado con el código)
`docs/quien_decide_que.md` actualizado: el código convierte los tiempos de las tools y fija el instante de partida de cada interacción; la plataforma calcula la tendencia de la ruta; `LINK_ANOMALY` es una fuente propia al decidir de qué es un `SENSOR_FAULT`; la hora de vuelta del enlace del informe sale del código; la causa del viento sin estación, la del spoofing y la del silencio del GPS siguen siendo del modelo.

## URLs consultadas
Ninguna (todo es código propio; el parser de tiempos y la pendiente de mínimos cuadrados no dependen de librerías nuevas).

## Ficheros
Nuevos: `contracts/python/src/poc_contracts/times.py`, `ai-module-py/src/ai_module/link_log.py`, `tools/experiments/equivalence.py`, `scenarios/demo-meteo.yaml`, `runs/demo-meteo/`, `model-profiles/actual-sin-{fase15-1,tendencia,asof}.yaml`, tests (`test_times.py`, `test_window_rules.py`, `test_link_back_time.py`, `test_equivalence.py`) y `experiments/e15_1-*` (solo se versionan los `compare.md`). Modificados: contratos (`eventos.md` v0.17, `enums.py`, `tools.py`, esquemas), plataforma (`tools/{context,events,metrics}.py` y tests), módulo (`monitor.py`, `monitor_state.py`, `chat.py`, `chat_facts.py`, `runtime.py`, `module.py`, `report.py`, `report_facts.py`, `evaluate.py`, `agent/{assets,profiles,tools,trace}.py` y tests), `agent-assets` (`agents.yaml`, `tools.json`, skills `route-deviation` y `link-anomaly`, prompts `monitor_objective` y de los dos chats), `tools/experiments/{run_matrix,text_metrics}.py`, `scenarios/README.md`, `docs/` y los `CLAUDE.md`. **Cambia en `runs/`:** solo `runs/demo-meteo/` (nuevo); el resto, idéntico.

## Pruebas
Módulo de IA 671, plataforma 250, contratos 177 (1 omitida), `ruff check` y `ruff format --check` limpios. Copias exactas de cada paso en `~/poc-backups/fase15_1/{paso1,paso2,paso3,paso4,paso4-fin,paso5,paso5-fin,final}/`.

## Mensaje de commit propuesto
```
feat: phase 15.1 - link source of LINK_ANOMALY, silent weather station, now route trend, data tool times

LINK_ANOMALY is the "link" source when deciding what a SENSOR_FAULT belongs to.
demo-meteo scenario (demo + weather station muted from T+25 s).

Contract v0.17: now.route_trend (approaching / moving_away / steady, last 4 s, GPS jump
excluded), given to the monitor only in the hijack recovery (monitor.now_route_trend:
link_recovery; in every invocation it made the spoofing diagnosis of demo-battery fail
3 times in 8 runs, 0 in 6 without it). get_events and get_track_metrics take since/until
as seconds or T+mm:ss (converted by code), last_s, and a since later than the starting
instant is rejected; get_events source all returns every source with its feed.

An invocation starts at the warning instant with or without waiting for the agent
(monitor.as_of_from_warning); chats get the same cut (chat.window_rules); the report gives
the time the link returned (first LinkStatus with the mission controller); the report chat
gets each alert's phase and the monitor chat its own decisions.
```

## Pendiente: `demo-meteo` con la 15.1 etiqueta el spoofing como `SENSOR_FAULT` (decisión de Carlos: no se investiga en esta fase)

Series de `demo-meteo` ×3 (`--no-ask`, 16×, «esperar al agente») más la ejecución de la comparación final:

| Configuración | A1 viento | A2 spoofing (T+03:12 y recuperación T+03:42) | F1 estación callada | Etiquetas |
|---|---|---|---|---|
| `actual` (15.1 completa; `e15_1-meteo-actual` y `e15_1-final2`) | `UNKNOWN` ❌ (esperado, sin estación) | **`SENSOR_FAULT` `medium` en 4 de 4** ❌ | `SENSOR_FAULT` ✅ | 2/4 |
| Control `actual-sin-fase15-1` (`e15_1-meteo-ctrl`) | `UNKNOWN` ❌ | **`GPS_SPOOFING` `high` en 3 de 3** ✅ | `UNKNOWN` **3 de 3** ❌ | 2/4 |
| Base del paso 2 (código del paso 1, ×1) | `UNKNOWN` ❌ | `GPS_SPOOFING` ✅ | `SENSOR_FAULT` ✅ | 3/4 |

Los dos modos fallan en dos etiquetas, pero **en distintas**: con la 15.1 el silencio de la estación sale bien y el spoofing mal; sin ella, al revés. Hipótesis sin medir: cuando el modelo ya ha publicado un `SENSOR_FAULT` (el de la estación), repite esa causa para la discrepancia GPS–radar de T+03:12 (el mismo patrón que el spoofing de `demo-battery` en la Fase 15). No se ha aislado qué ayuda de la 15.1 lo provoca (candidatas: `as_of_from_warning`, que cambia lo que ve el prompt, y la ayuda `link_recovery`); la serie corta de 2 repeticiones por ayuda se dejó sin hacer. **Hasta entonces:** `demo` (el de la presentación) sale 3/3 en todas las ejecuciones de la fase y `demo-battery` 3/3 con la configuración final; `demo-meteo` no es un escenario de la demo. Ver también `docs/mejoras_futuras.md`.
