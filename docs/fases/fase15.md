# Fase 15 · Correcciones tras la prueba manual (05/11/2026)

Escrito para: Carlos, que decide qué se queda de la Fase 15. Perfil `actual` (Qwen3-14B-AWQ sin razonamiento, T=0). Pruebas dirigidas, sin matrices de seis escenarios ni otros modelos. **Contrato v0.16, aditivo** (regla `LINK_ANOMALY`, fila en `detections_by_rule`, etiqueta del secuestro). `agent-assets-v13/` no se ha tocado (`git diff` vacío). vLLM, plataforma, módulo y web quedaron parados (puertos 8000, 8100 y 3000 libres, GPU a 0 MiB). Git solo de lectura. **Pruebas:** módulo de IA 629 (578 al empezar la fase), plataforma 236, contratos 132 (1 omitida), web 55; `ruff check` y `ruff format --check` limpios, `pnpm typecheck` y `pnpm build` sin errores. Copias exactas de cada paso en `~/poc-backups/fase15/{paso1,paso2,paso2-fin,paso3,paso4,paso4-fin}/`.

## Resumen

| Paso | Resultado | Interruptor |
|---|---|---|
| 0 · Diagnóstico | Las tres hipótesis confirmadas (con matices, abajo) | – |
| 1 · Chat desplegado | Reproducido (solape de hasta 103 px) y corregido: 0 px en 18 combinaciones; Markdown básico en los dos chats | – |
| 2 · Un fallo de sensor por fuente | Adoptado. El fallo **no se reproduce** con ×1 (4 de 4 bien antes y después); el mecanismo se prueba con la repetición determinista de tu traza | `monitor.sensor_fault_per_source` |
| 3 · Chats con tools de lectura | Adoptado: datos reales, ≤ 5,2 s por respuesta, 0 llamadas escritas como texto | `chat.tools_enabled: true` |
| 4 · Recuperación del secuestro | Adoptado: `HIJACK` `high` a T+05:35, `recovering` a T+06:25, cierre a T+07:21; A1 y A2 de `demo` sin cambios | `monitor.link_anomaly` |

## Paso 0 · Diagnóstico (`runs/demo/20261105-174746`, `runs/hijack/20261105-180322`)

### 1. Dos fallos de sensor mezclados: hipótesis confirmada, con dos matices

| T+ | Invocación | Qué pasó |
|---|---|---|
| 00:25 | – | `sim-0001` silencia la batería (manual). |
| 00:51 | `inv-0001` | `det-0001` `SOURCE_SILENT` batería → **ai-0001** `SENSOR_FAULT` «Battery has stopped reporting». |
| 03:12 | `inv-0004` (7 iteraciones) | `det-0004` `SOURCE_DISCREPANCY`. Métricas: GPS en el plan (media 4,1 m), radar fuera, `gps_radar.disagreed: true`, fix `3d`. El modelo propone `publish_alert` **`SENSOR_FAULT`** («check radar quality»). |
| 03:12 | `inv-0004` | **Rechazo de `no_duplicate_cause`:** «ai-0001 (SENSOR_FAULT) is open: use supersedes ai-0001 if the cause or severity changes, or acknowledge_detection». |
| 03:12 | `inv-0004` | El modelo obedece: `acknowledge_detection(det-0004, alert_id=ai-0001)` → **ai-0004** (`DetectionAcknowledged`). |
| 03:42 | `inv-0005` | El estado dice «Recent GPS alert: yes — ai-0001 SENSOR_FAULT (open). If this warning is the GPS recovery: cause SENSOR_FAULT, supersedes ai-0001, phase recovering». El modelo propone **`GPS_SPOOFING`** `high` `active`, que era **lo correcto**. |
| 03:42 | `inv-0005` | Rechazo: «GPS recovery of ai-0001 (SENSOR_FAULT): expected cause SENSOR_FAULT and supersedes ai-0001» (más severidad y fase). |
| 03:42 | `inv-0005` | Segundo intento obligado: **ai-0005** `SENSOR_FAULT` `recovering` `supersedes ai-0001`. |

**Causa en el código:** `MonitorState.is_gps_alert` recorría `detections_of(alerta)`; al reconocer, `_on_ack` añade `det-0004` a la alerta de la batería y esta pasa a ser «del GPS». **Matices:** fue **reconocer**, no sustituir, y lo empujó el mensaje de nuestro propio guardrail (`no_duplicate_cause`); y a T+03:42 **el guardrail impuso la causa equivocada contra un modelo que acertaba**. Efectos: ai-0005 arrastra `det-0001`, que nunca se cierra (ai-0006 y ai-0007: «stays open because…»), los `checks` del secuestro (ai-0012) dicen `gps_alert_recent: true` y el informe cuenta A1 mezclando batería y GPS («with the GPS position jumping 67.9 m when it recovered»).

**ai-0003 y ai-0004 no son alertas:** el contador `ai-` es común. ai-0003 = `AlertClosed` de ai-0002 (viento); ai-0004 = `DetectionAcknowledged` de `det-0004`; ai-0006 y ai-0007 = reconocimientos deterministas; ai-0008 a ai-0011 = respuestas del chat.

### 2. El chat del monitor no usa tools: confirmado
`inv-0008` a `inv-0011`: `aids {chat_tools_enabled: false}`, `tools_offered: []`, 1,5–1,9 s. Recibía el estado, las alertas (resumen, recomendación, `checks`, ids de evidencia) y los últimos hechos del monitor, pero **ningún dato de `BatteryStatus`** (solo los ids `bat-0001` y `bat-0002`). «You would need to consult the full log» era lo honesto con lo que tenía; «I do not have access to external tools» sale de su prompt («**You have no tools.**»). «The current state of the battery is reported as low» era un invento a partir de la severidad `low` de la detección.

### 3. Secuestro sin recuperación: confirmado, con una salvedad
En `hijack` el enlace pasa a `UNK-4F2A` en `lnk-0067` (T+05:35) y vuelve a `GCS-1` en `lnk-0076` (T+06:20). La última respuesta del monitor es de T+05:41 (`ai-0002`) y **entre T+05:41 y T+06:50 no hay ningún aviso del detector**: no existe regla del enlace. Salvedad: esa ejecución **termina pausada a T+06:50** (`plr-0009`); el cierre a T+07:21 está en `demo` (`det-0010`, `ai-0014`). La desviación de `hijack` es de 692 m a T+06:20 y de 328 m a T+06:50.

## Paso 1 · Web: el desplegable del chat

**Reproducido** con tu captura (`capturas_05-11/chat_desplegado_solapado.png`) y con Playwright (`node scripts/capture.mjs chatlayout <carpeta>`, nuevo): con el chat grande, la tarjeta `SOURCE_SILENT` del feed se pintaba detrás de la conversación. **Causa:** la raíz de `monitor-feed.tsx` no tenía `overflow-hidden` y su lista (`min-h-24`) se salía de su caja cuando el chat (`shrink-0` con la altura guardada) le dejaba menos sitio; el chat no tenía fondo propio.

