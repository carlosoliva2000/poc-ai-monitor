# Fase 7 · experimentos E0 y E1 (23/10/2026)

Objetivo: ejecutar E0 (referencia `actual`) y E1 (solo cambia el modelo: `qwen3-14b-t0` y `qwen3-30b-a3b-t0`) en **una sola matriz** y analizarla. **No se ha cambiado nada**: ni prompts, ni skills, ni `agents.yaml`, ni perfiles, ni código (huella de `agent-assets` `e28d071e856efb09` en `compare.md`; repositorio en `3c6de09` y sin cambios sin guardar al empezar). Contratos sin cambios (v0.10).

## 1. Qué se ha ejecutado
```
uv run --project ai-module-py python tools/experiments/run_matrix.py \
    --profiles actual,qwen3-14b-t0,qwen3-30b-a3b-t0 \
    --scenarios demo,nominal,wind,spoofing,hijack,faults --reps 3 --id e0e1
```
- Preguntas por defecto (en `demo` las tres del guion; en los otros cinco, solo la del informe).
- **54 de 54 ejecuciones `ok`**, sin reintentos, sin cuelgues de Windows, WSL ni vLLM. Tiempo de reloj de las ejecuciones: `actual` 22,4 min, `qwen3-14b-t0` 20,9 min, `qwen3-30b-a3b-t0` 18,2 min (≈ 62 min, más los arranques).
- Servidores (cada uno arrancado **una sola vez**, en este orden): `actual` listo en 72 s, `qwen3-14b-t0` en 46 s y **`qwen3-30b-a3b-t0` en 88 s** (primer arranque de este modelo con `serve.sh`: llegó a `/health` a la primera, 22,4 GiB de GPU, vLLM 0.31.0). Entre perfiles, `serve.sh stop` esperó a que la GPU bajase a 0 MiB.
- Estado final: `serve.sh status` → sin servidor, puerto 8000 libre, `nvidia-smi` 0 MiB.
- Salida: `experiments/e0e1/` (`manifest.json`, `runs/<perfil>/<escenario>/r<k>/`, `logs/`, `compare.md`). Solo `compare.md` se versiona.
- Desviación del plan de §8 de la fase 6: no se hizo la ejecución previa «`demo` ×1 para vigilar la carga del 30B» porque pediste una sola matriz; el 30B iba el último, así que un fallo de su arranque habría dejado intactos los otros dos perfiles.
- **Criterio de E0 (fase 6): cumplido.** `actual`: demo 3/3 (A1, A2, A3 en las tres repeticiones) y `faults` 2 de 3 etiquetas (F1 y F2 ✅, F3 ❌ en las tres).

## 2. Resultados de un vistazo
Aciertos por etiqueta (✅ en k de 3 repeticiones). «Estable» = las 3 repeticiones dejaron la misma firma (causas, cadenas, cierres y abiertas).

| Escenario | `actual` | `qwen3-14b-t0` | `qwen3-30b-a3b-t0` |
|---|---|---|---|
| demo | A1 3 · A2 3 · A3 3 — estable | A1 3 · A2 3 · A3 3 — estable | A1 3 · **A2 2 · A3 2** — 1/3 iguales |
| nominal | sin etiquetas, 0 falsas alarmas — estable | ídem | ídem |
| wind | A1 3 — estable | A1 3 — estable | A1 3 — 2/3 iguales |
| spoofing | A1 3 — estable | A1 3 — estable | **A1 2** — 2/3 iguales |
| hijack | A1 3 — estable | A1 3 — estable | A1 3 — estable |
| faults | F1 3 · F2 3 · **F3 0** — 2/3 iguales | F1 3 · F2 3 · **F3 0** — estable | F1 3 · F2 3 · **F3 0** — 1/3 iguales |

Resto de contadores (sumas de las 3 repeticiones; tomados de `compare.md`):

| Contador | `actual` | `qwen3-14b-t0` | `qwen3-30b-a3b-t0` |
|---|---|---|---|
| Falsas alarmas | 0 | 0 | 2 (demo r2, r3) |
| Fallbacks | 0 | 0 | 3 (demo r3, faults r1, faults r3) |
| Alertas abiertas al final | 3 (faults) | 0 | 7 demo + 2 wind + 3 spoofing + 2 faults = **14** |
| Etiquetas con más de una cadena | F2 (3/3) | 0 | F2 en 1 repetición (faults r1) |
| Frases que contradicen los checks | 6 (demo) + 3 (faults) = **9** | 0 | 0 |
| No latinos (monitor / informe / chats) | 0 / 0 / **2** (demo) | 0 / 0 / 0 | 0 / 0 / 0 |
| Rechazos de guardrails (total) | 35 | 27 | **73** |
| Cortes por longitud | 0 | 0 | 0 |

## 3. Comentario por escenario
- **nominal.** Los tres perfiles: 0 falsas alarmas, 0 fallbacks, 0 abiertas, estables. Aquí no hay diferencia.
- **wind.** Los tres aciertan A1 3/3. Diferencias solo de ciclo de vida: el 30B deja la alerta abierta en r2 y r3 (publica una alerta `WIND` baja que sustituye en vez de cerrar; ver §4) y no es estable. `actual` y 14B: 0 abiertas, 2–3 rechazos, estables.
- **spoofing.** `actual` y 14B 3/3 y estables. El 30B falla r3: diagnostica `GPS_JAMMING` en vez de `GPS_SPOOFING` en el aviso de `SOURCE_DISCREPANCY` (T+03:12) y lo arrastra en toda la cadena; deja la alerta abierta en las tres repeticiones (cierra con `acknowledge_detection` o con una alerta `UNKNOWN`, nunca con `close_alert`).
- **hijack.** Empate: 3/3, estables, 3 rechazos cada uno. Es el único escenario en que el 30B no tiene ningún problema (y el más rápido: p50 de invocación 2,9 s frente a 5,5–7,3 s).
- **demo.** `actual` y 14B aciertan A1, A2, A3 en las tres repeticiones y son estables. Diferencias:
  - `actual` escribe en las tres repeticiones dos frases que contradicen el check `wind_notable = false` (ai-0004 y ai-0008) y en dos repeticiones (r1 y r3) el chat del monitor (pregunta de T+342 s) mete una frase en chino. 14B: 0 y 0.
  - El 30B: 2/3 en A2 y A3 (r1 diagnostica A2 como `GPS_JAMMING`; r3 contesta A3 con un fallback), 2 falsas alarmas, 7 abiertas y 28 rechazos (14B: 9; `actual`: 14).
- **faults.** Ver §6.

## 4. Fallos clasificados (tras leer cada traza)
Clases: **formato** (forma de la llamada), **decisión** (la llamada es válida pero la causa o la acción son otras), **ids**, **idioma**, **bucle**, **tiempo**. «inv-NNNN» es la invocación en `llm_trace.jsonl` de la ejecución citada (`experiments/e0e1/runs/<perfil>/<escenario>/r<k>/`).

### 4.1 `actual`
| Fallo | Ejecuciones | Clase | Qué pasa en la traza |
|---|---|---|---|
| Frase que contradice: «The wind is notable (mean 1.9 m/s…)» con `wind_notable = false` (ai-0004, T+03:12) y «the wind is notable but not affecting the deviation» (ai-0008, T+05:38) | demo r1, r2, r3 (inv-0004 e inv-0008; idénticas) | decisión (el texto no sigue a los checks) | El guardrail de coherencia no lo rechaza (la frase es solo texto); la métrica lo cuenta. |
| Misma contradicción: ai-0008 (T+05:04) «The wind is notable (mean 2.5 m/s…)»; en r3 también ai-0001 (T+02:05) | faults r2 (inv-0008), r3 (inv-0001, inv-0008) | decisión | Ídem. |
| Chino en el chat del monitor: «…suggesting不稳定连接。这些迹象表明命令链可能存在异常。» | demo r1 y r3, inv-0010 (chat-monitor, T+342 s). r2 no | idioma | Mismo texto en r1 y r3 (temperatura 0). Es el caso de la 5.3. |
| F3 sin alerta propia: `acknowledge_detection` sobre `ai-0003` (la alerta `SENSOR_FAULT` de F2) tras un `publish_alert` rechazado por «Nothing changes…» | faults r1, inv-0008 | decisión | La causa (`SENSOR_FAULT`) es la esperada, pero la skill dice que `SOURCE_SILENT` «es siempre un fallo distinto y lleva su propia alerta»; la evaluación exige una alerta publicada en la ventana, así que ❌. |
| F3 con causa equivocada: `GPS_JAMMING` (alerta ai-0008, severidad alta) | faults r2, r3, inv-0008 | decisión | Carga la skill, pide métricas, gps, radar y link y razona con «la GPS discrepa del radar»; no sigue el paso 5 («solo el GPS calla y el enlace sigue: fallo del receptor»). |
| F2 con 2 cadenas | faults r1, r2, r3 (inv-0003 e inv-0004) | decisión | `GPS_DEGRADED` abre ai-0003 (`SENSOR_FAULT`); `SOURCE_DISCREPANCY` abre ai-0004 (`GPS_JAMMING`) como alerta nueva en vez de sustituir a la anterior. |
| Alerta abierta ai-0004 (`GPS_JAMMING`) al final | faults r1, r2, r3, inv-0011 (T+05:20) | decisión | Ante `DetectionCleared` de `SOURCE_DISCREPANCY` hace `acknowledge_detection` diciendo «the GPS and radar still disagree despite the detection being cleared» en vez de `close_alert`. |

### 4.2 `qwen3-14b-t0`
| Fallo | Ejecuciones | Clase | Qué pasa en la traza |
|---|---|---|---|
| F3 con causa equivocada: `GPS_JAMMING` severidad alta, `supersedes: ai-0006`, `link_checked: false`, `gps_radar_disagreed: false` | faults r1, r2, r3, inv-0008 (idénticas) | decisión | Antes carga una skill que no existe, `source-silence` (la tool contesta «unknown skill… available: route-deviation, source-discrepancy»; **ids**/nombre inventado) y luego `source-discrepancy`. Mira solo `gps` y una ventana de métricas de 5 s, no mira `radar` ni `link`, y publica `GPS_JAMMING` como continuación de la alerta de F2. Ninguna regla del guardrail lo para (`GPS_JAMMING` no exige mirar el enlace). |

Sin ningún otro fallo: 0 contradicciones, 0 no latinos, 0 fallbacks, 0 abiertas, 0 cortes, 3/3 estables en los seis escenarios.

### 4.3 `qwen3-30b-a3b-t0`
| Fallo | Ejecuciones | Clase | Qué pasa en la traza |
|---|---|---|---|
| A2 diagnosticado `GPS_JAMMING` (esperado `GPS_SPOOFING`) | demo r1 inv-0004; spoofing r3 inv-0001 | decisión | Carga `source-discrepancy`, mira gps, radar, enlace y viento y publica `GPS_JAMMING`; el único rechazo fue el `null` del check, no la causa. Arrastra la causa en el aviso siguiente (la recuperación se ve como «recuperación del GPS_JAMMING»). |
| A3 respondido con fallback («sin diagnóstico») | demo r3 inv-0008 (T+05:38) | decisión + bucle | Con el enlace anómalo (`link_anomalous` debía ser `true`), publica `WIND` con `wind_notable=false`; el guardrail lo rechaza dos veces («WIND requires notable wind…» y «This is the same call as before; change what I told you») y el modelo repite la misma llamada hasta llegar a 12 iteraciones → fallback. En r1 y r2 sí llega a `HIJACK` (tras 2 y 1 `publish_alert` fallidos). El aviso de escalada (T+05:41) se contesta bien (`HIJACK`). |
| Fallback en la recuperación de F2 | faults r1 y r3, inv-0011 (T+05:20) | tiempo (iteraciones) | 11 llamadas de lectura (cada `get_events` por fuente, métricas, detector, `get_mission_plan`, skill) antes de intentar publicar; la 12.ª es un `publish_alert` rechazado y se agota `max_iterations` (12). No es lentitud: 7,4–7,6 s. |
| Alerta abierta: usa `publish_alert` (`WIND`/`UNKNOWN`, severidad baja, `supersedes`) o `acknowledge_detection` en vez de `close_alert` al llegar el `DetectionCleared` | wind r2/r3 inv-0002; spoofing r1 (ack), r2/r3 inv-0004; demo r1 (inv-0003, inv-0011), r2 (inv-0003, inv-0007, inv-0011), r3 (inv-0003, inv-0011); faults r1/r2 | decisión | Total de `close_alert` en la matriz: 24 (`actual`), 24 (14B), **10** (30B). Las alertas `UNKNOWN`/baja publicadas tras el último aviso son las 2 «falsas alarmas» de demo r2 y r3 (ai-0011, T+07:21, fuera de toda ventana). |
| F2 con 2 cadenas | faults r1 (inv-0003, inv-0004, inv-0005, inv-0008) | decisión | `SOURCE_DISCREPANCY` abre otra alerta `GPS_JAMMING` en vez de sustituir; luego varias intentonas con `supersedes`. |
| F3 causa equivocada `GPS_JAMMING` | faults r1 (solo `acknowledge_detection` sobre ai-0004), r2, r3 (alerta ai-0008) | decisión | Igual que en los otros dos perfiles. |
| `link_anomalous: null` aunque ha mirado el enlace | 43 rechazos (§5) | formato | Se corrige siempre en la llamada siguiente, a costa de ~2 s y una iteración. |
| `explanation` ausente y `` `explanatio n` `` (campo escrito con un espacio) | demo r1 inv-0005; spoofing r2 inv-0002 | formato | El guardrail lo describe y el modelo lo repara en la llamada siguiente. |
| Ids de otra detección: `detection_ids: [det-0004, det-0006]` en una invocación de `det-0008` | faults r2 inv-0009 | ids | Rechazado dos veces (`publish_alert` y `acknowledge_detection`); luego usa `close_alert`. |
| Inestabilidad con temperatura 0 | demo, wind, spoofing, faults | — | Las 3 repeticiones difieren en 4 de 6 escenarios; con `actual` y 14B no. Posible causa (no comprobada): el 30B-A3B es un MoE y la ejecución por lotes de vLLM no es bit a bit reproducible. |

