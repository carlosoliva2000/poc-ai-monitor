# Comparativa · e5-sonnet-b

Perfiles: `claude-sonnet-5-5-b` · escenarios: demo, faults · repeticiones: 1 · huella de `agent-assets`: d71cd7ec17440056 · vLLM: n/d · repositorio: b4d3a2b674 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones); las iteraciones, percentiles de las invocaciones del monitor con LLM.

## demo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `claude-sonnet-5-5-b` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 2 | 1 (window_without_jump 1) · veto 0 · sin métricas 0 | 0 / 0 / 0 | 2 | 0 / 0 | 0 / 0 / 0 | 1.8 s / 4.7 s · inv. 6.6 s / 11.5 s | 3 / 4 / 4 | 233372 / 10039 / 717 | 1 repetición |

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `claude-sonnet-5-5-b` | F1 1/1 · F2 1/1 · F3 0/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 5 | 0 · veto 0 · sin métricas 0 | 0 / 0 / 0 | 3 | 0 / 0 | 0 / 0 / 0 | 2.0 s / 4.9 s · inv. 8.4 s / 14.1 s | 3 / 5 / 5 | 226222 / 10077 / 286 | 1 repetición |

## Checks que no cuadran con las tools, por campo

| Perfil | wind_with_drift |
|---|---|
| `claude-sonnet-5-5-b` | 7 |

## Detalle de las repeticiones

- **demo · `claude-sonnet-5-5-b`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 2 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `claude-sonnet-5-5-b`**
  - r1: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 5 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas
