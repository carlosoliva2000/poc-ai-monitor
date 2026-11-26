# E7c · Monitor de situación

Informe de cierre: pasos 1, 1b, 2, 3, 4 y 5. Referencia: especificación del núcleo v2 (v1.2). Escrito para: Carlos, que revisa la fase y hace el commit.

## Paso 1 · Lo congelado se ejecuta
- `situation/facets.py`: dos motores con la misma salida (`Snapshot`: estado, fila, entradas y confianza de cada faceta). `LearnedFacets` (por defecto) ejecuta las 13 tablas aprendidas y la regla de la situación; `HandwrittenFacets` conserva las tablas del vídeo como alternativa (`tables: learned | handwritten` en `config.yaml`, `--tables`). Catálogo, seguidor y política son los mismos con las dos: la E8 compara solo las tablas.
- `situation/freeze.py`: al crear `LearnedFacets` se comprueba el sha256 de los ficheros del paquete contra `tables_freeze.json`; si uno cambió, el monitor no arranca (`FreezeError`). `tools/training/check_freeze.py` sigue siendo la comprobación completa y da `ok`.
- **Incoherencia anotada:** `situation_rule.py` (congelado) tiene `MARGIN_K = 1.0`, pero `tables_freeze.json` dice `margin_k: 0.5` y la evaluación de la E7b usó 0,5. El monitor lee el 0,5 del fichero de congelación (`freeze.margin_k()`) sin tocar el fichero congelado. **Propuesta para la especificación:** que `situation_rule.py` y el fichero de congelación digan lo mismo en la próxima congelación.
- Apaños del vídeo que salen del camino por defecto: `GnssReference`, `WIND_LIMIT_MPS`, `telemetry < 3 s` (viven solo en `HandwrittenFacets`), el `> 50` del secuestro, la confianza fija por fila y `UNDETERMINED_QUIET_S` (sustituido por la regla «un incidente abierto explica la desviación»). `DRIFT_FACTOR` se queda (especificación §6) y pasa a `policy.yaml` (`drift_factor`).
- `demo` con las tablas aprendidas = lo de la E7b (±4 s); con las de mano, los instantes del vídeo. Las tablas a mano no tienen las facetas de causa, así que **no ven el secuestro** (se quedan en «enlace perdido»): queda escrito.

## Paso 1b · Módulo antiguo retirado (lista aprobada)
Borrado el módulo de IA antiguo (`agent/` salvo `profiles.py` y `__init__.py`, que `serve.sh` necesita hasta la E7d; `config/`, `testing/`, detector, monitor, chats, informe, agente del instructor, evaluación, `runtime`…), 56 tests, `tools/experiments/`, `agent-assets-v13/`, la API de tools (`POST /api/tools/{name}`, `platform_app/tools/`) y «esperar al agente». Se quedan `export_dmn.py` (exporta `tables_learned.yaml` —13 decisiones, 68 filas— y la regla —10 filas— sin cambios; lo comprueba `test_export_dmn.py`; no se ha validado con un motor DMN real y las salidas con decimales se escriben con 6 cifras), `agent-assets/`, `model-profiles/`, `serve.sh` y la dependencia `openai`. La tabla de la E6 pasó a `tests/data/decision_table_e6.yaml` (los tests de `table.py` la usan; `table.py` está congelado y su ruta por defecto ya no existe). Se borró `test_bus_client.py` (se colgaba) y se escribió uno nuevo en el paso 2. Contrato v1.3 (rompe): fuera `tools.py`, `times.py`, `ToolOk/ToolError`, `wait_agent` y `waiting_agent`.

## Paso 2 · Catálogo, seguidor y política

### Catálogo (`situation/catalog.py` + `policy.yaml`; política, no aprendida)
Varios incidentes a la vez, **uno por familia**; el nombre solo cambia hacia un tipo más grave de su familia (el orden de la lista) o desde `UNDETERMINED` a la causa que se confirma.

