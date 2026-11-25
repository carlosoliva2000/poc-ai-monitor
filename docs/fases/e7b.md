# E7b · Datos y entrenamiento

Informe (pasos 0 a 5, con 2b y 2c; faltan la revisión de Carlos y la congelación, paso 5). Referencia: especificación del núcleo v2 (v1.1).

## Paso 0 · Fusión de `feature/experimental`
Hecha y con su commit (Carlos). Dos conflictos de texto (`contracts/eventos.md`, cabecera de versión: v1.0 final de `main` más la frase de la v1.1; `ai-module-py/CLAUDE.md`: bloque del monitor de situación). Esquemas regenerados (68, iguales a los de la fusión), `runs/` idéntico. Contratos 203 (+1 saltado), plataforma 348, módulo de IA 375 (+15 saltados), web 77, `ruff` limpio.

## Paso 1 · Generador de variantes por clase

### Qué hay
- `tools/training/manifests/e7b-v1.yaml`: manifiesto (semilla maestra 7011, 2400 variantes, cuotas por familia, rangos y combinaciones). Se versiona.
- `tools/training/variants.py`: muestrea cada variante (ruta al azar de 3–6 puntos, dron dentro de los rangos de §5, ruido del GPS, radar, estación, enlace, batería, viento, y una anomalía principal más, a veces, una segunda y una tercera), la genera con el simulador v2 **sin tocarlo** y escribe `events.jsonl.gz`, `states.jsonl.gz`, `scenario.yaml`, `assets.yaml` (posición y alcance del radar: lo que el monitor conocerá de antemano) y `meta.json`. `index.json` lleva la partición **por variante** (70/15/15, estratificada por familia). Todo sale de `zlib.crc32`, nunca de `hash()`; ficheros comprimidos con `mtime=0`.
- `tools/training/counts.py` (recuentos), `tools/training/examples.py` (gráficas de ejemplo) y `tools/training/tests/` (8 tests).
- Datos en `experiments/e7b/e7b-v1/` (217 MB, ignorado por `.gitignore`, no se ha tocado). Se regenera con `uv run --project platform python tools/training/variants.py`.

### Familias y cuotas
nominal 4 %, wind 7 %, spoofing 10 %, hijack 8 %, gps_loss 9 %, jamming 7 %, gps_degraded 5 %, link_degraded 7 %, link_mute 12 %, source_mute 18 % (una o dos fuentes), radar_range 5 %, battery 8 %. Un 38 % de las variantes tiene segunda anomalía y un 9 % tercera; la mitad se solapan con la primera. Un fallo no se solapa con otro de la misma fuente (la regla del generador), y los `unexplained` > 0 se descartan y se vuelve a muestrear (con otra semilla).

### Cambios sobre lo propuesto en el plan
- Los mínimos de 150/30/30 episodios por estado anómalo no eran alcanzables para los silencios de fuente: bajan a **60/15/15**.
- Se subieron las cuotas de `source_mute` (6 → 18 %), `link_mute` (6 → 12 %), `battery` (4 → 8 %) y `radar_range` (3 → 5 %), y el conjunto pasó de 1600 a 2400 variantes. Con `hold` al 35 % en la acción ante la pérdida de enlace.
- `max_duration_s` de cada variante = 1,3 × plan + 60 s: con `hold` el dron se quedaba esperando hasta el límite de 1800 s.
- Se regeneró tres veces (en cada una el recuento decidía la siguiente).

### Tamaño y tiempo
2400 variantes (2400 generadas, 433 intentos descartados por `unexplained` o por no validar), duración media 765 s, unos 1,9 M de instantes. Generador: 0.53 s por variante (máx. 2.6 s), 1269 s de CPU, **321 s de pared con 4 procesos**.

### Recuento (instantes / episodios; sin `n/a` ni `?`)
| Faceta | Estado | train | validation | test |
|---|---|---|---|---|
| gps.availability | normal | 1203316 / 2440 | 254749 / 519 | 258307 / 522 |
| gps.availability | no_data | 6035 / 129 | 1246 / 29 | 1292 / 27 |
| gps.availability | no_fix | 12317 / 303 | 2601 / 62 | 2804 / 62 |
| gps.quality | good | 1185059 / 2613 | 250814 / 556 | 255106 / 559 |
| gps.quality | degraded | 18257 / 370 | 3935 / 83 | 3201 / 69 |
| gps.integrity | reliable | 1187013 / 2635 | 251400 / 563 | 255038 / 561 |
| gps.integrity | spoofed | 16303 / 245 | 3349 / 53 | 3269 / 49 |
| radar.availability | normal | 1249861 / 2019 | 257909 / 435 | 264606 / 430 |
| radar.availability | no_data | 6929 / 139 | 1617 / 33 | 989 / 25 |
| radar.availability | out_of_range | 38790 / 234 | 8075 / 52 | 10117 / 59 |
| link.availability | connected | 1221668 / 2047 | 258596 / 439 | 262403 / 436 |
| link.availability | lost | 73912 / 475 | 9005 / 96 | 13309 / 95 |
| link.quality | good | 1213684 / 2200 | 256825 / 474 | 261108 / 465 |
| link.quality | degraded | 7984 / 191 | 1771 / 42 | 1295 / 32 |
| meteo.availability | normal | 1289390 / 1800 | 266385 / 384 | 274217 / 392 |
| meteo.availability | no_data | 6190 / 120 | 1216 / 25 | 1495 / 31 |
| battery.availability | normal | 1216422 / 2150 | 257360 / 463 | 260611 / 469 |
| battery.availability | no_data | 5246 / 112 | 1236 / 26 | 1792 / 33 |
| battery.level | normal | 1200219 / 2143 | 252959 / 462 | 256166 / 469 |
| battery.level | low | 12413 / 179 | 3409 / 46 | 3402 / 45 |
| battery.level | critical | 3790 / 169 | 992 / 45 | 1043 / 45 |
| battery.endurance | sufficient | 1194754 / 2265 | 251629 / 487 | 254775 / 499 |
| battery.endurance | cannot_reach_home | 21668 / 260 | 5731 / 60 | 5836 / 69 |
| environment.wind | calm | 727377 / 1142 | 150925 / 240 | 155920 / 249 |
| environment.wind | notable | 557749 / 1110 | 114570 / 230 | 117219 / 249 |
| environment.wind | beyond_limit | 10454 / 198 | 2106 / 37 | 2573 / 47 |
| drone.mode | mission | 1144966 / 1802 | 241178 / 387 | 244254 / 392 |
| drone.mode | failsafe_return | 37830 / 294 | 9426 / 69 | 10432 / 73 |
| drone.mode | failsafe_hold | 49215 / 76 | 9772 / 14 | 9370 / 13 |
| drone.mode | failsafe_land | 1927 / 162 | 528 / 41 | 521 / 41 |
| drone.mode | foreign_control | 61642 / 197 | 6697 / 37 | 11135 / 43 |
| drone.situation | on_route | 1203936 / 2451 | 254876 / 520 | 259149 / 533 |
| drone.situation | deviated | 85379 / 848 | 11467 / 171 | 15208 / 185 |
| drone.situation | returning | 6265 / 279 | 1258 / 56 | 1355 / 60 |
| drone.cause | foreign_control | 63139 / 198 | 6726 / 36 | 10278 / 43 |
| drone.cause | spoofed_position | 10541 / 198 | 1858 / 38 | 2154 / 39 |
| drone.cause | dead_reckoning | 4738 / 173 | 1212 / 33 | 977 / 36 |
| drone.cause | wind | 13226 / 540 | 2929 / 118 | 3154 / 127 |
| drone.cause | unexplained | 0 / 0 | 0 / 0 | 0 / 0 |

Por debajo del mínimo (60/15/15): solo `drone.mode=failsafe_hold` en validación (14) y prueba (13). `hold` dura hasta el final del vuelo, así que cada variante aporta un episodio largo: 21 000 instantes en pocos episodios. No hay ningún segundo `unexplained`.

### Ejemplos
`experiments/e7b/e7b-v1/examples/<variante>/` (copiadas a `results/`): `v0267` (engaño + pérdida de GPS solapados), `v0005` (interferencia + secuestro) y `v0109` (secuestro).

### Descartes (363 intentos) y decisiones de Carlos
Los 363 intentos descartados son **todos** por `unexplained` (una desviación sin causa en `states.jsonl`), ninguno por no validar: `battery` 126 (de 192 variantes), `link_mute` 114 (de 288), `jamming` 63 (de 168), `gps_degraded` 32 (de 120), `source_mute` 29 (de 432), `gps_loss` 20 (de 216), `link_degraded` 17 (de 168), `spoofing` 9 (de 240), `wind` 7, `hijack` 7, `radar_range` 5 y `nominal` 4. Es un **sesgo de selección** del conjunto: los árboles no ven las combinaciones que dejan al dron fuera de la referencia del modo sin causa (sobre todo batería baja y `link_mute` con `return`/`land`/`hold`, que el etiquetador del simulador no explica). El simulador no se toca; queda anotado en `docs/mejoras_futuras.md`.
Carlos acepta los mínimos de 60/15/15 episodios y `failsafe_hold` como está (14 episodios en validación y 13 en prueba, por debajo de 15).

