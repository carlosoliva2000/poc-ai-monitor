# Comparativa · e14-1-informe

Perfiles: `actual` · escenarios: nominal, wind, spoofing, hijack, faults, demo · repeticiones: 1 · huella de `agent-assets`: c16120188410b179 · vLLM: 0.31.0 · repositorio: 2ebfe8f539 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones).

## nominal

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 3439 / 432 / 0 | 1 repetición |

## wind

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 1.8 s / 5.0 s · inv. 2.6 s / 13.2 s | 39847 / 1654 / 0 | 1 repetición |

## spoofing

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 6.2 s · inv. 8.6 s / 13.7 s | 72361 / 2154 / 0 | 1 repetición |

## hijack

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 4.1 s · inv. 6.3 s / 7.8 s | 60322 / 1734 / 0 | 1 repetición |

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 5 | 0 / 0 / 0 | 0.9 s / 6.4 s · inv. 7.4 s / 16.7 s | 208135 / 4925 / 0 | 1 repetición |

## demo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 5.8 s · inv. 6.6 s / 13.8 s | 158796 / 4282 / 0 | 1 repetición |

## Detalle de las repeticiones

- **nominal · `actual`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — ; 0 abiertas
- **wind · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `actual`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `actual`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
