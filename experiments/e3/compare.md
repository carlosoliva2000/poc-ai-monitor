# Comparativa · e3

Perfiles: `qwen3-14b-think` · escenarios: demo, faults, spoofing · repeticiones: 3 · huella de `agent-assets`: e28d071e856efb09 · vLLM: 0.31.0 · repositorio: a17a835fa8 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones).

## demo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-think` | A1 3/3 · A2 1/3 · A3 2/3 | A1 3/3 · A2 1/3 · A3 3/3 | 0 | 1 | 1 | 0 | 0 / 0 / 0 | 8 | 0 / 0 / 0 | 8.6 s / 18.3 s · inv. 30.3 s / 66.0 s | 167293 / 19118 / 14889 | 1/3 iguales — otras: A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas | A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/UNKNOWN ×2 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 1 abiertas |

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-think` | F1 3/3 · F2 3/3 · F3 0/3 | F1 3/3 · F2 3/3 · F3 3/3 | 0 | 0 | 2 | 0 | 0 / 0 / 0 | 2 | 0 / 0 / 0 | 8.7 s / 16.9 s · inv. 19.4 s / 62.0 s | 120817 / 13576 / 10853 | 2/3 iguales — otras: F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas |

## spoofing

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-think` | A1 2/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | 9.2 s / 18.2 s · inv. 37.7 s / 72.9 s | 55821 / 7400 / 5939 | 2/3 iguales — otras: A1 SENSOR_FAULT/SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas |

## Detalle de las repeticiones

- **demo · `qwen3-14b-think`**
  - r1: ⚠️ 1/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 1 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/UNKNOWN ×2 cadenas, 2 cierres; A3 UNKNOWN ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ⚠️ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/UNKNOWN ×2 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 1 abiertas
- **faults · `qwen3-14b-think`**
  - r1: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 SENSOR_FAULT/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 1 abiertas
  - r2: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas
  - r3: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 SENSOR_FAULT/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 1 abiertas
- **spoofing · `qwen3-14b-think`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ❌ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 SENSOR_FAULT/SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