| Tipo | Familia (orden) | Abre con | Contexto | Sev. base |
|---|---|---|---|---|
| `HIJACK` | control (3.º) | enlace perdido **y** `drone.cause` y `drone.mode` = control ajeno, **las dos confirmadas** | sospecha, hueco de telemetría | alta |
| `LINK_LOSS` | control (2.º) | `link.availability` = perdido | sospecha «HIJACK (probable)» si el control ajeno es probable | media |
| `LINK_DEGRADED` | control (1.º) | `link.quality` = degradado, enlace conectado | — | baja |
| `GPS_SPOOFING` | engaño | `gps.integrity` = engañado (abre antes de desviarse) | viento estimado | alta |
| `DEAD_RECKONING` | GPS (3.º) | causa = navegación a estima | fuente de la desviación | media |
| `GPS_NO_FIX` | GPS (2.º) | `gps.availability` = sin fix | — | media |
| `GPS_DEGRADED` | GPS (1.º) | `gps.quality` = degradada | — | baja |
| `WIND` | viento | viento fuera de límites (sin engaño ni pérdida de GPS en curso) o causa = viento (sin otra causa en curso) | fuente de la desviación | baja (sube si se desvía) |
| `SOURCE_SILENT` (sujeto = fuente) | `source:<fuente>` | `<fuente>.availability` = sin datos; el GPS y la batería no si el enlace está caído, recién vuelto o degradado | — | GPS y radar media; estación y batería baja |
| `RADAR_OUT_OF_RANGE` | radar | `radar.availability` = fuera de alcance | — | baja |
| `BATTERY_CRITICAL` / `CANNOT_REACH_HOME` / `BATTERY_LOW` / `FAILSAFE` (sujeto = modo) | batería (de más a menos) | nivel crítico / no llega a casa (solo en misión) / nivel bajo / failsafe que nada explica | carga | alta / media / baja / media (aterrizar, alta) |
| `UNDETERMINED` | sin determinar | desviado, causa dudosa y ningún incidente (ni rebote) que lo explique | causa posible anotada (hipótesis vacía hasta la E7d) | media |

- **Máscaras** (como al entrenar): con el enlace perdido, GPS y batería son `?`; con una entidad no disponible, sus otras facetas `n/a`; sin desviación no hay causa. Un `?` **mantiene** el incidente (ni sigue ni «la causa ha desaparecido»).
- **Failsafes:** contexto de lo que los provoca (enlace, batería); incidente propio (`FAILSAFE`) solo si nada lo explica en el instante en que saltó.
- **Solapes resueltos:** desviación con incidente abierto → evidencia de ese incidente; el viento falso del estimador al acabar un engaño o una pérdida de GPS no abre `WIND`; la causa «viento» de las tablas (la más probable cuando falta información) no cuenta con otra causa en curso; la telemetría callada por el enlace no abre incidentes de fuente.
- **Confianza** del incidente = la mejor de las filas que lo deciden (cortes 0,9 y 0,6 de las filas). **Política de la causa dudosa:** una fila `possible` no abre nada (salvo una fuente sin datos, que es un hecho y no una causa) y una causa dudosa sin explicación sale como `UNDETERMINED`; el secuestro solo con filas confirmadas; con una sola de las dos tablas (o una probable) se queda en `LINK_LOSS`; una confianza `possible` no sube la severidad.

### Seguidor y severidad (`situation/tracker.py`, `engine.py`)
- Abre a los k instantes; cambia de nombre sin cerrar; en los tipos con recuperación, pasa a «en recuperación» al acabar la causa (baja un nivel) y cierra a los m instantes en ruta; los demás cierran a los m instantes sin causa.
- **Las dos revisiones de más del viento:** una causa que reaparece en los 15 s siguientes a pasar a recuperación (`bounce_s`) no reabre el incidente; después, solo tras k instantes. En `demo`, el viento tiene una sola recuperación (antes, tres: T+02:37, 02:42 y 02:51).
- **Severidad:** base por tipo; sube **una vez** por empeorar (el dron empieza a desviarse en `WIND`, o una distancia al plan se duplica a partir de 20 m) y **una vez** por llevar más de 120 s abierto; baja uno en recuperación. Configurable en `policy.yaml` (`defaults`, `escalate_on_deviation`, `escalate_after_s`).
- Valores por tipo (`k_open` de `WIND` y `LINK_DEGRADED` = 8, `SOURCE_SILENT` = 5) elegidos mirando los falsos por tipo de la validación: parpadean unos segundos cerca de su umbral (viento falso del estimador al arrancar, latencia del enlace).

### Calibración de k y m (`tools/situation/`, `experiments/e7c/`)
- **Incidentes de verdad:** el mismo catálogo y seguidor alimentados con `states.jsonl` (k = m = 1, sin retardos). Un incidente de verdad de menos de 10 s es un transitorio y no se exige verlo (`short_truth_incidents`: 54 en validación; son sobre todo los «viento» de T+3…10 del arranque).
- **Regla de elección (escrita antes de ver las curvas):** el menor k con falsos ponderados ≤ 0,5/h (ataque ×3), falsos de ataque (`HIJACK`, `GPS_SPOOFING`) ≤ 0,1/h y parpadeo ≤ 5 % de los incidentes de verdad; después el menor m con lo mismo.
- **Primera pasada** (`e7b-v3-validation-grid-before-refinements.md`): ningún par cumplía (con k = 5 y m = 10: 0,95 ponderados, 0,15 de ataque, 3,7 % de parpadeo). Se vio por tipo que los falsos eran de cuatro clases y se corrigieron en el catálogo, no en las tablas: (1) cortes del enlace **sin secuestro** que las tablas de causa leen como «control ajeno» (13–15 `HIJACK` falsos en 85 h) → el secuestro pide causa **y** modo, confirmados; (2) viento falso al volver el GPS tras una pérdida y al arrancar → supresión y `k_open` = 8; (3) parpadeos de calidad del enlace → `k_open` = 8; (4) telemetría callada por un enlace degradado → no abre incidentes de fuente.
- **Resultado** (359 variantes de validación de e7b-v3, 84,8 h; curvas en `e7b-v3-validation-grid.png`, tabla en `e7b-v3-validation-grid.md`; cifras rehechas el 26/11 tras corregir la herramienta, ver «Diagnóstico antes del paso 3»): **k = 5, m = 10** (0,50 ponderados/h, 0,09 de ataque/h, 1,8 % de parpadeo, 494 de 505 incidentes de verdad detectados). m casi no influye a partir de 10. k = 3 queda en 0,53 y 0,11 (por poco); k = 8 cumple con más margen (0,41 y 0,07) pero retrasa 8 s los incidentes rápidos. **Aprobados k = 5 y m = 10** y el catálogo (26/11).

| Tipo (verdad) | de verdad | detectados | con su nombre | retraso apertura mediana / p90 (s) |
|---|---|---|---|---|
| `GPS_SPOOFING` | 47 | 47 | 47 | 4 / 4 |
| `HIJACK` | 44 | 44 | 40 | 4 / 5 (el nombre, 23 s de mediana: viene de `LINK_LOSS`) |
| `LINK_LOSS` | 94 | 94 | 94 | 4 / 5 |
| `LINK_DEGRADED` | 33 | 31 | 25 | 7 / 13 |
| `GPS_NO_FIX` / `GPS_DEGRADED` | 53 / 52 | 52 / 52 | 52 / 52 | 4 / 3 |
| `DEAD_RECKONING` | 31 | 31 | 27 | 4 / 4 |
| `WIND` | 39 | 34 | 34 | 7 / 16 |
| `SOURCE_SILENT` | 95 | 92 | 92 | 5 / 13 |
| `RADAR_OUT_OF_RANGE` | 51 | 51 | 51 | 4 / 5 |
| `BATTERY_CRITICAL` | 38 | 38 | 36 | 9 / 12 |
| `CANNOT_REACH_HOME` | 51 | 51 | **13** | 9 / 12 |
| `BATTERY_LOW` | 9 | 9 | **0** | — |
| `FAILSAFE` | 2 | 2 | 2 | 5 / 5 |

  Falsos en validación: `HIJACK` 8, `LINK_DEGRADED` 7, `SOURCE_SILENT` 6, `UNDETERMINED` 3, `GPS_DEGRADED` 1, `WIND` 1 (0,50/h ponderados). Detalle: `e7b-v3-validation-k5-m10.md`.
- **Generalización** (`e7b-gen-v3`, 600 variantes, 115 h; medida sin decidir nada; rehecha el 26/11 con la herramienta corregida): 1,42 ponderados/h, 0,10 de ataque/h, 4,4 % de parpadeo (`e7b-gen-v3-test-k5-m10.md`). Incidentes de GPS: `GPS_SPOOFING` 81 de 82, `DEAD_RECKONING` 77 de 78, `GPS_NO_FIX` 94 de 94, `GPS_DEGRADED` 57 de 70. Falsos más altos: **GPS degradado 71** (la tabla de `gps.quality` con otros receptores: precisión por segundo 0,51), fuentes 31, viento 15, `HIJACK` 11. **Es lo que la E8 debe mirar.** (La primera medida, 1,31/h con 39 de 82 engaños, estaba mal: ver el diagnóstico.)

### Lo que las tablas no ven bien (para la E8)
- **`endurance`:** ninguna tabla de batería ve a tiempo el `cannot_reach_home` (`BE-01` salta a T+710, la verdad lo da desde T+223). Lo cubre `FAILSAFE` (el vuelo vuelve solo a T+231, el incidente abre a T+03:53).
- `CANNOT_REACH_HOME` se nombra bien solo en 13 de 51 casos; `BATTERY_LOW` en ninguno: la tabla de `battery.endurance` da «no llega a casa» antes que la verdad, el monitor abre la familia ya como `CANNOT_REACH_HOME` y el orden no deja volver atrás (ver el diagnóstico).
- `GPS_DEGRADED` en la generalización: 71 falsos en 115 h (precisión por segundo de `gps.quality` 0,51).
- El secuestro se queda en `LINK_LOSS` cuando las tablas de causa y de modo no coinciden con fila confirmada (ver el diagnóstico).
- `BA-01` (batería sin datos) es `possible` (p = 0,57): por eso `SOURCE_SILENT` admite filas `possible`.

### Diagnóstico antes del paso 3 (26/11)
Sin ajustar nada con la validación. Scripts de diagnóstico fuera del repo; todo se reproduce con `calibrate.py`.

**1 · Incidentes de GPS en la generalización: era un error de la herramienta de evaluación.** `tools/situation/lib.py` creaba el monitor y le asignaba después los activos de la variante (`monitor.features.assets = …`), pero el extractor calcula al construirse las ventanas de frescura (1,5 periodos), la caducidad del radar y las líneas base del receptor. Se quedaban los periodos por defecto (GPS a 1 s: frescura 1,5 s). En `e7b-gen-v3` la mitad de las variantes tienen el GPS a **3 s** (validación: 0,5, 1 y 2 s), así que cada tercer segundo el GPS salía «sin dato fresco» y las tablas caían a `reliable`/`normal`: patrón `SS.SS.SS.` y nunca más de 2 instantes seguidos, cuando k = 5. Con GPS a 3 s se perdían **todos** (0/42 engaños, 0/35 estima, 0/40 sin fix); con 0,2 s, casi ninguno. No era la confianza (las filas eran `confirmed`) ni la máscara (2–7 % de instantes enmascarados). Ejemplos: `v0185` (engaño de T+747 a 884: 74 s «engañado» de 138, racha máxima 2), `v0284` (sin fix de T+678 a 797: 54 de 120, racha 2), `v0330` (estima: 4 instantes sueltos). En las variantes con GPS ≤ 2 s la edad por segundo nunca llega a 1,5 periodos, así que **la validación casi no cambia**.
- Arreglo: `variant_monitor()` crea el extractor con los activos de la variante; test en `tools/situation/tests/test_lib.py`. El monitor en directo no estaba afectado (`demo` y `nominal` usan los periodos de `assets.yaml`).
- **Qué cambia en validación:** detectados 493 → 494 de 505; parpadeo 2,0 → 1,8 %; falsos iguales (0,50 ponderados/h, 0,09 de ataque/h); `HIJACK` con su nombre 41 → 40, `DEAD_RECKONING` 28 → 27, `LINK_DEGRADED` 30/24 → 31/25. La regla sigue eligiendo **(5, 10)**.
- **Generalización corregida:** `GPS_SPOOFING` 81/82, `DEAD_RECKONING` 77/78, `GPS_NO_FIX` 94/94. Lo que queda: un engaño de 35 s con interferencia y enlace callado (`v0287`, racha máxima 1) y una estima dentro de un secuestro (`v0508`: la causa sale `wind` 315 s de 366; **tablas**, para la E8). La F1 por segundo de `gps.integrity` en la generalización es la de la E7b: 0,87–0,89 es la F1 de la clase «engañado» (sin y con máscara); la E7b da la **F1 macro** de las dos clases, que con la máscara sale **0,942**, el mismo número de la E7b (sin máscara, 0,932).
- **Comprobado que el entrenamiento no tiene el fallo:** la cadena de la E7b (`tools/training/features.py`: `build` → `variant_matrix`) crea el extractor con `FeatureExtractor(variant_assets(folder))`, así que las características de entrenamiento, validación, prueba y generalización de e7b-v3 y e7b-gen-v3 se calcularon con los periodos de cada variante. Que la F1 macro de la generalización salga igual (0,942) con el extractor corregido lo confirma. Las tablas congeladas no cambian.
- **Monitor en directo:** `SituationMonitor` crea su extractor con `FeatureExtractor()`, que lee `assets.yaml` en el constructor, y nadie le asigna los activos después: ni `ai_module.situation` (`__main__.py`, `replay.py`) ni `platform_app.run`, que lo arranca como proceso aparte. Todos los escenarios de `scenarios/` tienen los periodos de `assets.yaml`. Lo único distinto es el alcance del radar de `endurance` (8000 m frente a 6000), y no es este fallo: el monitor no conoce los activos de cada escenario, solo su configuración. **Para la E8:** que el inventario de activos del monitor coincida con el escenario (o anotar que en `endurance` el radar es de 8 km). `tools/training/replay_learned.py` y `live_check.py` también usan los activos por defecto, pero solo sobre `runs/<escenario>`, que coinciden.
- El mismo patrón está en `tools/training/hand_tables.py` (E7b, comparación con las tablas a mano). No lo he tocado: no afecta a las tablas congeladas, pero su comparación en variantes con periodos distintos de los de `assets.yaml` está sesgada contra las tablas a mano. **Para la E8:** crear allí el extractor con los activos de la variante (como `variant_monitor()`) y rehacer esa comparación; las cifras de la E7b no se rehacen ahora.

**2 · `BATTERY_LOW` (0 de 9 con su nombre en validación, 2 de 38 en la generalización): lo tapa otro incidente de su familia; no es un error del linaje.** En la verdad la secuencia es `BATTERY_LOW → CANNOT_REACH_HOME → BATTERY_CRITICAL` (las 9 de validación y 29 de las 38 de la generalización). El monitor abre la familia `battery` directamente como `CANNOT_REACH_HOME`, de 30 a 40 s **antes** de que la verdad diga `BATTERY_LOW`, porque la tabla de `battery.endurance` da «no llega a casa» antes que la verdad. Como el nombre solo cambia hacia más grave, ya no pasa por `BATTERY_LOW`. Ejemplos: `v0757` (verdad: bajo T+503, no llega T+528, crítico T+601; monitor: no llega T+464, crítico T+604), `v0952` (verdad 123/124/226; monitor 84/234), `v1183` (verdad 238/322/347; monitor 204/364). Es de la **tabla** (para la E8): en `endurance` la misma faceta va tarde, aquí va pronto. La familia se detecta siempre (9/9 y 38/38).

**3 · Secuestros** (contados desde las anomalías inyectadas; 3 de validación y 6 de la generalización caen después del fin del vuelo y no cuentan):

| | secuestros de verdad | `HIJACK` | se quedan en `LINK_LOSS` | de ellos, la verdad tampoco puede decir `HIJACK` |
|---|---|---|---|---|
| validación | 46 | 40 | 6 | 2 |
| generalización | 67 | 52 | 15 | 1 |