## 5. Rechazos de guardrails por perfil y tipo
Recuento por **mensaje de error** (una llamada rechazada puede llevar varios, por eso suman más que los 35 / 27 / 73 de `compare.md`). Todos son de `publish_alert` salvo uno de `acknowledge_detection` en el 30B.

| Tipo | `actual` | `qwen3-14b-t0` | `qwen3-30b-a3b-t0` |
|---|---|---|---|
| `link_anomalous = null` aunque pidió el enlace (**formato**) | 9 | 15 | 43 (40 contra `false`, 3 contra `true`) |
| «Nothing changes… use acknowledge_detection» (**decisión**: no hay nada nuevo) | 10 | 12 | 9 |
| «This is the recovery from the GPS_SPOOFING / GPS_JAMMING / SENSOR_FAULT… publish… medium and supersedes» (**decisión**) | 12 | 9 | 9 |
| `wind_with_drift = false` no coincide con `get_track_metrics` (**decisión**) | 6 | 0 | 0 |
| «HIJACK requires having looked at the link» | 3 | 0 | 0 |
| «detection … is already in the open alert …» | 0 | 0 | 8 |
| «WIND requires notable wind…» | 0 | 0 | 4 |
| «route deviation with cause GPS_JAMMING is the GPS recovery and requires a GPS alert…» | 0 | 0 | 4 |
| `explanation` ausente / `explanatio n` (**formato**) | 0 | 0 | 4 (2 rechazos) |
| `link_checked = true` sin haber mirado el enlace; llamada repetida; ids de otra invocación | 0 | 0 | 1 + 1 + 2 |
| **Rechazos (llamadas) totales** | **35** | **27** | **73** |

Lectura de lo que dice sobre cuánta ayuda necesita cada modelo:
- **`qwen3-14b-t0` es el que menos necesita**: 27 rechazos, 15 de ellos el `null` (formato, inocuo) y los demás son los dos «de ciclo de vida» (no hay nada nuevo / es la recuperación) que `actual` también necesita. No hace falta nada de la lista larga del 30B (ni «WIND requires notable wind», ni «ya está en la alerta abierta», ni ids).
- **`actual`** (35) necesita los mismos dos de ciclo de vida más tres que el 14B ya no necesita: `wind_with_drift` (6) y mirar el enlace antes de `HIJACK` (3), que son decisiones apoyadas por el guardrail de coherencia.
- **`qwen3-30b-a3b-t0`** (73) necesita 2–2,7 veces más que los otros: 8 mensajes de causa equivocada que el guardrail de coherencia sí detecta (4 `WIND` sin viento notable y 4 de recuperación del GPS), 8 de «ya está en la alerta abierta», 4 de campos mal escritos y 3 de ids/llamada repetida. El `null` por sí solo son 43; de sus 116 llamadas a `publish_alert`, 73 se rechazan (dos de cada tres).
- Los guardrails **sí cumplen su función en los tres** (comprobado en los `AnomalyDetected` publicados de las 54 ejecuciones): los 21 `WIND` publicados llevan `wind_notable = true` y ningún `HIJACK` lleva `link_checked = false`. Lo que no cubren (F3, A2 como `GPS_JAMMING`, cerrar con `close_alert`, saltarse la skill) es decisión del modelo, no hay regla que lo rechace; encaja con `docs/quien_decide_que.md` (causa y ciclo de vida los pone el modelo, salvo las reglas ya codificadas).

## 6. `faults` aparte (F2 y F3)
| | `actual` | `qwen3-14b-t0` | `qwen3-30b-a3b-t0` |
|---|---|---|---|
| F1 (radar mudo, `SENSOR_FAULT`) | 3/3 ✅, 1 cadena | 3/3 ✅, 1 cadena | 3/3 ✅, 1 cadena |
| F2 (pérdida de GPS, `GPS_JAMMING` o `SENSOR_FAULT`) | 3/3 ✅ pero **2 cadenas** (`SENSOR_FAULT` / `GPS_JAMMING` / `SENSOR_FAULT`) | 3/3 ✅, **1 cadena** (`GPS_JAMMING`×3, sustituyendo) | 3/3 ✅, 1 cadena salvo r1 (2) |
| F3 (GPS mudo 12 s, `SENSOR_FAULT`) | 0/3 (r1 `SENSOR_FAULT` por ack, sin alerta; r2 y r3 `GPS_JAMMING`) | 0/3 (`GPS_JAMMING`, las 3 idénticas) | 0/3 (`GPS_JAMMING` en las 3) |
| Abiertas / fallbacks / contradicciones | 3 / 0 / 3 | 0 / 0 / 0 | 2 / 2 / 0 |
| Estabilidad | 2/3 (r1 distinta en F3) | 3/3 | 1/3 |

- **F3 no discrimina entre modelos:** los tres lo fallan igual (9 de 9 ejecuciones ❌). Es el patrón «hay una alerta de GPS abierta, esto debe ser lo mismo» (paso 0 de la skill) frente al paso 5 («siempre es un fallo distinto y lleva su propia alerta»). Ninguno busca `radar`/`link` con `last_n = 2` y el 14B ni siquiera mira el enlace. Es un problema de la skill o de una regla, no de elegir modelo; **no se ha tocado** (solo se mide).
- **F2:** el 14B es el único que lo resuelve con una sola cadena en las tres repeticiones; `actual` abre una alerta nueva en vez de sustituir y la deja abierta.
- **Lo que fallaba en `actual` (F3 y la cadena de F2) sigue fallando igual con el 14B (F3) o mejor (F2)**; el 30B no lo mejora y añade fallbacks.

## 7. Latencia y tokens (mediciones)
Por llamada del monitor (`compare.md`) y por invocación; velocidad de generación = `completion_tokens / latencia` de las llamadas con ≥ 150 tokens de respuesta (incluye el prefill de 3–10 k tokens, así que es una cota baja).

| | `actual` | `qwen3-14b-t0` | `qwen3-30b-a3b-t0` |
|---|---|---|---|
| Llamada del monitor p50 / p95 / máx. | 0,9 / 6,1 / 7,5 s | 0,9 / 5,4 / 6,3 s | 0,4 / 2,2 / 3,2 s |
| Invocación del monitor p50 / p95 / máx. | 7,5 / 16,5 / 25,1 s | 6,5 / 12,9 / 14,2 s | 6,1 / 8,1 / 12,6 s |
| Iteraciones por invocación p50 / p95 / máx. | 4 / 7 / 7 | 4 / 5 / 5 | **8 / 12 / 12** (tope) |
| Informe / chat del informe (invocación p50) | 7,8 / 2,1 s | 7,9 / 3,4 s | 3,6 / 1,4 s |
| Generación (mediana) | 55 tok/s | 57 tok/s | 131 tok/s |
| Mayor prompt / mayor respuesta de una llamada | 7623 / 622 | 6280 / 679 | 9808 / 705 |
| Llamadas del monitor / `get_events` | 304 / 60 | 273 / 51 | **601 / 289** |
| Tokens por ejecución de `demo` (prompt / respuesta) | 161 k / 4,4 k | 144 k / 3,8 k | **422 k / 7,0 k** |
| Tokens por ejecución de `faults` (prompt / respuesta) | 199 k / 4,2 k | 169 k / 3,8 k | **478 k / 6,4 k** |
| Cortes por longitud (`finish_reason: length`) | 0 | 0 | 0 |

Lectura: el 30B-A3B genera 2,3× más rápido pero hace **el doble de llamadas** (una `get_events` por fuente en vez de pocas) y gasta 2,6–3× más tokens de prompt; el resultado es la misma latencia por invocación (6,1 s frente a 6,5 s) y más probabilidad de agotar las 12 iteraciones. Ningún perfil llega cerca de los límites actuales (monitor 60 s por invocación y 30 s por llamada).

## 8. Recomendación

### 8.1 ¿Merece la pena E2 (muestreo de Qwen)?
- **`qwen3-14b-t0`: no.** A temperatura 0 es 3/3 estable en los seis escenarios y no tiene fallos de formato, bucles, cortes ni idioma que un muestreo distinto pudiera arreglar; su único fallo (F3) es una decisión determinista que se repite idéntica. Subir la temperatura a 0,7 y `presence_penalty` 1,5 solo puede quitar reproducibilidad (justo lo que hace valioso a este perfil para quitar ayudas en la Fase 8) y arriesga mezcla de idiomas (la propia ficha avisa).
- **`qwen3-30b-a3b-t0`: solo como comprobación acotada**, y solo si el 30B sigue interesando. Sus fallos tienen forma de muestreo/repetición (la misma llamada repetida hasta el tope en demo r3, `explanatio n`, 12 lecturas seguidas) y ya no es reproducible a temperatura 0, así que la estabilidad deja de ser un argumento en contra. Coste: 3 escenarios × 3 repeticiones sobre el servidor del 30B ≈ 10 min. Si no se hace, no se pierde nada para elegir modelo.
- Recomiendo **saltar E2 para el 14B y decidir E2 del 30B después de ver E3**.

### 8.2 ¿Cuál de los dos Qwen3 es mejor candidato?
**`qwen3-14b-t0`.** Contra `actual` y contra el 30B:
- Mejor o igual que `actual` en todos los escenarios: iguales aciertos de etiqueta, pero **F2 con una cadena en vez de dos, 0 abiertas (frente a 3), 0 contradicciones (frente a 9), 0 chino en el chat (frente a 2)**, 27 rechazos frente a 35, y 11–15 % menos de tokens. Misma latencia (p50 de invocación 6,5 s frente a 7,5 s).
- Mejor que el 30B en todo salvo velocidad de generación: el 30B tiene 2 falsas alarmas, 3 fallbacks, 14 abiertas, A2/A3/spoofing fallados en alguna repetición, no es estable y gasta 3× más tokens.
- F3 es igual de malo en los tres: no decide.
- Cautela: con 3 repeticiones y 6 escenarios la evidencia es de «no hemos visto fallos»; el 14B repite idéntico, lo que significa que 3 repeticiones valen casi como 1 (la variabilidad entre guiones no se explora).

### 8.3 Latencias medidas y tiempos propuestos para los perfiles `-think` (E3)
Solo se proponen; **no se ha cambiado ningún perfil**. Lo medido sin razonamiento: generación 57 tok/s (14B) y 131 tok/s (30B-A3B); llamadas del monitor de hasta 6,3 s y 3,2 s; invocaciones de hasta 14 s (14B, 5 iteraciones) y 12,6 s (30B, 12 iteraciones). **No hay ninguna medición con razonamiento:** lo único que existe es la prueba de la fase 6 (420 tokens de razonamiento en una pregunta trivial). Por eso las cifras de abajo son estimaciones y la regla es fijar los definitivos con la ejecución previa `demo ×1` de E3.

| Parámetro | Actual (provisional) | Propuesta 14B-think | Propuesta 30B-think | Cálculo |
|---|---|---|---|---|
| `llm_timeout_s` monitor | 90 s | 90 s (se mantiene) | 45 s | peor caso `max_tokens` 4000 ÷ velocidad: 4000/57 ≈ 70 s; 4000/131 ≈ 31 s; con ×1,3–1,5 de margen |
| `llm_timeout_s` informe | 240 s | 150 s | 70 s | 6000 tokens: ≈ 105 s y ≈ 46 s |
| `llm_timeout_s` chats | 120 s | 90 s | 45 s | igual que el monitor |
| `max_invocation_s` monitor | 300 s | 300 s | 300 s | típico ≈ 5 llamadas × ~1000 tokens ÷ 57 ≈ 90 s (14B) y 8–12 × ~1000 ÷ 131 ≈ 90 s (30B); el peor caso teórico (todas las llamadas al tope de 4000 tokens) sería ≈ 350 s en ambos: el tope de 300 s corta la cola, no el caso normal |
| Espera de la plataforma | 330 s | 330 s (monitor + 15 s < espera) | 330 s | condición de la fase 6 |
- Los ~1000 tokens de razonamiento por llamada son una **hipótesis** (la prueba de la fase 6 dio 420 en una pregunta trivial); se sustituye por el p95 medido: `max_invocation_s` = p95 de la invocación × 1,5 y `llm_timeout_s` = máx. de la llamada × 1,5.
- Coste estimado de ejecutar `demo` con razonamiento y «esperar al agente»: ocho invocaciones del monitor con LLM (más dos chats y el informe); a ~90 s por invocación son ≈ 12 min de reloj por ejecución (estimación, no medida). Con 18 ejecuciones por perfil serían horas: conviene acotar E3 a `demo`, `faults` y `spoofing` (los que discriminan) antes de la matriz completa.
- El 30B-A3B tiene más margen de tiempo (2,3× más rápido) pero hace 2× llamadas, y cada llamada con razonamiento suma tokens; el 14B hace menos llamadas pero genera 2,3× más despacio.

## 9. Límites y avisos
- **n pequeño.** 3 repeticiones; el 14B y `actual` repiten idéntico a temperatura 0, así que los «3/3» valen poco más que una ejecución; el 30B, que sí varía, tiene 3 muestras. Todo recuento es una suma de 3.
- **La evaluación mide «alerta publicada en la ventana con causa aceptada».** F3 de `actual` r1 (ack sobre una alerta `SENSOR_FAULT` ya abierta) cuenta ❌ aunque la causa sea la esperada; es coherente con la skill (paso 5: alerta propia), pero la métrica y la skill coinciden por construcción.
- **Rechazos:** el recuento por llamada (`compare.md`: 35/27/73) y por mensaje de error (§5) difieren a propósito.
- **Velocidad de generación (§7):** mediana de llamadas con ≥ 150 tokens de respuesta; incluye prefill; no distingue caché de prefijos (⚠️ no he comprobado si vLLM la usa con esta configuración, así que no afirmo por qué el 30B gasta más tokens: solo que hace más llamadas).
- **MoE no determinista (§4.3):** es una hipótesis para la inestabilidad del 30B a temperatura 0; no la he verificado.
- Las cifras de §8.3 son estimaciones, no mediciones con razonamiento.
- No he leído los informes (`informe.md`) ni los chats de todas las ejecuciones: solo lo necesario para clasificar los fallos y el chat con caracteres no latinos.

## 10. Qué queda
- E2 solo si interesa el 30B (ver §8.1); E3 con `demo ×1` previo para medir y fijar los tiempos de los perfiles `-think`, y luego una matriz reducida.
- F3 (los tres modelos): el paso 5 de la skill no se aplica cuando hay una alerta del GPS abierta. Cualquier cambio (skill, regla) es una decisión tuya y se mediría como un experimento aparte.
- `docs/quien_decide_que.md`: contrastado, sin cambios (no hay código nuevo); los resultados confirman que la causa y el ciclo de vida de las alertas dependen del modelo salvo en las reglas ya codificadas.

## 11. Copias (reglas 13 y 15)
Las dos comprobaciones de la regla 15 (palabras prohibidas y nombres propios) **salen vacías**; no ha hecho falta corregir nada. `experiments/e0e1/compare.md` entra en las dos instantáneas (es lo único de `experiments/` que no se ignora). Copiado a `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`: `docs/fases/`, `experiments/e0e1_compare.md`, `eval.md` e `informe.md` de las 54 ejecuciones en `experiments/e0e1/<perfil>/<escenario>/r<k>/` y en `runs/<escenario>/<run_id>/`, una selección de trazas de los fallos en `trazas/fase7/`, `snapshots/fase7/` y `snapshots-limpias/fase7/`.

## 12. Mensaje de commit propuesto
```
feat: phase 7 - experiments E0 and E1 (actual, Qwen3-14B, Qwen3-30B-A3B)

- experiments/e0e1/compare.md: one matrix, 3 profiles x 6 scenarios x 3
  repetitions (54 runs, all ok); the rest of the output is not versioned
- docs: phase 7 report with the per-scenario comparison, classified failures,
  guardrail rejections by profile, the faults scenario, measured latencies and
  the recommendation for E2/E3
- no change to prompts, skills, agents.yaml, profiles or code
```
