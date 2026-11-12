# Comparativa · e15_1-final

Perfiles: `actual` · escenarios: demo, hijack, faults, demo-battery, demo-meteo · repeticiones: 1 · huella de `agent-assets`: 2babe22e39116f71 · vLLM: 0.31.0 · repositorio: a2a5362f82 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones); las iteraciones, percentiles de las invocaciones del monitor con LLM.

## demo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 1 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 5 | 0 / 1 | 0 / 0 / 0 | 0.8 s / 6.0 s · inv. 8.2 s / 16.9 s | 4 / 6 / 6 | 292162 / 5703 / 0 | 1 repetición |

## hijack

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 3 | 0 / 0 | 0 / 0 / 0 | 0.8 s / 5.4 s · inv. 8.7 s / 12.1 s | 4 / 5 / 5 | 145495 / 2951 / 0 | 1 repetición |

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 1 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 5 | 0 / 3 | 0 / 0 / 0 | 1.0 s / 5.7 s · inv. 8.8 s / 14.9 s | 4 / 7 / 7 | 258212 / 5028 / 0 | 1 repetición |

## demo-battery

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 1/1 · A2 0/1 · A3 1/1 · F1 1/1 | A1 1/1 · A2 1/1 · A3 1/1 · F1 1/1 | 0 | 0 | 1 | 0 | 0 | 0 · veto 1 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 6 | 0 / 0 | 0 / 0 / 0 | 0.9 s / 5.8 s · inv. 8.2 s / 15.8 s | 4 / 6 / 6 | 477621 / 8895 / 0 | 1 repetición |

## demo-meteo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 0/1 · A2 1/1 · A3 1/1 · F1 1/1 | A1 1/1 · A2 1/1 · A3 1/1 · F1 1/1 | 0 | 0 | 1 | 0 | 0 | 0 · veto 1 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 5 | 0 / 4 | 0 / 0 / 0 | 0.8 s / 6.4 s · inv. 8.8 s / 15.6 s | 5 / 7 / 7 | 334342 / 5740 / 0 | 1 repetición |

## Detalle de las repeticiones

- **demo · `actual`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `actual`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **demo-battery · `actual`**
  - r1: ❌ 3/4 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 SENSOR_FAULT/SENSOR_FAULT ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas
- **demo-meteo · `actual`**
  - r1: ❌ 3/4 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 UNKNOWN ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas
