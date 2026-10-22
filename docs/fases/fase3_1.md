# Fase 3.1 · informe determinista, «Quién decide qué» y mejora con modelos de Claude

Fecha: 22/10/2026. Estado: **terminada, pendiente de tu revisión**. Contrato v0.8 (sin cambios). Rompe la huella de congelado **solo en lo del informe**: el monitor, los chats y `agents.yaml` no se han tocado. **Huella nueva `40e5049dbf83198c`** (`find agent-assets -type f | sort | xargs sha256sum | sha256sum`; la anterior era `8e2376c580bab74b`). Comprobado fichero a fichero: solo cambian `agent-assets/prompts/report_system.md`, `agent-assets/prompts/report_objective.md` y `agent-assets/skills/report-format/SKILL.md`.

## 1. Informe: los hechos los escribe el módulo
**Qué se hizo**
- `ai-module-py/src/ai_module/report_facts.py` (nuevo, puro y probado): construye las **anomalías** a partir de `MonitorState` (cada cadena de `supersedes` es una; etiquetas `A1`, `A2`…) y escribe de forma determinista: cabecera (de `get_flight_summary`), **cronología** (detecciones —con sus subidas de severidad—, alertas, cierres de detección y de alerta, inicio y fin de la misión), y por anomalía: la **hora y la severidad de su primera alerta** y, si cambian, las de la última; T+ de detección; retraso de diagnóstico; evidencias; estado (cerrada por el monitor a T+…, con cuándo terminó la última detección de la cadena, o «ABIERTA al final»); detecciones sin alerta; una línea de **cifras del monitor** (invocaciones, duración, fallbacks, rechazos de los guardrails, ayudas activas) y las limitaciones.
- El LLM (sin tools, una llamada) **solo redacta** cuatro apartados: resumen, «qué se vio» de cada anomalía, valoración del monitor y recomendaciones. `parse_narrative` los lee por sus títulos (tolera que envuelva la respuesta en un bloque de código y descarta lo que escriba fuera de los cuatro apartados); lo que falte sale como «No disponible: el agente no redactó este apartado». Si no devuelve nada utilizable, el informe lleva los hechos y una nota (antes era un informe mínimo aparte; `_minimal_report` ya no existe).
- **Valoración crítica:** el módulo le inyecta los **retrasos** (de simulación y de reloj por anomalía), los **fallbacks**, los **rechazos de los guardrails** (por tool y con su motivo) y las **ayudas activas** (`monitor_stats` y `assessment_facts`); el prompt le pide cuatro viñetas (Respaldo, Retrasos, Fallbacks y rechazos, Ayudas), que no escriba «correcto», «preciso» ni «acertó» (no tiene la verdad del simulador) y que no proponga entrenar el modelo.
- `monitor_state.py`: `DetectionRecord` guarda ahora el mensaje, el valor, el umbral, la unidad, el máximo y las subidas de severidad de cada detección (el mensaje y el valor de apertura **no** se sobrescriben con una actualización: en una primera versión la cronología decía «84,5 m» a T+05:38 en vez de «36,7 m» y lo corregí). Las etiquetas de las comprobaciones pasan a la constante `CHECK_LABELS`. `runtime.py`: al reiniciar la ejecución se vacían las trazas en memoria (las usa el informe).
- Assets: `report_system.md`, `report_objective.md` y `skills/report-format/SKILL.md` reescritos para este reparto. `docs/01_definicion.md` (tabla de agentes) y `ai-module-py/CLAUDE.md` (§5) actualizados.
- Pruebas nuevas: `tests/test_report_facts.py` (10) y las del informe en `tests/test_report_chat.py` (informe con narrativa, y sin ella).

**Ejecución** (`demo` a 16× esperando al agente, con el LLM real y los assets finales): `runs/demo/20261022-094440/` (`informe.md`, `eval.md`). Hubo una ejecución previa, `runs/demo/20261022-093843/`, con una versión intermedia del prompt del informe, que usé para iterar el prompt (más una regeneración del informe sobre esa ejecución con un script mío fuera del repo); la de arriba es la definitiva. Ninguna de las dos se versiona.

**El monitor no cambia** (alertas de la ejecución definitiva frente a las de R9, `docs/fases/fase3.md` §5):

| T+ | Alerta | R9 (3 ejecuciones) | 22/10 |
|---|---|---|---|
| T+01:46 | WIND baja | ✅ las tres | `ai-0002` |
| T+03:12 | GPS_SPOOFING alta | ✅ las tres | `ai-0008` |
| T+03:42 | GPS_SPOOFING media, `supersedes` | ✅ las tres | `ai-0011` (sustituye a `ai-0008`) |
| T+05:38 | HIJACK alta | ✅ las tres | `ai-0018` |
| T+05:41 | HIJACK alta, `supersedes` | ejecuciones 2 y 3 (la 1 la reconoce con `acknowledge_detection`) | `ai-0021` (sustituye a `ai-0018`) |

Mismas causas, mismas cadenas (una por anomalía), 0 fallbacks, 0 alertas abiertas al final y **3/3** en `eval.md` (mismo resultado que R9). El monitor consumió 178.428 tokens de prompt y 3.306 de salida (R9: 236.961 y 3.698); el máximo de prompt en una llamada fue 8.509 (R9: 9.178); 3 rechazos de guardrails (R9: 4).

**Datos del informe frente a `eval.md`** (la ejecución definitiva):

| Dato | `eval.md` | `informe.md` |
|---|---|---|
| A1 wind: primera alerta y retraso de diagnóstico (sim) | WIND T+01:46 (0.85), 0,4 s | Viento (baja, 0.85), alerta a T+01:46, 0,4 s |
| A2 gps_spoofing | GPS_SPOOFING T+03:12 (0.85), 0,2 s; 1 cadena; la respuesta a det-0004 (T+03:42) sustituye | alta a T+03:12, 0,2 s; última alerta `ai-0011` a T+03:42, severidad alta → media; 1 cadena |
| A3 hijack | HIJACK T+05:38 (0.85), 0,7 s; la actualización (T+05:41) sustituye | alta a T+05:38, 0,7 s; última alerta `ai-0021` a T+05:41 sin cambio de causa ni severidad |
| Cierres | cierre de `ai-0002` en respuesta al aviso de T+02:36; `ai-0011` al de T+03:54; `ai-0021` al de T+07:21 | la última detección de cada cadena terminó a T+02:36 / T+03:54 / T+07:21 y el monitor cerró a T+03:12 / T+04:28 / T+08:07 |
| Cadenas, falsas alarmas, abiertas al final | 3, 0, 0 | 3 anomalías, sin detecciones sin alerta, abiertas al final: 0 |

Sobre los cierres: `eval.md` indica la hora del **aviso** de cierre de la detección (columna «T+»); el informe da, además, la hora a la que el monitor **publicó** el cierre (`AlertClosed.sim_time`), que a 16× es posterior porque el reproductor sigue mientras el modelo responde. Los dos datos aparecen en el informe (cronología y estado), así que ya no se da como cierre del viento una hora (T+03:12) que parecía contradecir a `eval.md`. En R9 el informe daba la alerta del spoofing a T+03:42 y «media» (la de la última alerta de la cadena) y ahora da T+03:12 y «alta» (la primera), con la última aparte.

**Calidad de lo que redacta el modelo.** Con el prompt definitivo la valoración nombra los retrasos (7–13 s de reloj por la primera alerta), los 3 rechazos y las ayudas, y ya no dice que los diagnósticos sean «precisos»; con la versión anterior del prompt decía «El monitor realizó diagnósticos precisos en todas las anomalías». Sigue siendo un 14B: en una regeneración dijo que no hubo rechazos y a continuación que el monitor corrigió tres (de ahí la línea de cifras que escribe el módulo), y la valoración es genérica («respaldado por la persistencia de la discrepancia»). Las horas, severidades, estados y cifras no dependen de él. Tokens del informe: 4.102 de prompt y 602 de salida (R9: 1.613 y 998), 11,7 s.

### Informe de `demo` generado (ejecución `20261022-094440`, tal cual)
# Informe de la misión MSN-DEMO

**Escenario:** demo · **Duración:** 09:16 · **Misión completada:** sí (regreso a base) · **Waypoints alcanzados:** 4 de 4 · **Anomalías:** 3 (abiertas al final: 0)

## Resumen

El vuelo de demostración completó su misión correctamente, alcanzando todos los waypoints planificados. Durante el vuelo se detectaron tres anomalías: una relativa a un viento notable, otra relacionada con un posible spoofing del GPS y una última que señalaba un posible secuestro del dron. La anomalía más grave fue la señalización de un secuestro del dron, aunque todas fueron identificadas y cerradas por el monitor en su momento.

## Cronología

| Tiempo | Fuente | Qué pasó |
|---|---|---|
| T+00:00 | Misión | Inicio de la misión MSN-DEMO |
| T+01:46 | Detector | det-0001 ROUTE_DEVIATION (media): La posición del GPS se aleja 30,5 m de la ruta planificada |
| T+01:46 | Monitor | Alerta ai-0002 (A1): Viento (baja, confianza 0.85) |
| T+02:36 | Detector | det-0001 ROUTE_DEVIATION cerrada (duró 50 s; máximo 53,0 m) |
| T+03:12 | Detector | det-0003 SOURCE_DISCREPANCY (media): El GPS y el radar difieren 31,2 m (media de las últimas 3 medidas) |
| T+03:12 | Monitor | Alerta ai-0008 (A2): Spoofing del GPS (alta, confianza 0.85) |
| T+03:12 | Monitor | Cierre de la alerta ai-0002 (A1) |
| T+03:42 | Detector | det-0004 ROUTE_DEVIATION (media): La posición del GPS se aleja 73,9 m de la ruta planificada |
| T+03:42 | Monitor | Alerta ai-0011 (A2): Spoofing del GPS (media, confianza 0.85), sustituye a ai-0008 |
| T+03:52 | Detector | det-0003 SOURCE_DISCREPANCY cerrada (duró 40 s; máximo 73,3 m) |
| T+03:54 | Detector | det-0004 ROUTE_DEVIATION cerrada (duró 12 s; máximo 73,9 m) |
| T+04:28 | Monitor | Cierre de la alerta ai-0011 (A2) |
| T+05:38 | Detector | det-0007 ROUTE_DEVIATION (media): La posición del GPS se aleja 36,7 m de la ruta planificada |
| T+05:38 | Monitor | Alerta ai-0018 (A3): Secuestro del dron (alta, confianza 0.85) |
| T+05:41 | Detector | det-0007 ROUTE_DEVIATION sube a alta: La posición del GPS se aleja 84,5 m de la ruta planificada |
| T+05:41 | Monitor | Alerta ai-0021 (A3): Secuestro del dron (alta, confianza 0.85), sustituye a ai-0018 |
| T+07:21 | Detector | det-0007 ROUTE_DEVIATION cerrada (duró 103 s; máximo 714,2 m) |
| T+08:07 | Monitor | Cierre de la alerta ai-0021 (A3) |
| T+09:16 | Misión | Fin de la misión: regreso a base |

## Anomalías

### A1 · Viento (baja, confianza 0.85)
- **Cuándo:** detección a T+01:46 (ROUTE_DEVIATION), primera alerta a T+01:46 (retraso de diagnóstico: 0,4 s de simulación).
- **Qué se vio:** Se observó una desviación de ruta de 30,5 m debido a un viento notable que empujaba en la dirección de la deriva del dron.
- **Evidencias:** detecciones det-0001; eventos citados por el monitor: met-0010, lnk-0016, lnk-0017, lnk-0018, lnk-0019, lnk-0020 y 1 más.
- **Estado:** cerrada por el monitor a T+03:12 (la última detección de la cadena terminó a T+02:36).

### A2 · Spoofing del GPS (alta, confianza 0.85)
- **Cuándo:** detección a T+03:12 (SOURCE_DISCREPANCY, ROUTE_DEVIATION), primera alerta a T+03:12 (retraso de diagnóstico: 0,2 s de simulación).
- **Última alerta:** ai-0011 a T+03:42 (severidad alta → media; 2 alertas en la cadena).
- **Qué se vio:** Se detectó una discrepancia de 31,2 m entre el GPS y el radar, seguido de una desviación de ruta del GPS de 73,9 m, lo que llevó a sospechar de un spoofing del GPS.
- **Evidencias:** detecciones det-0003, det-0004; eventos citados por el monitor: gps-000192, rad-000096, met-0019, gps-000218, gps-000222, rad-000111.
- **Estado:** cerrada por el monitor a T+04:28 (la última detección de la cadena terminó a T+03:54).

### A3 · Secuestro del dron (alta, confianza 0.85)
- **Cuándo:** detección a T+05:38 (ROUTE_DEVIATION), primera alerta a T+05:38 (retraso de diagnóstico: 0,7 s de simulación).
- **Última alerta:** ai-0021 a T+05:41 (sin cambio de causa ni de severidad; 2 alertas en la cadena).
- **Qué se vio:** Se registró una desviación de ruta del GPS de 36,7 m inicialmente y luego aumentó a 84,5 m, junto con un cambio en el controller_id del enlace de mando, lo que indicó un posible secuestro del dron.
- **Evidencias:** detecciones det-0007; eventos citados por el monitor: met-0033, lnk-0067, lnk-0068.
- **Estado:** cerrada por el monitor a T+08:07 (la última detección de la cadena terminó a T+07:21).

## Valoración del monitor

**Cifras del monitor** (las escribe el módulo): 9 invocaciones (8 con LLM y 1 deterministas) · duración de reloj por invocación con LLM: media 8 s, máxima 17 s · fallbacks: 0 · rechazos de los guardrails: 3 · alertas abiertas al final: 0 · ayudas activas: tool_choice «required» (respuesta siempre con una llamada a una tool); última iteración solo con las tools de respuesta; comprobaciones (`checks`) obligatorias antes de la causa; guardrail de coherencia, incluida la recuperación excluyente del GPS; hechos calculados por la plataforma (viento notable, discrepancia GPS–radar, salto del GPS).

- **Respaldo:** Para A1, la causa del viento fue respaldada por la desviación de ruta y la dirección del viento. Para A2, la discrepancia GPS-radar fue respaldada por la persistencia de la discrepancia y la alerta del GPS indicando una recuperación tras un spoofing. Para A3, la causa de secuestro fue respaldada por el cambio en el controller_id y la latencia en el enlace de mando.
- **Retrasos:** Los tiempos de reacción variaron entre 7 y 13 segundos de reloj, siendo estos tiempos aceptables pero posibles de mejorar para un operador.
- **Fallbacks y rechazos:** No hubo fallbacks, pero sí tres rechazos de llamadas por los guardrails, que el monitor tuvo que corregir manualmente en cada caso.
- **Ayudas:** Las ayudas activas como las comprobaciones obligatorias y los hechos calculados por la plataforma ayudaron a mantener la consistencia y coherencia de las alertas.

## Recomendaciones

1. Evaluar y mejorar los tiempos de reacción del monitor para reducir los retrasos en la generación de alertas.
2. Implementar mejoras en la lógica para evitar los rechazos de llamadas por los guardrails, asegurando que el monitor no tenga que realizar correcciones manuales frecuentemente.

## Limitaciones

Los datos son simulados y el monitor solo veía lo ocurrido hasta cada instante. Las horas, severidades, estados y evidencias de este informe las escribe el módulo a partir de los eventos; el resumen, «qué se vio», la valoración y las recomendaciones los redacta un modelo de lenguaje con esos mismos datos, sin la verdad del simulador.

## 2. «Quién decide qué»
Copiado de `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/Quien_decide_que.md` a `docs/quien_decide_que.md` y contrastado con el código. **Lo que he cambiado y por qué:**
1. **Cabecera:** ahora «al cierre de la Fase 3.1»; el informe ya no es «mixto en el futuro» sino como está hecho (fila de **Informe** del §1 y nueva fila «Informe: hechos escritos por el código» del §3). Nuevo punto 5 del §4 con el caso del informe.
2. **Guardrails (§1):** la fila decía que vetan «que la causa sea coherente con ellas», sin más. En el código (`guardrails.py`, `check_coherence`) la causa solo se veta en **tres casos**: `WIND` (viento notable y a favor de la deriva), `HIJACK` (haber mirado el enlace) y las causas del GPS sobre un `ROUTE_DEVIATION` (alerta del GPS reciente y discrepancia o salto ≥ 30 m). Añadí también lo que vetan sobre ids (detecciones del lote, sin duplicar alertas, `close_alert` con detecciones abiertas).
3. **`link_anomalous` (§1 Orquestación y §2 Secuestro):** el documento decía que «lo calcula el módulo». No es exacto: el modelo lee los eventos de enlace y **declara** el valor en `checks`; el módulo calcula el valor **esperado** sobre los eventos que pidió y rechaza una declaración distinta (el rechazo le dice el correcto). Además, el guardrail de `HIJACK` exige haber mirado el enlace, **no** que sea anómalo: elegir `HIJACK` es decisión del modelo.
4. **Spoofing, fuente callada y pérdida de GPS (§2):** aclarado que no hay veto de causa en ellos (solo en la recuperación tras un aviso `ROUTE_DEVIATION`).
5. **Orquestación (§1):** concretado el fallback (una alerta `UNKNOWN` «sin diagnóstico» solo si llega una detección nueva o actualizada y no hay ninguna alerta abierta; si la hay, reconocimiento sin alerta; en un cierre de la última detección, la cierra) y los cierres sin LLM (también cuando la detección no tenía alerta o su alerta ya estaba cerrada, no solo cuando quedan detecciones abiertas).
6. **Cierre (§2):** añadido que el guardrail no deja cerrar con detecciones abiertas y que, si el modelo no concluye, el módulo cierra.
7. **Recuperación (§2):** precisado el criterio («salto de 30 m o más» o discrepancia; alerta abierta o cerrada hace 60 s o menos; `supersedes` solo si sigue abierta).
8. **§4 punto 1:** «`required` lo resolvió por completo» pasa a «lo resolvió (que haya una llamada bien formada), no que vengan todos los campos obligatorios»: es lo que dice la fase 3 (§12, ⚠️ de vLLM con `required`).
9. **Tools de datos (§1):** añadido el corte temporal; **§5:** la entrada de los modelos de Claude con los tres modelos y la excepción a la regla 1.
Lo demás (piezas, ayudas del §3, lo que «no son ayudas») lo he contrastado con `agents.yaml`, `monitor.py`, `guardrails.py` y `platform/.../tools/metrics.py` y es exacto. **Mantenimiento:** he añadido una línea a `CLAUDE.md` (apartado de fases) para actualizarlo y contrastarlo al cerrar cada fase.

## 3. `docs/mejoras_futuras.md`
Nueva subsección «Probar el monitor con modelos de Claude» dentro de «Liberar al agente», con tu texto (excepción explícita a la regla 1 que decides tú; SDK nativo `anthropic` como segundo adaptador en `llm.py` con `provider: vllm | anthropic`; por qué no la capa de compatibilidad de `openai`; lo que cambia con los modelos 5.5; ⚠️ cómo se devuelven los bloques de razonamiento en un bucle de tools sin comprobar), los tres modelos en orden (Haiku 5.5 con `auto` + `strict` primero y `any` solo si falla el formato; Sonnet 5.5; Opus 5.5 solo como techo y avisando) y el método (ayudas apagadas, una ejecución por escenario, caché de prompts, revisar el diseño antes de encender ayudas, tokens y coste en `eval.md`). Añadí dos cosas mías, marcadas en el texto: que habría que decidir qué datos salen de la máquina, y que `eval.md` hoy da los tokens pero no los de caché ni el coste estimado, así que hay que añadírselos. **No se ha implementado nada de esto.**

## 4. Cómo se ejecuta
```bash
uv run --project platform python -m platform_app.run --scenario demo --speed 16 --wait-agent --evaluate   # con vLLM en marcha
(cd contracts/python && uv run pytest -q)   # 127 passed, 1 skipped
(cd platform && uv run pytest -q)           # 203 passed
(cd ai-module-py && uv run pytest -q)       # 280 passed (incluye la e2e, ≈ 55 s)
ruff check . && ruff format --check .       # limpio (ai-module-py y platform)
```

## 5. Problemas y ⚠️
- La primera versión de la cronología sobrescribía el mensaje y el valor de una detección con los de su actualización (T+05:38 decía 84,5 m): corregido y probado (`test_detection_updates_show_as_a_severity_rise_and_keep_the_opening_values`).
- El 14B envolvió la respuesta del informe en un bloque ```` ```markdown ```` y añadió una frase al final, que acababa dentro de «Recomendaciones»: el parser lo tolera ahora.
- ⚠️ Sin comprobar en la documentación (no se ha hecho nada con la API de Claude): cómo se devuelven los bloques de razonamiento en un bucle de tools.
- Nada se atascó más de 30 minutos.

## 6. Qué queda
- La valoración del informe sigue siendo genérica con este modelo; con uno mejor (ver «Liberar al agente») debería afinarse sin tocar los hechos.
- El informe y el chat del informe siguen sin topar `until` en `as_of` (nota del revisor, fase 3 §11).
- Pendientes de la fase 3 sin cambios (`fallos`: F3, las dos cadenas de F2 y las alertas abiertas; chats con tools).
- Cualquier cambio a `agent-assets/` o `agents.yaml` rompe la huella `40e5049dbf83198c`: pregúntame antes.

## 7. Copias (reglas 13 y 15)
`docs/fases/`, los PNG de `runs/*/`, los `eval.md`/`informe.md` de las ejecuciones; instantánea del código en `snapshots/fase3_1/` y la limpia en `snapshots-limpias/fase3_1/`, con las dos comprobaciones de la regla 15 vacías (sin coincidencias).

## 8. Mensaje de commit propuesto
```
feat: phase 3.1 - deterministic report facts, "who decides what" doc and Claude-models plan

- ai-module-py: report facts (timeline, T+ of detection, alert and closure, severity, status,
  evidence, monitor figures) written by the module from the monitor state; the LLM only writes
  the summary, "what was seen", the monitor assessment and the recommendations
- agent-assets: report prompts and report-format skill rewritten for that split (monitor untouched)
- docs: who-decides-what document checked against the code; future work to try Claude models
```
