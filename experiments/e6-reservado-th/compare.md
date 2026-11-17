# Comparativa · e6-reservado-th

Perfiles: `table`, `hybrid` · escenarios: d01-viento-en-spoof, d02-spoof-lento, d03-viento-flojo-sostenido, d04-secuestro-en-viento, d05-radar-callado-en-spoof, d06-enlace-degradado-y-secuestro, d07-degradacion-vuelo-entero, d08-interferencia-gps, d09-meteo-callada-en-viento, n01-calma, n02-viento-base-flojo, n03-ruido-alto, r01-racha-lateral, r02-viento-instructor, r03-dos-rachas, r04-spoof-lateral, r05-perdida-gps, r06-secuestro-recupera, r07-secuestro-sin-fin, r08-radar-callado, r09-fuentes-calladas, r10-ejercicio-completo · repeticiones: 1 · huella de `agent-assets`: c7072d881f461fb6 · vLLM: 0.31.0 · repositorio: 8e54034956 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones); las iteraciones, percentiles de las invocaciones del monitor con LLM.

## d01-viento-en-spoof

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 0/1 · A2 0/1 | A1 0/1 · A2 0/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8396 / 722 / 0 | 1 repetición |
| `hybrid` | A1 0/1 · A2 0/1 | A1 0/1 · A2 0/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 10103 / 1043 / 0 | 1 repetición |

## d02-spoof-lento

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 0/1 | A1 0/1 | 0 | 0 | 0 | 0 | 0 | 1 (window_without_jump 1) · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8690 / 958 / 0 | 1 repetición |
| `hybrid` | A1 0/1 | A1 0/1 | 0 | 0 | 0 | 0 | 0 | 1 (window_without_jump 1) · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 10454 / 1088 / 0 | 1 repetición |

## d03-viento-flojo-sostenido

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 0/1 | A1 0/1 | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 6422 / 567 / 0 | 1 repetición |
| `hybrid` | A1 0/1 | A1 0/1 | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 6435 / 589 / 0 | 1 repetición |

## d04-secuestro-en-viento

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 0/1 · A2 1/1 | A1 0/1 · A2 1/1 | 2 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 9405 / 912 / 0 | 1 repetición |
| `hybrid` | A1 0/1 · A2 1/1 | A1 0/1 · A2 1/1 | 2 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 11803 / 1248 / 0 | 1 repetición |

## d05-radar-callado-en-spoof

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 0/1 · F1 1/1 | A1 1/1 · F1 1/1 | 0 | 0 | 0 | 0 | 0 | 1 (no_metrics 1) · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8253 / 837 / 0 | 1 repetición |
| `hybrid` | A1 0/1 · F1 1/1 | A1 1/1 · F1 1/1 | 0 | 0 | 0 | 0 | 0 | 1 (no_metrics 1) · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 9946 / 1049 / 0 | 1 repetición |

## d06-enlace-degradado-y-secuestro

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 · F1 1/1 | A1 1/1 · F1 1/1 | 1 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 9970 / 1122 / 0 | 1 repetición |
| `hybrid` | A1 1/1 · F1 1/1 | A1 1/1 · F1 1/1 | 1 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 12227 / 1168 / 0 | 1 repetición |

## d07-degradacion-vuelo-entero

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | F1 1/1 · F2 1/1 | F1 1/1 · F2 1/1 | 1 | 0 | 2 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 9203 / 883 / 0 | 1 repetición |
| `hybrid` | F1 1/1 · F2 1/1 | F1 1/1 · F2 1/1 | 1 | 0 | 2 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 11737 / 1149 / 0 | 1 repetición |

## d08-interferencia-gps

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | F1 1/1 · F2 1/1 | F1 1/1 · F2 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 9575 / 924 / 0 | 1 repetición |
| `hybrid` | F1 1/1 · F2 1/1 | F1 1/1 · F2 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 12463 / 1095 / 0 | 1 repetición |

## d09-meteo-callada-en-viento

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 0/1 · F1 1/1 | A1 1/1 · F1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8279 / 895 / 0 | 1 repetición |
| `hybrid` | A1 0/1 · F1 1/1 | A1 1/1 · F1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 9911 / 990 / 0 | 1 repetición |

## n01-calma

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 6337 / 588 / 0 | 1 repetición |
| `hybrid` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 6251 / 505 / 0 | 1 repetición |

## n02-viento-base-flojo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 6307 / 509 / 0 | 1 repetición |
| `hybrid` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 6285 / 487 / 0 | 1 repetición |

## n03-ruido-alto

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | sin etiquetas | — | 6 | 0 | 2 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 9502 / 1032 / 0 | 1 repetición |
| `hybrid` | sin etiquetas | — | 6 | 0 | 2 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 11916 / 1499 / 0 | 1 repetición |

## r01-racha-lateral

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 7451 / 795 / 0 | 1 repetición |
| `hybrid` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8219 / 852 / 0 | 1 repetición |

## r02-viento-instructor

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 7448 / 739 / 0 | 1 repetición |
| `hybrid` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8289 / 966 / 0 | 1 repetición |

## r03-dos-rachas

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 · A2 1/1 | A1 1/1 · A2 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8529 / 804 / 0 | 1 repetición |
| `hybrid` | A1 1/1 · A2 1/1 | A1 1/1 · A2 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 10150 / 1041 / 0 | 1 repetición |

## r04-spoof-lateral

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 0/1 | A1 0/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 9215 / 898 / 0 | 1 repetición |
| `hybrid` | A1 0/1 | A1 0/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 11676 / 1155 / 0 | 1 repetición |

## r05-perdida-gps

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | F1 1/1 | F1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8968 / 841 / 0 | 1 repetición |
| `hybrid` | F1 1/1 | F1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 11114 / 1000 / 0 | 1 repetición |

## r06-secuestro-recupera

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8440 / 969 / 0 | 1 repetición |
| `hybrid` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 10062 / 1077 / 0 | 1 repetición |

## r07-secuestro-sin-fin

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 | A1 1/1 | 0 | 0 | 1 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 7798 / 936 / 0 | 1 repetición |
| `hybrid` | A1 1/1 | A1 1/1 | 0 | 0 | 1 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 13016 / 1187 / 0 | 1 repetición |

## r08-radar-callado

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | F1 1/1 | F1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 7285 / 761 / 0 | 1 repetición |
| `hybrid` | F1 1/1 | F1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 7979 / 845 / 0 | 1 repetición |

## r09-fuentes-calladas

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 9398 / 1078 / 0 | 1 repetición |
| `hybrid` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 11497 / 1291 / 0 | 1 repetición |

## r10-ejercicio-completo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 11331 / 974 / 0 | 1 repetición |
| `hybrid` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 15274 / 1349 / 0 | 1 repetición |

## Detalle de las repeticiones

- **d01-viento-en-spoof · `table`**
  - r1: ❌ 0/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering · 1 avisos ambiguos (aparte) — A1 — ×0 cadenas, 0 cierres; A2 SENSOR_FAULT ×2 cadenas, 2 cierres; 0 abiertas
- **d01-viento-en-spoof · `hybrid`**
  - r1: ❌ 0/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering · 1 avisos ambiguos (aparte) — A1 — ×0 cadenas, 0 cierres; A2 SENSOR_FAULT ×2 cadenas, 2 cierres; 0 abiertas
- **d02-spoof-lento · `table`**
  - r1: ⚠️ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING/UNKNOWN ×2 cadenas, 2 cierres; 0 abiertas
- **d02-spoof-lento · `hybrid`**
  - r1: ⚠️ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING/UNKNOWN ×2 cadenas, 2 cierres; 0 abiertas
- **d03-viento-flojo-sostenido · `table`**
  - r1: ❌ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — A1 — ×0 cadenas, 0 cierres; 0 abiertas
- **d03-viento-flojo-sostenido · `hybrid`**
  - r1: ❌ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — A1 — ×0 cadenas, 0 cierres; 0 abiertas
- **d04-secuestro-en-viento · `table`**
  - r1: ✅ 1/2 anomalías y fallos diagnosticados · 2 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering · 1 avisos ambiguos (aparte) — A1 — ×0 cadenas, 0 cierres; A2 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **d04-secuestro-en-viento · `hybrid`**
  - r1: ✅ 1/2 anomalías y fallos diagnosticados · 2 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering · 1 avisos ambiguos (aparte) — A1 — ×0 cadenas, 0 cierres; A2 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **d05-radar-callado-en-spoof · `table`**
  - r1: ❌ 1/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 UNKNOWN ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **d05-radar-callado-en-spoof · `hybrid`**
  - r1: ❌ 1/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 UNKNOWN ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **d06-enlace-degradado-y-secuestro · `table`**
  - r1: ✅ 2/2 anomalías y fallos diagnosticados · 1 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 0 abiertas
- **d06-enlace-degradado-y-secuestro · `hybrid`**
  - r1: ✅ 2/2 anomalías y fallos diagnosticados · 1 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 0 abiertas
- **d07-degradacion-vuelo-entero · `table`**
  - r1: ✅ 2/2 anomalías y fallos diagnosticados · 1 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 2 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 0 cierres; F2 SENSOR_FAULT ×1 cadenas, 0 cierres; 2 abiertas
- **d07-degradacion-vuelo-entero · `hybrid`**
  - r1: ✅ 2/2 anomalías y fallos diagnosticados · 1 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 2 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 0 cierres; F2 SENSOR_FAULT ×1 cadenas, 0 cierres; 2 abiertas
- **d08-interferencia-gps · `table`**
  - r1: ✅ 2/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas
- **d08-interferencia-gps · `hybrid`**
  - r1: ✅ 2/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas
- **d09-meteo-callada-en-viento · `table`**
  - r1: ❌ 1/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 UNKNOWN ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **d09-meteo-callada-en-viento · `hybrid`**
  - r1: ❌ 1/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 UNKNOWN ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **n01-calma · `table`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
- **n01-calma · `hybrid`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
- **n02-viento-base-flojo · `table`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
- **n02-viento-base-flojo · `hybrid`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
- **n03-ruido-alto · `table`**
  - r1: ❌ 0/0 anomalías y fallos diagnosticados · 6 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 2 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — ; 2 abiertas
- **n03-ruido-alto · `hybrid`**
  - r1: ❌ 0/0 anomalías y fallos diagnosticados · 6 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 2 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — ; 2 abiertas
- **r01-racha-lateral · `table`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **r01-racha-lateral · `hybrid`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **r02-viento-instructor · `table`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **r02-viento-instructor · `hybrid`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **r03-dos-rachas · `table`**
  - r1: ✅ 2/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **r03-dos-rachas · `hybrid`**
  - r1: ✅ 2/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **r04-spoof-lateral · `table`**
  - r1: ⚠️ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING/UNKNOWN ×2 cadenas, 2 cierres; 0 abiertas
- **r04-spoof-lateral · `hybrid`**
  - r1: ⚠️ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING/UNKNOWN ×2 cadenas, 2 cierres; 0 abiertas
- **r05-perdida-gps · `table`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; 0 abiertas
- **r05-perdida-gps · `hybrid`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; 0 abiertas
- **r06-secuestro-recupera · `table`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **r06-secuestro-recupera · `hybrid`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **r07-secuestro-sin-fin · `table`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK/HIJACK ×1 cadenas, 0 cierres; 1 abiertas
- **r07-secuestro-sin-fin · `hybrid`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK/HIJACK ×1 cadenas, 0 cierres; 1 abiertas
- **r08-radar-callado · `table`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **r08-radar-callado · `hybrid`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **r09-fuentes-calladas · `table`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 SENSOR_FAULT ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **r09-fuentes-calladas · `hybrid`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 SENSOR_FAULT ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **r10-ejercicio-completo · `table`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **r10-ejercicio-completo · `hybrid`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