### Tests (`uv run --project platform pytest tools/training/tests/test_variants.py`)
La variante es determinista (y otra semilla da otra); cuotas exactas; cada familia valida y respeta los rangos; sin fallos solapados de la misma fuente; partición por variante, completa y estable; **el conjunto sale igual byte a byte** al regenerarlo; qué ficheros deja cada variante.

## Paso 2 · Características y entrenamiento

### Revisión del código de la rama (lo que se hizo con `situation/`)
`features.py` **se reescribe** (misma interfaz `push`/`flush`, una `FeatureRow` con `values` por nombre y las propiedades que usa el monitor a mano); `monitor.py` y `__main__.py` solo se tocan en lo mínimo. Lo que no valía:
- **`GnssReference`** (referencia de C/N0 y AGC congelada mientras la tabla dice «no fiable») depende de la salida de la tabla: con otras tablas saldrían otras características y no se puede entrenar. Pasa a `monitor.py` (sigue alimentando la tabla a mano, provisional hasta la E7c). Los árboles usan dos referencias que no dependen de nada que decida el monitor: la mediana de los primeros 60 s con receptor y la de los 5 min anteriores al último minuto.
- **Frescura común a toda la telemetría** (con el GPS callado y el autopiloto llegando, el último GPS contaba como fresco para siempre): ahora **por fuente** (`FRESH_S`).
- **La «media de tres trazas» del radar** añadía la misma traza cada segundo (el radar publica cada 2 s) y no se vaciaba con el radar callado: ahora es la media de las últimas **2 trazas reales** con caducidad de 6 s.
- **Filas solo en los segundos con eventos**: ahora **una fila por segundo** (los segundos sin eventos repiten el estado con las edades creciendo), que es lo que alinea con `states.jsonl`.
- **Sin referencia del modo** (la etiqueta mide contra el tramo a casa o el punto de espera): ahora la hay.
- `WIND_LIMIT_MPS`, `wind_high_s`, `telemetry = tele_gap_s < 3`, `DRIFT_FACTOR`, `UNDETERMINED_QUIET_S`, la confianza fija, el `> 50` del secuestro y los umbrales 4/−2 dB, 25/15 m (medidos sobre `demo` y `nominal`) son del monitor, el seguidor y la política: **E7c, no se tocan** (`WIND_LIMIT_MPS` y la referencia se mudan a `monitor.py` con su comentario de provisional).
- **`__main__.py` ya no pide el plan por HTTP** (`fetch_mission_plan` fuera; regla de la especificación §2: el monitor lee solo del bus): el plan sale solo de `MissionPlanned`. **Limitación conocida:** si el monitor arranca a mitad de un vuelo no tiene el plan y no publica nada hasta el siguiente reinicio. Un test comprueba que el proceso no usa HTTP.
- **Efecto en `demo`** (por la fila por segundo; los tests de `test_situation` pasan con un único aserto ajustado, la distancia final del secuestro, que ahora acaba en 444 m y no en 597 m porque las revisiones salen en otros instantes): `WIND` abre a T+02:18 (igual), `GPS_SPOOFING` a T+03:20 (igual; su refresco por el radar pasa de T+03:31 a T+03:38), `LINK_LOSS` a T+06:12 (antes T+06:14) y `HIJACK` a T+06:20 (antes T+06:24). `nominal`, sin incidentes. **Las horas del guion del vídeo cambian**; el guion y las capturas de `video-19-11.md` ya no valen al segundo.

### Características (`situation/features.py`, 56 columnas, `FEATURES`)
- **Edades** (`age_*`) de las siete fuentes y `tele_gap_s`; valores de una fuente solo mientras son recientes (si no, `None`).
- **Receptor:** `gps_fix_3d`, `gps_sats`, `gps_hdop`, `gps_hacc_m`, `cn0_dbhz`, `agc_db`, y `cn0/agc_vs_base_db` y `cn0/agc_vs_slow_db`.
- **Distancias a la referencia del modo** (tramo de la misión, tramo a casa en `failsafe_return`, punto de espera en `hold`/`land`): `gps_dev_m`, `radar_dev_m` (media de 2 trazas), tendencia a 10 s y máximo a 30 s de cada una.
- **Retraso del tramo y su ritmo** con GPS y con radar (`*_delay_s`, `*_delay_rate`: `t` menos el instante previsto —los `eta_s` de `MissionPlanned`— para ese avance).
- **Discrepancia GPS–radar:** distancia, media de 3 y **CUSUM** (holgura fija de 12 m).
- **Autopiloto y viento:** modo (3 indicadores), velocidad respecto al aire y sobre el suelo y su diferencia, ángulo morro–rumbo, viento estimado (y media de 5 s), innovación (y máximo de 10 s), viento de la estación, su diferencia con el estimado y la de procedencias.
- **Enlace:** pérdida, RSSI, latencia. **Radar:** velocidad y `radar_range_ratio` (distancia del dron al radar entre su alcance, con la posición que el monitor conoce de antemano: `situation/assets.yaml`; **nunca coordenadas sueltas**, un test lo comprueba).
- **Batería:** carga, potencia, tiempo restante, distancia a casa, `home_time_ratio` (tiempo para volver al ritmo de crucero entre el tiempo restante) y consumo por km (60 s).
- **Qué falta de la lista de §6:** la energía para volver **con el viento** (se usa el ritmo de crucero, sin viento) y la «velocidad aire frente a suelo» sale como diferencia sin proyectar el viento. Una sola implementación (la misma en directo y fuera de línea), sin `t` absoluto, sin id de variante, sin nada de la verdad.
- **Tests** (`ai-module-py/tests/test_features.py`, 11): una fila por segundo y edades; distancia al tramo y cambio de tramo; referencia de `failsafe_return`; retraso del tramo y su ritmo; CUSUM; referencias del receptor; `radar_range_ratio` y sin coordenadas; el conjunto de columnas; **sin fugas** (eventos de otros dominios y el mismo vuelo 1000 s más tarde dan las mismas características); un `events.jsonl` real entero frente a evento a evento; el proceso solo lee del bus.
- **En directo = fuera de línea** (`tools/training/live_check.py`): la plataforma en directo (puerto 8100, a 16×) pasada por el `FeatureExtractor` evento a evento da **filas idénticas valor a valor** a las de `events.jsonl` en `demo` (572 filas), `faults` (442) y `endurance` (743). Hay una pequeña diferencia posible fuera de la prueba: el entrenamiento guarda las matrices en `float32` y el monitor en directo calcula en `float64` (solo importa a menos de 1e-7 de un umbral).

### Entrenamiento (`tools/training/{features,models,train}.py`)
- Matrices por partición (`features/<partición>.npz`, 40 s): 1 294 188 filas de entrenamiento, 267 304 de validación y 275 409 de prueba × 56 características. Las etiquetas salen de `states.jsonl` del mismo segundo; `n/a` y `?` enmascarados.
- Un `DecisionTreeClassifier` por faceta: `class_weight="balanced"`, `min_samples_leaf` 100 instantes, profundidad 6 u 8 y `ccp_alpha` en {0, 2e-4, 5e-4, 1e-3, 2e-3, 5e-3}. **Poda por episodios**: las hojas con menos de **5 variantes distintas** (una variante cuenta si aporta ≥ 3 instantes de la clase de la hoja) se colapsan en su padre, auditando con todo el entrenamiento. Elección en validación: F1 macro; entre los que quedan a menos de **0,01** del mejor, el de menos hojas (con 0,003 salían árboles de hasta 47 y 53 filas; la rejilla completa está en `step2-tol003.md`).
- **Submuestreo de los instantes normales** (solo entrenamiento), probado: con un tope de 40 000 por clase el entrenamiento era más rápido (140 s) pero **`gps.integrity` empeoraba en validación** (F1 macro 0,967 frente a 0,981 con todo; `drone.cause` y `link.quality` iguales). Se entrena **sin submuestrear** (16 min con 8 procesos). El bosque (100 árboles, `balanced_subsample`) sí usa un tope de 100 000 por clase.
- El árbol que se ejecuta es **propio** (`models.Tree`, copiado del de scikit-learn con el lado de los valores que faltan): predice igual que scikit-learn, también con NaN (test).
- **Valores que faltan en scikit-learn** (regla 8): el árbol los admite desde la 1.3 y el bosque desde la 1.4 (<https://scikit-learn.org/stable/auto_examples/release_highlights/plot_release_highlights_1_3_0.html> y <https://scikit-learn.org/stable/auto_examples/release_highlights/plot_release_highlights_1_4_0.html>). En entrenamiento cada corte prueba mandar todos los NaN a la izquierda o a la derecha, y si no hubo NaN en entrenamiento van al hijo con más muestras (<https://scikit-learn.org/stable/modules/tree.html>, §1.10.8). **⚠️ El atributo `tree_.missing_go_to_left`** (cómo se exporta el lado) **no aparece en esas páginas**: lo he comprobado en la versión instalada (1.9.1) con un test de que el árbol propio predice igual que scikit-learn con NaN y de que un NaN va donde mandaba el entrenamiento. scikit-learn también parte «NaN frente a no NaN» con umbral `inf`: la conversión lo trata (ver el paso 3).

## Paso 3 · Del árbol a la tabla de reglas (`tools/training/tree_to_table.py`)
- Formato de `situation/tables.yaml` (política FIRST, subconjunto FEEL de `decision/table.py`): una fila por hoja con **una condición por característica** (`<= a`, `> a`, `(a..b]`, con `null` si llegan los NaN, `not(null)` si no); salidas `state`, `probability` (pureza de la hoja en entrenamiento), `instants`, `variants` y `episodes`. La hoja normal con más instantes es la **fila por defecto**, al final y sin condiciones. Candidatas en `tools/training/candidates/e7b-v1.yaml` (se versiona; el evaluador de la E6 las carga).
- **Cobertura** (comprobación aparte de la conversión): sin solapes entre filas (cajas disjuntas) y sin huecos (resta de cajas con la caja real de la fila por defecto): **14 tablas, 0 solapes, 0 huecos**.
- **La tabla da lo mismo que el árbol** en los 267 304 instantes de validación, en las 14 facetas (evaluador vectorizado, comprobado contra el motor de la E6 en una muestra).
- **Error encontrado y corregido:** una condición «cualquier valor menos NaN» se escribía como `-` (cualquier valor), así que en `drone.situation` una fila solapaba con su hermana solo-NaN (50 instantes de validación distintos). Ahora es `not(null)` y hay un test de regresión.
- Exportación a XML de DMN: **no hecha** (existe `tools/decision/export_dmn.py`, de la E6, para otro formato de tabla; queda para el paso 5 si se quiere).
- **Tests** (`tools/training/tests/test_models.py`, `test_tree_to_table.py`, 13): árbol propio = scikit-learn con NaN, poda por episodios, auditoría de instantes/variantes/rachas, métricas y bootstrap, ninguna característica es el tiempo ni la variante, tabla = árbol, fila por defecto, números sin exponente, cobertura (detecta solapes y huecos), la regresión de `not(null)`.

## Paso 4 · Informe de las tablas candidatas
Informe completo, con las filas legibles y su soporte, las matrices de confusión, la calibración y los retrasos de detección: `experiments/e7b/e7b-v1/report/e7b-tablas.md` (copia en `results/experiments/e7b/`). F1 macro en **prueba** con IC 95 % por bootstrap de variantes (400 remuestreos):

| Faceta | Filas | Prof. | Árbol = tabla | Bosque (100 árboles) | Tabla a mano |
|---|---|---|---|---|---|
| gps.availability | 3 | 2 | 0,959 [0,931; 0,978] | 0,986 [0,976; 0,995] | — |
| gps.quality | 2 | 1 | 0,944 [0,925; 0,957] | 0,974 [0,962; 0,982] | — |
| gps.integrity | 4 | 3 | 0,972 [0,949; 0,990] | 0,999 [0,998; 1,000] | 0,997 [0,993; 0,999] |
| radar.availability | 3 | 2 | 0,967 [0,926; 0,988] | 0,975 [0,941; 0,990] | — |
| link.availability | 2 | 1 | 0,998 [0,996; 0,999] | 0,999 [0,997; 1,000] | 0,992 [0,988; 0,994] |
| link.quality | 3 | 2 | 0,879 [0,831; 0,913] | 0,932 [0,902; 0,950] | — |
| meteo.availability | 2 | 1 | 0,949 [0,939; 0,959] | 0,946 [0,934; 0,957] | — |
| battery.availability | 2 | 1 | 0,880 [0,843; 0,907] | 0,900 [0,868; 0,921] | — |
| battery.level | 5 | 4 | 0,959 [0,953; 0,964] | 0,959 [0,951; 0,966] | — |
| battery.endurance | 23 | 6 | 0,888 [0,859; 0,914] | 0,896 [0,869; 0,919] | — |
| environment.wind | 26 | 6 | 0,896 [0,861; 0,918] | 0,891 [0,859; 0,913] | 0,911 [0,883; 0,933] |
| drone.mode | 10 | 8 | 0,805 [0,757; 0,839] | 0,913 [0,886; 0,934] | — |
| drone.situation | 26 | 8 | 0,845 [0,798; 0,887] | 0,923 [0,893; 0,947] | 0,655 [0,636; 0,670] |
| drone.cause | 22 | 8 | 0,938 [0,917; 0,957] | 0,957 [0,936; 0,975] | — |

- **Frente a la tabla a mano** (diferencia emparejada, mismas variantes remuestreadas): `drone.situation` **+0,189** [+0,146; +0,231] (la tabla a mano, con umbrales de `demo`, no generaliza); `link.availability` +0,006 [+0,004; +0,009]; `environment.wind` −0,015 [−0,045; +0,013] (sin diferencia); `gps.integrity` **−0,025** [−0,051; −0,008] (la de mano es mejor: su referencia congelada mientras dura el engaño usa la propia salida de la tabla, que los árboles no pueden usar).
- **Frente al bosque:** pierden sobre todo `drone.mode` (0,805 frente a 0,913), `drone.situation` (0,845 frente a 0,923) y `link.quality`; en el resto la legibilidad cuesta menos de 0,03 o nada.
- **Filas y soporte:** 2 a 26 filas por tabla, profundidad máxima 8; **todas las hojas las sostienen al menos 5 variantes** (mínimos de 5 a 456 por tabla; en `step2.md` y, fila a fila, en `e7b-tablas.md`).
- **Calibración** (filas de estados anómalos de todas las facetas, prueba): prevista 0,21 / 0,53 / 0,80 / 0,96 / 0,995 frente a observada 0,19 / 0,61 / 0,75 / 0,95 / 0,99 en los tramos [0, 0,5), [0,5, 0,6), [0,6, 0,9), [0,9, 0,99), [0,99, 1]. **Cortes propuestos** (elegidos en validación banda a banda): **confirmado ≥ 0,9** y **probable ≥ 0,6**, los de la especificación; en prueba aciertan 0,983, 0,752 y, por debajo (posible), 0,267.
- **Retraso de detección** (prueba; mediana / p90 / máx., con 1 y con 3 instantes seguidos): engaño 0/0/3 s y 2/2/12 s (49 de 49 episodios); enlace perdido 0 s y 2 s (95 de 95); viento fuera de límites 0/10/36 s (46 de 47); desviado 0/1/6 s y 2/4/11 s (182 de 185 con k = 1); causa: control ajeno 1/8/23 s (41 de 43), engaño 0/0/4 s, navegación a estima 0/0/0 s, viento (ver el informe completo).
- **`demo` y `nominal` con las tablas aprendidas** (GPS, enlace, viento y situación aprendidas; la tabla de tipo de incidente, el seguidor y la política, los del vídeo): `demo` da los mismos diez cambios de incidente que con las tablas a mano en ±4 s (`WIND` abre a T+02:14 frente a T+02:18, cierra a T+03:02 frente a T+03:00; `GPS_SPOOFING` a T+03:20 igual; `LINK_LOSS` a T+06:10 y `HIJACK` a T+06:20); `nominal`, ningún incidente.
- **Ficheros de revisión** (`tools/training/review/<faceta>.yaml`, 14): cada fila en texto legible, con soporte en entrenamiento, probabilidad y acierto en validación (no en prueba); solo se pueden tocar `reject` (la fila se quita y su región pasa a la fila por defecto) y `round_to` por umbral.
- **Filas que Carlos probablemente querrá mirar** (absolutos que no parecen físicos): `drone.situation` DS-03 usa `cn0_dbhz <= 47,9`; `gps.integrity` GI-01 usa C/N0 y AGC absolutos (`agc_db <= -1,3` y `cn0_dbhz > 36,85`), no las referencias relativas.

## Dependencias nuevas (regla 8)
Grupo `train` de `ai-module-py` (el monitor en directo no las necesita): **scikit-learn 1.9.1** (BSD-3-Clause; <https://scikit-learn.org/stable/install.html>: «© Copyright 2007 - 2026, scikit-learn developers (BSD License)»), y las que trae: numpy 2.5.5 (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0), scipy 1.18.1 (BSD), joblib 1.6.0 (BSD-3-Clause), threadpoolctl 3.8.0 (BSD-3-Clause) y narwhals 2.29.0 (MIT). **⚠️** Las licencias de las cinco últimas las he leído de los metadatos de los paquetes instalados: no he podido confirmarlas en sus páginas oficiales (la consulta fue denegada). Sin GPU.

## Cambios que propongo en la especificación
- §6: una **fila por segundo**, y las características concretas (lista arriba); el monitor **no** usa un `fetch_mission_plan` HTTP.
- §5: el **submuestreo** de los instantes normales no sirve para `gps.integrity`; poda por episodios (mínimo 5 variantes por hoja) y tolerancia de 0,01 de F1 para elegir el árbol más pequeño.
- §5: los árboles **no pueden** usar la referencia de C/N0 del vídeo (circular); lo sustituyen dos referencias independientes.
- §4: `unexplained` aparece en el 13 % de los intentos de muestreo (363 de 2763) (sobre todo con batería baja y fallos del enlace): conviene revisar el etiquetador en la E9.

## Paso 2b · Que las tablas generalicen (e7b-v2)
Pedido de Carlos antes de revisar: las tablas de e7b-v1 solo valían para el Matrice 300 y los sensores de `demo` (unidades absolutas, C/N0 y AGC constantes, señales sin relación física en las filas complejas). e7b-v1 se mantiene para comparar; todo lo nuevo es **e7b-v2** (`experiments/e7b/e7b-v2/`, tablas en `tools/training/candidates/e7b-v2.yaml`).

### 1. Características relativas (`situation/features.py`, mismo código en directo y fuera de línea)
Se **añaden** al final de `FEATURES` (de 56 a 90 columnas; las absolutas de v1 siguen calculándose para poder evaluar las tablas de v1, pero las listas de v2 casi no las usan):
- **Antigüedad en periodos** de cada fuente (`age_*_p`, `tele_gap_p` con las fuentes rápidas del paquete); **la frescura de un dato es ahora 1,5 periodos de su fuente** (antes, segundos fijos).
- **Viento** estimado y de la estación entre `wind_limit` y entre `max_airspeed`; **velocidades** respecto a `max_airspeed` y al crucero.
- **Desviaciones en múltiplos del error esperado**: GPS (σ = `h_acc`/√2, que no cambia con el engaño; sin receptor, el σ nominal), radar (σ0 + σ/km × distancia de esa traza), GPS–radar (σ combinada, media y CUSUM con holgura de 2σ), innovación en σ y tendencias en fracción del crucero.
- **C/N0 y AGC frente a la referencia nominal del receptor** (más las de v1 frente a su propia historia, que ya eran relativas) y enlace frente a su línea base (latencia en cociente, RSSI en dB).
- **Absolutas que se conservan** (lista cerrada `ABSOLUTE_OK` en `allowed.py`, con un test): porcentaje de batería; los metros de «desviado/en ruta» (25/15 m, que es la definición de la etiqueta); `h_acc`, `hdop`, `sats` y fix (lo que dice el receptor de sí mismo); latencia y pérdida de paquetes con que se define «enlace degradado», y el viento en m/s **solo en `environment.wind`** (la etiqueta «notable» es 5 m/s absolutos: decisión operativa del etiquetador, no del dron; ver «Decisiones»).
- Tests (`test_features.py`, 9 nuevos): edades y frescura en periodos, invariancia al escalar el dron (el mismo viento relativo da la misma característica con otro límite), σ del GPS y del radar, C/N0 nominal, línea base del enlace, activos antiguos con valores por defecto y `tools/training/tests/test_features_builder.py` (cada variante se mide con **sus** activos). Error encontrado en el camino: `features.variant_assets` solo leía el radar y las primeras matrices se calcularon con los activos de referencia; se detectó antes de entrenar y se recalculó todo.

### 2. Configuración de los activos (`situation/assets.yaml`)
El monitor la conoce de antemano (en CITADEL saldrá del inventario) y **solo entra en las características a través de cocientes**: `drone` (`max_airspeed_mps` 17, `wind_limit_mps` 12, `cruise_mps` 15), `periods_s` (`gps` 1, `radar` 2, `link` 5, `meteo` 10, `battery` 10; el receptor y el autopiloto van con el GPS), `gps.sigma_m` (σ nominal 1,53), `radar` (`x`, `y`, `max_range_m`, `sigma0_m` 5, `sigma_per_km_m` 2) y `gnss` (`cn0_nominal_dbhz` 45, `agc_nominal_db` 0). Los valores del fichero son los de `demo`. **Cada variante escribe el suyo** (`variants/<v>/assets.yaml`); los ficheros antiguos (solo radar) se cargan con los valores por defecto.

### 3. Rangos de e7b-v2 (`tools/training/manifests/e7b-v2.yaml`; solo parámetros de las variantes, sin tocar la física)
| Parámetro | v1 | v2 |
|---|---|---|
| `max_airspeed` | 17 fijo | **10–23 m/s** |
| `wind_limit` | 12 fijo | **0,6–0,85 × `max_airspeed`** |
| crucero | 8–15 m/s | **0,5–0,9 × `max_airspeed`** |
| σ GPS (Gauss-Markov / blanco) | 0,8–2,5 / 0,1–0,5 m | **0,5–3,0 / 0,1–0,8 m** |
| radar σ0 / σ por km | 5 fijo / 1–4 | **2–10 m / 0,5–5 m/km** |
| periodos GPS, radar, enlace, estación, batería | 1, 2, 5, 10, 10 s | **{0,5; 1; 2}, {1; 2; 4}, {2; 5; 10}, {5; 10; 20}, {5; 10; 20} s** |
| viento base | 0–8 m/s | **0–0,8 × `wind_limit`** |
| episodios de viento | 5–12 / 12–17 / 17–24 m/s | **notable: 5 → `wind_limit`; por encima del límite sin deriva: `wind_limit` → `max_airspeed`; con deriva: 1–1,4 × `max_airspeed`** (cada variante respecto a su dron) |
| C/N0 y AGC nominales | 45 / 0 (constantes del simulador) | **igual: ver «Pendiente de tu visto bueno»** |
El resto (cuotas, combinaciones, rutas, emisores, fallos) como en v1. Semilla 7012, 2400 variantes en 178 s (0,58 s por variante, 8 procesos); 289 intentos descartados por `unexplained` (`battery` 72, `link_mute` 58, `jamming` 55, `gps_degraded` 23, `source_mute` 20 y el resto menos de 15). Un parámetro que existía y solo tenía un valor: los **periodos** (`period_s`, múltiplos de 0,1 s) y las σ; ninguno requirió tocar el simulador.

### Recuento de e7b-v2 (`experiments/e7b/e7b-v2/counts.md`)
1 680 variantes de entrenamiento, 359 de validación y 361 de prueba (1,42 M, 0,29 M y 0,31 M de instantes). Se cumplen los mínimos de 60/15/15 episodios por estado anómalo **salvo `drone.mode=failsafe_hold` en validación (13 episodios)**, como en v1. Duración media 841 s (vuelos más lentos).

### 4. Entradas permitidas por faceta (`tools/training/allowed.py`; justificadas una a una en `report/inputs.md`)
Cada árbol, y el bosque de referencia, solo ve su lista (de 1 a 22 características); un test comprueba que todas existen, que están justificadas y que ninguna es absoluta salvo las de `ABSOLUTE_OK`. Resumen:
| Faceta | Entradas (qué señal informa y por qué) |
|---|---|
| gps.availability | `age_gps_p`, `age_gnss_p` (fuente callada), `gps_fix_3d`, `gps_sats`, `gps_hdop` (sin fix) |
| gps.quality | `gps_hacc_m` (la etiqueta está en metros), `gps_hdop`, `gps_sats`, `innovation_max10_sigma` |
| gps.integrity | C/N0 y AGC frente al nominal, a la línea base y a la referencia lenta; GPS–radar en σ (media y CUSUM); viento estimado − estación |
| radar.availability | `age_radar_p`, `radar_range_ratio` |
| link.availability | `link_loss_pct`, `tele_gap_p`, `age_link_p` |
| link.quality | pérdida y latencia (la definición), latencia y RSSI frente a la línea base, RSSI |
| meteo / battery.availability | `age_meteo_p` / `age_battery_p` |
| battery.level | `battery_pct` |
| battery.endurance | `home_time_ratio`, `battery_pct`, viento/`max_airspeed`, velocidad/crucero |
| environment.wind | viento estimado y de la estación entre `wind_limit` (y su media), `age_meteo_p`, y el viento en m/s para el umbral de 5 |
| drone.mode | `mode_*` y edad del autopiloto, `link_loss_pct`, desviación del radar en σ (máximo, ritmo) |
| drone.situation | desviación en m (la definición) y en σ, máximos y ritmo, edades, modos y las señales de que la causa continúa (viento, C/N0, AGC, enlace, fix) |
| drone.cause | enlace y telemetría, radar, GPS–radar, C/N0 y AGC, viento, `airspeed_over_max`, `speed_gap_over_max`, innovación |
**Revisión de una lista tras ver resultados (a declarar):** la de `drone.situation` salió con F1 macro de validación 0,73 y la clase `returning` con precisión 0,26; esa clase se define por «ya no hay causa activa y el dron sigue fuera», así que añadí las señales de causa activa (siete entradas, con su justificación) y reentrené (0,764 de validación). El resto de listas no se tocó. Al decidirlo ya había visto el resumen de prueba de esa primera pasada (`step2-first-lists.json`), así que la elección **no es limpia**: se declara.

### Por qué en v1 salieron árboles de profundidad 8
La rejilla de v1 era {6, 8} y la regla elegía, entre los árboles a menos de 0,01 de F1 del mejor, el de menos hojas. En `drone.situation` los de profundidad 6 no pasaban de 0,770 de validación y el de 8 llegaba a 0,794, así que el de 6 quedaba fuera de la tolerancia; `drone.mode` (0,770 → 0,797), `drone.cause` y `battery.endurance` iguales. Es decir: con las características absolutas y sin relación física hacía falta más profundidad para compensarlas. **En v2 la rejilla es {4, 5, 6}** (profundidad ≤ 6) con las mismas poda por episodios (mínimo 5 variantes por hoja) y tolerancia: salen profundidades de 1 a 6 y de 2 a 16 filas (la causa, 14).

### 5. `drone.cause`: qué hacer con lo dudoso
Antes, la fila por defecto era la hoja mayor, `foreign_control`: cualquier caso que no encajara acababa en secuestro. Ahora:
- **Sin clase normal no hay hoja por defecto**: todas las hojas llevan sus condiciones y la fila por defecto es un **`unexplained` al que no llega ninguna muestra** (el árbol cubre todo el espacio; el cubrimiento se comprueba aparte y no cuenta esa fila).
- **Cada fila lleva una salida `confidence`** (`confirmed` ≥ 0,9, `probable` ≥ 0,6, `possible` por debajo; en prueba aciertan 0,978 / 0,726 y, por debajo de 0,5, 0,248) además de `probability`.
- **Propuesta para la política de la E7c** (no se implementa aquí): una causa con confianza `possible` sale como **«sin determinar»**; un incidente `HIJACK`/control ajeno solo se abre con una fila `confirmed` (con `probable` se queda en «enlace perdido» con la sospecha anotada) y la severidad no sube por una causa `possible`. En la tabla actual, las filas de causa con probabilidad < 0,6 son tres (`wind` 0,45, `spoofed_position` 0,44 y `dead_reckoning` 0,55) y ninguna es `foreign_control`; las de `foreign_control` valen 0,83–1,0.

### Resultados: las 14 tablas de v2 frente a v1 y al bosque (prueba de v2; F1 macro, IC 95 % por bootstrap de variantes)
Informe completo, con filas, soporte, calibración, retrasos y `demo`/`nominal`: `report/e7b-tablas.md`. Comparación: `report/generalization.md`.
| Faceta | Filas (prof.) | Tabla v1 | **Tabla v2** | Bosque v2 |
|---|---|---|---|---|
| gps.availability | 4 (3) | 0,665 | **0,976** [0,955; 0,989] | 0,972 |
| gps.quality | 4 (2) | 0,912 | **0,987** [0,980; 0,991] | 0,980 |
| gps.integrity | 6 (4) | 0,964 | 0,961 [0,933; 0,980] | 0,985 |
| radar.availability | 3 (2) | 0,668 | **0,988** [0,968; 0,996] | 0,983 |
| link.availability | 2 (1) | 0,733 | **0,998** [0,997; 0,999] | 0,998 |
| link.quality | 4 (2) | 0,884 | 0,930 [0,892; 0,956] | 0,899 |
| meteo.availability | 2 (1) | 0,496 | **0,936** [0,917; 0,950] | 0,936 |
| battery.availability | 2 (1) | 0,485 | **0,828** [0,770; 0,868] | 0,828 |
| battery.level | 4 (3) | 0,938 | 0,918 [0,907; 0,929] | 0,921 |
| battery.endurance | 16 (6) | 0,869 | 0,872 [0,840; 0,900] | 0,878 |
| environment.wind | 7 (5) | 0,680 | **0,879** [0,844; 0,904] | 0,876 |
| drone.mode | 7 (4) | 0,815 | 0,816 [0,798; 0,833] | 0,845 |
| drone.situation | 11 (4) | 0,821 | 0,737 [0,699; 0,786] | 0,813 |
| drone.cause | 14 (6) | 0,925 | 0,920 [0,895; 0,940] | 0,948 |
- **Mejoran mucho** las de disponibilidad (en v1 las edades estaban en segundos y con periodos distintos fallaban) y `environment.wind` (+0,20). **Empatan** `gps.integrity`, `battery.*`, `drone.mode` y `drone.cause` con tablas **mucho más pequeñas** (v1: 22–30 filas de profundidad 8 en la causa y la situación).
- **Pierde `drone.situation`** (−0,084 frente a v1; el bosque con las mismas entradas llega a 0,813): la clase `returning` depende de la historia de la causa y con entradas relativas y profundidad ≤ 4 la tabla se queda en 11 filas. Si se quisiera más, el camino es más profundidad (6) o la lista (p. ej. retraso del tramo), pero hay que decidirlo con validación, no con prueba.
- **Cortes de confianza** (elegidos en validación): 0,9 y 0,5; se mantienen **0,9 y 0,6** (los de la especificación), con 0,978 / 0,726 y 0,248 (por debajo de 0,5) en prueba.
- `demo` con las tablas de v2 (GPS, enlace, viento y situación; resto del vídeo): los mismos diez cambios que el vídeo en ±5 s (viento T+02:22…03:03, engaño T+03:20, secuestro T+06:10→06:20); `nominal`, ningún incidente.

### 6. Prueba de generalización (`experiments/e7b/e7b-gen/`, 600 variantes, no se usa para decidir nada)
Drones y sensores **fuera** de los rangos de entrenamiento (`tools/training/manifests/e7b-gen.yaml`): `max_airspeed` de 7,5–8,5 y de 27–29 m/s, σ del GPS de 0,2–0,4 y de 3,3–3,8 m, σ0 del radar de 0,5–1,5 y de 12–15 m, σ por km de 0,1–0,4 y de 6–8, periodos de {0,2; 3}, {0,5; 8}, {1; 20}, {2; 40} y {2; 40} s. F1 macro (la tabla de v1 con las mismas características absolutas que antes):
| Faceta | Tabla v1 | **Tabla v2** | Bosque v2 |
|---|---|---|---|
| gps.availability | 0,601 | **0,953** | 0,949 |
| gps.quality | 0,532 | **0,774** | 0,647 |
| gps.integrity | 0,913 | 0,922 | 0,740 |
| radar.availability | 0,600 | **0,978** | 0,971 |
| link.availability | 0,591 | **0,995** | 0,994 |
| link.quality | 0,871 | 0,914 | 0,861 |
| meteo.availability | 0,388 | **0,682** | 0,682 |
| battery.availability | 0,410 | **0,659** | 0,659 |
| battery.level | 0,907 | 0,886 | 0,886 |
| battery.endurance | 0,551 | **0,872** | 0,886 |
| environment.wind | 0,565 | **0,867** | 0,865 |
| drone.mode | 0,781 | 0,808 | 0,839 |
| drone.situation | 0,622 | 0,612 | 0,699 |
| drone.cause | 0,868 | 0,882 | 0,900 |
- Las tablas de v2 **casi no pierden** al salir de los rangos (de la prueba de v2 a la generalización: viento 0,879 → 0,867, causa 0,920 → 0,882, enlace y radar iguales); las de v1 caen en las ocho facetas que dependen de periodos o de unidades del dron. **El bosque, con las mismas entradas, generaliza peor** en `gps.integrity` (0,985 → 0,740) y `gps.quality`: una ventaja de la tabla pequeña.
- Peor caso: **`drone.situation` con 28 m/s** (0,582 la tabla v2, 0,653 el bosque) y `environment.wind` con 8 m/s (0,708, solo ~25 variantes: el IC es ancho, [0,544; 0,772]). `meteo` y `battery.availability` bajan porque con periodos de 40 s la fuente tarda 60 s en considerarse callada (1,5 periodos) y la etiqueta empieza con el suceso: es retraso de detección, no un error de la tabla.
- Los grupos de 8 y de 28 m/s por faceta (viento, modo, situación, causa) están en `generalization.md`.
- **Qué no mide:** el C/N0 y el AGC nominales no varían (ver abajo); el simulador, el etiquetador y los umbrales operativos (25/15 m, 5 m/s, 15/7 % de batería, 100 ms) son los mismos.

### Pendiente de tu visto bueno: C/N0 y AGC nominales variables (no tocado)
Hoy son constantes del código (`sensors.GNSS_CN0_NOMINAL_DBHZ = 45.0` en `generator/sensors.py`; el AGC nominal es 0 y la lectura es `d_agc + ruido`). **Cambio mínimo propuesto** (aditivo; con los valores por defecto `runs/` sale byte a byte igual):
1. `contracts/python/src/poc_contracts/scenario.py`, `GpsConfig`: `cn0_nominal_dbhz: float = Field(default=45.0, gt=0)` y `agc_nominal_db: float = 0.0`; `contracts/eventos.md` (YAML), esquemas exportados y `scenarios/README.md`.
2. `platform/src/platform_app/generator/receiver.py` (líneas 106–107): `cn0 = max(5.0, gps.cn0_nominal_dbhz + d_cn0 + ruido)` y `agc = gps.agc_nominal_db + d_agc + ruido`, y `simulator.py:821` (la verdad), con `config.sensors.gps.cn0_nominal_dbhz`. Los efectos de los emisores siguen siendo variaciones en dB.
3. En los manifiestos, `gnss: {cn0_nominal_dbhz, agc_nominal_db}` (p. ej. 38–50 dB-Hz y ±3 dB en v2; 30 y 55 dB-Hz fuera de rango en la generalización); `assets_of` ya escribe esos valores y `cn0_vs_nominal_db` los usa. Regenerar v2 y gen (≈4 min) y reentrenar (≈6 min).
Mientras tanto las tablas de v2 **no están probadas frente a otro receptor**: las filas con `cn0_vs_nominal_db` valen igual que las absolutas de v1 en este simulador.

### Decisiones que necesito de Carlos
1. Visto bueno al cambio mínimo del C/N0 y del AGC nominales (arriba) o decir que no.
2. El umbral de «viento notable» (5 m/s absolutos) es una definición del etiquetador y por eso `environment.wind` usa también el viento en m/s; si se quiere que sea relativo (p. ej. 0,4 × `wind_limit`) hay que cambiar `labeling.wind_notable_mps` por variante (parámetro del escenario, no de la física) y regenerar.
3. `drone.situation` queda por debajo de v1 (0,737 frente a 0,821): ¿se acepta, se prueba profundidad 6 o se amplía la lista (con validación)?
4. La política de la causa dudosa (`possible` → «sin determinar», `HIJACK` solo con `confirmed`) para la E7c.

## Paso 2c · e7b-v3: receptor y viento relativos, regla determinista de la situación
Decisiones de Carlos tras el 2b (el C/N0 y el AGC nominales variables, el viento «notable» relativo, la situación determinista y la política de la causa). v1 y v2 se mantienen para comparar; todo lo nuevo es **e7b-v3** (`experiments/e7b/e7b-v3/`, tablas en `tools/training/candidates/e7b-v3.yaml`, revisión en `tools/training/review/e7b-v3/`) y la prueba de generalización nueva **e7b-gen-v3**.

### 1. Contrato y simulador v1.2 (cambio aprobado; `runs/` idéntico)
- `GpsConfig.cn0_nominal_dbhz` (45,0) y `agc_nominal_db` (0,0): `receiver.py` y la verdad (`simulator.py`) los leen; la constante `GNSS_CN0_NOMINAL_DBHZ` desaparece. Con los valores por defecto, `test_determinism` (los once escenarios, los cinco ficheros) sigue pasando: **`runs/` idéntico**. Test nuevo: con 38 dB-Hz y +2,5 dB el receptor lee −7 dB y +2,5 dB con el mismo ruido y todo lo demás (posiciones, radar, estima) sale igual.
- **Viento «notable» = 0,4 × `wind_limit`** (`labeling.wind_notable_over_limit`, sustituye a `wind_notable_mps`; 4,8 m/s con el Matrice 300). Comprobado sobre los **once** escenarios: **0 segundos de `states.jsonl` cambian** (el viento base es de 2 m/s y las rampas cruzan la banda 4,8–5 entre dos segundos), así que `runs/` no se regenera. Test nuevo (6 m/s son notables con un límite de 12 y calma con uno de 20).
- `contracts/eventos.md` (cabecera v1.2 y YAML), `scenarios/README.md`, esquemas (68) y los `CLAUDE.md` actualizados. Contratos 203 (+1 saltado), plataforma 350.

### 2. e7b-v3 (`manifests/e7b-v3.yaml`) y generalización (`e7b-gen-v3.yaml`)
- Como e7b-v2 más: **C/N0 nominal 38–50 dB-Hz y AGC nominal ±3 dB** por variante (fuera de rango en la generalización: 30–34 y 54–58 dB-Hz, ±5–8 dB) y episodios de viento «notables» desde 0,4 × `wind_limit`. `assets.yaml` de cada variante lleva sus valores.
- 2400 variantes en 183 s (1680 / 359 / 361); 326 intentos descartados por `unexplained` (`battery` 109, `link_mute` 59, `jamming` 44, `gps_degraded` 26, `source_mute` 21). Mínimos 60/15/15 salvo `failsafe_hold` en validación (14). e7b-gen-v3: 600 variantes en 63 s, 178 descartes (`battery` 40, `link_mute` 30, `source_mute` 23). Los descartes suben un poco (v2: 289 y 87) porque con el viento «notable» relativo un dron grande se desvía con vientos de 5 a 0,4 × límite sin que cuente como causa.
- `environment.wind` ya **no usa el viento en m/s absolutos** (la lista de v3 son solo las cuatro relativas; un test lo comprueba).
- Dos características nuevas, en metros, solo para la regla de la situación: `gps_sigma_m` (error esperado del GPS) y `radar_sigma_m` (el del radar a esa distancia entre √trazas promediadas).

### 3. `drone.situation`: regla determinista (no aprendida)
`ai_module/situation/situation_rule.py` + `situation_rule.yaml` (mismo formato y evaluador FIRST que `tables.yaml`; E7c la enchufa). La etiqueta es geométrica, así que la tabla decide con **una distancia y la histéresis de la etiqueta**: 25 m desviado, 15 m en ruta, entre medias se mantiene el estado, «volviendo» = sigue fuera de ruta sin causa activa. Lo difícil se resuelve **antes** de la tabla:
- **Qué posición creer:** el GPS si es reciente, tiene fix y la tabla de integridad no dice «engañado»; si está engañado, perdido o sin telemetría, el radar promediado; sin ninguno, se mantiene el estado anterior.
- **Margen para no parpadear:** el dron solo salta a «desviado» con `dev − k·σ > 25` y a «en ruta» con `dev + k·σ ≤ 15`, con σ el error esperado de la posición usada (receptor, o radar a esa distancia). `k` se elige **en validación** (0 a 3; el mejor, 0,5; la curva es plana: 0,832–0,837).
- **Causa activa para «volviendo»:** salen de las **facetas aprendidas** que definen las causas de la etiqueta (viento ≥ notable, GPS engañado, GPS sin fix, control ajeno). La tabla `drone.cause` aprendida **no sirve** para esto: su etiqueta es pegajosa (mantiene la última causa mientras el dron vuelve), así que no distingue «activa» de «terminada».
- Tests (`test_situation_rule.py`, 5): la histéresis completa, sin posición se mantiene, el margen evita una falsa desviación por ruido, el GPS engañado se descarta, las cuatro causas.

**Comparación** (F1 macro con IC 95 % por bootstrap de variantes; la aprendida con **solo geometría**, y un árbol de referencia con las señales de causa):
| | Validación | Prueba de v3 | Generalización | 28 m/s | 8 m/s |
|---|---|---|---|---|---|
| **Regla determinista** | **0,837** [0,782; 0,888] | **0,803** [0,743; 0,854] | **0,756** [0,711; 0,796] | **0,750** | 0,800 |
| Árbol aprendido (solo geometría, 19 hojas) | 0,750 | 0,724 | 0,555 | 0,546 | 0,649 |
| Árbol + señales de causa (38 hojas) | 0,781 | 0,761 | 0,677 | 0,663 | 0,823 |
| Bosque (solo geometría) | 0,787 | 0,761 | 0,664 | 0,656 | 0,721 |
**La regla gana** (o empata dentro del IC en 8 m/s) en las tres, así que **es la que se queda**; el árbol aprendido de `drone.situation` queda solo como referencia. Informe completo, F1 por clase y análisis: `report/situation.md`.

**Qué pasaba con el dron de 28 m/s — no eran las esquinas.** Con la regla, a 28 m/s: 12 422 errores; cerca de un waypoint (< 150 m) solo **~23 %** (con 8 m/s, 19 %), y las desviaciones de la etiqueta fuera de toda anomalía inyectada y cerca de una esquina son **137 de 32 152 segundos (0,4 %)**; los reintentos descartados por `unexplained` son 23 % frente a 18 %. El desglose por verdad (`diag`) mostró que **el 37 % de los errores caían en `failsafe_hold` y `failsafe_land`**: en una variante con GPS de 3 s y 16 m/s, el dron está a 0,3 m de su punto de espera real y mi referencia estaba a **23–25 m de forma constante**, porque el primer mensaje con el modo nuevo llega hasta un periodo tarde y fijaba la referencia con la estima de ese instante (error ≈ velocidad × periodo). **Corregido en `features.py`:** la referencia del punto de espera es primero el punto medio de las dos estimas que rodean el cambio y, cuando el dron se para (< 1 m/s), donde se para (el simulador lo lleva a ese punto). Efecto en la regla: errores a 28 m/s 12 422 → 12 339 (solo el punto medio) → **9 426** (anclado donde se para); F1 de generalización 0,718 → 0,726 → **0,756** y de validación 0,789 → 0,810 → 0,837. Ficheros: `situation-before-anchor.md`, `situation-anchor-midpoint.md` y `situation.md`. **Lo que queda de error a 28 m/s** (9 426) es sobre todo falsos «desviado» (5 121) y solo el 16 % cerca de esquinas (8 m/s: 18 %): **no hay base para anotar «los 25/15 m fijos abren las esquinas»**; lo que sí se anota es que la referencia del modo es más difícil de situar con un dron rápido y un GPS lento (error ∝ velocidad × periodo), y que los 25/15 m no escalan con el dron (ya en `mejoras_futuras.md`).
- Tests nuevos de `features.py` (3): el punto de espera entre las dos estimas, y que sigue provisional hasta que el dron se para.

### 4. Política de la causa (para la E7c; de acuerdo con Carlos)
Una fila de `drone.cause` con confianza `possible` (< 0,6) se resuelve como **«sin determinar»**; el incidente de **secuestro** solo se abre con una fila `confirmed` (≥ 0,9). Las tablas ya llevan `confidence` y la fila por defecto de la causa es un `unexplained` al que no llega nada. Queda para la E7c.

### Resultados de las 14 tablas de v3 (prueba de v3; F1 macro [IC 95 %]; la situación, la regla)
Detalle por fila, soporte, calibración y retrasos en `report/e7b-tablas.md`; comparación con v2 y el bosque en `report/generalization.md`.
| Faceta | Filas (prof.) | Tabla v2 | **Tabla v3** | Bosque v3 |
|---|---|---|---|---|
| gps.availability | 4 (3) | 0,953 | **0,953** [0,912; 0,978] | 0,947 |
| gps.quality | 3 (2) | 0,979 | **0,980** [0,968; 0,989] | 0,974 |
| gps.integrity | 4 (3) | 0,961 | **0,977** [0,965; 0,986] | 0,982 |
| radar.availability | 3 (2) | 0,994 | **0,994** [0,991; 0,996] | 0,989 |
| link.availability | 2 (1) | 0,996 | **0,996** [0,993; 0,998] | 0,995 |
| link.quality | 5 (3) | 0,959 | **0,947** [0,928; 0,960] | 0,941 |
| meteo.availability | 2 (1) | 0,945 | **0,945** [0,925; 0,961] | 0,945 |
| battery.availability | 2 (1) | 0,823 | **0,823** [0,758; 0,857] | 0,823 |
| battery.level | 4 (3) | 0,922 | **0,931** [0,922; 0,940] | 0,926 |
| battery.endurance | 10 (6) | 0,888 | **0,866** [0,832; 0,891] | 0,902 |
| environment.wind | 8 (5) | 0,831 | **0,853** [0,823; 0,872] | 0,855 |
| drone.mode | 13 (6) | 0,808 | **0,814** [0,783; 0,836] | 0,829 |
| drone.situation | regla | 0,730 | **0,803** [0,743; 0,854] | 0,761 |
| drone.cause | 10 (4) | 0,902 | **0,869** [0,831; 0,900] | 0,934 |
(Las tablas de v2 se evalúan con las mismas características; su `environment.wind` se entrenó con la etiqueta de 5 m/s absolutos.) Las tablas de v3 **empatan o mejoran** a las de v2 salvo `drone.cause` (−0,034 [IC ancho], 10 filas frente a 14: la tolerancia de 0,01 elige el árbol más pequeño; el bosque llega a 0,934) y `battery.endurance` (−0,022). Cortes de confianza elegidos en validación: 0,9 y 0,4; se mantienen 0,9 y 0,6 (la especificación).

### Generalización (e7b-gen-v3: drones, sensores **y receptor** fuera de rango; F1 macro)
| Faceta | Tabla v2 | **Tabla v3** | Bosque v3 |
|---|---|---|---|
| gps.availability | 0,952 | **0,952** | 0,948 |
| gps.quality | 0,769 | **0,818** | 0,673 |
| gps.integrity | 0,913 | **0,942** | 0,590 |
| radar.availability | 0,973 | 0,936 | 0,929 |
| link.availability | 0,995 | **0,995** | 0,994 |
| link.quality | 0,924 | 0,882 | 0,869 |
| meteo / battery.availability | 0,711 / 0,644 | 0,711 / 0,644 | 0,711 / 0,644 |
| battery.level | 0,874 | **0,880** | 0,877 |
| battery.endurance | 0,838 | 0,821 | 0,863 |
| environment.wind | 0,729 | **0,831** (+0,102) | 0,834 |
| drone.mode | 0,805 | **0,812** | 0,845 |
| drone.situation | 0,639 | **0,756** (regla) | 0,664 |
| drone.cause | 0,893 | 0,857 | 0,903 |
- **El receptor ya no es una constante:** `gps.integrity` con el C/N0 y el AGC nominales fuera de rango (30–34 y 54–58 dB-Hz, ±5–8 dB) sigue en **0,942** (la de v2 evaluada ahí: 0,913; el bosque con las mismas entradas se hunde a 0,590). Las filas de C/N0 y AGC valen ahora para otro receptor, no solo para el del simulador.
- `environment.wind` pierde su dependencia de los 5 m/s: +0,102 en generalización.
- Peor: `radar.availability` y `link.quality` bajan algo (−0,037 y −0,042) con σ y periodos extremos; `meteo`/`battery.availability` siguen limitadas por el periodo de 40 s (retraso de detección: 1,5 periodos).

### `demo` con las tablas de v3
Con la regla para la situación y las facetas aprendidas (resto del vídeo): `WIND` abre T+02:19 (vídeo T+02:18) y cierra T+03:00; `GPS_SPOOFING` T+03:20 → T+04:33; `LINK_LOSS` T+06:10 → `HIJACK` T+06:20 → cierre T+07:58; **`nominal`, ningún incidente.** El viento muestra dos revisiones de estado de más (T+02:42 y T+02:51) al acabar el episodio: es la histéresis de la política de incidentes del vídeo (E7c), no de las tablas.

### Tests
Contratos 203 (+1 saltado), plataforma 350, módulo de IA 403 (+15 saltados), herramientas 31 (entorno del módulo) y 12 de variantes (entorno de la plataforma); `ruff` limpio; `runs/` idéntico; en directo = fuera de línea (`live_check`: `demo` y `faults`, filas idénticas); puertos 8000, 8100 y 3000 libres.

## Paso 5 · Revisión de Carlos, congelación y cierre
### Revisión aplicada (e7b-v3)
Carlos: **no se redondea ningún umbral**; se **rechazan tres filas** con probabilidad < 0,1 (en su propio entrenamiento el estado que dan es erróneo más de 9 de cada 10 veces; existen por el peso por clase); el resto se queda, y las filas de probabilidad baja salen como `possible` y las resuelve la política en la E7c. `drone.situation` se queda con la **regla determinista** (`situation_rule.yaml`).
`tools/training/apply_review.py` aplica cada rechazo **por separado**, mide su efecto en **validación** y lo deshace si la F1 macro de esa faceta baja más de 0,005 (ninguno bajó). Una fila rechazada deja su región a la fila por defecto (las filas son excluyentes: no hay solapes ni huecos nuevos; sin redondeos no hay que repetir la comprobación de umbrales vecinos).
| Fila | Faceta | Estado que daba | Probabilidad (entrenamiento) | Soporte (inst. / variantes / rachas) | Validación: instantes que caían (acierta) | F1 macro validación |
|---|---|---|---|---|---|---|
| **LQ-03** | link.quality | `degraded` | 0,0375 | 31 / 8 / 11 | 200 (7 = 3,5 %) | 0,9167 → **0,9404** (+0,024) |
| **BE-06** | battery.endurance | `cannot_reach_home` | 0,0632 | 105 / 6 / 6 | 796 (37 = 4,7 %) | 0,8583 → **0,8761** (+0,018) |
| **DM-10** | drone.mode | `failsafe_land` | 0,0813 | 823 / 46 / 49 | 1 554 (158 = 10,2 %) | 0,8477 → **0,9121** (+0,064) |
- Condiciones: LQ-03 = `link_latency_vs_base <= 1,407` y `link_rssi_dbm > −81,65` y `link_loss_pct > 97,7` (con una pérdida del 98 % el enlace está caído, no «degradado»); BE-06 = `battery_pct > 32,65` y `wind_est_over_airspeed <= 0,8455` y `home_time_ratio > 0,3643`; DM-10 = `mode_land > 0,5` y `mode_hold <= 0,5` y `mode_return` ausente y `age_autopilot_p` en (5,25; 60,25] y `radar_dev_sigma <= 5,70`. Todas con `null` donde la tabla lo dice.
- Efecto por clase: la F1 de `failsafe_land` pasa de 0,346 a 0,669 y las demás clases de `drone.mode` no cambian; `cannot_reach_home` 0,724 → 0,759; `degraded` 0,834 → 0,882. **La regla de la situación no se mueve** (usa de `drone.mode` solo `foreign_control`).
- **Guardado para restaurarlas:** `tools/training/review/e7b-v3/rejected.yaml` (las tres filas **completas**: condiciones, estado, probabilidad, soporte, aciertos en validación, motivo, fecha 2026-11-25 y efecto), `candidate-unreviewed.yaml` (la candidata sin revisar; es copia de `candidates/e7b-v3.yaml`) y los 14 `review/e7b-v3/<faceta>.yaml` con `reject: true` y su motivo. Un test comprueba que la tabla congelada **es exactamente la candidata menos esas tres filas**.

### Métricas finales en prueba y en generalización (F1 macro [IC 95 %]; revisadas; la situación, la regla con margen 0,5)
Informe completo, con «sin revisar» al lado y la validación: `experiments/e7b/e7b-v3/report/e7b-final.md`.
| Faceta | Prueba de v3 | Generalización (e7b-gen-v3) | Δ por la revisión (prueba / gen.) |
|---|---|---|---|
| gps.availability | 0,953 [0,912; 0,978] | 0,952 [0,931; 0,968] | 0 / 0 |
| gps.quality | 0,980 [0,968; 0,989] | 0,818 [0,770; 0,863] | 0 / 0 |
| gps.integrity | 0,977 [0,965; 0,986] | 0,942 [0,923; 0,959] | 0 / 0 |
| radar.availability | 0,994 [0,991; 0,996] | 0,936 [0,875; 0,976] | 0 / 0 |
| link.availability | 0,996 [0,993; 0,998] | 0,995 [0,993; 0,997] | 0 / 0 |
| link.quality | 0,966 [0,952; 0,976] | 0,929 [0,907; 0,943] | +0,019 / +0,047 |
| meteo.availability | 0,945 [0,925; 0,961] | 0,711 [0,674; 0,746] | 0 / 0 |
| battery.availability | 0,823 [0,758; 0,857] | 0,644 [0,607; 0,682] | 0 / 0 |
| battery.level | 0,931 [0,922; 0,940] | 0,880 [0,859; 0,898] | 0 / 0 |
| battery.endurance | 0,876 [0,845; 0,900] | 0,825 [0,799; 0,848] | +0,011 / +0,004 |
| environment.wind | 0,853 [0,823; 0,872] | 0,831 [0,807; 0,855] | 0 / 0 |
| drone.mode | 0,874 [0,828; 0,906] | 0,866 [0,841; 0,888] | +0,060 / +0,054 |
| drone.situation (regla) | 0,803 [0,743; 0,854] | 0,756 [0,711; 0,796] | 0 / 0 |
| drone.cause | 0,869 [0,831; 0,900] | 0,857 [0,834; 0,877] | 0 / 0 |
Los tres rechazos **mejoran** también la prueba y la generalización (no solo la validación con la que se decidieron). Las filas de probabilidad baja que quedan (p. ej. de la causa: `wind` 0,45, `spoofed_position` 0,44 y `dead_reckoning` 0,55) salen como `possible`: **E7c** (una causa `possible` → «sin determinar»; el secuestro solo con una fila `confirmed`).
`demo` con las tablas congeladas (resto del vídeo): `WIND` T+02:19 → T+03:00, `GPS_SPOOFING` T+03:20 → T+04:33, `LINK_LOSS` T+06:10 → `HIJACK` T+06:20 → T+07:58 (con dos revisiones de estado de más del viento al acabar el episodio: histéresis de la política del vídeo, E7c); `nominal`, ningún incidente.

### Congelación
- **Tablas:** `ai-module-py/src/ai_module/situation/tables_learned.yaml` (13 tablas aprendidas, 976 líneas; la situación es `situation_rule.yaml`). **No sustituyen a `tables.yaml` hasta la E7c.** El margen de la regla (0,5) queda en `situation_rule.py::MARGIN_K`.
- **Hash:** `tables_freeze.json` (decisión de Carlos: junto a las tablas, sin tocar `.gitignore`) con el sha256 de nueve ficheros (las tablas, la regla, `features.py`, `assets.yaml`, `decision/table.py`, el manifiesto, la candidata y `rejected.yaml`), uno combinado (`13f6cfd61d835c6e`) y la fecha. `tools/training/check_freeze.py` da `ok`; congelar de nuevo exige `--force` (cuenta como «a posteriori»).
- **JSON de reglas de la web:** `web/lib/situation-tables-frozen.json`, generado con `export_tables.build_frozen()` (`tools/training/export_frozen.py`) a partir de las mismas tablas; un test comprueba que no se desincroniza. La web aún no lo lee (E7c); el `situation-tables.json` de las tablas a mano no cambia.
- **Tests nuevos** (`test_tables_freeze.py`, 4): cada faceta aprendida tiene su tabla, que termina en la fila por defecto y lleva `probability` y `confidence`; **la tabla congelada es la candidata menos las tres filas** (y las tres están completas); el hash de cada fichero coincide con el congelado; el JSON de la web sale de las tablas que se ejecutan.

### Dependencias, tests y estado
Dependencias de la E7b: solo el grupo `train` (scikit-learn 1.9.1 BSD-3-Clause y sus dependencias; ⚠️ las licencias de numpy, scipy, joblib, threadpoolctl y narwhals leídas de los metadatos instalados, no de sus páginas oficiales). Contratos 203 (+1), plataforma 350, módulo de IA 407 (+15 saltados), herramientas 31 y 12, web (`pnpm`) sin cambios; `ruff` limpio; `runs/` idéntico; puertos 8000, 8100 y 3000 libres.

### Qué queda (E7c y E8)
Enchufar las tablas congeladas y la regla al monitor (k y m del seguidor, severidad con escalado, confianza calibrada con los cortes 0,9 y 0,6, la política de la causa `possible` y `confirmed`), la web con `situation-tables-frozen.json`, y la evaluación a ciegas (E8) con el hash de `tables_freeze.json`.

### Cambios que propongo en la especificación
§4: «notable» es 0,4 × `wind_limit`; §5: la situación del dron es una regla determinista (no un árbol), el margen de la posición y la causa activa de las facetas aprendidas; §6: configuración de los activos (`assets.yaml`) como entrada del monitor; contrato v1.2 (C/N0 y AGC nominales del receptor).

### Mensaje de commit propuesto
```
feat: E7b - learned situation tables, relative features and frozen tables

Situation monitor features rewritten (one row per second, mode reference
anchored where the drone stops, source freshness in periods, relative
features and per-variant asset configuration). Data generator by class
(e7b-v1..v3, generalization set), one CART tree per facet converted into
FIRST decision tables with probability, confidence and support per row,
episode-based pruning, bootstrap confidence intervals and a deterministic
rule for the drone situation. Contract v1.2 (additive): nominal C/N0 and AGC
of the receiver, and notable wind as 0.4 x wind_limit (runs/ unchanged).
Review applied (three rows rejected, kept in rejected.yaml) and tables frozen
with a hash; the monitor still runs the hand-written tables until E7c.
```
