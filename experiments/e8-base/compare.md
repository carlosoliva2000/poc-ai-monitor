# Comparativa · e8-base

Perfiles: `qwen3-14b-t0` · escenarios: demo, nominal, wind, spoofing, hijack, faults · repeticiones: 1 · huella de `agent-assets`: da0582239a3a3c9a · vLLM: 0.31.0 · repositorio: e3d08e3b5b (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones).

## demo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 5.2 s · inv. 5.3 s / 12.7 s | 143844 / 3588 / 0 | 1 repetición |

## nominal

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 2743 / 316 / 0 | 1 repetición |

## wind

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 3.9 s · inv. 2.7 s / 10.0 s | 35539 / 1293 / 0 | 1 repetición |

## spoofing

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 5.5 s · inv. 7.4 s / 12.9 s | 57052 / 1927 / 0 | 1 repetición |

## hijack

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 3.6 s · inv. 5.3 s / 7.4 s | 54372 / 1439 / 0 | 1 repetición |

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 5 | 0 / 0 / 0 | 0.9 s / 5.4 s · inv. 9.0 s / 12.9 s | 196429 / 4192 / 0 | 1 repetición |

## Detalle de las repeticiones

- **demo · `qwen3-14b-t0`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **nominal · `qwen3-14b-t0`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
- **wind · `qwen3-14b-t0`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `qwen3-14b-t0`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `qwen3-14b-t0`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `qwen3-14b-t0`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