- «La verdad tampoco puede» = el dron sigue en ruta todo el corte (sin desviación no hay causa), así que el catálogo sobre `states.jsonl` también da `LINK_LOSS`. Sin ellos: 40 de 44 y 52 de 66.
- Los que se quedan en `LINK_LOSS` lo hacen porque **las dos tablas no coinciden con fila confirmada**: en la generalización, ningún instante de esos 14 tiene causa y modo confirmados a la vez. Lo normal es causa `foreign_control` confirmada con modo `mission` confirmado (`v0175`, `v0346`), o modo `foreign_control` `possible` con causa `wind` confirmada (`v0462`, `v0574`, `v0590`). Es de las **tablas** (`drone.mode` con el control ajeno, `drone.cause` que lee viento): para la E8. Con una sola tabla confirmada saldrían más `HIJACK`, pero también los 13–15 falsos por cada 85 h que vimos al calibrar. No lo cambio.
- El nombre llega tarde: 23 s de mediana en validación y 43 s en la generalización desde que abre `LINK_LOSS`.

### `demo` y `nominal` frente al vídeo (`python -m ai_module.situation.replay runs/<esc>/events.jsonl`)
| Incidente | Vídeo (tablas a mano) | Ahora (aprendidas, k = 5) |
|---|---|---|
| `WIND` | abre 02:18, recuperación 02:35, cierra 03:00 | abre 02:19 (sube a media 02:20), recuperación 02:37, cierra 03:00; **una recuperación** |
| `GPS_SPOOFING` | 03:20, 04:12, 04:32 | 03:22, 04:12, 04:33 |
| `LINK_LOSS` → `HIJACK` | 06:14 → 06:24; recuperación 06:55; cierra 07:58 | 06:12 → **06:28** (pide las dos tablas confirmadas); recuperación 06:53; cierra 07:58 |
`nominal`: ningún incidente. Revisiones de evidencias en `demo`: 8 en el replay y 9 en directo (antes 12).

## Contrato
v1.3 (rompe, 25/11/2026): ver el encabezado de `contracts/eventos.md`. Quitado: API de tools, `wait_agent`, `waiting_agent`, `ToolSource`, `EventSource` y `TOOL_SOURCE_TO_ENVELOPE_SOURCE`. Añadido (aditivo): 8 tipos de `IncidentKind` (`BATTERY` fuera, nadie lo publicaba) e `IncidentUpdated.subject`.

## Paso 3 · Web
- **Ventana de reglas con las tablas congeladas.** `RulesDialog` lee `situation-tables-frozen.json` (13 tablas aprendidas y la regla de la situación: las 14 facetas) y, si el incidente dice que corrió con las tablas a mano (`IncidentUpdated.table` = `handwritten-video`), `situation-tables.json`; los ids de fila (`GI-01`…) se repiten entre los dos juegos, así que se elige el fichero por el nombre de la tabla (`rules.ts::pickRules`). Cada fila enseña su salida con la **confianza y la probabilidad** («spoofed · confirmed (p 0.96)») y, en el `title`, el respaldo del entrenamiento (variantes e instantes). Los tests de sincronía de los dos JSON siguen en el módulo (`test_tables_freeze`, `test_situation`).
- **Lectura de las tablas aprendidas** (`incidents.ts`, con pruebas): etiquetas de las 14 facetas y de todos sus estados, de las 35 entradas aprendidas (cocientes con los activos, edades en periodos), celdas `> N, null` («or no data»), rangos `(a..b]` y `not(null)`, umbrales con a lo sumo 2 decimales (venían con 15) y las banderas 0/1 (`mode_hold`…) como sí/no. Lo vi en las capturas del ensayo y lo corregí antes de repetirlo.
- **Tarjeta:** confianza (ya estaba) y `data-subject`; el historial usa el nombre del incidente (con `SOURCE_SILENT`, «Radar silent», no «Source silent»); contexto nuevo (`possible_cause`, `suspected_cause`, `telemetry_gap_s`, `battery_pct`); `UNDETERMINED` enseña «Hypothesis: none» hasta la E7d. **«Pending…» de la interpretación** sin plazo solo para los tipos de los que el asistente preparado ya ha escrito en la ejecución; para el resto, 8 s y nada (antes, cualquier incidente de un tipo sin texto —batería, fuente callada— se quedaba en «pending…» para siempre).
- **«Injected vs detected»:** una interferencia cuenta como vista por GPS degradado, sin fix o a estima; silenciar una fuente, por `SOURCE_SILENT` **con su sujeto** (el enlace, por enlace perdido o secuestro); la pérdida de GPS, por sin fix o a estima. Antes un fallo no se emparejaba nunca. Las dos vistas siguen funcionando (comprobado en el ensayo).
- Tests: web **85** (eran 77: +8), `pnpm typecheck` y `pnpm build` bien (la primera ejecución de `pnpm build` falló sin un error legible, tras el aviso de seguridad de Next.js 16.4.1 que ya estaba anotado; la repetición pasó).

## Paso 4 · Módulo antiguo y `platform_app.run`
- **Lo que quedaba del código antiguo ya se había retirado en el paso 1b con la lista aprobada** (§1b); en este paso solo he buscado referencias vivas y no queda ninguna en código, pruebas ni configuración (`ai_module.runtime|agent|config|testing`, `PENDING_E7C`, `/api/tools`, `wait_agent`, `tools/experiments`, `agent-assets-v13`). **Se conserva a propósito:** `agent/profiles.py` (lo necesita `serve.sh`), `agent-assets/`, `model-profiles/`, la dependencia `openai` (E7d), `decision/table.py` (lo ejecutan las tablas) y `export_dmn.py`.
- `platform_app.run` arranca el monitor nuevo (`--tables learned|handwritten`, `--assistant scripted|off`, `--platform URL`, `--no-ai`): `demo` (3 incidentes, 21 revisiones) y `nominal` (0) de principio a fin sin errores.
- **Documentos:** `CLAUDE.md` raíz (estructura, E6 marcada como retirada, E7c), `ai-module-py/CLAUDE.md` (reescrito: describe el monitor de situación), `platform/CLAUDE.md` (sin tools de datos ni «esperar al agente»), `web/CLAUDE.md`, `README.md` (reescrito: el monitor, sin vLLM como requisito), `docs/quien_decide_que.md`, `docs/mejoras_futuras.md`.
- **Quién decide qué, contrastado con el código:** el apartado nuevo de `quien_decide_que.md` (arriba del todo) sustituye a los apartados 1 a 6, que describían el módulo anterior y quedan como histórico. Cambia: la causa la ponen las tablas y no un modelo (ya no hay ningún caso en que la ponga el LLM); el secuestro lo decide el catálogo con causa y modo confirmados; la severidad y la confianza salen de la política y de las filas; el asistente no decide nada del incidente. Sin cambios: el simulador, los failsafes y el instructor.

## Paso 5 · Ensayo, capturas y guion
- **Ensayo con la web** (plataforma 8100, monitor, `pnpm dev` 3000; los lancé yo y los he parado: puertos 8000, 8100 y 3000 libres): `node scripts/capture.mjs video1` (`demo`, vista del alumno, pausas, pregunta al chat del monitor, informe y vista del instructor) y `video2` (`nominal`, modo interactivo, las dos órdenes del instructor con Confirm). Sin errores de página. Capturas en `results/capturas/e7c/video1/` (13) y `video2/` (8), con `capture_log.json` y los `.log` de salida.
- **Instantes nuevos** (solo anotados, sin ajustar nada): en `docs/fases/video-19-11-e7c.md`. Resumen: viento T+02:19 / 02:37 / 03:00; engaño T+03:22 / 04:12 / 04:33; enlace perdido T+06:12, secuestro T+06:28, recuperación T+06:53, cierre T+07:58; con las órdenes en `nominal`, viento T+01:59 / 02:40 / 02:49; «Injected vs detected» 7, 4 y 4 s.
- **Lo que se ve distinto:** la tarjeta ya no dice «viento por encima del límite 7 s» ni «desvío 29 m», sino cocientes con los activos; el secuestro lleva 208 m a la pausa de T+398 (el guion decía 288 m; el texto del chat, «more than 200 m», sigue siendo cierto).
- **Una cosa que hay que contar a quien mire la tarjeta del viento:** en el primer segundo la fila de causa dice «spoofed position» (la estación aún no ha registrado la ráfaga) y un segundo después «wind»; la tarjeta enseña las dos. Es de la tabla (E8), no se ha tocado.
- **Dos pasadas en `runs/`:** el ensayo deja ejecuciones en `runs/demo/<run_id>/` y `runs/nominal/<run_id>/` (no se versionan); `runs/<escenario>/` sin cambios.

## Tests
Contratos 134, plataforma 299, módulo de IA 167, herramientas `tools/situation` 5, web 85 (`pnpm typecheck` y `pnpm build` bien). `ruff check` limpio; `ruff format --check` solo marca `tools/e7a_gnss_example.py`, que no he tocado (viene de antes). `check_freeze` ok; los ficheros congelados (`features.py`, `tables_learned.yaml`, `situation_rule.*`, `tables_freeze.json`) sin cambios; `runs/<escenario>/` sin cambios.

## Qué propongo cambiar en la especificación
- `situation_rule.py` y `tables_freeze.json` deberían decir lo mismo de `margin_k` (1,0 frente a 0,5) en la próxima congelación.
- Anotar que el inventario de activos del monitor es único (`assets.yaml`) y que la evaluación debe crear el extractor con los activos de cada variante (el fallo de `tools/situation/lib.py` y de `hand_tables.py`).
- §6: k = 5 y m = 10 (el ⚠️ de k = 3 y m = 10 era del vídeo), con `WIND` y `LINK_DEGRADED` en 8; y el catálogo de 15 tipos con sus familias.
- Nada de la política de la causa dudosa cambia: se cumple tal cual.

## Para la E8 (resumen; el detalle en `docs/mejoras_futuras.md`)
`GPS_DEGRADED` en generalización (71 falsos en 115 h), `BATTERY_LOW` (la tabla de autonomía va por delante de la verdad), el nombre tardío o ausente de `HIJACK`, la causa «spoofed position» el primer segundo del viento, `hand_tables.py` con los activos de la variante, y el radar de `endurance` (8000 m frente a 6000).

## Problemas
- La primera ejecución de `pnpm dev` paró con el aviso de seguridad de Next.js 16.4.1 (`Reference: https://registry.npmjs.org/-/npm/v1/security/advisories/bulk … [ELIFECYCLE] Command failed with exit code 1`); la repetición arrancó. Ya estaba anotado en la E7a. No se actualiza Next.js.
- La primera ejecución de `pnpm build` falló (`exitCode: 1`, sin más detalle en la cola) y la segunda pasó. No lo he reproducido.
- **Instantánea limpia (regla 15):** la primera comprobación encontró una referencia a `docs/fases/e7c.md` en un comentario de `policy.yaml`; la corregí en el repo (ahora cita `tools/situation/calibrate.py`), repetí las dos instantáneas y las dos búsquedas salieron vacías (`snapshots/e7c/` con 653 ficheros y `snapshots-limpias/e7c/` con 598).
- Nada que haya pasado de 30 minutos.

## URLs consultadas
Ninguna: no he afirmado nada nuevo sobre librerías.

## Mensaje de commit propuesto
```
E7c steps 2-5: situation catalog, tracker and policy; web reads the frozen rules; retire the old module docs

- catalog (15 incident kinds), tracker (k = 5, m = 10 calibrated on validation), severity with
  escalation and the doubtful-cause policy; per-incident metrics and the calibration tools
  (tools/situation)
- fix the calibration tool: build the feature extractor with the assets of each variant
- web: rules window reads the frozen tables (and the hand-written ones when the monitor runs
  them), confidence and probability on every row, readable learned inputs, new incident kinds,
  "no hypothesis" for undetermined, pending text only for kinds the assistant writes about,
  injected-vs-detected for the new kinds
- contract v1.3: 8 new incident kinds and IncidentUpdated.subject; tools API and wait-for-agent
  removed
- docs: ai-module, platform, web, README, who-decides-what, future improvements and the video
  script annex with the new instants
```
