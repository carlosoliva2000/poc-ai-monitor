# Fase 14.1 · Textos, hechos de «ahora» e informe de misión (04/11/2026)

Escrito para: Carlos, que decide qué se queda de la 14.1 y qué pasa a la 14.2. Perfil `actual` (Qwen3-14B-AWQ sin razonamiento, T=0). Base: `experiments/e12-cierre/` (huella de `agent-assets` `293927dd0c038af5`). Contrato: **un cambio aditivo (v0.13, el bloque `now`)**, que aprobaste. No se arrancó ningún híbrido; vLLM, plataforma, módulo y web quedaron parados al terminar, puerto 8000 libre y GPU en reposo (0 MiB). Git solo de lectura.

## Resumen

| Paso | Qué se cambió | Huella `agent-assets` | Evaluación frente a su base | Medida de textos | Decisión |
|---|---|---|---|---|---|
| 1 · Medida | `tools/experiments/text_metrics.py` (+10 tests) | `293927dd0c038af5` | – | línea base: 26 fugas, 0 errores | hecho |
| control | `demo` con los textos congelados (`actual-textos-v13`) | `293927dd0c038af5` | misma firma que `e12-cierre` (9 respuestas, mismas causas y severidades, 3 rechazos) | – | el juego antiguo sigue disponible |
| 2 · `now` | bloque `now` en `get_track_metrics`; skills y cierre dicen cuándo usarlo | `fb63ccbf0538279f` | igual (6/6, todo a 0, rechazos 3/0/1/1/1/5) | fugas 26 → 26, errores 0 → 0 | **adoptado** |
| 3a · Plantillas | criterio en `monitor_output.md`, skills sin frases ni valores fijos, rechazo de la recuperación sin frase | `2b9eb18cbf6a52e8` | igual (6/6, todo a 0, rechazos 3/0/1/1/1/5) | fugas 26 → **7**; errores 0 → 4 (ver «Para decidir») | **adoptado**, con reserva |
| 3a′ · Línea de estado `data` | (ablación) la línea de la recuperación sin frase | – | 6/6, pero en `demo` **desaparece la alerta de recuperación** (0 sustituciones frente a 1) | fugas 11 | **no adoptado**: `state_line: legacy` |
| 3b · Muletas | quitar «Every step of your work is a tool call» y la regla 10 | `d1f74f0061307f09` | 6/6, pero en `faults` F2 pierde la alerta de recuperación; rechazos 5 → 6 | fugas 7 → 9 | **revertido** (`monitor_system.md` idéntico al de antes) |
| 4 · Informe | informe de misión + autoevaluación aparte (2.ª llamada) | `c16120188410b179` | igual (6/6, todo a 0, rechazos 3/0/1/1/1/5) | fugas del informe de misión 7 → 6 | **adoptado** |

Huella final: **`c16120188410b179`**. Pruebas: módulo de IA 454 (428 + 26), plataforma 225, contratos 130 (+1 omitida), web 48; `ruff check` y `ruff format --check` limpios en los cuatro componentes; `typecheck` y `pnpm build` de la web limpios. Revisor de contratos: el agente `revisor-contratos` no encuentra incumplimientos (contrato v0.13 coherente entre documento, modelo, esquema, plataforma y `tools.json`; corte temporal correcto; sin imports de `platform/` en `ai-module-py`; sin verdad ni etiquetas fuera de `evaluate.py`; `assets` de perfil acotado a carpetas `agent-assets*`). Observación menor suya: con `now_facts: false` la descripción de la tool en `tools.json` sigue nombrando `now` (solo ocurre con assets que no lo desactivan por su cuenta; los congelados llevan su propio `tools.json`) y los chats con tools habilitadas verían `now` siempre (en la demo van sin tools)

## Para decidir

1. **La medida ampliada dice que los pasos 3a y 4 introducen errores de contenido que antes no había.** Cuando leí los textos vi dos errores que la medida del paso 1 no detectaba y añadí dos reglas (con tests): «GPS and radar disagree by N m» con N por debajo del umbral de discrepancia (25 m) y «el viento no empuja con la deriva» cuando los hechos dicen que sí. Con ellas: base 0 errores, paso 2 → 0, paso 3a → 4, paso 4 → 5. Son **dos problemas distintos**, los dos por mezclar «ahora» con la ventana:
   - la alerta de recuperación del spoofing (`demo` T+03:42) dice «GPS and radar disagree by 9.9 m» (9,9 m es la distancia **actual**: coinciden), en el resumen y en la explicación (cuenta dos);
   - los cierres del viento y de `demo` dicen «The wind is currently light (2.3 m/s from NW) and does not push in the direction of the drift (164.7°)»: el viento **actual** es flojo y la deriva de la ventana va a favor del viento (`with_drift` verdadero). Es discutible (el viento de ahora quizá ya no explica la deriva) y la regla es estricta.
   Según el criterio que acordamos («se revierte si la medida empeora»), el paso 3a no pasaría con la medida ampliada; lo dejé adoptado porque pasó con la medida tal como estaba definida al empezar y porque baja las fugas de 26 a 7. **Mi recomendación: dejarlo y corregir en la 14.2** (que `now` no se cuele en frases de «la ventana»: skill más explícita o `checks` con `now`). Si prefieres revertir 3a, son las dos skills y `monitor_output.md` (los originales están en `agent-assets-v13/`); el estado y el rechazo de la recuperación son aparte.
2. **Las plantillas nuevas no son neutras para otros modelos.** `gpt-oss-20b-low` falló `spoofing` en la matriz (SENSOR_FAULT por avería del radar) y el 30B-A3B-2507 empeora mucho (ver «Comparación final»). Repetí `spoofing` ×2 con gpt-oss y salió bien las dos veces, así que en su caso es variación; en el 30B, no.
3. **El reconocimiento de la recuperación** (`acknowledge_detection`) no lo veta ningún guardrail: con `state_line: data` (3a′) en `demo` y con el paso 3b en `faults` el modelo reconoció en lugar de publicar la recuperación, y la alerta se quedó en `high`. Está en `docs/mejoras_futuras.md` para la 14.2.
4. **Severidad:** con el criterio nuevo **no se mueve** (las mismas causas y severidades que la base en los seis escenarios); la **confianza** sí: secuestro 0,8 → 0,7 en `demo` y `hijack`, fallo de sensor F1 0,6 → 0,7. Sigue en 0,7–0,8 casi siempre.

## Cómo siguen disponibles los textos antiguos
- **`agent-assets-v13/`**: copia exacta de `agent-assets/` antes de la 14.1 (su huella, calculada con el nombre `agent-assets`, es `293927dd0c038af5`; un test lo comprueba). No se edita.
- **Perfil `actual-textos-v13`** (`model-profiles/actual-textos-v13.yaml`): mismo servidor y muestreo que `actual` con `assets: agent-assets-v13`. La clave `assets` es nueva y solo admite carpetas `agent-assets*` de la raíz del repositorio (3 tests); el perfil no edita nada dentro. `profile.json` y `manifest.json` anotan la carpeta y su huella.
- Las claves nuevas de `agents.yaml` significan «comportamiento antiguo» si faltan (`monitor.now_facts`, `monitor.state_line`, `report.annex_system_prompt`/`annex_objective_prompt`), así que el mismo código ejecuta los dos juegos. **Límite:** el texto de rechazo de la recuperación del guardrail (código) es el nuevo también con v13; el antiguo está en `experiments/e12-cierre/` y en `experiments/e13-textos.md`.
- **Control** (`experiments/e14-1-control/`): `demo` con ese perfil da las mismas 9 respuestas, causas y severidades que `e12-cierre`, 3 rechazos y 0 fallbacks.

## Paso 1 · Medida de los textos
`tools/experiments/text_metrics.py` (sin LLM, usa el extractor de `texts.py`; `ai-module-py/tests/test_text_metrics.py`, 12 pruebas). Por texto (alerta: `summary`, `explanation`, `recommendation`; cierres y reconocimientos: `reason`; chats; secciones del informe) mide:
- **Nombres internos filtrados:** tools, skills, campos de `get_track_metrics` (incluidos `wind.*`, `gps_radar.*` y `now.*`, sacados de los modelos del contrato), campos de `checks`, ids del módulo, `true`/`false` sueltos (`=true`, `is false`…, no «a false alarm») y, aparte, nombres de causas y reglas en mayúsculas.
- **Frases copiadas:** 6 palabras seguidas o más iguales a las de los prompts y skills (las dos carpetas de assets), a los rechazos de los guardrails o a la línea de estado de la traza.
- **Ids que no existen** en la ejecución, con Unicode normalizado (NFKC y guiones/espacios especiales) y sin tocar el guardrail.
- **Cifras y direcciones** frente a los hechos de **la invocación** (monitor) o de todas las del monitor hasta ese instante (chats e informe): velocidad y racha del viento ±0,5 m/s; de dónde viene el viento ±15° (±25° si el texto da solo un punto cardinal) y la confusión de/hacia (±180°); distancia GPS–radar y desviación ±1 m. Más las dos reglas añadidas después (arriba).
- **Concreción:** longitud, cifras, ids y tiempos por texto.
- **La autoevaluación del monitor (anexo del informe, y su «Monitor assessment» en el formato antiguo) se mide aparte** (`annex`), porque es técnica a propósito; no entra en los totales.
Salidas: `experiments/<id>-textos-medida.md` y `.json` (cada hallazgo con su frase). Resultados: `e14-base-e4a-textos-medida.*` (base y los cinco modelos de E4a, r1), `e14-1-pasos-textos-medida.*` (cada paso), `e14-1-final-textos-medida.*` (final).

**Qué encuentra de `Revision_textos_E4a.md` §2 y qué no:**
| Caso | ¿Medible así? |
|---|---|
| Ministral: «wind … from 171.3°» (es hacia donde sopla) | **Sí:** `wind_dir_reversed` (1) |
| Ministral, gpt-oss y otros: nombres internos, `true`/`false`, `GPS_SPOOFING`… | **Sí** (Ministral: 24 nombres, 22 enums, 19 booleanos sueltos; 70 fugas en total) |
| 30B-2507: «wind is light (2.3 m/s, from 336°)» cuando la media era 7,2 | **No:** 2,3 m/s es una muestra real (`met-0015`, 336,1°); el fallo es interpretar la última muestra como el viento del episodio. `now` lo separa, pero la medida no lo marca |
| 30B-2507: «4.2° drift relative to intended course» (el 4,2° es deriva–viento) | **No** |
| 30B-2507: enlace «no anomalies» en pleno secuestro; «A2 escalating to high» | **No** (interpretación sin cifra) |
| `actual`: «no indication of a major disruption» con el controlador cambiado | **No** |
| gpt-oss: «the rule-based detector attributes the deviation to wind» | **No** |
| Ids inexistentes | 0 en todos (como en la Fase 13.1) |
Esos casos «No» necesitan la rúbrica (correcto · concreto · crítico con respaldo · legible), a mano o con un modelo (E5).

**Línea base (`e12-cierre`, seis escenarios, r1; sin anexo):** 82 textos; 6 nombres internos, 5 enums, 7 booleanos, 8 frases copiadas = **26 fugas**; 0 errores; 241 caracteres, 2,1 cifras, 0,46 ids y 0,26 tiempos por texto.

## Paso 2 · Bloque `now` en `get_track_metrics`
- **Contrato v0.13** (`contracts/eventos.md` §7, `NowFacts` en `contracts/python`, esquemas exportados, ejemplo validado): `now` = `{as_of, window_s, gps_radar_distance_m, gps_radar_agree, gps_deviation_from_plan_m, radar_deviation_from_plan_m, wind_speed_mps, wind_gust_mps, wind_from_deg, wind}`; `wind` es el texto corto («from NW (326°), pushing SE»; «calm» si no sopla).
- **Tamaño: 10 s**, para que siempre entre una muestra de GPS y de radar (1 s y 2 s) y, para el viento (cada 10 s), se mira el último de los 30 s anteriores. Es la **última muestra**, no la media: justo tras el salto de la recuperación del spoofing la media de 10 s sigue cerca de 50 m y la última muestra da 9,9 m (un test lo comprueba). `gps_radar_agree` = distancia < 25 m (`DISAGREED_M`).
- **Corte temporal:** `as_of` es `until` recortado al instante actual; ninguna muestra posterior (tests: ventana larga y corta dan el mismo `now`, `until` anterior, fuentes silenciadas, texto del viento).
- **No cambian** los hechos de la ventana ni `checks` ni los guardrails. `monitor.now_facts` decide si el modelo lo ve (sin la clave, no); `strip_computed_facts` también lo quita.
- **Skills y cierre, antes → después:**
  - `route-deviation`, nuevo apartado «Window or now»: *«Decide (steps 2 to 6) and fill in `checks` with the facts of the window. To say how things are at this moment (in a recovery, in an update, when you explain that the drone is back or still off route), use the `now` block of the same result… Do not present the mean or the maximum of the window as the present.»* `source-discrepancy`, la misma idea en un párrafo. `monitor_objective.md`, sección `cleared`: «decide with how things are now» → «decide with how things are now (the `now` block of that result)».
- **Resultado (`e14-1-now`):** 6/6, 0 falsas alarmas, 0 fallbacks, 0 abiertas, 0 contradicciones, 0 checks≠tools, rechazos 3/0/1/1/1/5 (igual que la base). Mismas cadenas y severidades (spoofing 0,8 → 0,85). Fugas 26 → 26: desaparecen los 6 nombres de la ventana, pero el modelo cita ahora `gps_radar_agree` en 5 cierres. Prompt del monitor +2 % (462 794 → 472 741 tokens).
- **Adoptado.** Huella `fb63ccbf0538279f`. (Una nota de método: mi primera medida no contaba los campos de `now` como nombres internos y daba 19 en vez de 26; lo corregí al ver «gps_radar_agree: true» en un cierre.)

## Paso 3 · Plantillas del monitor
**Qué se cambió (antes → después):**
- **`monitor_output.md`.** Antes: *«The severity is `low` if the cause is physical and under control…, `medium` if…, and `high` if there may be an attack… Confidence is 0.8 or more if at least two independent sources fit the criteria of the skill, between 0.5 and 0.7 if they fit in part and less than 0.5 if it is a conjecture.»* Después: **severidad = riesgo operativo ahora para el responsable del dron** (`low`: causa física y dron bajo control, basta vigilar; `medium`: hay que comprobar o vigilar, una fuente no es fiable o la causa es desconocida, sin riesgo inmediato; `high`: hay que actuar ya, la posición o el control pueden no ser fiables o estar en otras manos; «cuando la situación mejora, la severidad baja con ella»); **confianza por fuentes independientes** (GPS, radar, estación meteorológica, enlace: ≥ 0,8 con dos o más que coinciden y nada que contradiga; 0,5–0,7 con una o apoyo parcial; < 0,5 conjetura; cada contradicción la baja; «no repitas el mismo valor por costumbre»); y un apartado de **texto para el operador**: ningún nombre de tool, skill o campo, ni `true`/`false`, ni nombres de causas o reglas en mayúsculas; cifras con unidad, ids y T+mm:ss; frases propias y no copiadas de las skills, del estado o de los rechazos; la recomendación dice qué hacer en este caso y por qué.
- **`route-deviation`.** Antes (paso 2, recuperación): *«… `severity: medium`. Say that the GPS is back and the drone is correcting towards the route. `supersedes` = that alert if it is still open… Recommendation: verify the GPS receiver.»* Después: la causa es la de esa alerta (la línea del estado da su id y su causa), `severity: medium` («the situation is improving», un límite real: lo impone el guardrail), `supersedes` si el estado dice que sigue abierta, y «describe qué cambió: el GPS ha vuelto y, según `now`, a cuántos metros de la ruta está el dron». Paso 4 (viento): se quitan `severity: low if gps_deviation_from_plan_m.max < 80…`, `confidence 0.8–0.9` y «Recommendation: no intervention; watch that it recovers the route». Paso 5 (secuestro): se quitan `severity: high`, `confidence 0.8–0.9` y la recomendación; el caso del rumbo sin enlace anómalo queda «con menos confianza porque solo lo apoya el rumbo». Paso 6: se queda `UNKNOWN` con `confidence ≤ 0.4` (un límite de verdad).
- **`source-discrepancy`.** Antes: *«`GPS_SPOOFING`, `severity: high`, `confidence` 0.8–0.9. Recommendation: do not trust the GPS, use the radar as reference and notify the person in charge.»*, `GPS_JAMMING` `high`/`medium` con `confidence` 0.8–0.9, `SENSOR_FAULT` `medium` 0.5–0.7, `SOURCE_SILENT` `medium` (`high` si…) 0.7–0.9 y «`summary` says which source is silent». Después: solo la causa y el criterio («el riesgo es mayor si `gps_radar.disagreed` es verdadero: el dron navega a estima y se desvía»; «mayor si el GPS o el radar callan con otra detección abierta»), sin números ni frases. Se mantiene `confidence` 0,7 como máximo si el radar calla a la vez (límite de verdad) y `UNKNOWN` ≤ 0,4.
- **Código:** el rechazo de la recuperación pasa de *«This is the recovery from the GPS_SPOOFING of ai-0004: publish cause GPS_SPOOFING, severity medium and supersedes ai-0004»* a *«GPS recovery of ai-0004 (GPS_SPOOFING): expected cause GPS_SPOOFING, severity medium and supersedes ai-0004»* (y su variante «already medium…»). Misma lógica; la frase que el modelo copiaba al texto de la alerta venía de aquí y **no del estado**, como decía la revisión. Tests actualizados (`test_coherence.py`).
- **Línea del estado:** `monitor_state.describe_gps_alert(now, style)`; `state_line: data` da solo «yes — ai-0008 GPS_SPOOFING (open)», `legacy` añade «If this warning is the GPS recovery: cause X, supersedes Y». **Se adopta `legacy`** (ver abajo).

**3a · resultados (`e14-1-plantillas-b`, huella `2b9eb18cbf6a52e8`):** 6/6, 0 falsas alarmas, 0 fallbacks, 0 abiertas, 0 contradicciones, 0 checks≠tools, rechazos 3/0/1/1/1/5 (igual que la base). Mismas cadenas y sustituciones en los seis escenarios. Fugas 26 → 7 (internos 6 → 4, enums 5 → 3, booleanos 7 → 0, frases copiadas 8 → 0); la frase «This is the recovery from…» ya no sale. Coste: prompt del monitor +18 % (462 794 → 544 826 tokens).
- **Ablación de la línea de estado (`e14-1-plantillas`, `state_line: data`):** `demo` A2 sin la alerta de recuperación: a T+03:42 el modelo cargó `source-discrepancy` en vez de seguir el paso 2 de `route-deviation`, publicó la misma causa en `high` sin `supersedes`, el rechazo por «causa duplicada» le ofreció `acknowledge_detection` y reconoció. Con `legacy` (`e14-1-plantillas-legacy`, `demo`, `spoofing` y `faults`) vuelve (1 sustitución) y los textos son mejores (fugas 4 frente a 11 con `data`). n=1 por variante, pero es el único cambio entre las dos. **No se adopta la línea sin frase**: `agents.yaml` queda con `state_line: legacy` y un comentario.
- **3b (`e14-1-muletas`, huella `d1f74f0061307f09`):** 6/6 y todo a 0, pero la alerta de recuperación de F2 en `faults` desaparece (0 sustituciones), rechazos 5 → 6 y las fugas no mejoran (9 frente a 7). Prompt −2,6 %. **Revertido** con la copia exacta de `monitor_system.md`; la huella vuelve a `2b9eb18cbf6a52e8`. Las dos muletas **se quedan** (anotado: no se dispone de evidencia de que ya no hagan falta con el 14B).
- **Adoptado: 3a con `state_line: legacy`.**

## Paso 4 · Informe de misión y autoevaluación aparte
- **Propuesta adoptada, sin cambiar el contrato:** un solo `ReportGenerated` `{run_id, markdown, alerts_count}`. El `markdown` termina con **`## Annex: monitor self-assessment`** (cifras del monitor escritas por el módulo, `### Assessment` y `### Technical recommendations`). Lo escribe **el mismo agente en una segunda llamada** (otra invocación, otros prompts), para que la misión no se contagie de retrasos, rechazos ni ayudas. Si falla solo el anexo, sale «No disponible» y el informe de misión se publica igual (test).
- **Informe de misión** (primera llamada, `report_system.md`/`report_objective.md`/`report-format`): `## Summary`, `## What was seen` (una subsección por anomalía) y `## Recommendations` operativas («what to check or do after this flight»), sin retrasos, rechazos ni ayudas. **Sin la duda obligatoria**: antes la skill pedía «what doubt remains» por anomalía y los modelos se la inventaban; ahora: *«Write a doubt only if the data supports it: two sources that contradict each other, a source that was missing, a cause that changed during the episode or an anomaly still open.»* El módulo tampoco escribe ya «diagnosis delay» ni la hora de la primera alerta en los datos que recibe el LLM (en el informe sigue la hora de la primera alerta de cada anomalía, sin el retraso). `LIMITATIONS` pasa a una versión de misión que explica el anexo.
- **Autoevaluación** (segunda llamada, `report_annex_system.md`/`report_annex_objective.md`): los cuatro apartados de antes (Support, Delays, Fallbacks and rejections, Aids) y 2–4 recomendaciones técnicas sobre el sistema de monitorización.
- **Código:** `report.py` (`_annex`, dos trazas `report`, una sola actividad), `report_facts.py` (`assemble`, `parse_annex`, `Narrative.annex`), `agents.yaml` (`report.annex_*`; sin ellas, el formato antiguo de una llamada, que sigue probado con los assets congelados), `texts.py` y `text_metrics.py` (leen los dos formatos). El chat del informe no cambia (recibe el informe entero, anexo incluido).
- **Web:** `lib/report.ts` (`splitReport`, 3 pruebas) separa el anexo y `agent-console.tsx` lo muestra **plegado** (`<details data-testid="report-annex">`) bajo el informe de misión. 48 pruebas y `typecheck` limpios; capturas en `results/capturas/fase14_1/` (`01_informe_de_mision_anexo_plegado.png`, `02_anexo_autoevaluacion_desplegado.png`, `03_informe_de_mision_inicio.png`, generadas con el modo `fase14_1` de `web/scripts/capture.mjs`).
- **Resultado (`e14-1-informe`, huella `c16120188410b179`):** 6/6, todo a 0, rechazos 3/0/1/1/1/5. Fugas del informe de misión 7 → 6; 12 trazas del informe (2 por escenario), 0 fallbacks. Duración: 4,8–11,4 s la misión y 4,2–12,7 s el anexo (antes, una llamada de 4,8–11,4 s). Prompt del informe 14 996 → 21 742 tokens.
- **Adoptado.**

## Comparación final (seis escenarios ×1; `experiments/e14-1-final/`, `e14-1-informe/` y `e14-1-gptoss-spoofing/`)
Evaluación (suma de los seis escenarios), antes (E4a, `e13-*`) y después (assets de la 14.1, huella `c16120188410b179`):

| Modelo | Etiquetas ❌ antes | Etiquetas ❌ después | Fallbacks (antes → después) | Rechazos (antes → después) | Prompt del monitor (tokens) | Invocación p50 / p95 |
|---|---|---|---|---|---|---|
| `actual` (Qwen3-14B-AWQ) | 0 | 0 | 0 → 0 | 11 → 11 | 462 794 → 503 883 | 7,0 / 13,1 s → 7,4 / 13,7 s |
| `gpt-oss-20b-low` | 0 | **1** (`spoofing` A1: SENSOR_FAULT; en 2 repeticiones más ✅) | 0 → 0 | 5 → **14** | 345 044 → 454 959 | 7,6 / 11,1 s → 7,7 / 16,4 s |
| `qwen3-32b-awq` | 1 (`faults` F3) | 1 (`faults` F3) | 0 → 0 | 10 → 11 | 467 687 → 541 890 | 12,7 / 23,5 s → 15,1 / 26,9 s |
| `qwen3-30b-a3b-2507` | 2 (`faults` F1, F3) | **6** (`spoofing` A1, `faults` F1 F2 F3, `demo` A2 A3) | 5 → **13** | 21 → **28** | 1 095 477 → 1 527 970 | 6,1 / 9,9 s → 6,4 / 12,5 s |

Medida de textos (seis escenarios, r1; sin el anexo):

| Modelo | Fugas antes → después | Errores de contenido antes → después | Caracteres / cifras por texto antes → después |
|---|---|---|---|
| `actual` | 26 → **6** | 0 → 5 (ver «Para decidir») | 241 / 2,1 → 239 / 2,8 |
| `gpt-oss-20b-low` | 14 → 13 | 0 → 1 | 211 / 2,5 → 226 / 2,6 |
| `qwen3-32b-awq` | 10 → **0** | 0 → 0 | 251 / 2,2 → 265 / 2,6 |
| `qwen3-30b-a3b-2507` | 9 → 3 | 0 → 1 | 281 / 5,3 → 322 / 5,6 (61 textos frente a 75: los fallbacks no escriben) |

Lectura:
- **Los textos mejoran en todos los modelos** (el 32B queda sin fugas). El 14B es el que más gana, que es para el que se escribieron.
- **La decisión no mejora con las plantillas nuevas para otros modelos.** `gpt-oss` casi dobla los rechazos (5 → 14) y `faults` va a 11; el 30B-2507 pasa de 5 a 13 fallbacks y de 2 a 6 etiquetas ❌. En ninguno de los dos hay mucho que concluir con n=1 (el spoofing de gpt-oss salió bien en las dos repeticiones), pero el 30B ya era el más frágil de E4a. Las plantillas se evalúan para el modelo por defecto; **si se quisiera adoptar otro modelo habría que repetir ×3 con los dos juegos** (`actual-textos-v13` ya existe para esa comparación con el 14B).
- Los textos antes y después de cada modelo (`demo` y `faults`, r1) están en **`experiments/e14-1-textos.md`** (2 414 líneas, copiado a `results/experiments/`), para que Claude los revise en el chat: los errores de criterio no los ve la medida.

## Ejemplos antes y después (`actual`, `demo`, r1)
| Caso (de `Revision_textos_E4a.md`) | Antes | Después |
|---|---|---|
| §3.2 nombres internos | «Wind is notable (met-0010) and causing drift (drift_vs_wind_deg: 4.9)». Cierre de F: «(wind.with_drift)» | «At T+01:46, GPS shows 30.5 m deviation from route. Wind reported at T+01:45 (met-0010) is from N (342°), pushing S (146°), with gusts up to 9.7 m/s. Wind aligns with drift direction (4.9°). GPS and radar agree (distance 5.7 m).» |
| §3.1 recomendación de la skill | «Do not trust the GPS; use radar as reference and notify the person in charge.» (y en `faults`) | «Investigate GPS spoofing immediately. Verify the authenticity of GPS signals and ensure secure communication channels.» |
| §3.3 frase del estado/rechazo | «…This is the recovery from the GPS_SPOOFING of ai-0004.» | «At T+03:42, GPS and radar disagree by 9.9 m. GPS shows good signal… This suggests GPS spoofing.» (la frase copiada ya no sale, pero aparece el error de «disagree by 9,9 m»: ver «Para decidir») |
| §2 `actual`: chat del secuestro | «There is no indication of a major disruption, but the change in the controller and fluctuating latency could suggest potential issues…» | «These anomalies suggest a potential hijack or unauthorized access. The checks were based on event ids: lnk-0067 and others referenced in the alert ai-0008.» (mejor, aunque «The checks were based on event ids» es relleno) |
| §2 «ahora» frente a la ventana | Cierre de A1: «Wind conditions (mean 7.2 m/s, max gust 16.1 m/s from 351.3°) are consistent with the drift» (la ventana, presentada como cierre) | «The GPS and radar now agree (distance 7.9 m), and both show a deviation of less than 5 m from the route. The wind is currently light (2.3 m/s from NW)…» (usa `now`; pero añade «does not push in the direction of the drift», que la medida marca) |
| §3.4 dudas forzadas | «though wind alignment with drift introduces some uncertainty» (en la valoración, por anomalía) | informe de misión sin esa sección; el resumen no inventa dudas: «All anomalies were resolved by the end of the simulation, with no open issues remaining.» |
| §3.5 el informe habla del monitor | Resumen/Recomendaciones: «Review the wind-related checks for A1, as GPS and radar disagreement was not present…» | Recomendaciones de la misión: «Review the link status and controller ID changes during A3 to ensure secure communication protocols are in place.»; el retraso y los rechazos van al anexo (plegado en la web) |
| §3.6 severidad de la recuperación | A2 baja de `high` a `medium` por el guardrail | **igual** (no se toca hasta la 14.2); `monitor_output.md` ya dice que la severidad baja cuando la situación mejora |

## Problemas (con su error literal)
- `ERROR: serve.sh start actual failed (3): [serve] ERROR: my server (PID 62034, profile actual-textos-v13) is running: stop it first` — la primera matriz del paso 2 no arrancó porque dejé el servidor del control con `--keep-server` y `serve.sh` no cambia de perfil con uno vivo aunque el servidor sea el mismo. Paré el mío con `serve.sh stop` y relancé (la carpeta vacía de esa matriz se borró).
- El mismo error con `PID 65251, profile actual` al lanzar la comparación final: igual solución.
- Un `pkill -f` mío coincidió con el texto de mi propio comando y cerró el shell (`Exit code 144`) al parar la web, el módulo y la plataforma de las capturas; no tocó nada ajeno y comprobé después con `ps` y `ss` qué quedaba vivo.
- Mi medida del paso 1 tenía dos huecos (los campos de `now` no contaban como nombres internos y faltaban las dos reglas de contenido); los corregí al leer los textos y volví a medir **todas** las tablas con la misma definición (los números de los pasos 2 y 3a de la primera medida eran 19 y 9).
- Falsos positivos de la medida corregidos con test: una distancia entre paréntesis leída como desviación, «below 6 m» como medida, «12 m/s while wind» como viento y decimales que rompían la frase.

## Límites
- n = 1 por escenario y modelo (la repetición de `gpt-oss` en `spoofing`, n = 2 más). Con T=0 sigue habiendo variación de vLLM: una alerta de recuperación que aparece o desaparece con un cambio, como en 3a′ y 3b, es evidencia, no prueba.
- La medida de textos solo ve cifras, direcciones y nombres; los errores de interpretación sin cifra y las conclusiones blandas (§2 de la revisión) quedan fuera, y sus reglas nuevas de contenido son estrictas (la del viento con la deriva marca una frase discutible).
- La severidad por criterio no se ejercita: en los seis escenarios la causa decide la severidad igual que antes. Hace falta un caso donde el criterio y el valor fijo difieran.
- No se probó `now` en los chats ni con memoria A o modo guiado.

