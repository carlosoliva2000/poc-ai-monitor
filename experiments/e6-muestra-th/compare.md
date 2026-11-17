# Comparativa · e6-muestra-th

Perfiles: `table`, `hybrid` · escenarios: demo, demo-battery, demo-meteo, faults, hijack, nominal, nominal-wind-cmd, spoofing, wind · repeticiones: 1 · huella de `agent-assets`: c7072d881f461fb6 · vLLM: 0.31.0 · repositorio: 8e54034956 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones); las iteraciones, percentiles de las invocaciones del monitor con LLM.

## demo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 26452 / 1342 / 0 | 1 repetición |
| `hybrid` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 30222 / 1587 / 0 | 1 repetición |

## demo-battery

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 · A2 1/1 · A3 1/1 · F1 1/1 | A1 1/1 · A2 1/1 · A3 1/1 · F1 1/1 | 0 | 0 | 1 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 158384 / 3814 / 0 | 1 repetición |
| `hybrid` | A1 1/1 · A2 1/1 · A3 1/1 · F1 1/1 | A1 1/1 · A2 1/1 · A3 1/1 · F1 1/1 | 0 | 0 | 1 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 163319 / 4209 / 0 | 1 repetición |

## demo-meteo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 0/1 · A2 1/1 · A3 1/1 · F1 1/1 | A1 1/1 · A2 1/1 · A3 1/1 · F1 1/1 | 0 | 0 | 1 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 12080 / 1074 / 0 | 1 repetición |
| `hybrid` | A1 0/1 · A2 1/1 · A3 1/1 · F1 1/1 | A1 1/1 · A2 1/1 · A3 1/1 · F1 1/1 | 0 | 0 | 1 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 16733 / 1576 / 0 | 1 repetición |

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 10868 / 1233 / 0 | 1 repetición |
| `hybrid` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 14426 / 1492 / 0 | 1 repetición |

## hijack

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 13212 / 1290 / 0 | 1 repetición |
| `hybrid` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 9994 / 1005 / 0 | 1 repetición |

## nominal

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 6273 / 510 / 0 | 1 repetición |
| `hybrid` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 6278 / 500 / 0 | 1 repetición |

## nominal-wind-cmd

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 7415 / 771 / 0 | 1 repetición |
| `hybrid` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8194 / 861 / 0 | 1 repetición |

## spoofing

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8126 / 781 / 0 | 1 repetición |
| `hybrid` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 · salto del módulo 1, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 9756 / 980 / 0 | 1 repetición |

## wind

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `table` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 7419 / 799 / 0 | 1 repetición |
| `hybrid` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 / 0 | n/d / n/d · inv. 0.0 s / 0.0 s | 0 / 0 / 0 | 8192 / 835 / 0 | 1 repetición |

## Detalle de las repeticiones

- **demo · `table`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `hybrid`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo-battery · `table`**
  - r1: ✅ 4/4 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas
- **demo-battery · `hybrid`**
  - r1: ✅ 4/4 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas
- **demo-meteo · `table`**
  - r1: ❌ 3/4 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 UNKNOWN ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas
- **demo-meteo · `hybrid`**
  - r1: ❌ 3/4 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 UNKNOWN ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas
- **faults · `table`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `hybrid`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `table`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `hybrid`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK/HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **nominal · `table`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
- **nominal · `hybrid`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
- **nominal-wind-cmd · `table`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **nominal-wind-cmd · `hybrid`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `table`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `hybrid`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `table`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `hybrid`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
