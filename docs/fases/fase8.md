# Fase 8 · Liberar al agente, parte B: análisis (28/10/2026)

Análisis de los datos de `docs/fases/fase8_datos.md` (perfil base `qwen3-14b-t0`, 1 repetición, seis escenarios; matrices `e8-base`, `e8-una` y `e8-comb`). **No se ha ejecutado nada** ni se ha arrancado vLLM; no se ha cambiado código, prompts, skills, perfiles ni `quien_decide_que.md`. Fuentes: las tablas de `fase8_datos.md`, las filas de detalle de los `compare.md` y **solo** las trazas de `faults` del índice (§5 de los datos), leídas con `jq`:

| Traza | Ruta |
|---|---|
| B0 | `experiments/e8-base/runs/qwen3-14b-t0/faults/r1/llm_trace.jsonl` |
| sin `require_checks` | `experiments/e8-una/runs/qwen3-14b-t0-sin-require-checks/faults/r1/llm_trace.jsonl` |
| sin `source_silent_own_alert` | `experiments/e8-una/runs/qwen3-14b-t0-sin-silent-own-alert/faults/r1/llm_trace.jsonl` |
| sin `computed_facts` | `experiments/e8-una/runs/qwen3-14b-t0-sin-computed-facts/faults/r1/llm_trace.jsonl` |

Clases de fallo (como en la Fase 7): **formato**, **decisión**, **ids**, **bucle**, **tiempo**. «inv-NNNN» es la invocación del monitor en la traza de `faults`.

## 1. Ayuda por ayuda

Costes frente a B0 (seis escenarios sumados): rechazos 14, iteraciones p50/máx. 4/7, invocación p50/p95 7,2/12,9 s, 502 734 tokens.

### 1.1 `computed_facts` (hechos calculados en `get_track_metrics`) — **hace falta**
- **Qué cambia en la tool.** Comparado en inv-0003: sin la ayuda, `wind` pierde `wind_to_deg`, `drift_vs_wind_deg`, `notable` y `with_drift`, y desaparecen `gps_radar.disagreed` y `gps_max_step_m`. Quedan las cifras (media del viento 1,6 m/s, `from_deg` 298,6, `drift_direction_deg` 103,7, distancia GPS–radar media 7,0 m).
- **Qué falla (decisión).** El modelo no compara los números: en su primera `publish_alert` declara `wind_notable = true` y `gps_radar_disagreed = true` en las seis invocaciones con alerta de `faults` (inv-0001, 0003, 0004, 0005, 0006, 0008), sea cual sea el dato. El guardrail de coherencia lo rechaza **diciéndole el valor correcto** («`checks.wind_notable = true` does not match get_track_metrics (false)»), y el modelo vuelve a pedir `get_track_metrics` (la misma ventana) y corrige **un campo cada vez**, a veces pasándose: en inv-0001 e inv-0003 cambia `wind_with_drift` a `false` sin motivo y hace falta un tercer intento. Es decir, sin los hechos el que calcula es el guardrail y el modelo copia el resultado del rechazo.
- **Qué se publica mal (decisión, texto).** El texto se escribe con la primera suposición y el guardrail solo corrige los `checks`, no la prosa: ai-0001 (inv-0001) dice «wind conditions (met-0012) are notable but not extreme» y ai-0003 (inv-0003) «Wind is notable and contributes to the drift», ambas con `wind_notable = false`. En B0 las mismas alertas dicen «The link status is stable» y «Wind conditions are not notable». Son las 2 contradicciones de la tabla.
- **Coste que quita la ayuda.** 33 rechazos (47 frente a 14; los 34 de `wind_notable`, `wind_with_drift` y `gps_radar_disagreed`), iteraciones 5/10 frente a 4/7, invocación p50/p95 10,5/19,7 s frente a 7,2/12,9 s, tokens +32,6 %. inv-0008 llega a **10 iteraciones de 12**: con un rechazo más por invocación se agotaría `max_iterations` y saltaría el fallback (riesgo de **bucle/tiempo**, no observado).
- Etiquetas iguales a B0: el diagnóstico no cambia porque la causa la decide con la calidad del fix del GPS y el silencio, no con el viento; pero los hechos son los que sostienen `WIND` (A1) y la recuperación.

### 1.2 `source_silent_own_alert` (alerta propia para la fuente callada) — **hace falta**
- **Qué falla (decisión).** inv-0008 (`SOURCE_SILENT` del GPS con la alerta `GPS_JAMMING` de F2 abierta) es idéntica en B0 y sin la ayuda hasta la llamada decisiva: `load_skill("source-silence")` (no existe), `load_skill("source-discrepancy")`, `get_events(gps, 5)`, `get_track_metrics(299–304)` y `publish_alert` con `GPS_JAMMING`, alta, `supersedes: ai-0006`, `link_checked: false`. En B0 la regla lo rechaza («a SOURCE_SILENT warning is a different fault… publish_alert with cause SENSOR_FAULT and without supersedes») y el modelo publica `SENSOR_FAULT` media; sin ella se publica tal cual y **F3 pasa a ❌**. Es el mismo fallo de los tres modelos de la Fase 7 (9 de 9 ejecuciones): la regla es la que lo resuelve, el modelo no.
- **Coste que quita.** Un rechazo y una iteración en inv-0008. La bajada a 12 rechazos y 4/5 iteraciones no es toda de la ayuda: en inv-0001 (radar mudo, F1, donde la regla no actúa) el modelo no pide el enlace y se ahorra el rechazo de `link_anomalous = null` (5 iteraciones frente a 7). Esa diferencia es de la ejecución, no del interruptor (ver §6). inv-0009 pasa a respuesta determinista porque la alerta del GPS sigue teniendo detecciones abiertas.

### 1.3 `require_checks` (`checks` obligatorios) — **dudosa**
- **Nunca actuó.** En ninguna de las ocho configuraciones hay un rechazo por `checks` ausentes, y sin la ayuda el modelo los sigue escribiendo en todas las `publish_alert` de `faults` (10 de 10, comprobado en la traza).
- **Qué cambia (decisión, ciclo de vida).** Apagarla quita `checks` de la lista de obligatorios del esquema de `publish_alert`; el prompt de inv-0003 pasa de 3682 a 3679 tokens. Con ese esquema, en inv-0004 (`SOURCE_DISCREPANCY` de la pérdida de GPS) el modelo propone lo mismo que en B0 (`GPS_JAMMING`, alta, mismos `checks`) **salvo `supersedes`: `null` en vez de `ai-0003`**. En B0 eso se rechazaba por «Nothing changes» y acababa en reconocimiento; con `supersedes: null` ninguna regla lo para y se publica una **segunda alerta `GPS_JAMMING`** con otra abierta de la misma causa: F2 queda con 2 cadenas. Después, inv-0005 añade un rechazo (`link_anomalous = null`) y otro «Nothing changes» contra la alerta nueva, inv-0008 cita `ai-0004` e inv-0010 la cierra el modelo (2 iteraciones) en vez del código.
- **Lectura.** El fallo no lo causa que falten las comprobaciones, sino un cambio de 3 tokens del esquema a temperatura 0, y deja ver un hueco de reglas: **nada impide abrir una alerta nueva con la misma causa que una abierta** (es el F2 de 2 cadenas que tenía `actual` en la Fase 7). Una sola ejecución y efecto indirecto: dudosa.
- **Ojo:** la exigencia de `checks` vive dentro de `check_coherence` (`guardrails.py`); con el guardrail de coherencia apagado, `require_checks` solo hace obligatorio el campo en el esquema.

### 1.4 `coherence_guardrail` (guardrail de coherencia, con la recuperación excluyente) — **se puede quitar**
- **Qué falla sin él.** Nada en estos seis vuelos: mismas etiquetas, cadenas, cierres, 0 abiertas, 0 contradicciones. En B0 **no vetó ninguna causa** (no hay rechazos de `WIND`, `HIJACK` o GPS sobre `ROUTE_DEVIATION` en ningún perfil); sus 9 rechazos fueron 6 de `link_anomalous = null` (formato) y 3 de recuperación (decisión).
- **Recuperación.** Sin la regla, los 3 rechazos de recuperación desaparecen y «Nothing changes» sube de 4 a 7: el modelo propone la causa anterior con su severidad, se le manda reconocer y después publica. Las cadenas quedan con la misma forma que en B0 (`GPS_SPOOFING/GPS_SPOOFING` en demo y spoofing, `GPS_JAMMING` ×3 en F2, según los `compare.md`), así que la recuperación sí sale como alerta que sustituye. **La severidad de esas alertas no la he comprobado** (no hay trazas de este perfil en el índice y la evaluación no mide la severidad).
- **Coste que quita.** 6 rechazos (8 frente a 14), iteraciones máx. 6 frente a 7, invocación p50/p95 6,1/9,7 s frente a 7,2/12,9 s (−1,1 s y −3,2 s), tokens −5,0 %. Casi todo es el rechazo de formato de `link_anomalous = null`.
- **Lo que se pierde aunque no se vea:** con él apagado **nadie contrasta los `checks` con las tools**. La evaluación cuenta frases que contradicen los `checks`, no `checks` que contradicen los datos, así que un `wind_notable` falso pasaría sin dejar rastro en `eval.md`.

### 1.5 `final_iteration_response_tools_only` (última iteración solo con las respuestas) — **se puede quitar**
- Solo actúa en la iteración 12 y el máximo observado es 7 (B0) y 10 (sin hechos calculados): **no se activó nunca**, ni en B0. Resultado y costes iguales a B0 (14 rechazos, 4/7, +0,06 % de tokens; la p95 de 13,2 s frente a 12,9 s es ruido). El experimento no prueba que sobre: prueba que con este modelo no se llega a usar.

### 1.6 `tool_choice: required` — **se puede quitar**
- Con `auto`: 0 recordatorios en todos los perfiles, así que el modelo contestó siempre con una tool call; no hay fallos de **formato**. Mismo resultado; 13 rechazos, iteraciones máx. 6, tokens −2,5 % (diferencias del orden del ruido de §6). Es la ayuda que más falta hacía a `actual` (Qwen2.5) y la que menos al 14B.

## 2. La combinación (`sin-todas-las-sobrantes`)
Guardrail de coherencia, última iteración restringida y `tool_choice: required` apagados a la vez: **sin interacciones**. Mismas etiquetas y cadenas que B0 en los seis escenarios, y los contadores son prácticamente los del guardrail apagado solo (8 rechazos; 4/6; 6,1/9,6 s; 477 372 tokens, −5,0 %). Las otras dos ayudas no añaden nada encima, coherente con que una no se activa nunca y la otra no corrige nada.

La interacción que sí existe **no se ha medido en la combinación**: sin hechos calculados, el que da los valores correctos es el guardrail de coherencia (§1.1). Apagar los dos a la vez publicaría `checks` equivocados en las seis alertas de `faults` y nadie lo vería (§1.4).

## 3. Clasificación

| Ayuda | Clasificación | Por qué |
|---|---|---|
| `computed_facts` | **hace falta** | Sin ella el modelo escribe los `checks` al azar (decisión); +33 rechazos, +33 % de tokens, 10 de 12 iteraciones y 2 frases que contradicen. Además, solo funciona porque el guardrail le da los valores. |
| `source_silent_own_alert` | **hace falta** | F3 ✅→❌ (decisión), mismo fallo que con los tres modelos de la Fase 7. Cuesta 1 rechazo. |
| `require_checks` | **dudosa** | No se activó nunca; el cambio de F2 (2 cadenas) es de una sola ejecución y viene de la forma del esquema, no de que falten comprobaciones. |
| `coherence_guardrail` | **se puede quitar** | Ningún veto de causa en seis vuelos; quita sobre todo rechazos de formato. Con dos condiciones: mantener `computed_facts` y medir los `checks` en la evaluación. |
| `final_iteration_response_tools_only` | **se puede quitar** | No se activó nunca (máx. 7 de 12 iteraciones). |
| `tool_choice: required` | **se puede quitar** | 0 recordatorios con `auto`; sin efecto. |

Con 1 repetición a temperatura 0, «se puede quitar» significa «en estos seis vuelos el resultado no cambia»: no mide la variabilidad ni otros guiones. Y como `F2` muestra, un cambio pequeño del contexto (3 tokens) puede llevar al modelo a otra rama de decisión; una ayuda que «no hace nada» en seis vuelos puede hacer algo en el séptimo.

## 4. Recomendación

**Configuración para seguir: la de `qwen3-14b-t0-sin-todas-las-sobrantes`** (guardrail de coherencia, última iteración restringida y `tool_choice: required` apagados; `computed_facts`, `source_silent_own_alert` y `require_checks` encendidos). Es la única combinación medida entera, da el mismo resultado que B0 con un 43 % menos de rechazos, una p95 de invocación un 25 % más baja (9,6 s frente a 12,9 s) y un 5 % menos de tokens. `require_checks` se queda encendido porque así se midió y no cuesta nada (con el guardrail apagado solo deja el campo obligatorio en el esquema).

Condición antes de adoptarla: que la evaluación cuente **`checks` que no cuadran con las tools** (lo que hasta ahora vigilaba el guardrail en tiempo real; el módulo ya calcula esos valores aunque no los use). Sin esa métrica, quitar el guardrail convierte un fallo visible (rechazo) en uno invisible. Es un cambio de código: lo decides tú.

**¿E4 para quitar las dos que hacen falta? No merece la pena con ese objetivo.**
- `source_silent_own_alert`: F3 lo fallaron igual `actual`, Qwen3-14B y Qwen3-30B-A3B (Fase 7, 9 de 9). Es un patrón de la skill y del prompt («hay una alerta del GPS abierta, será lo mismo»), no de un modelo concreto; la regla cuesta un rechazo y es la decisión mecánica que el diseño ya pone en código.
- `computed_facts`: calcular hechos en código es el principio que funcionó (punto 3 de «Qué contar al equipo» de `quien_decide_que.md`), lo usan también los chats y abarata al modelo (−33 % de tokens); quitarla con un modelo mejor solo serviría para demostrar que puede comparar ángulos, no mejoraría la demo.
- E4 tiene sentido con **otro objetivo**: elegir modelo (calidad del texto, robustez del ciclo de vida, coste) **con la configuración propuesta**. En ese caso, para Qwen3-30B-A3B-Instruct-2507, gpt-oss-20b y Ministral 3 14B: comprobar antes que estén en la caché de Hugging Face (si no, preguntar; `HF_HUB_OFFLINE=1`) y qué parser de tool calls necesita cada uno en vLLM (⚠️ no lo he comprobado), y usar 3 repeticiones, porque el 30B-A3B ya no fue reproducible a temperatura 0 en la Fase 7.

## 5. Qué cambiaría en `quien_decide_que.md` si se adopta
Solo descrito; no se ha aplicado.
- **Cabecera:** estado al cierre de la Fase 8 con el perfil adoptado y las tres ayudas apagadas.
- **§1, fila Guardrails:** se quedan formato, ids (incluido «Nothing changes»), evidencias y la regla de la fuente callada; desaparecen la comparación de `checks` con las tools, los tres vetos de causa (`WIND`, `HIJACK` y causas del GPS sobre `ROUTE_DEVIATION`), la exigencia de `link_checked`/`link_anomalous` y la recuperación impuesta.
- **§1, fila Orquestación:** el valor esperado de `link_anomalous` ya no se usa para vetar (solo lo usaría la evaluación).
- **§1, fila Agente monitor:** sus `checks` tampoco se verifican antes de publicar (hoy solo se dice del texto). Fila Evaluación: añadir la métrica de `checks` contra tools, si se hace.
- **§2:** Viento, Secuestro y Pérdida de GPS: «Modelo», **sin veto**. **Recuperación del GPS: pasa de «Código (guardrail)» a «Modelo»**; medido que publica la recuperación como alerta que sustituye a la anterior, sin comprobar la severidad. Fuente callada: sin cambios (sigue la regla). Cierre: sin cambios.
- **§2, «En una frase»:** los guardrails vetan lo incoherente en ids y en la fuente callada; ya no deciden la recuperación.
- **§3:** marcar como apagadas en la Fase 8, con su medida, `coherence_guardrail`, `final_iteration_response_tools_only` y `tool_choice`; anotar que `require_checks` solo actúa con el guardrail de coherencia; `computed_facts` y `source_silent_own_alert` como necesarias con este modelo.
- **§4, punto 3:** matizar: con el 14B bastan los hechos calculados y las reglas mecánicas de ciclo de vida; vetar lo incoherente dejó de hacer falta (sigue haciéndola con `actual` y con el 30B, Fase 7).
- **§6:** «Liberar al agente» hecho para el 14B; nuevo pendiente: regla para no abrir una alerta nueva con la misma causa que otra abierta (F2 de 2 cadenas, visto en `actual` y en `sin-require-checks`).

## 6. Límites
- **1 repetición por perfil.** A temperatura 0 el 14B repite su decisión ante la misma entrada, pero **la entrada no es idéntica entre ejecuciones**: con «esperar al agente», el instante de cada invocación varía unas décimas (inv-0001: 125,1 s en B0, 125,4 s sin hechos, 125,7 s sin la regla de la fuente callada). En `sin-silent-own-alert`, inv-0001 no depende del interruptor (el prompt tiene los mismos tokens hasta la llamada 4) y aun así el modelo cambia de camino. Por eso diferencias de ±1–2 rechazos o iteraciones no se pueden atribuir a una ayuda; B0 frente a `e72b` ya difería en uno.
- **Solo he leído trazas de `faults`**, las del índice. Lo dicho sobre los otros escenarios y sobre los perfiles sin trazas (`sin-coherence-guardrail`, `sin-final-tools-only`, `sin-tool-choice`, la combinación) sale de los contadores de `fase8_datos.md` y de las filas de detalle de los `compare.md`. La recuperación sin guardrail (§1.4) es una inferencia de los contadores (−3 rechazos de recuperación, +3 «Nothing changes») y de la forma de las cadenas, no de la traza.
- **La evaluación no mide la severidad ni los `checks` contra los datos**, así que «sin cambios» no cubre esas dos cosas.
- **Una sola configuración sin dos ayudas no se probó:** `computed_facts` + `coherence_guardrail` apagados a la vez; la conclusión de §2 sobre ese caso sale de leer las trazas, no de ejecutarlo.
- Los seis escenarios son los de la demo: con 14B no hay casos en que el guardrail tuviera que vetar una causa, así que no se ha probado su valor como red de seguridad frente a un error de causa (en la Fase 7 sí lo tuvo con `actual` y con el 30B).

## 7. Copias (reglas 13 y 15)
`snapshots/fase8/` y `snapshots-limpias/fase8/` actualizadas con este documento (la limpia no lo incluye porque excluye `docs/`; se rehízo igualmente). Las dos comprobaciones de la regla 15 salen **vacías**. Documento copiado a `results/docs/fases/`.

## 8. Mensaje de commit propuesto
```
docs: phase 8 (part B) - analysis of removing the monitor aids

- docs/fases/fase8.md: per-aid analysis with qwen3-14b-t0 (needed:
  computed facts and own alert for a silent source; doubtful: mandatory
  checks; removable: coherence guardrail, final-iteration restriction and
  tool_choice required), the combination, the proposed configuration and
  what would change in who-decides-what
- no change to code, prompts, skills or profiles
```