## Qué queda
- **Tu decisión:** mantener 3a con los errores de contenido de `now` (recomendado) o revertirlo; y qué hacer con la portabilidad a otros modelos.
- **14.2:** reconocer la recuperación (guardrail y severidad de la recuperación), que `now` no entre en frases de ventana, `now` para los chats, y un caso donde la severidad por criterio importe. Todo en `docs/mejoras_futuras.md`.

## Documentos actualizados
`docs/quien_decide_que.md` (cabecera, §1 tools, monitor e informe, §3 ayudas, §5), `docs/mejoras_futuras.md` (tres entradas de agente y «Texto fiable del monitor»), `CLAUDE.md` (carpeta `agent-assets-v13/`), `ai-module-py/CLAUDE.md`, `platform/CLAUDE.md`, `web/CLAUDE.md`. Contrastado `quien_decide_que.md` con el código: el reparto no cambia (causa y guardrails igual); cambian **dónde vive el criterio de severidad y confianza** (el prompt de salida, no las skills) y **qué cuenta el informe** (misión y autoevaluación separadas).

## URLs consultadas
Ninguna (solo código y documentación locales).

## Ficheros
Nuevos: `agent-assets-v13/`, `agent-assets/prompts/report_annex_{system,objective}.md`, `model-profiles/actual-textos-v13.yaml`, `tools/experiments/text_metrics.py`, `ai-module-py/tests/test_text_metrics.py`, `web/lib/report.ts`, `web/lib/report.test.ts`, `docs/fases/fase14_1.md`, `experiments/e14-*` (matrices, textos y medidas; solo se versionan los `compare.md`). Modificados: `agent-assets/{agents.yaml,tools.json,prompts/{monitor_output,monitor_objective,report_system,report_objective}.md,skills/{route-deviation,source-discrepancy,report-format}/SKILL.md}`, `contracts/{eventos.md,python/src/poc_contracts/tools.py,schemas/tools/get_track_metrics.result.json}`, `platform/src/platform_app/tools/metrics.py` y `platform/tests/test_tools.py`, `ai-module-py/src/ai_module/{monitor.py,monitor_state.py,monitor_usage.py,report.py,report_facts.py,agent/{assets,guardrails,profiles,tools}.py,__main__.py}` y sus tests (`test_coherence`, `test_monitor_state`, `test_profiles`, `test_report_chat`, `test_report_facts`, `test_round8`, `test_texts`, `agent_helpers`), `tools/experiments/{run_matrix,texts}.py`, `web/components/mission/agent-console.tsx`, `web/scripts/capture.mjs`. **Los ficheros de `runs/` no cambian** (no se tocó el generador ni los escenarios).

## Copias (reglas 13 y 15)
En `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`: `docs/fases/`, `docs/quien_decide_que.md`, `experiments/` (los `e14-*-textos-medida.{md,json}`, `e14-1-textos.md`, los `compare.md` y los `eval.md` e `informe.md` de cada ejecución), `capturas/fase14_1/`, `snapshots/fase14_1/` y `snapshots-limpias/fase14_1/`. Las dos comprobaciones de la regla 15 (palabras prohibidas y nombres propios) **salen vacías**; no hizo falta corregir nada. `diff -rq docs/fases results/docs/fases` solo difiere en el `quien_decide_que.md` que ya estaba allí desde la Fase 13 (sincronizado también).

## Mensaje de commit propuesto
```
feat: phase 14.1 - now facts, criterion-based monitor templates, mission report with annex

get_track_metrics returns a now block (last sample of the last 10 s; contract
v0.13, additive). Monitor skills no longer dictate severity, confidence or
recommendation text: monitor_output.md gives the criterion (severity as
operational risk now, confidence by independent sources) and asks for plain
language. The recovery rejection no longer carries a copyable sentence. The
report is a mission report for the person in charge plus a separate monitor
self-assessment annex (second call, same ReportGenerated, shown folded in the
web). New text_metrics tool measures leaked names, copied phrases, unknown ids
and figures that do not match the facts. agent-assets-v13 and the profile
actual-textos-v13 keep the previous texts for comparison.
```
