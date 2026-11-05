# Comparativa · e14-3-now-spoof3

Perfiles: `actual` · escenarios: spoofing · repeticiones: 3 · huella de `agent-assets`: 11230dc56ed275d3 · vLLM: 0.31.0 · repositorio: 9974120f43 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones); las iteraciones, percentiles de las invocaciones del monitor con LLM.

## spoofing

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual` | A1 3/3 | A1 3/3 | 0 | 0 | 0 | 0 | 0 | 3 (window_without_jump 3) · veto 0 · sin métricas 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 6.9 s · inv. 9.6 s / 11.3 s | 4 / 8 / 8 | 99218 / 2051 / 0 | estable (3/3) |

## Detalle de las repeticiones

- **spoofing · `actual`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
  - r2: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
  - r3: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 1 recuperaciones sin fase recovering — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
