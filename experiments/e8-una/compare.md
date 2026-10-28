# Comparativa · e8-una

Perfiles: `qwen3-14b-t0-sin-coherence-guardrail`, `qwen3-14b-t0-sin-computed-facts`, `qwen3-14b-t0-sin-final-tools-only`, `qwen3-14b-t0-sin-require-checks`, `qwen3-14b-t0-sin-silent-own-alert`, `qwen3-14b-t0-sin-tool-choice` · escenarios: demo, nominal, wind, spoofing, hijack, faults · repeticiones: 1 · huella de `agent-assets`: da0582239a3a3c9a · vLLM: 0.31.0 · repositorio: e3d08e3b5b (con cambios sin guardar)

Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones).

## demo

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0-sin-coherence-guardrail` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 2 | 0 / 0 / 0 | 0.9 s / 5.1 s · inv. 5.7 s / 9.5 s | 137602 / 3489 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-computed-facts` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 8 | 0 / 0 / 0 | 0.9 s / 5.2 s · inv. 8.7 s / 19.7 s | 186896 / 4936 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-final-tools-only` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 5.8 s · inv. 5.4 s / 14.1 s | 143947 / 3781 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-require-checks` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 5.2 s · inv. 5.4 s / 12.8 s | 143784 / 3747 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-silent-own-alert` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 5.9 s · inv. 5.5 s / 14.2 s | 143851 / 3710 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-tool-choice` | A1 1/1 · A2 1/1 · A3 1/1 | A1 1/1 · A2 1/1 · A3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 5.7 s · inv. 5.4 s / 13.7 s | 143894 / 3705 / 0 | 1 repetición |

## nominal

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0-sin-coherence-guardrail` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 2740 / 324 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-computed-facts` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 2712 / 326 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-final-tools-only` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 2725 / 319 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-require-checks` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 2768 / 349 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-silent-own-alert` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 2730 / 351 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-tool-choice` | sin etiquetas | — | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | n/d / n/d · inv. n/d / n/d | 2763 / 381 / 0 | 1 repetición |

## wind

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0-sin-coherence-guardrail` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 / 0 / 0 | 0.7 s / 3.9 s · inv. 2.7 s / 6.1 s | 29872 / 1033 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-computed-facts` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 3.6 s · inv. 3.2 s / 9.3 s | 35371 / 1348 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-final-tools-only` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.7 s / 3.6 s · inv. 2.7 s / 8.8 s | 35509 / 1285 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-require-checks` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 3.9 s · inv. 2.6 s / 10.0 s | 35487 / 1258 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-silent-own-alert` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 3.9 s · inv. 2.7 s / 10.0 s | 35515 / 1265 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-tool-choice` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 3.9 s · inv. 2.8 s / 9.8 s | 35613 / 1330 / 0 | 1 repetición |

## spoofing

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0-sin-coherence-guardrail` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 5.4 s · inv. 7.7 s / 8.8 s | 56399 / 1615 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-computed-facts` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 2 | 0 / 0 / 0 | 0.9 s / 4.5 s · inv. 10.5 s / 11.8 s | 68920 / 2006 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-final-tools-only` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 5.7 s · inv. 7.4 s / 13.2 s | 57026 / 1906 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-require-checks` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 5.7 s · inv. 7.4 s / 13.2 s | 56985 / 1859 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-silent-own-alert` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 5.7 s · inv. 7.4 s / 13.1 s | 56996 / 1902 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-tool-choice` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 5.8 s · inv. 7.6 s / 13.4 s | 56935 / 1798 / 0 | 1 repetición |

## hijack

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0-sin-coherence-guardrail` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 3.6 s · inv. 5.4 s / 7.3 s | 54337 / 1436 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-computed-facts` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 4.1 s · inv. 9.1 s / 11.3 s | 65633 / 1876 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-final-tools-only` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 3.7 s · inv. 5.4 s / 7.2 s | 54370 / 1409 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-require-checks` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 3.7 s · inv. 5.3 s / 7.5 s | 54297 / 1392 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-silent-own-alert` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 3.7 s · inv. 5.5 s / 7.2 s | 54377 / 1467 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-tool-choice` | A1 1/1 | A1 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 1 | 0 / 0 / 0 | 0.9 s / 3.7 s · inv. 5.3 s / 7.6 s | 54325 / 1378 / 0 | 1 repetición |

## faults

| Perfil | Aciertos (✅ por etiqueta) | 1 cadena | Falsas alarmas | Fallbacks | Alertas abiertas | Frases que contradicen | No latinos (monitor / informe / chats) | Rechazos guardrails | Cortes por longitud (monitor / informe / chats) | Latencia monitor p50 / p95 | Tokens por ejecución (prompt / respuesta / razonamiento) | Estabilidad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3-14b-t0-sin-coherence-guardrail` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 4 | 0 / 0 / 0 | 0.9 s / 5.4 s · inv. 7.7 s / 9.8 s | 185171 / 3819 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-computed-facts` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 2 | 0 / 0 / 0 | 12 | 0 / 0 / 0 | 0.9 s / 4.7 s · inv. 14.6 s / 21.4 s | 290575 / 6153 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-final-tools-only` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 5 | 0 / 0 / 0 | 0.9 s / 5.4 s · inv. 9.3 s / 12.9 s | 196483 / 4273 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-require-checks` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 0/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 5 | 0 / 0 / 0 | 0.9 s / 4.7 s · inv. 6.1 s / 13.3 s | 209484 / 4448 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-silent-own-alert` | F1 1/1 · F2 1/1 · F3 0/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 3 | 0 / 0 / 0 | 0.9 s / 5.2 s · inv. 6.5 s / 12.6 s | 169328 / 3749 / 0 | 1 repetición |
| `qwen3-14b-t0-sin-tool-choice` | F1 1/1 · F2 1/1 · F3 1/1 | F1 1/1 · F2 1/1 · F3 1/1 | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 4 | 0 / 0 / 0 | 0.9 s / 5.4 s · inv. 7.8 s / 12.9 s | 183964 / 4087 / 0 | 1 repetición |

## Detalle de las repeticiones

- **demo · `qwen3-14b-t0-sin-coherence-guardrail`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `qwen3-14b-t0-sin-computed-facts`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `qwen3-14b-t0-sin-final-tools-only`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `qwen3-14b-t0-sin-require-checks`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `qwen3-14b-t0-sin-silent-own-alert`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **demo · `qwen3-14b-t0-sin-tool-choice`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; A2 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; A3 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **nominal · `qwen3-14b-t0-sin-coherence-guardrail`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
- **nominal · `qwen3-14b-t0-sin-computed-facts`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
- **nominal · `qwen3-14b-t0-sin-final-tools-only`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
- **nominal · `qwen3-14b-t0-sin-require-checks`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
- **nominal · `qwen3-14b-t0-sin-silent-own-alert`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
- **nominal · `qwen3-14b-t0-sin-tool-choice`**
  - r1: ✅ 0/0 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — ; 0 abiertas
- **wind · `qwen3-14b-t0-sin-coherence-guardrail`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `qwen3-14b-t0-sin-computed-facts`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `qwen3-14b-t0-sin-final-tools-only`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `qwen3-14b-t0-sin-require-checks`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `qwen3-14b-t0-sin-silent-own-alert`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **wind · `qwen3-14b-t0-sin-tool-choice`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 WIND ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `qwen3-14b-t0-sin-coherence-guardrail`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `qwen3-14b-t0-sin-computed-facts`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `qwen3-14b-t0-sin-final-tools-only`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `qwen3-14b-t0-sin-require-checks`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `qwen3-14b-t0-sin-silent-own-alert`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **spoofing · `qwen3-14b-t0-sin-tool-choice`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 GPS_SPOOFING/GPS_SPOOFING ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `qwen3-14b-t0-sin-coherence-guardrail`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `qwen3-14b-t0-sin-computed-facts`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `qwen3-14b-t0-sin-final-tools-only`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `qwen3-14b-t0-sin-require-checks`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `qwen3-14b-t0-sin-silent-own-alert`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **hijack · `qwen3-14b-t0-sin-tool-choice`**
  - r1: ✅ 1/1 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — A1 HIJACK ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `qwen3-14b-t0-sin-coherence-guardrail`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `qwen3-14b-t0-sin-computed-facts`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 2 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `qwen3-14b-t0-sin-final-tools-only`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `qwen3-14b-t0-sin-require-checks`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×2 cadenas, 2 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
- **faults · `qwen3-14b-t0-sin-silent-own-alert`**
  - r1: ❌ 2/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 GPS_JAMMING ×1 cadenas, 0 cierres; 0 abiertas
- **faults · `qwen3-14b-t0-sin-tool-choice`**
  - r1: ✅ 3/3 anomalías y fallos diagnosticados · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 detecciones sin respuesta · 0 alertas abiertas al final · 0 frases que contradicen los checks — F1 SENSOR_FAULT ×1 cadenas, 1 cierres; F2 GPS_JAMMING/GPS_JAMMING/GPS_JAMMING ×1 cadenas, 1 cierres; F3 SENSOR_FAULT ×1 cadenas, 1 cierres; 0 abiertas
