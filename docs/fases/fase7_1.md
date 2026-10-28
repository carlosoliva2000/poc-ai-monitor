# Fase 7.1 · E3 parte B: análisis del razonamiento (27/10/2026)

Análisis de los datos de `docs/fases/fase7_1_datos.md` (E3: `qwen3-14b-think`, `demo`, `faults` y `spoofing` × 3, frente a `qwen3-14b-t0` de `e0e1`). **No se ha ejecutado nada ni se ha arrancado vLLM.** No se ha cambiado código, prompts, skills ni perfiles; el único cambio sin guardar del repositorio sigue siendo el de los tiempos de `model-profiles/qwen3-14b-think.yaml` (parte A). Las trazas se han leído filtrando con `jq`/`grep` a partir del índice del §6 de los datos; las cifras nuevas de este documento (marcadas con *) salen de esos filtros sobre `experiments/e3/runs/qwen3-14b-think/` y `experiments/e0e1/runs/qwen3-14b-t0/`.

**Resumen:** con el razonamiento, el 14B **no acierta más** (pierde A2 en 2 de 3 demos, A3 en 1 de 3 y A1 en 1 de 3 spoofing), **no resuelve F3**, necesita un recordatorio en la mitad de sus invocaciones, es 2,5–3,5 veces más lento en reloj y deja de ser reproducible. Lo que mejora (menos rechazos del `null` y de ciclo de vida) se explica sobre todo porque **mira menos y reconoce más**, no porque decida mejor. Recomendación: **sin razonamiento en la Fase 8; seguir con `qwen3-14b-t0`.**

## 1. Think frente a t0

| | t0 (demo / faults / spoofing) | think | Lectura |
|---|---|---|---|
| Aciertos | A1 3 · A2 3 · A3 3 / F1 3 · F2 3 · F3 0 / A1 3 | A1 3 · **A2 1** · A3 2 / F1 3 · F2 3 · F3 0 / **A1 2** | **Empeora**: 14 de 21 frente a 18 de 21 (ninguna mejora) |
| Etiquetas con una cadena | todas | A2 1 de 3 en demo; el resto igual | Empeora en demo |
| Alertas abiertas al final | 0 | 1 (demo r3) + 2 (faults r1, r3) | Empeora |
| Fallbacks | 0 | 1 (demo r1 inv-0006, `repeated_rejection`) | Empeora |
| Falsas alarmas, contradicciones, no latinos | 0 / 0 / 0 | 0 / 0 / 0 | Igual |
| Rechazos (llamadas) | 9 / 9 / 3 = 21 | 8 / 2 / 0 = 10 | Mejora en número (ver §3: en buena parte porque publica menos) |
| Estabilidad | 3/3 en los tres | 1/3 · 2/3 · 2/3 | Empeora (esperable: think muestrea a temperatura 0,6) |
| Recordatorios del monitor* | 0 | **29** (en 29 de 59 invocaciones con LLM) | Empeora: fallo de formato nuevo (§3) |

Qué cambia en el comportamiento (recuentos de tools del monitor, sumas de 3 repeticiones de los tres escenarios)*:

| | t0 | think |
|---|---|---|
| `get_events` (de ellas, `link`) | 42 (18) | 23 (8) |
| `get_track_metrics` | 57 | 45 |
| `publish_alert` (intentos) | 51 | 33 |
| `acknowledge_detection` | 9 | **19** |
| `close_alert` | 18 | 16 |
| Invocaciones con LLM que deciden **sin ninguna lectura** de datos | **0 de 57** | **11 de 59** (las 11, `acknowledge_detection`) |
| Invocaciones que cargan una skill | 39 | 30 |

Los fallos nuevos tienen tres formas, todas de **decisión**:
- **Diagnostica sin seguir la skill.** A2 en demo r1 y r3 (inv-0005, T+03:42): no carga `route-deviation` (en r3 el razonamiento dice «I should load the 'route-deviation' skill. Let me do that first» y no lo hace) y pide `get_track_metrics` con la ventana de la propia detección («The detection window for det-0004 is from 222.0 to 222.0»: 0–0,8 s en vez de detección − 30). Sin viento en la ventana (`mean n/a`), en r1 declara `wind_notable = true` (rechazado) y acaba en `UNKNOWN` como alerta nueva; t0 cargaba la skill, miraba 30 s y sustituía. Ese `UNKNOWN` suelto provoca en r1 la invocación del cierre de det-0003 (en t0 la resolvía el código), donde el modelo se empeña cuatro veces en det-0004 («This invocation handles det-0003, not det-0004») hasta el fallback.
- **Reconoce donde debía publicar o cerrar.** F3 en las tres repeticiones (§2), la recuperación de spoofing (inv-0002: t0 publica `GPS_SPOOFING` que sustituye en 3/3; think reconoce en 3/3, en r1 sin ninguna lectura y en r3 solo tras cargar la skill), y el fin de F2 en faults r1 y r3 (inv-0011: «GPS and radar still disagree» y `acknowledge_detection` en vez de `close_alert`, el mismo error que tenía `actual` en la fase 7). No lo para ningún guardrail: el de «Nothing changes» solo actúa sobre `publish_alert`, y un `acknowledge_detection` sobre una alerta abierta siempre es válido de formato.
- **Razona en contra de la skill.** spoofing r2 inv-0001: con la skill cargada (que dice «the radar has no bias») y el GPS sano, concluye «Since the GPS is working normally, the most probable cause is a sensor fault in the radar» y publica `SENSOR_FAULT`.

## 2. F3: el razonamiento no lo resuelve