**Qué se cambió:** feed con `min-h-48 overflow-hidden` (la lista, `min-h-0`), chat con `bg-card` y altura guardada que **cede** (`shrink`), y las flechas del asa parten del alto realmente visible. **Markdown en los dos chats** (`lib/chat-markdown.ts`): negrita, cursiva, listas, código en línea y en bloque, con `react-markdown` (ya estaba, sin dependencias nuevas) y sin `rehype-raw`: el HTML embebido sale como texto (https://github.com/remarkjs/react-markdown#security, comprobado en el README instalado: «typically escapes HTML»).

| Solape del feed con el chat (px) | Antes | Después |
|---|---|---|
| 1920×1080, chat a la altura máxima | 31 | **0** |
| 1440×900 | 67 | **0** |
| 1280×720 (también los chips: 7 px) | 103 | **0** |
| 18 combinaciones (3 tamaños × chat plegado, por defecto, con respuestas largas, mínima, máxima y tras recargar) | hasta 103 | **0** |

Markdown medido por DOM: `strong` 2, `em` 2, `ul` 1, `ol` 1, `li` 5, `code` 2, `pre` 1, `**` en crudo: no, `<b>raw html</b>` como texto: sí. Tests de la web 55/55 (6 nuevos, `lib/chat-markdown.test.ts`), `pnpm typecheck` y `pnpm build` sin errores. Capturas en `results/capturas/fase15/{antes,despues}/`.

## Paso 2 · Un fallo de sensor por fuente

**Escenario** `scenarios/demo-battery.yaml` = `demo` + `faults: [{source: battery, mode: mute, start_s: 25, end_s: 900}]` (se recorta al fin del vuelo, T+556,3). Determinista (dos generaciones idénticas, sha256 `8eb0bcdb…`), mismos eventos que `demo` salvo los de la batería desde T+25 s (un `mute` no cambia el ruido; test nuevo). `labels.json`: A1 viento, A2 spoofing, A3 secuestro y **F1** (`source_silent`, batería, T+25–556).

**Qué se cambió (`monitor.sensor_fault_per_source`, sin la clave apagado):**
- `AlertRecord.opened_by` (las detecciones que abrieron el episodio); `is_gps_alert` solo mira esas (no las que se le reconocen después); `fault_sources` saca la fuente (`SOURCE_SILENT` → su fuente, `GPS_DEGRADED` → `gps`, discrepancia o desviación → `position`).
- Guardrail: no se puede reconocer ni sustituir un `SENSOR_FAULT` con una detección de otra fuente. El rechazo dice con datos que es otro problema y pide alerta propia (ejemplo: «ai-1 (SENSOR_FAULT) is a fault of the battery and det-2 (SOURCE_DISCREPANCY: …) is a different problem: it needs its own alert (publish_alert without supersedes)»).
- **`no_duplicate_cause` por fuente** (no estaba en tu propuesta y hace falta: sin ello el modelo se quedaba sin salida): un `SENSOR_FAULT` de otra fuente no cuenta como causa duplicada.
- El estado dice «SENSOR_FAULT **of the battery**» (menos ancla) y el fallback `UNKNOWN` no se bloquea por un fallo de otra fuente.

**Prueba.** El "antes" **no reproduce** tu fallo: `demo-battery` sale **4/4 en las 4 ejecuciones** con el código de hoy (`e15-antes`, `e15-antes-x3`): batería abierta, `GPS_SPOOFING` propio a T+03:12 y su recuperación en su cadena. Es una decisión intermitente del 14B a T+03:12 (T=0 pero con variaciones entre ejecuciones). Para tener una prueba determinista, `test_sensor_fault_source.py` repite las llamadas de tu traza (`inv-0004` e `inv-0005`) contra el estado de entonces: **sin el interruptor** reproduce la cadena mezclada (la batería es «la alerta del GPS» y se impone `supersedes ai-1`); **con él** la discrepancia tiene alerta propia, la batería queda aparte y la recuperación sigue a la alerta de la discrepancia.

| | Antes (interruptor apagado) | Después (encendido) |
|---|---|---|
| `demo-battery` | 4/4 × 4 ejecuciones | **4/4 × 3 ejecuciones** (batería abierta al final; `GPS_SPOOFING` high → recovering; viento y secuestro bien) |
| `demo` ×1 | 3/3 (`e14-4-final` r1) | 3/3, 0 rechazos nuevos |
| `faults` ×1 | 3/3 (`e14-4-final` r1) | 3/3 |

**Honestidad:** con el 14B, si a T+03:12 elige `SENSOR_FAULT` sigue siendo suyo (no hay veto de causa sobre una discrepancia): el interruptor evita que esa decisión contamine la cadena de la batería y la recuperación, no la causa que elija. **Decisión: adoptado** (22 pruebas nuevas).

## Paso 3 · Chats con tools de lectura

**Qué se cambió:** `chat.tools_enabled: true` en `agents.yaml` (el interruptor ya existía). Las tools de los chats ya eran solo de lectura (`get_events`, `get_track_metrics`, `get_mission_plan`, `get_my_alerts`, `load_skill`; el del informe, además `get_flight_summary`) y un test lo fija (nunca `publish_alert`, `acknowledge_detection` ni `close_alert`). Prompts reescritos: el chat puede consultar datos, **abrir, cambiar o cerrar alertas es trabajo del monitor** y nunca debe decir que no tiene herramientas; las tools toman segundos (T+03:42 = 222 s) y se pide una ventana alrededor del instante; llamar sin anunciarlo y contestar una vez. El chat del monitor **sigue llevando en el sistema** sus alertas con los `checks` y los últimos hechos (con tools, además puede consultar). `chat.py`: la respuesta es el último mensaje del modelo cuando hubo tools (antes se concatenaba el «voy a consultar…» y salía un párrafo repetido: `e15-paso3-a`). Contador nuevo en `eval.md`: llamadas a tool escritas como texto.

**Texto como llamada:** 0 de 12 consultas (el motivo por el que se apagó en la Fase 3 era Qwen2.5). No hace falta detectarlo ni corregirlo; queda el contador.

Guion en `demo-battery` (con la batería ya callada), mismas preguntas antes y después (`e15-antes` frente a `e15-final`):

| Pregunta | Antes (sin tools, 2,0–4,5 s) | Después (con tools) |
|---|---|---|
| «What is the current state of the battery?» | «…reporting… no recent battery-related events… » sin un solo dato; en la ejecución manual: «reported as low», «no specific percentage provided» | `get_events battery` (2,8 s): «voltage of 25.21 V and a charge level above 99.5% at T+00:10 and T+00:20 … no battery reports since … state is unknown» |
| «What was the last battery event and what data does it have?» | «no specific values or timestamps are provided in the available information» | `get_events battery last_n 1` (2,8 s): «`bat-0002` at T+00:20 … 99.6% and a voltage of 25.21 V» |
| «Check the link now» | Hechos del monitor de T+05:41 | `get_events link` (3,6 s): «controlled by UNK-4F2A … RSSI −78.5 to −81.9 dBm, latency 117.8 to 128.1 ms» (datos del instante de la pregunta) |
| «Open an alert for the battery» | «An alert for the battery is already open… No new alert needs to be opened» | Sin tools (2,9 s): «I cannot open new alerts directly through this interface. The monitor agent is responsible for opening, closing, or modifying alerts … there is an open alert (ai-0001)…» |
| Informe: «Which was the most serious anomaly and why?» | «A4 · Drone hijacking … 714.2 m» (del informe) | Sin tools (2,9 s), mismo contenido |
| Informe: «What did the GPS do at T+03:42?» | «jumped back to the real position… 67.9 m» (de las alertas) | `get_events gps 222–232` (3,1 s): «position (x=2067.4, y=994.6) with a 3D fix, 14 satellites, HDOP 0.8 … 73.9 m away from the route» |

**Latencia:** 2,8–3,6 s por respuesta (máximo 5,2 s en la serie con el prompt anterior; 10,6 s con 3 tools en `e15-paso3-a`), muy por debajo de 20 s. **Correcciones que arreglé:** «T+03:42» leído como 3,42 s (devolvía 0 eventos y preguntaba) y el párrafo repetido. **Fallos que quedan (sin tapar):** en la primera pregunta dice «no battery reports since T+00:51» (la batería calló en T+00:20; T+00:51 es la hora de la detección) y en la última atribuye la desviación de 73,9 m a «GPS spoofing» cuando a T+03:42 es la recuperación (la cifra sale del informe, no de la tool). A 16× la respuesta llega decenas de segundos de simulación después de la pregunta (anotado en `mejoras_futuras.md`). **Decisión: adoptado.**

## Paso 4 · Recuperación del secuestro (contrato v0.16)

**Detector, regla `LINK_ANOMALY`** (`source: link`, `unit: ms`, `value` = latencia): abre si el `controller_id` deja de ser el de la misión (**el primero visto** desde `SimulationStarted`; no toca el plan ni los eventos) o si la latencia > 90 ms o el RSSI < −72 dBm (`high` con otro controlador, `medium` solo por calidad; sube a `high` con un `DetectionUpdated` si luego cambia el controlador); cierra con el controlador de la misión, latencia < 70 ms y RSSI > −68 dBm durante 5 s. Umbrales en `detector.yaml` según los datos de los siete escenarios (normal: 30–56 ms y −65 a −59 dBm; secuestro: 116–128 ms y −82 a −76 dBm). En `hijack` y `demo`: abre a **T+05:35** (3 s antes que la desviación) y cierra a **T+06:25**; `nominal`, `wind`, `spoofing`, `faults` sin ninguna detección nueva. Se apaga con `monitor.link_anomaly: false` (`__main__` la desactiva).

**Monitor (`monitor.link_anomaly`, sin la clave apagado):** skill nueva `link-anomaly` (otro controlador → `HIJACK`; mismo controlador y solo calidad → `SENSOR_FAULT` del enlace o `UNKNOWN`; sin tocar `route-deviation`). **Quién decide la fase: el código.** El cierre de la `LINK_ANOMALY` cuya alerta es un `HIJACK` `active` con un `ROUTE_DEVIATION` aún abierto (`MonitorState.link_recovery_alert`) va al modelo con una sección nueva (`link_recovered`) en lugar del reconocimiento determinista; el guardrail impone causa `HIJACK`, `supersedes` esa alerta y fase `recovering`, la severidad es `low` o `medium` (`high` se rechaza) y **reconocer se veta**; si el modelo no concluye, reconocimiento de fallback y la alerta **no** se cierra. El cierre final sigue llegando con el `DetectionCleared` de la desviación. Evaluación: cuenta «secuestro sin `recovering` cuando el enlace volvió antes que la ruta» (motivos `fallback`, `acknowledged`, `other`). `labels.json` de `hijack`, `demo` y `demo-battery` esperan también `LINK_ANOMALY` (cambian solo `runs/demo/labels.json` y `runs/hijack/labels.json`, más `runs/demo-battery/` nuevo; eventos, verdad y plan, idénticos).

**Primera versión → ajuste:** la sección `link_recovered` pedía `get_events` de 3 enlaces y no decía qué ids usar. En `demo` la recuperación tardó 32,1 s (7 iteraciones, 4 rechazos: usaba el id de la desviación, olvidaba `supersedes` y declaraba `link_anomalous = false`). Con el texto corregido (6 eventos de enlace, «deja `detection_ids` fuera», `supersedes` = esa alerta): `demo` ×2 y `hijack` ×2 con ≤ 6 iteraciones y ≤ 15,7 s.

| | Antes (`e14-4-final` r1) | Después (`e15-final`, interruptor encendido) |
|---|---|---|
| `hijack` | `HIJACK` `high` a T+05:38 y se queda así hasta T+07:21 | `HIJACK` `high` **T+05:35 → `recovering` `medium` T+06:25**, cierre T+07:21 |
| `demo` A3 | idem | `HIJACK` `high` T+05:35 → `recovering` `medium` T+06:25 |
| `demo` A1 y A2 | viento `medium`; `GPS_SPOOFING` `high` → `recovering` | **sin cambios** |

Texto de la recuperación (`hijack`): «Hijack recovery: link back to GCS-1, drone still off route» / «The command link returned to GCS-1 at T+06:20 (lnk-0076) and remains stable (lnk-0077). The drone is currently 686.1 m from the route … and 695.9 m according to radar. GPS and radar agree now». Fugas: el modelo escribe «(now.gps_radar_agree: true)» entre paréntesis (la web lo quita; `mejoras_futuras.md`). **Decisión: adoptado.**

## Comparación final (`e15-final`, ×1 cada uno, `actual`, `agent-assets` con las tres ayudas nuevas)

| Escenario | Etiquetas | Fallbacks / checks≠tools / contradicciones / sin fase | Rechazos (e14-4 r1 → e15) | Iteraciones máx. | Invocación más larga | Prompt máx. (tokens) |
|---|---|---|---|---|---|---|
| `demo` | 3/3 (3/3) | 0 / 0 / 0 / 0 | 3 → 4 | 7 → 6 | 16,6 → 16,3 s | 8 588 → 7 593 |
| `hijack` | 1/1 (1/1) | 0 / 0 / 0 / 0 | 2 → 2 | 5 → 5 | 13,8 → 8,8 s | 6 682 → 7 258 |
| `faults` | 3/3 (3/3) | 0 / 0 / 0 / 0 | 7 → 5 | 9 → 8 | 21,2 → 15,3 s | 8 398 → 8 492 |
| `demo-battery` | 4/4 (nuevo) | 0 / 0 / 0 / 0 | – → 4 | – → 6 | – → 14,8 s | – → 7 650 |

Tokens de prompt por ejecución: `demo` 191 677 → 258 950, `hijack` 74 003 → 126 745, `faults` 304 787 → 264 724 (suben por las invocaciones nuevas del monitor, la skill y los chats con tools). Chats del guion: 6 respuestas de 2,8 a 3,6 s, 0 llamadas como texto. Textos de las alertas nuevas y de los chats (antes y después): `experiments/e15-textos.md`.

## Quién decide qué (contrastado con el código)
`docs/quien_decide_que.md` actualizado: **cambia quién decide la fase del secuestro** (el código, con el cierre de la detección del enlace) **y qué es «del GPS»** (solo la fuente de las detecciones que abrieron un `SENSOR_FAULT`); **los chats** consultan datos y no pueden publicar; la causa del secuestro, la severidad y el texto siguen siendo del modelo; el detector sigue sin saber de causas.

## Revisor de contratos
Una pasada (`revisor-contratos`, parcial, sin shell). **Un incumplimiento menor, que no cambio:** `chat.tools_enabled` vale `True` sin la clave (`assets.py:335`). Es su valor de siempre (el `agents.yaml` y los assets congelados llevan la clave explícita; los congelados, `false`) y no es una ayuda del monitor; los interruptores de la Fase 15 (`sensor_fault_per_source`, `link_anomaly`) valen `False` sin la clave. Observación: la skill `link-anomaly` no está en el chat del monitor (el chat explica un secuestro con los hechos del monitor; en `mejoras_futuras.md`). Sin ningún import de `platform/` en el módulo, sin verdad ni `sim` hacia el LLM, corte temporal intacto en el chat. Sin revisar por el revisor: la web (los tests y capturas la cubren) y el cuerpo de `monitor.py`.

## Problemas (con su error literal)
- `pkill -f "python -m ai_module"` dentro de un comando mató mi propio shell (la cadena aparecía en la línea de comando): salida 144 sin más mensaje; paré los procesos por puerto.
- Reevalué una copia de `experiments/` sin `labels.json` al lado y sobrescribí su `eval.md` con `❌ 0/0 anomalías y fallos diagnosticados · 10 falsas alarmas`; lo regeneré desde `runs/demo-battery/<run_id>/` y lo copié de vuelta (sin otro efecto).
- `ValidationError … event_id 'd-gps' lacks the prefix 'det' of DetectionRaised` y `LINK_ANOMALY mide la latencia en milisegundos: unit debe ser 'ms'`: mis pruebas y el helper `detection_event` (ids de detección numéricos; `unit` de `LINK_ANOMALY`); corregidos.
- `AssertionError: ['trayectoria idéntica a nominal hasta T+556 s (truth.json): distinta', …]` y `KeyError: 'battery'` en `scenario_metrics.py`: los criterios de aceptación suponían fallos solo de GPS y radar y comparaban con `nominal` aunque hubiera anomalías; generalizado (`FAULT_EVENT_TYPE`) y limitado a escenarios sin anomalías.
- Cuatro rechazos de ruff `E501` en el hook; corregidos. Dos avisos transitorios del clasificador del modo automático («gave no verdict (error)»); reintento sin más.
- La serie del "antes" ×4 no reproduce el fallo manual (ver Paso 2): no se puede demostrar con el modelo vivo que el interruptor lo evite, solo con la repetición determinista.

## Límites
- n = 1 en `demo`, `hijack`, `faults` y `demo-battery` de la comparación final (3 en `demo-battery` del paso 2 y 2 en `hijack`/`demo` del paso 4).
- Un caso de `LINK_ANOMALY` sin cambio de controlador (solo calidad) y un secuestro donde el dron vuelve a la ruta antes que el enlace no se han probado con el modelo: ningún escenario los produce.
- El controlador de la misión es el primero visto, no el del plan.
- Las preguntas de los chats se han medido con un guion de 6; la corrección de sus textos se ha leído, no medido con métricas.

## Nota para la demo
**Funciona ya:** `demo` con la batería ya callada si se quiere (`demo-battery`: la alerta de la batería queda abierta toda la ejecución); `HIJACK` a T+05:35, antes que la desviación, con su recuperación a T+06:25 («link back to GCS-1, drone still off route») y el cierre a T+07:21; chats que consultan datos (batería, enlace, GPS en un instante) y explican que abrir alertas es cosa del monitor; chat desplegado sin solape y con Markdown.
**No tocar en directo:** no cargues otro escenario con el módulo a medias (la regla del enlace va con el monitor; sin la clave se apaga); no pidas a los chats cifras de instantes lejanos a 16× (la respuesta llega decenas de segundos de simulación después de la pregunta); el chat del informe puede atribuir mal la causa de un instante concreto: usa «most serious anomaly» o las alertas. Apagar los chats con tools: `chat.tools_enabled: false` en `agents.yaml`. Los fallos manuales con el modo interactivo (batería, GPS) siguen igual.

## Documentos actualizados
`contracts/eventos.md` (v0.16), `docs/quien_decide_que.md`, `docs/mejoras_futuras.md` (seis entradas nuevas), `scenarios/README.md`, y los `CLAUDE.md` raíz, `ai-module-py`, `platform` y `web`.

## URLs consultadas
https://github.com/remarkjs/react-markdown (README instalado en `web/node_modules/react-markdown/readme.md`: «typically escapes HTML», `allowedElements`, `unwrapDisallowed`). Ninguna otra.

## Ficheros
Nuevos: `scenarios/demo-battery.yaml`, `runs/demo-battery/`, `agent-assets/skills/link-anomaly/`, `ai-module-py/tests/{test_sensor_fault_source,test_link_recovery}.py`, `web/lib/chat-markdown.{ts,test.ts}`, `experiments/e15-*` (solo se versionan los `compare.md`) y `docs/fases/fase15.md`. Modificados: contratos (`eventos.md`, `enums.py`, `payloads.py`, `tools.py`, esquemas), `platform` (`build.py`, `scenario_metrics.py` y tests), `ai-module-py` (`detector.py`, `config/detector.yaml`, `monitor.py`, `monitor_state.py`, `agent/{guardrails,assets,profiles}.py`, `chat.py`, `evaluate.py`, `monitor_usage.py`, `runtime.py`, `__main__.py` y tests), `agent-assets` (`agents.yaml`, prompts del monitor y de los chats, `operational_knowledge.md`), `tools/experiments/run_matrix.py` (guion de `demo-battery`) y `web` (`chat-panel.tsx`, `monitor-feed.tsx`, `globals.css`, `contracts.ts`, `scripts/capture.mjs`).

## Mensaje de commit propuesto
```
feat: phase 15 - sensor faults per source, read-only chat tools, hijack recovery

demo-battery scenario (demo + battery muted from T+25 s). monitor.sensor_fault_per_source:
a SENSOR_FAULT belongs to the source of the detections that opened it; it cannot be
acknowledged or superseded by a detection of another source and is not a duplicate cause
of another source's alert.

Chats can read data (get_events, get_track_metrics, get_mission_plan, get_my_alerts,
load_skill; the report chat also get_flight_summary) but never publish or close alerts;
replies render basic Markdown and the expanded chat no longer overlaps the monitor feed.

Contract v0.16: LINK_ANOMALY detector rule (controller change, latency or signal) and
monitor.link_anomaly: when the link returns while the route deviation is still open, the
code decides cause, supersedes and phase recovering of the HIJACK alert; the model picks
low or medium severity. Hijack labels also expect LINK_ANOMALY.
```
