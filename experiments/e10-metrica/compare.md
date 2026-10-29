# Comparativa · e10-metrica

Perfiles: `qwen3-14b-t0-sin-hechos-sin-coherencia` · escenarios: faults · repeticiones: 1 · huella de `agent-assets`: e41c4a68a68dfa93 · vLLM: 0.31.0 · repositorio: 9302d105c4 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones).

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0-sin-hechos-sin-coherencia` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 6 | 0 / 0 / 0 | 4 | 0 / 0 / 0 | 1.0 s / 4.7 s · inv. 8.1 s / 11.2 s | 178202 / 3764 / 0 | 1 repetición |

## Checks que no cuadran con las tools, por campo

| Perfil | gps_radar_disagreed | wind_notable |
|---|---|---|
| `qwen3-14b-t0-sin-hechos-sin-coherencia` | 3 | 3 |

## Detalle de las repeticiones

- **faults · `qwen3-14b-t0-sin-hechos-sin-coherencia`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 6 checks que no cuadran con las tools — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
