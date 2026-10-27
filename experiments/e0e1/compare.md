# Comparativa · e0e1

Perfiles: `actual`, `qwen3-14b-t0`, `qwen3-30b-a3b-t0` · escenarios: demo, nominal, wind, spoofing, hijack, faults · repeticiones: 3 · huella de `agent-assets`: e28d071e856efb09 · vLLM: 0.31.0 · repositorio: 3c6de093f2

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones).

## demo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 3/3 · A2 3/3 · A3 3/3 | A1 3/3 · A2 3/3 · A3 3/3 | 0 | 0 | 0 | 6 | 0 / 0 / 2 | 14 | 0 / 0 / 0 | 0.9 s / 6.2 s · inv. 7.5 s / 18.3 s | 161366 / 4442 / n/d (0 car.) | estable (3/3) |
| `qwen3-14b-t0` | A1 3/3 · A2 3/3 · A3 3/3 | A1 3/3 · A2 3/3 · A3 3/3 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 9 | 0 / 0 / 0 | 0.9 s / 5.7 s · inv. 5.5 s / 13.9 s | 143944 / 3791 / 0 | estable (3/3) |
| `qwen3-30b-a3b-t0` | A1 3/3 · A2 2/3 · A3 2/3 | A1 3/3 · A2 3/3 · A3 3/3 | 2 | 1 | 7 | 0 | 0 / 0 / 0 | 28 | 0 / 0 / 0 | 0.4 s / 2.4 s · inv. 6.7 s / 8.4 s | 421615 / 6963 / 0 | 1/3 iguales — otras: A1 WIND ×1 cadenas, 0 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 0 cierres; A3 HIJACK ×1 cadenas, 0 cierres; 3 abiertas | A1 WIND ×1 cadenas, 0 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 sin diagnóstico ×1 cadenas, 0 cierres; 2 abiertas |

## nominal

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 2660 / 284 / n/d (0 car.) | estable (3/3) |
| `qwen3-14b-t0` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 2720 / 327 / 0 | estable (3/3) |
| `qwen3-30b-a3b-t0` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 2711 / 308 / 0 | estable (3/3) |

## wind

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 2 | 0 / 0 / 0 | 0.9 s / 5.4 s · inv. 1.7 s / 13.1 s | 33804 / 1179 / n/d (0 car.) | estable (3/3) |
| `qwen3-14b-t0` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 3.9 s · inv. 2.7 s / 10.1 s | 35500 / 1278 / 0 | estable (3/3) |
| `qwen3-30b-a3b-t0` | A1 3/3 | A1 3/3 | 0 | 0 | 2 | 0 | 0 / 0 / 0 | 4 | 0 / 0 / 0 | 0.4 s / 2.0 s · inv. 4.4 s / 6.9 s | 73667 / 1752 / 0 | 2/3 iguales — otras: A1 WIND ×1 cadenas, 1 cierres; 0 abiertas |

## spoofing

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 4 | 0 / 0 / 0 | 0.8 s / 6.1 s · inv. 9.3 s / 16.5 s | 86105 / 1940 / n/d (0 car.) | estable (3/3) |
| `qwen3-14b-t0` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.7 s / 5.7 s · inv. 7.5 s / 13.2 s | 56996 / 1886 / 0 | estable (3/3) |
| `qwen3-30b-a3b-t0` | A1 2/3 | A1 3/3 | 0 | 0 | 3 | 0 | 0 / 0 / 0 | 10 | 0 / 0 / 0 | 0.3 s / 2.4 s · inv. 6.5 s / 9.2 s | 157396 / 3049 / 0 | 2/3 iguales — otras: A1 GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; 1 abiertas |

## hijack

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 4.9 s · inv. 7.3 s / 9.2 s | 54506 / 1442 / n/d (0 car.) | estable (3/3) |
| `qwen3-14b-t0` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 3.6 s · inv. 5.5 s / 7.4 s | 54330 / 1411 / 0 | estable (3/3) |
| `qwen3-30b-a3b-t0` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.4 s / 1.7 s · inv. 2.9 s / 4.6 s | 79266 / 1594 / 0 | estable (3/3) |

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | F1 3/3 · F2 3/3 · F3 0/3 | F1 3/3 · F2 0/3 · F3 3/3 | 0 | 0 | 3 | 3 | 0 / 0 / 0 | 12 | 0 / 0 / 0 | 0.9 s / 6.1 s · inv. 8.6 s / 16.2 s | 199416 / 4177 / n/d (0 car.) | 2/3 iguales — otras: F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 SENSOR_FAULT/GPS_JAMMING/SENSOR_FAULT ×2 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas |
| `qwen3-14b-t0` | F1 3/3 · F2 3/3 · F3 0/3 | F1 3/3 · F2 3/3 · F3 3/3 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 9 | 0 / 0 / 0 | 0.9 s / 5.4 s · inv. 6.6 s / 12.8 s | 169311 / 3750 / 0 | estable (3/3) |
| `qwen3-30b-a3b-t0` | F1 3/3 · F2 3/3 · F3 0/3 | F1 3/3 · F2 2/3 · F3 3/3 | 0 | 2 | 2 | 0 | 0 / 0 / 0 | 28 | 0 / 0 / 0 | 0.4 s / 2.1 s · inv. 6.0 s / 7.6 s | 477954 / 6406 / 0 | 1/3 iguales — otras: F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; F3 GPS_JAMMING ×1 cadenas, 1 cierres; 1 abiertas | F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas |

## Detalle de las repeticiones

- **demo · `actual`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 2 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 2 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 2 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `qwen3-14b-t0`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `qwen3-30b-a3b-t0`**
  - r1: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 2 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 0 cierres; A2 GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 0 cierres; 2 abiertas
  - r2: ✅ 3/3 anomalías y fallos diagnosticados · 1 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 3 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 0 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 0 cierres; A3 HIJACK ×1 cadenas, 0 cierres; 3 abiertas
  - r3: ⚠️ 2/3 anomalías y fallos diagnosticados · 1 falsas alarmas · 1 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 2 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 0 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 sin diagnóstico ×1 cadenas, 0 cierres; 2 abiertas
- **nominal · `actual`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
  - r2: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
  - r3: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
- **nominal · `qwen3-14b-t0`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
  - r2: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
  - r3: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
- **nominal · `qwen3-30b-a3b-t0`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
  - r2: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
  - r3: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
- **wind · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `qwen3-14b-t0`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `qwen3-30b-a3b-t0`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 0 cierres; 1 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 0 cierres; 1 abiertas
- **spoofing · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `qwen3-14b-t0`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `qwen3-30b-a3b-t0`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 0 cierres; 1 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 0 cierres; 1 abiertas
  - r3: ❌ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; 1 abiertas
- **hijack · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `qwen3-14b-t0`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `qwen3-30b-a3b-t0`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `actual`**
  - r1: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 SENSOR_FAULT/GPS_JAMMING/SENSOR_FAULT ×2 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas
  - r2: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 1 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 SENSOR_FAULT/GPS_JAMMING/SENSOR_FAULT ×2 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 1 abiertas
  - r3: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 2 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 SENSOR_FAULT/GPS_JAMMING/SENSOR_FAULT ×2 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 1 abiertas
- **faults · `qwen3-14b-t0`**
  - r1: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas
  - r2: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas
  - r3: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas
- **faults · `qwen3-30b-a3b-t0`**
  - r1: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 1 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×2 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 1 abiertas
  - r2: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; F3 GPS_JAMMING ×1 cadenas, 1 cierres; 1 abiertas
  - r3: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 1 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas
