# Comparativa · e6-reservado-l

Perfiles: `actual` · escenarios: d01-viento-en-spoof, d02-spoof-lento, d03-viento-flojo-sostenido, d04-secuestro-en-viento, d05-radar-callado-en-spoof, d06-enlace-degradado-y-secuestro, d07-degradacion-vuelo-entero, d08-interferencia-gps, d09-meteo-callada-en-viento, n01-calma, n02-viento-base-flojo, n03-ruido-alto, r01-racha-lateral, r02-viento-instructor, r03-dos-rachas, r04-spoof-lateral, r05-perdida-gps, r06-secuestro-recupera, r07-secuestro-sin-fin, r08-radar-callado, r09-fuentes-calladas, r10-ejercicio-completo · repeticiones: 2 · huella de `agent-assets`: c7072d881f461fb6 · vLLM: 0.31.0 · repositorio: 8e54034956 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones); las iteraciones, percentiles de las invocaciones del monitor con LLM.

## d01-viento-en-spoof

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 0/2 · A2 2/2 | A1 0/2 · A2 0/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 2 | 0 / 2 | 0 / 0 / 0 | 0.8 s / 5.7 s · inv. 4.5 s / 9.2 s | 3 / 5 / 5 | 98038 / 2066 / 0 | estable (2/2) |

## d02-spoof-lento

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 0/2 | A1 0/2 | 0 | 0 | 0 | 0 | 0 | 2 (window_without_jump 2) · veto 0 · sin métricas 0 | 0 / 0 / 0 | 4 | 0 / 6 | 0 / 0 / 0 | 0.7 s / 5.6 s · inv. 7.3 s / 12.4 s | 4 / 6 / 6 | 133483 / 2736 / 0 | estable (2/2) |

## d03-viento-flojo-sostenido

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 0/2 | A1 0/2 | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 6402 / 548 / 0 | estable (2/2) |

## d04-secuestro-en-viento

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 0/2 · A2 2/2 | A1 0/2 · A2 2/2 | 4 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 10 | 0 / 6 | 0 / 0 / 0 | 0.7 s / 5.2 s · inv. 8.0 s / 17.2 s | 4 / 8 / 8 | 214854 / 4219 / 0 | estable (2/2) |

## d05-radar-callado-en-spoof

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 0/2 · F1 2/2 | A1 2/2 · F1 2/2 | 0 | 0 | 0 | 0 | 0 | 2 (other 2) · veto 0 · sin métricas 0 | 0 / 0 / 0 | 6 | 0 / 8 | 0 / 0 / 0 | 0.7 s / 6.5 s · inv. 2.8 s / 34.3 s | 2 / 12 / 12 | 168990 / 3339 / 0 | estable (2/2) |

## d06-enlace-degradado-y-secuestro

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 2/2 · F1 2/2 | A1 2/2 · F1 2/2 | 2 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 10 | 0 / 6 | 0 / 0 / 0 | 0.8 s / 5.3 s · inv. 7.1 s / 19.5 s | 4 / 9 / 9 | 215278 / 4122 / 0 | estable (2/2) |

## d07-degradacion-vuelo-entero

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | F1 2/2 · F2 0/2 | F1 2/2 · F2 2/2 | 2 | 0 | 4 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 6 | 0 / 2 | 0 / 0 / 0 | 0.6 s / 5.5 s · inv. 9.9 s / 15.8 s | 5 / 10 / 10 | 150694 / 2843 / 0 | estable (2/2) |

## d08-interferencia-gps

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | F1 2/2 · F2 2/2 | F1 2/2 · F2 2/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 2 · sin métricas 0 · salto del módulo 2, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 8 | 0 / 4 | 0 / 0 / 0 | 0.7 s / 5.8 s · inv. 7.9 s / 15.2 s | 4 / 8 / 8 | 208044 / 3686 / 0 | estable (2/2) |

## d09-meteo-callada-en-viento

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 0/2 · F1 2/2 | A1 2/2 · F1 2/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 2 | 0 / 0 / 0 | 0.7 s / 4.9 s · inv. 2.1 s / 7.3 s | 2 / 4 / 4 | 83116 / 1825 / 0 | estable (2/2) |

## n01-calma

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 6254 / 508 / 0 | estable (2/2) |

## n02-viento-base-flojo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 6344 / 552 / 0 | estable (2/2) |

## n03-ruido-alto

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | sin etiquetas | — | 12 | 0 | 4 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 4 | 0 / 0 | 0 / 0 / 0 | 0.7 s / 6.3 s · inv. 5.2 s / 16.7 s | 3 / 8 / 8 | 150170 / 3266 / 0 | estable (2/2) |

## r01-racha-lateral

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 2/2 | A1 2/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 2 | 0 / 0 / 0 | 0.7 s / 3.8 s · inv. 2.5 s / 6.3 s | 2 / 4 / 4 | 44268 / 1248 / 0 | estable (2/2) |

## r02-viento-instructor

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 2/2 | A1 2/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 2 | 0 / 0 / 0 | 0.7 s / 3.9 s · inv. 2.4 s / 6.3 s | 2 / 4 / 4 | 44328 / 1229 / 0 | estable (2/2) |

## r03-dos-rachas

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 2/2 · A2 2/2 | A1 2/2 · A2 2/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 4 | 0 / 0 / 0 | 0.7 s / 4.3 s · inv. 2.6 s / 7.0 s | 2 / 4 / 4 | 82594 / 1752 / 0 | estable (2/2) |

## r04-spoof-lateral

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 0/2 | A1 0/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 2, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 4 | 0 / 8 | 0 / 0 / 0 | 0.8 s / 6.4 s · inv. 8.0 s / 15.3 s | 4 / 6 / 6 | 140782 / 3348 / 0 | estable (2/2) |

## r05-perdida-gps

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | F1 2/2 | F1 2/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 2 · sin métricas 0 · salto del módulo 2, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 8 | 0 / 4 | 0 / 0 / 0 | 0.8 s / 5.6 s · inv. 7.7 s / 14.5 s | 5 / 6 / 6 | 157462 / 3082 / 0 | estable (2/2) |

## r06-secuestro-recupera

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 2/2 | A1 2/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 4 | 0 / 0 | 0 / 0 / 0 | 0.7 s / 5.4 s · inv. 7.1 s / 9.0 s | 4 / 5 / 5 | 137053 / 2724 / 0 | estable (2/2) |

## r07-secuestro-sin-fin

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 2/2 | A1 2/2 | 0 | 0 | 2 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 4 | 0 / 0 | 0 / 0 / 0 | 0.7 s / 5.6 s · inv. 7.2 s / 8.6 s | 4 / 5 / 5 | 90343 / 2164 / 0 | estable (2/2) |

## r08-radar-callado

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | F1 2/2 | F1 2/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | 0.7 s / 5.7 s · inv. 2.5 s / 8.9 s | 2 / 5 / 5 | 52601 / 1385 / 0 | estable (2/2) |

## r09-fuentes-calladas

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | F1 2/2 · F2 0/2 · F3 2/2 | F1 2/2 · F2 2/2 · F3 2/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | 0.7 s / 5.1 s · inv. 2.8 s / 7.8 s | 2 / 5 / 5 | 125938 / 2440 / 0 | estable (2/2) |

## r10-ejercicio-completo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 2/2 · A2 2/2 · A3 2/2 | A1 2/2 · A2 2/2 · A3 2/2 | 0 | 0 | 0 | 0 | 0 | 0 · veto 2 · sin métricas 0 · salto del módulo 2, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 8 | 0 / 6 | 0 / 0 / 0 | 0.8 s / 5.9 s · inv. 7.1 s / 15.2 s | 4 / 6 / 6 | 265796 / 4800 / 0 | estable (2/2) |

## Detalle de las repeticiones

- **d01-viento-en-spoof · `actual`**
  - r1: ✅ 1/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering · 1 avisos ambiguos (aparte) — A1 — ×0 cadenas, 0 cierres; A2 GPS_SPOOFING ×2 cadenas, 2 cierres; 0 abiertas
  - r2: ✅ 1/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering · 1 avisos ambiguos (aparte) — A1 — ×0 cadenas, 0 cierres; A2 GPS_SPOOFING ×2 cadenas, 2 cierres; 0 abiertas
- **d02-spoof-lento · `actual`**
  - r1: ⚠️ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING/UNKNOWN ×2 cadenas, 2 cierres; 0 abiertas
  - r2: ⚠️ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING/UNKNOWN ×2 cadenas, 2 cierres; 0 abiertas
- **d03-viento-flojo-sostenido · `actual`**
  - r1: ❌ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — A1 — ×0 cadenas, 0 cierres; 0 abiertas
  - r2: ❌ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — A1 — ×0 cadenas, 0 cierres; 0 abiertas
- **d04-secuestro-en-viento · `actual`**
  - r1: ✅ 1/2 anomalías y fallos diagnosticados · 2 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering · 1 avisos ambiguos (aparte) — A1 — ×0 cadenas, 0 cierres; A2 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/2 anomalías y fallos diagnosticados · 2 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering · 1 avisos ambiguos (aparte) — A1 — ×0 cadenas, 0 cierres; A2 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **d05-radar-callado-en-spoof · `actual`**
  - r1: ❌ 1/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 UNKNOWN ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ❌ 1/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 UNKNOWN ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **d06-enlace-degradado-y-secuestro · `actual`**
  - r1: ✅ 2/2 anomalías y fallos diagnosticados · 1 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK ×1 cadenas, 1 cierres; F1 UNKNOWN ×1 cadenas, 0 cierres; 0 abiertas
  - r2: ✅ 2/2 anomalías y fallos diagnosticados · 1 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK ×1 cadenas, 1 cierres; F1 UNKNOWN ×1 cadenas, 0 cierres; 0 abiertas
- **d07-degradacion-vuelo-entero · `actual`**
  - r1: ❌ 1/2 anomalías y fallos diagnosticados · 1 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 2 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 GPS_JAMMING ×1 cadenas, 0 cierres; F2 HIJACK ×1 cadenas, 0 cierres; 2 abiertas
  - r2: ❌ 1/2 anomalías y fallos diagnosticados · 1 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 2 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 GPS_JAMMING ×1 cadenas, 0 cierres; F2 HIJACK ×1 cadenas, 0 cierres; 2 abiertas
- **d08-interferencia-gps · `actual`**
  - r1: ✅ 2/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 GPS_JAMMING ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas
  - r2: ✅ 2/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 GPS_JAMMING ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas
- **d09-meteo-callada-en-viento · `actual`**
  - r1: ❌ 1/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 UNKNOWN ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ❌ 1/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 UNKNOWN ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **n01-calma · `actual`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
  - r2: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
- **n02-viento-base-flojo · `actual`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
  - r2: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
- **n03-ruido-alto · `actual`**
  - r1: ❌ 0/0 anomalías y fallos diagnosticados · 6 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 2 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — ; 2 abiertas
  - r2: ❌ 0/0 anomalías y fallos diagnosticados · 6 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 2 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — ; 2 abiertas
- **r01-racha-lateral · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **r02-viento-instructor · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **r03-dos-rachas · `actual`**
  - r1: ✅ 2/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 2/2 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **r04-spoof-lateral · `actual`**
  - r1: ⚠️ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING/HIJACK ×2 cadenas, 2 cierres; 0 abiertas
  - r2: ⚠️ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING/HIJACK ×2 cadenas, 2 cierres; 0 abiertas
- **r05-perdida-gps · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; 0 abiertas
- **r06-secuestro-recupera · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **r07-secuestro-sin-fin · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK/HIJACK ×1 cadenas, 0 cierres; 1 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK/HIJACK ×1 cadenas, 0 cierres; 1 abiertas
- **r08-radar-callado · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **r09-fuentes-calladas · `actual`**
  - r1: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 UNKNOWN ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 UNKNOWN ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **r10-ejercicio-completo · `actual`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