En las tres repeticiones, el aviso `SOURCE_SILENT gps` (det-0008, T+05:04, inv-0008) se contesta con **una sola llamada, `acknowledge_detection` sobre la alerta `GPS_JAMMING` abierta**: sin cargar la skill, sin `get_events` y sin publicar alerta propia (t0 al menos publicaba, aunque con `GPS_JAMMING`). El razonamiento (397, 909 y 625 tokens) **no menciona el paso 5, ni el radar, ni el enlace** (búsqueda de `radar`, `link`, `step 5`, `own alert`, `different fault`, `receiver`: 0 en las tres).
- **r1:** «If the GPS is jammed, it might stop sending updates, leading to the SOURCE_SILENT detection… this new detection doesn't change the cause or severity. Therefore, I should acknowledge».
- **r2:** sabe qué skill toca y no la carga: «Since det-0008 is a SOURCE_SILENT, the appropriate skill is source-discrepancy… So the skill for this detection is source-discrepancy», y aun así: «the existing alert already covers this. Therefore, the response would be to acknowledge».
- **r3:** llega a dudar («might be a sign of jamming or a sensor fault»; «need to check if there's another possible cause, like a sensor fault») y lo descarta sin mirar: «given the existing alert is GPS_JAMMING, which includes signal interference, it's plausible».

Lo que domina el razonamiento es la regla general del prompt («if the detection belongs to an open alert and nothing changes, use acknowledge_detection»), la misma que el paso 5 contradice («It is always a different fault and carries its own alert, even if another one is open»). Como no se carga la skill, el modelo **nunca ve** esa frase. Razonar más no sustituye a leer la skill: sigue haciendo falta un cambio en la skill, en el prompt o una regla (decisión de Carlos, fuera de E3).

## 3. Ayudas: cuáles parece necesitar menos y cuáles más

- **`link_anomalous = null`** (rechazo de formato): 12 → 2 mensajes. Una parte es real: por lectura del enlace, t0 lo dejaba en `null` 12 veces de 18 (67 %) y think 2 de 8 (25 %)*. Otra parte es que **mira el enlace menos** (18 → 8 lecturas; en spoofing, 3 → 0). Con n tan pequeño, el guardrail **no se puede quitar**: sigue disparándose y además es barato.
- **Rechazos de ciclo de vida** («Nothing changes… use acknowledge_detection» 9 → 0; «This is the recovery… supersedes» 9 → 1): la caída es aparente. think ya no intenta el `publish_alert` que estos mensajes paran porque **va directo a `acknowledge_detection`** (9 → 19), también cuando no toca (F3, recuperación de spoofing, fin de F2). El sesgo se ha dado la vuelta: si en la Fase 8 se quitaran estas ayudas con think, el problema que aparecería es el contrario (reconocer de más), y para ese **no hay ayuda hoy**. Con t0 siguen siendo necesarias igual que en la fase 7.
- **Necesita más:**
  - **El recordatorio** (orquestación, no está en el §3 de `quien_decide_que.md`): 0 con t0, 29 con think. En 28 de 29 el intento fallido es la iteración 2: un texto con `<tool_call><tool_call>` duplicado, `tool_calls` vacío y 1 token de razonamiento. Sin recordatorio, esas invocaciones habrían terminado en fallback. ⚠️ No he comprobado si la causa es la plantilla de Qwen3, el analizador `hermes` de vLLM o su combinación con `tool_choice: required` y el razonamiento; solo describo el patrón.
  - **Ids de la detección que se atiende**: 4 mensajes nuevos (demo), todos en invocaciones de cierre con dos alertas abiertas; el guardrail los describe y en r3 el modelo se corrige, en r1 no (fallback).
  - **Coherencia del viento**: vuelve a hacer falta (2 mensajes `wind_notable`/`wind_with_drift` y 1 «WIND requires notable wind», demo r1 inv-0005), que t0 no necesitaba.
- **`computed_facts`, `require_checks`, guardrail de coherencia:** nada en E3 sugiere que think los necesite menos; los fallos de §1 son justo de no usar los hechos (ventana de 0 s) o de razonar contra ellos.

## 4. Recordatorio: ¿pierde el razonamiento anterior?

Descripción, sin juicio:
- Tras el recordatorio, la plantilla deja de mostrar el razonamiento previo (§1 de los datos). En las trazas se ve: el razonamiento de la llamada siguiente **vuelve a empezar desde cero** en 27 de 29 casos («Okay, let's tackle this step by step…», «First, I need to load the route-deviation skill as instructed», cuando ya está cargada), frente a 7 de 79 en el resto de llamadas que no son la primera de su invocación*.
- **No repite lecturas** (0 de 29; dato de la parte A): reconstruye el plan a partir de los resultados de tools que siguen en `messages`.
- **Cambia de plan en 7 de 29** (la primera tool tras el recordatorio no es la del texto fallido). Dos ejemplos leídos: faults r1 inv-0003 (`GPS_DEGRADED`) iba a pedir `get_events` del radar y, tras el recordatorio, sigue el paso 4 de la skill (métricas y GPS; publica `SENSOR_FAULT`, que inv-0004 sustituye por `GPS_JAMMING`); spoofing r3 inv-0002 iba a pedir `get_track_metrics` y, tras 1565 tokens de razonamiento nuevo, contesta `acknowledge_detection` **sin ninguna lectura**. No puedo atribuir a la pérdida del razonamiento ningún fallo concreto de §1: también hay acks sin leer y sin recordatorio (F3, inv-0008, en las tres repeticiones).

## 5. Idioma del razonamiento

Todo en inglés: las 191 llamadas con razonamiento empiezan por «Okay, …» (157 «Okay, let's», 20 «Okay, let me»), 0 caracteres no latinos (parte A) y 0 líneas con palabras funcionales del castellano*. Tiende a referirse al prompt como «the user» («The user has provided a detailed scenario…»). Sin efecto visible en la salida (0 no latinos en monitor, informe y chats).

## 6. Coste frente a t0

| | demo | faults | spoofing |
|---|---|---|---|
| Llamada del monitor p50 | 0,9 → 8,6 s (×9,6) | 0,9 → 8,7 s (×9,7) | 0,7 → 9,2 s (×13) |
| Invocación del monitor p50 / p95 | 5,5 / 13,9 → 30,3 / 66,0 s | 6,6 / 12,8 → 19,4 / 62,0 s | 7,5 / 13,2 → 37,7 / 72,9 s |
| Reloj por ejecución | 102 → 356 s (×3,5) | 101 → 266 s (×2,6) | 63 → 158 s (×2,5) |
| Tokens de prompt | +16 % | −29 % | −2 % |
| Tokens de respuesta | ×5,0 | ×3,6 | ×3,9 |
| Parte de la respuesta que es razonamiento | 78 % | 80 % | 80 % |

- Las llamadas se encarecen ~10×; las invocaciones algo menos (×3–5) porque hace menos llamadas por invocación (p50 de iteraciones 4 → 4 / 5 → 2,5 / 4 → 3) y en faults lee mucho menos (de ahí el −29 % de prompt).
- **En la demo en directo**, con «esperar al agente», el dron se queda parado hasta ~73 s en un aviso (p95 de 62–73 s frente a 13–14 s): se nota mucho delante del público.
- **Para la Fase 8**, la matriz de tres escenarios × 3 tarda ~2,5–3,5 veces más (≈ 39 min frente a ≈ 13 min de ejecución, sin arranques).

## 7. Recomendación

**Razonamiento: no** para la Fase 8. Seguir con **`qwen3-14b-t0`**.
- No aporta aciertos: 14 de 21 frente a 18 de 21 (etiqueta × repetición), y F3 sigue en 0/3 sin que el razonamiento llegue siquiera a cargar la skill.
- Lo que parece mejora (menos rechazos) es en gran parte un sesgo hacia `acknowledge_detection` que hoy ningún guardrail vigila: 11 decisiones sin mirar ningún dato, frente a 0.
- Introduce un fallo de formato que t0 no tiene (29 recordatorios) y un fallback.
- Para quitar ayudas en la Fase 8 hace falta medir el efecto de cada una; t0 es reproducible (3/3 estable) y think no (1/3–2/3), así que con think haría falta el triple de repeticiones a 3 veces el coste cada una.
- Lo que sí aprendemos de E3 es útil sin el razonamiento: el razonamiento **cita la skill que toca y el paso que toca, y no lo ejecuta** (A2 r3: «Let me do that first»; A3 demo r1 inv-0008: «Step 5: Hijacking? Check the link… Need to call get_events for link», y publica `UNKNOWN` sin mirarlo). Confirma el punto 2 del §4 de `quien_decide_que.md`: el árbol largo de la skill no se ejecuta por leerlo, también con razonamiento.
- No he medido `qwen3-30b-a3b-think`; con estos resultados no lo recomiendo como siguiente paso (más coste y el 30B ya era peor sin razonar). E2 sigue como en la fase 7 (§8.1).

## 8. Límites

- **n pequeño:** 3 repeticiones por escenario y tres escenarios; las diferencias de aciertos son de 1–2 etiquetas, y con think (que muestrea) otras 3 repeticiones podrían salir algo distintas. No hay intervalos de confianza.
- **Comparación desigual:** t0 es determinista (3 repeticiones ≈ 1) y think no; parte de la «inestabilidad» es el muestreo que el perfil think pide (temperatura 0,6), no el razonamiento en sí. No se ha probado think a temperatura 0 ni t0 muestreando.
- **Tiempos:** los de think se tomaron con los topes nuevos (parte A); el informe tocó su tope (24,0 de 24 s) sin cortarse.
- **No he leído:** los informes (`informe.md`) ni los chats de E3; las trazas enteras (solo las invocaciones del índice del §6, filtradas); ni el razonamiento de las 72 invocaciones una a una (los recuentos marcados con * son filtros por palabras o por forma, p. ej. «empieza desde cero» se ha detectado con un patrón de frases de arranque).
- La causa del `<tool_call><tool_call>` no está comprobada (⚠️ §3).

## 9. `docs/quien_decide_que.md`

Contrastado, **sin cambios**: el razonamiento no cambia quién decide nada (las mismas piezas deciden lo mismo; solo cambia cómo lo hace el modelo). Los resultados refuerzan dos cosas que ya dice: el punto 2 del §4 (el modelo no ejecuta el árbol de la skill, ahora también razonando) y el pendiente de `faults` del §6 (F3 y las alertas abiertas, candidatas a regla). La conclusión de §3 sobre el recordatorio (de 0 a 29) es del perfil, no de quién decide; está en este documento.

## 10. Copias (reglas 13 y 15)

Actualizadas `snapshots/fase7_1/` y `snapshots-limpias/fase7_1/` con los comandos de las reglas 13 y 15 (entran `experiments/e3/compare.md` y `experiments/e3-medida/compare.md`; `docs/` solo en la primera). Las dos comprobaciones de la regla 15 (palabras prohibidas y nombres propios) **salen vacías**; no ha hecho falta corregir nada. `fase7_1.md`, `fase7_1_datos.md` y `quien_decide_que.md` copiados también a `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/docs/fases/`.

## 11. Mensaje de commit propuesto

```
feat: phase 7.1 - experiment E3 (Qwen3-14B with reasoning)

- model-profiles/qwen3-14b-think.yaml: timeouts measured with one demo run
  (monitor 37 s per call and 99 s per invocation, chats 11/14 s, report 24 s)
- docs: phase 7.1 data (think vs t0 on demo, faults and spoofing x 3) and
  analysis: no accuracy gain, F3 still failing, a bias towards
  acknowledge_detection without reading data, 29 reminders for a duplicated
  tool call tag, 2.5-3.5x wall time; recommendation: no reasoning for phase 8,
  keep qwen3-14b-t0
- experiments/e3/compare.md and experiments/e3-medida/compare.md
- no change to prompts, skills, agents.yaml or code
```
