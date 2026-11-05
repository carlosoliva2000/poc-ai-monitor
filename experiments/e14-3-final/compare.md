# Comparativa · e14-3-final

Perfiles: `actual`, `gpt-oss-20b-low` · escenarios: nominal, wind, spoofing, hijack, faults, demo · repeticiones: 3 · huella de `agent-assets`: d358e3d292c769e0 · vLLM: 0.31.0 · repositorio: 9974120f43 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones); las iteraciones, percentiles de las invocaciones del monitor con LLM.

## nominal

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 4266 / 517 / 0 | estable (3/3) |
| `gpt-oss-20b-low` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | n/d | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | n/d | 4397 / 599 / 48 | estable (3/3) |

## wind

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 1.0 s / 4.8 s · inv. 2.6 s / 13.2 s | 2 / 5 / 5 | 46460 / 1655 / 0 | estable (3/3) |
| `gpt-oss-20b-low` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | 1.3 s / 5.4 s · inv. 4.6 s / 8.1 s | 2 / 3 / 3 | 29475 / 1529 / 497 | estable (3/3) |

## spoofing

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 1.0 s / 7.2 s · inv. 9.4 s / 16.5 s | 4 / 5 / 5 | 72838 / 2449 / 0 | estable (3/3) |
| `gpt-oss-20b-low` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 1.0 s / 7.8 s · inv. 9.3 s / 15.7 s | 4 / 5 / 5 | 60705 / 2389 / 1101 | estable (3/3) |

## hijack

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 6 | 0 / 0 / 0 | 0.9 s / 5.0 s · inv. 7.4 s / 14.0 s | 4 / 5 / 5 | 73978 / 2197 / 0 | estable (3/3) |
| `gpt-oss-20b-low` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | 1.0 s / 5.9 s · inv. 8.2 s / 9.5 s | 4 / 4 / 4 | 60564 / 2124 / 775 | estable (3/3) |

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | F1 3/3 · F2 3/3 · F3 3/3 | F1 3/3 · F2 3/3 · F3 3/3 | 0 | 0 | 0 | 0 | 0 | 0 · veto 3 · sin métricas 0 | 0 / 0 / 0 | 19 | 0 / 0 / 0 | 0.9 s / 5.8 s · inv. 7.4 s / 20.7 s | 4 / 8 / 8 | 254537 / 5230 / 0 | estable (3/3) |
| `gpt-oss-20b-low` | F1 2/3 · F2 3/3 · F3 3/3 | F1 3/3 · F2 3/3 · F3 3/3 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 11 | 0 / 0 / 0 | 1.0 s / 7.1 s · inv. 7.8 s / 21.3 s | 3 / 7 / 8 | 182994 / 5138 / 2888 | 2/3 iguales — otras: F1 UNKNOWN ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas |

## demo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 3/3 · A2 3/3 · A3 3/3 | A1 3/3 · A2 3/3 · A3 3/3 | 0 | 0 | 0 | 0 | 0 | 0 · veto 3 · sin métricas 0 | 0 / 0 / 0 | 15 | 0 / 0 / 0 | 1.0 s / 6.2 s · inv. 6.4 s / 24.7 s | 4 / 9 / 9 | 225862 / 5138 / 0 | estable (3/3) |
| `gpt-oss-20b-low` | A1 3/3 · A2 3/3 · A3 3/3 | A1 3/3 · A2 3/3 · A3 3/3 | 0 | 0 | 0 | 0 | 0 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 1.0 s / 7.2 s · inv. 7.7 s / 17.6 s | 3 / 7 / 8 | 158773 / 4981 / 2541 | estable (3/3) |

## Detalle de las repeticiones

- **nominal · `actual`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
  - r2: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
  - r3: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
- **nominal · `gpt-oss-20b-low`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
  - r2: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
  - r3: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · n/d recuperaciones sin fase recovering — ; 0 abiertas
- **wind · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `gpt-oss-20b-low`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `gpt-oss-20b-low`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `gpt-oss-20b-low`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `actual`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `gpt-oss-20b-low`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 UNKNOWN ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `actual`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `gpt-oss-20b-low`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
