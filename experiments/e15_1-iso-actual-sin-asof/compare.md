# Comparativa · e15_1-iso-actual-sin-asof

Perfiles: `actual-sin-asof` · escenarios: demo-battery · repeticiones: 3 · huella de `agent-assets`: 2babe22e39116f71 · vLLM: 0.31.0 · repositorio: a2a5362f82 (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones); las iteraciones, percentiles de las invocaciones del monitor con LLM.

## demo-battery

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | Checks≠tools | Recuperación sin fase | No latinos (monitor / informe / chats) | Rechazos guardrails | Rechazos link=null / rellenos | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Iteraciones monitor p50 / p95 / máx | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `actual-sin-asof` | A1 3/3 · A2 2/3 · A3 3/3 · F1 3/3 | A1 3/3 · A2 3/3 · A3 3/3 · F1 3/3 | 0 | 0 | 3 | 0 | 0 | 0 · veto 3 · sin métricas 0 · salto del módulo 3, ventana del modelo sin verlo 0 | 0 / 0 / 0 | 13 | 0 / 6 | 0 / 0 / 0 | 0.9 s / 5.7 s · inv. 7.8 s / 15.4 s | 4 / 6 / 6 | 300999 / 5351 / 0 | 2/3 iguales — otras: A1 WIND ×1 cadenas, 1 cierres; A2 SENSOR_FAULT/SENSOR_FAULT ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas |

## Detalle de las repeticiones

- **demo-battery · `actual-sin-asof`**
  - r1: ✅ 4/4 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas
  - r2: ❌ 3/4 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 SENSOR_FAULT/SENSOR_FAULT ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas
  - r3: ✅ 4/4 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 1 alertas abiertas al final · 0 frases que contradicen los checks · 0 checks que no cuadran con las tools · 0 recuperaciones sin fase recovering — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK/HIJACK ×1 cadenas, 1 cierres; F1 SENSOR_FAULT ×1 cadenas, 0 cierres; 1 abiertas
