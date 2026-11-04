# Comparativa · e14-1-final

Perfiles: `gpt-oss-20b-low`, `qwen3-32b-awq`, `qwen3-30b-a3b-2507` · escenarios: nominal, wind, spoofing, hijack, faults, demo · repeticiones: 1 · huella de `agent-assets`: c16120188410b179 · vLLM: 0.31.0 · repositorio: 2ebfe8f539 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones).

## nominal

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `gpt-oss-20b-low` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 3548 / 483 / 60 | 1 repetición |
| `qwen3-32b-awq` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 3409 / 426 / 0 | 1 repetición |
| `qwen3-30b-a3b-2507` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 3598 / 617 / n/d (0 car.) | 1 repetición |

## wind

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `gpt-oss-20b-low` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | 1.5 s / 4.7 s · inv. 2.8 s / 7.3 s | 24828 / 1548 / 323 | 1 repetición |
| `qwen3-32b-awq` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 2.2 s / 8.7 s · inv. 3.9 s / 25.3 s | 39657 / 1483 / 0 | 1 repetición |
| `qwen3-30b-a3b-2507` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.4 s / 2.2 s · inv. 1.9 s / 6.4 s | 56318 / 1896 / n/d (0 car.) | 1 repetición |

## spoofing

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `gpt-oss-20b-low` | A1 0/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 1.0 s / 7.5 s · inv. 10.6 s / 11.3 s | 55407 / 2038 / 980 | 1 repetición |
| `qwen3-32b-awq` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 1.6 s / 11.5 s · inv. 17.6 s / 30.4 s | 87382 / 2257 / 0 | 1 repetición |
| `qwen3-30b-a3b-2507` | A1 0/1 | A1 1/1 | 0 | 3 | 0 | 0 | 0 | 0 / 0 / 0 | 5 | 0 / 0 / 0 | 0.3 s / 3.8 s · inv. 7.4 s / 12.8 s | 252171 / 3652 / n/d (0 car.) | 1 repetición |

## hijack

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `gpt-oss-20b-low` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 1.0 s / 6.3 s · inv. 8.0 s / 10.3 s | 53583 / 2191 / 812 | 1 repetición |
| `qwen3-32b-awq` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 1.7 s / 9.5 s · inv. 15.5 s / 16.8 s | 67397 / 1690 / 0 | 1 repetición |
| `qwen3-30b-a3b-2507` | A1 1/1 | A1 1/1 | 0 | 1 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.3 s / 2.4 s · inv. 3.5 s / 6.4 s | 119894 / 2691 / n/d (0 car.) | 1 repetición |

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `gpt-oss-20b-low` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 11 | 0 / 0 / 0 | 2.0 s / 6.3 s · inv. 9.8 s / 27.3 s | 223813 / 6402 / 4079 | 1 repetición |
| `qwen3-32b-awq` | F1 1/1 · F2 1/1 · F3 0/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 4 | 0 / 0 / 0 | 2.2 s / 9.6 s · inv. 12.8 s / 26.9 s | 199930 / 4110 / 0 | 1 repetición |
| `qwen3-30b-a3b-2507` | F1 0/1 · F2 0/1 · F3 0/1 | F1 1/1 · F2 0/1 · F3 0/1 | 0 | 5 | 0 | 0 | 0 | 0 / 0 / 0 | 13 | 0 / 0 / 0 | 0.3 s / 3.0 s · inv. 6.7 s / 16.6 s | 584542 / 9322 / n/d (0 car.) | 1 repetición |

## demo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `gpt-oss-20b-low` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 1.0 s / 6.1 s · inv. 6.8 s / 16.4 s | 131991 / 4620 / 2049 | 1 repetición |
| `qwen3-32b-awq` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 4 | 0 / 0 / 0 | 2.1 s / 10.4 s · inv. 15.1 s / 28.7 s | 182602 / 4310 / 0 | 1 repetición |
| `qwen3-30b-a3b-2507` | A1 1/1 · A2 0/1 · A3 0/1 | A1 1/1 · A2 0/1 · A3 1/1 | 0 | 4 | 0 | 0 | 0 | 0 / 0 / 0 | 8 | 0 / 0 / 0 | 0.3 s / 3.1 s · inv. 6.4 s / 11.6 s | 550046 / 7844 / n/d (0 car.) | 1 repetición |

## Detalle de las repeticiones

- **nominal · `gpt-oss-20b-low`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — ; 0 abiertas
- **nominal · `qwen3-32b-awq`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — ; 0 abiertas
- **nominal · `qwen3-30b-a3b-2507`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — ; 0 abiertas
- **wind · `gpt-oss-20b-low`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `qwen3-32b-awq`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `qwen3-30b-a3b-2507`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `gpt-oss-20b-low`**
  - r1: ❌ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 SENSOR_FAULT/SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `qwen3-32b-awq`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `qwen3-30b-a3b-2507`**
  - r1: ❌ 0/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 3 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 sin diagnóstico/sin diagnóstico ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `gpt-oss-20b-low`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `qwen3-32b-awq`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `qwen3-30b-a3b-2507`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 1 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `gpt-oss-20b-low`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `qwen3-32b-awq`**
  - r1: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `qwen3-30b-a3b-2507`**
  - r1: ❌ 0/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 5 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — F1 UNKNOWN ×1 cadenas, 1 cierres; F2 sin diagnóstico/sin diagnóstico/sin diagnóstico ×2 cadenas, 2 cierres; F3 sin diagnóstico ×0 cadenas, 0 cierres; 0 abiertas
- **demo · `gpt-oss-20b-low`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `qwen3-32b-awq`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `qwen3-30b-a3b-2507`**
  - r1: ❌ 1/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 4 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 WIND ×1 cadenas, 1 cierres; A2 sin diagnóstico/HIJACK ×2 cadenas, 2 cierres; A3 sin diagnóstico ×1 cadenas, 1 cierres; 0 abiertas
