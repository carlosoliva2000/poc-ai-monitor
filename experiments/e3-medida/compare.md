# Comparativa · e3-medida

Perfiles: `qwen3-14b-think` · escenarios: demo · repeticiones: 1 · huella de `agent-assets`: e28d071e856efb09 · vLLM: 0.31.0 · repositorio: a17a835fa8

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones).

## demo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-think` | A1 1/1 · A2 0/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 2 | 0 / 0 / 0 | 8.9 s / 16.3 s · inv. 35.3 s / 65.4 s | 176742 / 18798 / 14896 | 1 repetición |

## Detalle de las repeticiones

- **demo · `qwen3-14b-think`**
  - r1: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 SENSOR_FAULT/SENSOR_FAULT ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
