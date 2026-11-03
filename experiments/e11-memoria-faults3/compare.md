# Comparativa · e11-memoria-faults3

Perfiles: `actual-memoria-a` · escenarios: faults · repeticiones: 3 · huella de `agent-assets`: 40d9cff3f1e110f3 · vLLM: 0.31.0 · repositorio: fb23fbe7e9 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones).

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual-memoria-a` | F1 3/3 · F2 3/3 · F3 3/3 | F1 3/3 · F2 3/3 · F3 3/3 | 0 | 0 | 3 | 0 | 0 | 0 / 0 / 0 | 14 | 0 / 0 / 0 | 1.1 s / 5.5 s · inv. 7.7 s / 15.9 s | 573543 / 4075 / 0 | estable (3/3) |

## Detalle de las repeticiones

- **faults · `actual-memoria-a`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 1 abiertas
  - r2: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 1 abiertas
  - r3: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 0 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 1 abiertas
