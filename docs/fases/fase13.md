# Fase 13 · E4: modelos nuevos (03/11/2026) — parte E4a

Escrito para: Carlos, que decide si se sigue con E4b/E4c y qué modelo por defecto. Contratos **sin cambios**. Configuración de la prueba: la de hoy (todas las ayudas encendidas; modo guiado y memoria A apagados), huella de `agent-assets` `293927dd0c038af5` (la misma que la base; confirmada en cada `manifest.json`). Base: `experiments/e12-cierre/` (perfil `actual`, Qwen3-14B-AWQ, no se repite). **No se ha cambiado el modelo por defecto.** `qwen2.5-14b` no se ha probado (E4a no lo exigía y queda para si sobra tiempo).

## Resumen

| Modelo (quién publica) | Arranque | Nivel 1 | Matriz (6 escenarios) | Veredicto |
|---|---|---|---|---|
| `Qwen/Qwen3-14B-FP8` (Qwen) | 3.er intento; **contexto 28 000** y `VLLM_USE_DEEP_GEMM=0` | PASA | ×1: igual que la base en todo; **más lento** (p50 de invocación 8,6 s frente a 7,0 s) | Entra; no mejora a `actual` |
| `Qwen/Qwen3-32B-AWQ` (Qwen) | 3.er intento; **contexto 10 240**, KV en FP8, atención `TRITON_ATTN` | PASA | ×1: **F3 falla**, el resto igual; **el doble de lento** (12,7 s / 27,8 s) | Entra; peor que `actual` |
| `stelterlab/Qwen3-30B-A3B-Instruct-2507-AWQ` (comunidad) | 1.er intento, 32 768 | PASA | ×1: **5 fallbacks**, F1 y F3 ❌, 2× rechazos, 2,3× tokens | Entra; peor que `actual` |
| `mistralai/Ministral-3-14B-Instruct-2512` (Mistral) | 1.er intento, 32 768, sin visión | PASA | ×3 (no reproducible): **`wind` 1/3**, 13 cortes por longitud, 2,4× más lento | Entra; peor que `actual` |
| `openai/gpt-oss-20b` (OpenAI) | 2.º intento (`--enforce-eager` + `TRITON_ATTN`) | **FALLA 6a** (ver §4) | no se ejecutó (regla del banco) | **Descartado** (con una duda abierta) |

Ningún modelo supera a `actual`. El más cercano es el mismo modelo en FP8 (empata en calidad y pierde en velocidad); el 30B-A3B-2507 es el único más rápido por llamada, pero hace más del doble de llamadas y pierde decisiones.

## 1. Descargas
Todas desde Hugging Face, sin token, una detrás de otra y en segundo plano, **sin ninguna matriz en marcha** (así que no hay latencias contaminadas por descargas). ~133 MB/s. Espacio libre antes: 850 GB; después: 773 GB. Antes de descargar se comprobó la ficha por la API (`huggingface.co/api/models/<repo>`): públicos, no *gated*.

| Modelo | Fichero(s) descargados | Tamaño | Tiempo |
|---|---|---|---|
| `Qwen/Qwen3-14B-FP8` | safetensors oficiales | 16 GB | 261 s |
| `Qwen/Qwen3-32B-AWQ` | safetensors oficiales | 19 GB | 326 s |
| `stelterlab/Qwen3-30B-A3B-Instruct-2507-AWQ` | safetensors | 16 GB | 266 s |
| `mistralai/Ministral-3-14B-Instruct-2512` | solo `consolidated.safetensors` + `params.json`/`tekken.json` (formato Mistral; sin los 4 shards de HF) | 15 GB | 249 s |
| `openai/gpt-oss-20b` | sin `original/` ni `metal/` | 13 GB | 217 s |

- **Cuantización de la comunidad:** la ficha de `stelterlab` dice «AWQ», pero su `config.json` es `compressed-tensors` (`pack-quantized`, 4 bits, grupos de 128), hecha con llm-compressor y probada por su autor con vLLM 0.9.2; licencia apache-2.0. Si este modelo sale peor, puede ser la cuantización.
- El script de descarga y su registro están en la carpeta temporal de la sesión; no entran en el repo.

## 2. Arranque y banco (niveles 0 y 1)
Todos con `serve.sh start <perfil>` (el mismo comando que usa la matriz), vLLM 0.31.0, `HF_HUB_OFFLINE=1`, vigilancia de 180 s de log congelado y 25 min máximos. GPU en reposo 0 MiB. Banco: `~/llm-bench/nivel0_perfil.py` y `nivel1_e4.py` (ficheros nuevos; el banco original no se tocó). Resultados copiados a `results/` (ver §9).

| Modelo | Hasta `/health` | GPU cargado | Pesos | Caché KV («GPU KV cache size») | Contexto |
|---|---|---|---|---|---|
| `qwen3-14b-fp8` | 74 s | 21 266 MiB | 15,33 GiB | 28 592 tok (1,02×) | **28 000** |
| `qwen3-32b-awq` | 98 s | 21 332 MiB | 18,24 GiB | 10 432 tok (1,02×), KV en FP8 | **10 240** |
| `qwen3-30b-a3b-2507` | 107 s | 22 422 MiB | 15,7 GiB | 53 200 tok (1,62×) | 32 768 |
| `ministral-3-14b` | 80 s | 21 498 MiB | 13,89 GiB | 39 728 tok (1,21×) | 32 768 |
| `gpt-oss-20b-low` | 27 s | 22 666 MiB | 13,8 GiB | 288 069 tok (8,79×) | 32 768 |

### Intentos de arranque fallidos (errores literales)
- **`qwen3-14b-fp8`, intento 1** (36 s): `RuntimeError: Assertion error (…/deep_jit/backend/cuda/backend.hpp:200): not home_path.empty() and std::filesystem::exists(home_path)` en `deepgemm_post_process_fp8_weight_block` (kernel `DeepGemmFp8BlockScaledMMKernel`): DeepGEMM no encuentra un CUDA toolkit. **Intento 2** con `VLLM_USE_DEEP_GEMM=0`: cargó (15,33 GiB) pero `ValueError: To serve at least one request with the model's max seq len (32768), (5.0 GiB KV cache is needed, which is larger than the available KV cache memory (4.36 GiB)… the estimated maximum model length is 28544`. **Intento 3**: `max_model_len: 28000`, PASA. Se bajó el contexto en vez de usar KV en FP8 para no mezclar otra variable en lo que es el control de la cuantización. **Hace falta `VLLM_USE_DEEP_GEMM=0` al arrancar este modelo** (`serve.sh` y los perfiles no llevan variables de entorno: se exportó en la sesión; ver §8).
- **`qwen3-32b-awq`, intento a:** `ValueError: … (8.0 GiB KV cache is needed, which is larger than the available KV cache memory (1.26 GiB))… estimated maximum model length is 5136` (la estimación del plan, ~16 k, era optimista: son 256 KiB por token). **Intento b** (`--kv-cache-dtype fp8`, 10 240): `RuntimeError: Could not find nvcc and default cuda_home='/usr/local/cuda' doesn't exist` (con KV en FP8 vLLM elige FLASHINFER y compila con `nvcc`). **Intento c** (`--attention-backend TRITON_ATTN`): PASA. Los intentos a y b son la escalera de memoria prevista; c es el reintento por fallo de arranque.
- **`gpt-oss-20b`, intento 1** (`--enforce-eager`): MXFP4 con backend MoE `MARLIN` bien, y luego `RuntimeError: FlashInfer backend is not available`. **Intento 2** (`--attention-backend TRITON_ATTN`): PASA.
- Sin cuelgues de Windows, WSL ni vLLM en ningún momento; GPU y puerto liberados tras cada fallo (`serve.sh` y comprobación manual).

### Nivel 1 (modo A: T=0, sin razonamiento salvo gpt-oss, 5 repeticiones por caso, 75 respuestas)
| | 1–5, 6b, 7, 8a, 9 | 6a | 8b (idioma, informativo) | Velocidad |
|---|---|---|---|---|
| `qwen3-14b-fp8` | 5/5 | 5/5 | 5/5 | 43 tok/s |
| `qwen3-32b-awq` | 5/5 | 5/5 | **0/5** (responde en español) | 33 tok/s |
| `qwen3-30b-a3b-2507` | 5/5 | 5/5 | 5/5 | 160 tok/s |
| `ministral-3-14b` | 5/5 | 5/5 | **0/5** (responde en español) | 47 tok/s |
| `gpt-oss-20b-low` | 5/5 | **0/5** | 5/5 | 47 tok/s |
Referencia `actual` (fase 7, sin repetir): 57–65 tok/s. Ninguna respuesta cortada por longitud ni con fugas de formato; `required` y `función por nombre` pasan en los cinco. El 8b es informativo (en la PoC todo el input va en inglés).

## 3. Reproducibilidad y matriz
Prueba `demo` ×2; «estable» si las dos repeticiones dejan la misma firma. `--reps 1` si estable, `--reps 3` si no.

| Modelo | `demo` ×2 | Repeticiones de la matriz |
|---|---|---|
| `qwen3-14b-fp8` | estable (2/2) | 1 |
| `qwen3-32b-awq` | estable (2/2) | 1 |
| `qwen3-30b-a3b-2507` | estable (2/2), **pero con 4 fallbacks** | 1 |
| `ministral-3-14b` | **no estable (1/2)** | **3** |

### Resultados frente a la base (`experiments/e13-<modelo>-vs-e12.md`, con `compare.py`)
Aciertos por etiqueta (✅ en k de n repeticiones). Ministral va ×3; el resto ×1, como la base.

| Escenario | `actual` (base) | FP8 | 32B | 30B-2507 | Ministral |
|---|---|---|---|---|---|
| demo | A1 A2 A3 ✅ | A1 A2 A3 ✅ | A1 A2 A3 ✅ | A1 A2 A3 ✅ (2 fallbacks) | A1 A2 A3 3/3 |
| nominal | 0 falsas alarmas | ídem | ídem | ídem | ídem |
| wind | A1 ✅ | ✅ | ✅ | ✅ | **A1 1/3** |
| spoofing | A1 ✅ | ✅ | ✅ | ✅ | 3/3 |
| hijack | A1 ✅ | ✅ | ✅ | ✅ (1 fallback) | 3/3 |
| faults | F1 F2 F3 ✅ | F1 F2 F3 ✅ | F1 F2 ✅, **F3 ❌** | **F1 ❌**, F2 ✅, **F3 ❌** (2 fallbacks) | F1 3/3, F2 3/3, F3 2/3 |

Contadores (sumas de las repeticiones; salvo los tokens):

| | `actual` | FP8 | 32B | 30B-2507 | Ministral (×3) |
|---|---|---|---|---|---|
| Falsas alarmas / abiertas / frases que contradicen / `checks` ≠ tools | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Fallbacks | 0 | 0 | 0 | **5** | 0 |
| Rechazos de guardrails | 11 | 10 | 10 | **21** | 15 (en 3 vuelos) |
| Cortes por longitud (monitor) | 0 | 0 | 0 | 0 | **13** |
| No latinos | 0 | 0 | 0 | 0 | 0 |

## 4. Fallos clasificados (tras leer las trazas)
Clases: formato · decisión · ids · idioma · bucle · tiempo. «inv-NNNN» es la invocación en `llm_trace.jsonl` de `experiments/e13-<modelo>/runs/<perfil>/<escenario>/r<k>/`.

**`qwen3-14b-fp8` y `actual`:** sin fallos nuevos. 10 rechazos frente a 11 (tipos: nothing_changes 4, recovery 3, link_anomalous 2, source_silent 1); en `ROUTE_DEVIATION` carga otra skill en 2 de 9 invocaciones.

**`qwen3-32b-awq`**
| Fallo | Dónde | Clase | Qué pasa |
|---|---|---|---|
| F3 con causa `GPS_JAMMING` alta como alerta nueva | faults r1, inv-0008 (5 iter.) | decisión | Carga la skill, mira solo `gps` y métricas, no `radar` ni `link`. Su único rechazo fue de formato (`gps_radar_disagreed = true` no cuadra con la tool). La regla de alerta propia solo veta reconocer o sustituir, no la causa de una alerta nueva. Es el patrón F3 de los tres modelos de la Fase 7. |
| Responde en español a un usuario en español | nivel 1, 8b | idioma | Informativo. |
Sin fallbacks ni bucles. Más lento, no más acertado.

**`qwen3-30b-a3b-2507`** (parecido al 30B GPTQ de la Fase 7)
| Fallo | Dónde | Clase | Qué pasa |
|---|---|---|---|
| Se agotan las 12 iteraciones → fallback | demo inv-0007 e inv-0009; faults inv-0005 | bucle (tiempo de iteraciones) | Series de `get_events` por fuente antes de publicar; no es lento (6–8 s). |
| Llamada rechazada repetida → fallback | hijack inv-0002 (`link_anomalous = true` no cuadra con el enlace pedido); faults inv-0008 (F3: varios `publish_alert` contra la regla de alerta propia) | bucle | «This is the same call as before; change what I told you.» y corte. |
| F1 diagnosticado `UNKNOWN` | faults inv-0001 (12 iteraciones; 2 rechazos: `wind_notable` y `link_anomalous`) | decisión | |
| `link_anomalous: null` aunque miró el enlace | 13 rechazos | formato | Se corrige en la llamada siguiente. |
Coste: 24 invocaciones con 9 / 12 iteraciones (p50 / máx.) frente a 4 / 8; 1 095 477 tokens de prompt frente a 462 794 (2,4×); 21 rechazos.

**`ministral-3-14b`**
| Fallo | Dónde | Clase | Qué pasa |
|---|---|---|---|
| Reconoce el viento en vez de alertarlo | wind r1 y r3, inv-0001 | decisión (acción) | Diagnostica bien («notable wind… GPS and radar agree… link stable») y llama a `acknowledge_detection` con «No alert is needed»; sin alerta, no cuenta. 2 de 3. |
| Texto largo en `content` que agota `max_tokens` | 13 respuestas del monitor (demo 5, faults 5, hijack 1, spoofing 1, wind 1), p. ej. demo r1 inv-0004, inv-0005, inv-0009 | formato / tiempo | Escribe un análisis en markdown («### Analysis… Step-by-Step Diagnosis… ### Response:») junto a la llamada; 800 tokens a ~47 tok/s son 18 s por llamada. |
| F3 con `GPS_JAMMING` alta | faults r2 | decisión | Las otras dos: `SENSOR_FAULT` ✅ (la base también). No se leyó la traza completa. |
| Idioma en el 8b | nivel 1 | idioma | Informativo. |
Sin fallbacks, bucles ni ids inventados. Rechazos: source_silent 5, link_anomalous 4, checks 3, nothing_changes 2, otros 1. Respuesta del monitor: 51 069 tokens en 3 vuelos (~17 000 por vuelo) frente a 8 748 en uno.

**`gpt-oss-20b-low` (nivel 1, caso 6a):** las 5 repeticiones fallan porque el comprobador busca «-91» con guion ASCII; el modelo escribe el resultado correcto pero con **U+2013 (guion en), U+202F (espacio fino) y U+2011 (guion no separable, también dentro de los ids: «EV‑2108»)**. Con normalización Unicode pasarían 5/5 (comprobado sobre los ficheros guardados). Por la regla del banco no entra en la matriz y no se insistió. **Riesgo real para la PoC, no comprobado:** si el modelo escribe un id con U+2011 dentro de `evidence_event_ids`, la comparación exacta del guardrail lo rechazaría como inexistente (clase *ids*). Los casos 6b y 7 (argumentos de tool) pasan 5/5, así que en llamadas de tool copia bien; la duda es el texto libre.

## 5. Coste

| | `actual` | FP8 | 32B | 30B-2507 | Ministral |
|---|---|---|---|---|---|
| Invocación p50 / p95 (todas las ejecuciones) | 7,0 / 13,8 s | 8,6 / 17,5 s | 12,7 / 27,8 s | 6,1 / 10,6 s | 16,7 / 30,0 s |
| Iteraciones p50 / máx. | 4 / 8 | 4 / 8 | 4 / 6 | 9 / 12 | 4 / 6 |
| Tokens de prompt / respuesta (suma) | 462 794 / 8 748 | 478 800 / 8 212 | 467 687 / 7 587 | 1 095 477 / 15 988 | 1 344 562 / 51 069 (×3) |
| Pico de prompt en una llamada | 7 003 | 7 886 | 7 256 | 10 707 | 8 021 |
| Generación (nivel 1) | 57–65 tok/s (fase 7) | 43 | 33 | 160 | 47 |
| Memoria GPU / contexto | 21 336 MiB (fase 7) / 32 768 | 21 266 MiB / 28 000 | 21 332 MiB / 10 240 | 22 422 MiB / 32 768 | 21 498 MiB / 32 768 |
Tiempo de reloj de las matrices (suma de las ejecuciones): FP8 ≈ 8 min, 32B ≈ 11 min, 30B-2507 ≈ 6 min, Ministral (×3) ≈ 33 min.
El 32B con contexto 10 240 deja poco margen (pico medido de prompt 7 256 + hasta 800 de respuesta); cabe, pero no con la memoria A ni con vuelos más largos.

## 6. Qué ayudas parece necesitar cada uno
Con una repetición por escenario (tres en Ministral) no hay base para quitar ninguna ayuda con otro modelo; lo que se ve:
- **`qwen3-14b-fp8` y `qwen3-32b-awq`:** las mismas que `actual` (las dos reglas de ciclo de vida: «nada cambia» y «recuperación»); el 32B además activó `no_duplicate_cause` 3 veces.
- **`qwen3-30b-a3b-2507`:** más (21 rechazos, 13 de formato `link_anomalous: null`) y aun así 5 fallbacks: necesita, además, un tope de iteraciones o una guía de «qué leer» que no tiene.
- **`ministral-3-14b`:** la regla de alerta propia de `SOURCE_SILENT` (5 rechazos) y el guardrail de `checks`; lo que le falta no está en los guardrails: **cuándo publicar `WIND` frente a reconocer**, y que **no escriba análisis largos** fuera de la tool (un `max_tokens` mayor o una instrucción de salida más corta; no se probó).

## 7. Recomendación de modelo por defecto (decides tú)
**Mantener `Qwen/Qwen3-14B-AWQ` (`actual`).** Con la configuración de hoy ningún candidato lo mejora: FP8 y 32B no ganan en calidad y pierden en velocidad (el 32B además tiene F3 ❌ y solo 10 240 de contexto), el 30B-A3B-2507 pierde estabilidad (5 fallbacks), Ministral pierde `wind` y se eterniza (invocación p50 16,7 s). Lo único a vigilar para otro candidato: el 30B-A3B-2507 es el único con generación mucho más rápida (160 tok/s), pero hace el doble de llamadas. Lo que dice **cada resultado** es una repetición; la evidencia de «no mejora» es más fuerte para el 32B y el 30B (fallos de etiqueta o fallbacks) que para el FP8 (empate).
Ruta natural si quieres seguir: E4b (Mistral Small 3.2 24B) tiene poco que prometer visto Ministral; **gpt-oss** es la única duda abierta (ver §4): ¿ejecuto la matriz de gpt-oss pese a no pasar el nivel 1 por un comprobador estricto? No lo he hecho porque la regla lo descarta.

## 8. Cambios en el repo y problemas
- **Código (sin cambiar los perfiles existentes):** claves de perfil/agente nuevas `reasoning_effort` (se envía en `extra_body` solo si no es `None`) y `reasoning_field` (por defecto `reasoning_content`; vLLM 0.31 lee `reasoning` para gpt-oss), en `agent/assets.py`, `agent/llm.py` (`assistant_message(reasoning_field)`), `agent/engine.py` y `agent/profiles.py`. Tests nuevos en `ai-module-py/tests/test_profiles.py`: las peticiones de todos los perfiles existentes no cambian (con un literal exacto para `actual`), un perfil con las claves nuevas las envía, y el mensaje del asistente usa el campo configurado. **419 tests pasan** (416 + 3), `ruff` limpio.
- **Perfiles nuevos** (`model-profiles/`): `qwen3-14b-fp8`, `qwen3-32b-awq`, `qwen3-30b-a3b-2507`, `ministral-3-14b`, `gpt-oss-20b-low` (con `--dry-run` hecho de los cinco).
- **`qwen3-14b-fp8` necesita `VLLM_USE_DEEP_GEMM=0` en el entorno al arrancar**, y los perfiles no pueden llevar variables de entorno. Se exportó en la sesión; para que sea reproducible habría que exportarlo en `serve.sh` (cambio pequeño, no hecho porque toca a todos los perfiles). El perfil lo avisa en un comentario.
- **Un solo reintento por modelo ante un fallo de arranque:** se respetó (FP8: el 2.º intento por el kernel, el 3.º por la memoria; 32B: a y b eran la escalera de memoria que pedías, c el reintento; gpt-oss: 1 reintento). El 3.er intento del FP8 es un ajuste de contexto, no un reintento por cuelgue; lo señalo por si lo ves distinto.
- **Monitores de la sesión:** varios vigilantes se quedaron releyendo logs antiguos por un fallo mío (`pgrep -f` casaba consigo mismo); no afectó a ninguna ejecución.
- **`gpt-oss-20b-low`:** `repetition_penalty: 1.0` (no 1,05): se dejó neutra y no se comprobó qué recomienda su ficha. No se llegó a ejecutar la PoC con él, así que `reasoning_field: reasoning` y el esfuerzo `low` están sin probar de extremo a extremo (el nivel 1 solo los usa en peticiones sueltas).

## 9. Límites y URLs
- **n = 1** (Ministral, 3) por escenario; con T=0 hay variación residual de vLLM (en la Fase 12 los rechazos variaban 1–2 entre ejecuciones iguales). Las diferencias de 1–2 rechazos no cuentan.
- Cuantización de la comunidad y contextos reducidos (28 000 y 10 240) mezclan variables con el modelo.
- Ministral: la mala nota de `wind` (2 de 3 sin alerta) viene de dos ejecuciones idénticas en lo esencial (T=0); lo mide poco.
- ⚠️ **No leí** la receta de vLLM para Ministral ni el cookbook de OpenAI para gpt-oss (no hay lectura web en esta sesión): lo de los flags salió de `vllm serve --help=all` y del código de vLLM 0.31 instalado (`entrypoints/openai/parser/harmony_utils.py`, `chat_utils.py`: el razonamiento devuelto se lee del campo `reasoning`; `reasoning_effort` es un campo de primer nivel de Chat Completions).
- URLs consultadas: `https://huggingface.co/api/models/<repo>` de los cinco repositorios (tamaño, formato, cuantización) y las fichas citadas en los perfiles.

## 10. Qué queda
- **Tu decisión:** seguir con E4b (Mistral Small 3.2 24B), E4c (híbrido), ejecutar la matriz de gpt-oss pese al nivel 1, o parar aquí.
- No se ha actualizado el TRASPASO del banco (solo lo pide E4c).
- `docs/quien_decide_que.md`: contrastado; sin cambios de reparto. Se añade a §3 bis que un perfil puede fijar `reasoning_effort` y `reasoning_field`.

## 11. Ficheros
Nuevos: `model-profiles/{qwen3-14b-fp8,qwen3-32b-awq,qwen3-30b-a3b-2507,ministral-3-14b,gpt-oss-20b-low}.yaml`, `experiments/e13-*` (matrices y repros; solo los `compare.md` y los `e13-*-vs-e12.md` y `e13-*-uso.md` se versionan). Modificados: `ai-module-py/src/ai_module/agent/{assets,llm,engine,profiles}.py`, `ai-module-py/tests/test_profiles.py`, `docs/quien_decide_que.md`.

Copias (reglas 13 y 15) en `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`: `docs/fases/` (más `quien_decide_que.md`, que ya estaba allí), `experiments/` (`e13-*_compare.md`, `e13-*-vs-e12.md`, `e13-*-uso.md` y los `eval.md`/`informe.md` de cada ejecución), `bench/` (los dos scripts nuevos del banco, los `nivel0_*.json` y `nivel1_*.md/.json` de los cinco modelos y los logs de vLLM de los arranques fallidos de FP8, 32B y gpt-oss; el banco original no se tocó), `snapshots/fase13/` y `snapshots-limpias/fase13/`. Las dos comprobaciones de la regla 15 (palabras prohibidas y nombres propios) **salen vacías**; no hizo falta corregir nada. No hay PNG nuevos ni capturas de la web.

## 12. Mensaje de commit propuesto
```
feat: phase 13 (E4a) - five candidate models against the current baseline

Profiles for Qwen3-14B-FP8, Qwen3-32B-AWQ, Qwen3-30B-A3B-Instruct-2507-AWQ,
Ministral-3-14B and gpt-oss-20b. New optional profile keys reasoning_effort and
reasoning_field (defaults leave every existing request unchanged, with tests).
Level 0/1 bench, reproducibility check and six-scenario matrix for four of them
against e12-cierre; gpt-oss-20b fails level 1 and is not run. No model change.
```

---

# 13.1 · gpt-oss, variables de entorno por perfil y textos para revisar (04/11/2026)

Escrito para: Carlos. Contratos **sin cambios**; `agent-assets` igual (huella `293927dd0c038af5`, confirmada en cada `manifest.json`); no se cambia el modelo por defecto. Un servidor cada vez (gpt-oss, después `qwen3-14b-fp8`), puerto 8000 libre al empezar y al terminar, sin cuelgues de Windows, WSL ni vLLM, `HF_TOKEN` no usado. E4b y E4c no se hacen.

## Resumen

**gpt-oss-20b (esfuerzo `low`) iguala a `actual` en las seis pruebas de la matriz, con menos rechazos y menos tokens de prompt, y a una velocidad parecida.** El fallo de la Fase 13 era del comprobador (guiones y espacios Unicode), no del modelo. Sigue sin ser una mejora demostrada (n = 1, empate en calidad): la decisión de modelo por defecto es tuya.

## 1. Nivel 1 normalizado
- `~/llm-bench/nivel1_e4.py` (fichero nuevo de la Fase 13; el banco original no se toca): función `norm()` que convierte en ASCII los guiones U+2010–U+2015, U+2212 (y las variantes pequeñas U+FE58, U+FE63, U+FF0D) y los espacios U+00A0, U+1680, U+2000–U+200A, U+202F, U+205F y U+3000. Se aplica al texto libre que comprueban 6a («-91» y «18») y 6b (la distancia). El resto de casos no compara texto libre.
- **`gpt-oss-20b-low`: PASA, 11 casos × 5/5** (el 6a pasa de 0/5 a 5/5; el 8b también 5/5). 48 tok/s, 0 cortes por longitud, 0 fugas. Arranque con el perfil de la Fase 13 y `--drop-thinking-kwargs --body-extra '{"repetition_penalty":1.0,"reasoning_effort":"low"}'`.
- **Control: `qwen3-14b-fp8`, mismo banco normalizado: idéntico al de la Fase 13** (11 casos, 5/5 antes y después, comparados caso a caso). La normalización no cambia un resultado ya aprobado.
- Los `nivel1_gpt-oss-20b-low.*` de `~/llm-bench/` se sobrescriben con la nueva ejecución; la antigua (con el 6a en 0/5) sigue en `results/bench/nivel1/`.

## 2. gpt-oss: perfil, reproducibilidad y matriz
- **`repetition_penalty`:** su `generation_config.json` (en la caché) no trae ninguno (solo ids de tokens y `do_sample`) y el README no lo menciona; no hay valor recomendado y **el perfil se queda en 1,0**. No se leyó la ficha web, solo la copia local de la caché.
- **`demo` ×2** (`experiments/e13-gpt-oss-20b-low-repro/`): **estable (2/2)**, A1 A2 A3 ✅ en las dos, 0 fallbacks, 1 rechazo en total → `--reps 1`.
- **Matriz de los seis escenarios ×1** (`experiments/e13-gpt-oss-20b-low/`; comparación `experiments/e13-gpt-oss-20b-low-vs-e12.md` con `compare.py` juntando manifiestos; uso en `experiments/e13-gpt-oss-20b-low-uso.md` con `monitor_usage`). Arranque como en la Fase 13 (`--enforce-eager`, `--attention-backend TRITON_ATTN`, `reasoning_effort: low`, `reasoning_field: reasoning`); listo en 36 s, 22 666 MiB, contexto 32 768; la PoC completa funciona con él de extremo a extremo (hasta ahora solo se había probado el nivel 1).

| Escenario | `actual` (base) | gpt-oss-20b-low | Rechazos (base / gpt-oss) |
|---|---|---|---|
| demo | A1 A2 A3 ✅ | A1 A2 A3 ✅ | 3 / 0 |
| nominal | 0 falsas alarmas | ídem | 0 / 0 |
| wind | A1 ✅ | ✅ | 1 / 0 |
| spoofing | A1 ✅ | ✅ | 1 / 0 |
| hijack | A1 ✅ | ✅ | 1 / 0 |
| faults | F1 F2 F3 ✅ | F1 F2 F3 ✅ | 5 / 5 |

Falsas alarmas, fallbacks, alertas abiertas, frases que contradicen, `checks`≠tools, cortes por longitud y caracteres no latinos: **0** en todo (como la base). Una sola cadena por anomalía en las seis.

### Tabla resumen de E4a actualizada
| Modelo | Nivel 1 | Matriz (6 escenarios) | Veredicto |
|---|---|---|---|
| `qwen3-14b-fp8` | PASA | ×1: igual que la base; más lento (p50 8,6 s) | no mejora a `actual` |
| `qwen3-32b-awq` | PASA | ×1: **F3 ❌**; el doble de lento | peor |
| `qwen3-30b-a3b-2507` | PASA | ×1: **5 fallbacks**, F1 y F3 ❌ | peor |
| `ministral-3-14b` | PASA | ×3: `wind` 1/3, 13 cortes por longitud | peor |
| **`gpt-oss-20b-low`** | **PASA (normalizado)** | **×1: igual que la base en las seis pruebas; 5 rechazos frente a 11; 0 fallbacks** | **empata con `actual`; nada que ganar en calidad, algo en tokens** |

## 3. Fallos clasificados
No hay fallos de etiqueta, de formato, de bucle ni de idioma. Los **5 rechazos** de los guardrails (todos en `faults`, que en la base también concentra 5), tras leer `guardrail_rejections` de la traza:

| Rechazo | Dónde | Clase | Qué pasa |
|---|---|---|---|
| `recovery` | faults inv-0006 | decisión | Intenta otra alerta en una recuperación de `GPS_JAMMING`; el guardrail le dice «publish cause GPS_JAMMING, severity medium and supersedes ai-0004». |
| `source_silent` ×2 | faults inv-0008 | decisión | Intenta reconocer y luego sustituir una alerta de `GPS_JAMMING` ante `SOURCE_SILENT`; el guardrail le exige una alerta propia `SENSOR_FAULT` (la regla de la Fase 8). |
| `checks` | faults inv-0008 | formato | `gps_radar_disagreed = true` contra un `get_track_metrics` que no había llamado. |
| `ids` | faults inv-0009 | ids | **No es un id de evidencia inexistente:** `close_alert` con `ai-0006` cuando el aviso de cierre era de `ai-0008`; el guardrail dice «use ai-0008». Ambos ids en ASCII (véase §4). |

Los cinco se corrigen en la llamada siguiente. En `faults` la invocación inv-0008 llega a 9 iteraciones (el máximo; la base, 8).

## 4. Ids con caracteres Unicode (solo medido)
**No se ha añadido ninguna normalización al guardrail.** Medido sobre las trazas y las líneas de tiempo de la matriz (6 ejecuciones), con U+2010–U+2015 y U+2212 dentro de un id:

- **Rechazos por ids de evidencia inexistentes: 0.** El único rechazo de clase `ids` es el de arriba, con ids ASCII.
- **Llamadas a tools del monitor: 85, ninguna con un guion Unicode en los argumentos** (`evidence_event_ids` incluido; las publicadas, también ASCII). Coincide con el nivel 1 (6b y 7 pasan 5/5): en argumentos de tool copia bien los ids.
- **Donde sí aparece U+2011 es en el texto libre**, con la forma «met‑0010», «gps‑000106», «lnk‑0067», «ai‑0004»: en **5 respuestas de chat** (demo ×2, faults, hijack, spoofing) y **3 informes** (demo, faults, hijack; ahí sobre todo ids de otro tipo como «UNK‑4», «sub‑5»), y en el mensaje del asistente que el motor guarda del propio chat/informe. Los textos de las alertas (`summary`, `explanation`, `recommendation`) no traen ningún id con guion Unicode.
- **Efecto:** ninguno en las pruebas de la PoC (los chats y el informe no pasan por el guardrail), pero un id copiado de esos textos no se podría buscar con una comparación exacta, y los textos escriben además guiones y espacios finos Unicode («off‑route», «3.9 m/s» con U+202F). Si gpt-oss se adopta, merece la pena decidir si la web o el guardrail deben normalizarlos (**no hecho**; es tu decisión).
- Ejemplo con traza: `experiments/e13-gpt-oss-20b-low/runs/gpt-oss-20b-low/demo/r1/llm_trace.jsonl`, invocación del chat del monitor (la de `inv-0002`: «`met‑0010`, `gps‑000106`»); el rechazo `ids`, en `faults/r1`, `inv-0009`.

## 5. Coste (gpt-oss frente a `actual`, mismas seis pruebas)
| | `actual` | gpt-oss-20b-low |
|---|---|---|
| Invocaciones con LLM | 25 | 25 |
| Invocación p50 / p95 | 7,0 / 13,8 s | 7,6 / 11,7 s |
| Iteraciones p50 / máx. | 4 / 8 | 3 / 9 |
| Tokens de prompt / respuesta (suma) | 462 794 / 8 748 | 345 044 / 8 346 (+ 6 496 de razonamiento, que no cuentan como respuesta) |
| Pico de prompt en una llamada | 7 003 | 6 007 |
| Generación (nivel 1) | 57–65 tok/s (fase 7) | 48 tok/s |
| Memoria GPU / contexto | 21 336 MiB / 32 768 | 22 666 MiB / 32 768 |
Reloj de la matriz: ≈ 8 min (106 + 38 + 54 + 68 + 69 + 137 s). `demo` ×2 de la reproducibilidad: ≈ 4 min.

## 6. Límites
- n = 1 por escenario (la reproducibilidad `demo` ×2 sale estable): diferencias de 1–2 rechazos no cuentan (Fase 12). El empate en calidad no dice que sea mejor, solo que no es peor con esta batería.
- No se comprobó la calidad de los textos (ahí, §8): los contadores de frases que contradicen los `checks` son reglas simples.
- El modelo razona en `low`; el razonamiento no se envía a la web (regla de la PoC) y cuesta ~6 500 tokens en las seis pruebas.

## 7. `server.env` en los perfiles (código)
- **`model-profiles/*.yaml`:** nueva clave opcional `server.env: {VAR: "valor"}`. Se valida en `agent/profiles.py`: tiene que ser un mapa; los nombres, `[A-Z_][A-Z0-9_]*`; los valores, **texto** (`"0"` entre comillas; un `0` de YAML se rechaza para que no cambie en silencio). Forma parte de `server_signature()`, así que `run_matrix` reinicia el servidor si cambia.
- **`tools/vllm/serve.sh`:** nuevo subcomando interno `profiles serve-env <perfil>`; `start` lanza `setsid env VAR=valor … vllm …`, de modo que las variables llegan **solo** a ese servidor (no se exportan en el shell) y el comando impreso las muestra (`--dry-run` incluido).
- **`model-profiles/qwen3-14b-fp8.yaml`:** `env: {VLLM_USE_DEEP_GEMM: "0"}`. Comprobado arrancando el perfil: arranca a la primera (47 s) y `/proc/<pid>/environ` del servidor tiene `VLLM_USE_DEEP_GEMM=0`.
- **Tests (+9):** `test_server_env_is_validated_and_part_of_the_server_signature` (perfiles), `test_server_env_is_shown_in_the_dry_run` y `test_server_env_reaches_only_that_server` (`serve.sh` con un `vllm` falso que escribe la variable que ve; el servidor siguiente sin `env` no la hereda).
- **`--dry-run` de los 25 perfiles, antes y después:** idéntico el comando de **24**; solo cambia `qwen3-14b-fp8`, que añade `VLLM_USE_DEEP_GEMM=0` antes del binario (era lo pedido). Los perfiles existentes siguen con el mismo comando que antes.
- **Pruebas:** 428 pasan (419 + 9), `ruff` limpio.

## 8. Textos para revisar la calidad (solo extraídos, nada evaluado)
- **`experiments/e13-textos.md`** (1 687 líneas, copiado a `results/experiments/`): `demo` y `faults` de `actual` (base `e12-cierre`), `qwen3-14b-fp8`, `qwen3-32b-awq`, `qwen3-30b-a3b-2507`, `ministral-3-14b` (**r1**) y `gpt-oss-20b-low`. Un bloque por etiqueta y, dentro, un modelo detrás de otro: alertas (T+, causa, severidad, confianza, `summary`, `explanation`, `recommendation` completos), cierres y reconocimientos con su `reason` (un fallback sin `alert_id` se asigna a la etiqueta por su detección), las respuestas de los dos chats con su pregunta y las secciones del informe que escribe el modelo (Summary, What was seen, Monitor assessment, Recommendations). Sin recortar nada.
- Notas para leerlo: el informe numera sus anomalías A1, A2… (también en `faults`, donde la evaluación usa F1…F3), por eso «What was seen» va aparte con el título del propio informe; un `_missing_` es un apartado que ese modelo no escribió (en el 30B-A3B-2507, el F3, que no publicó alerta).
- **Generador:** `tools/experiments/texts.py` (`nombre=experimento[:perfil]`, `--scenarios`, `--rep`, `--out`), con test (`ai-module-py/tests/test_texts.py`, 6 pruebas sobre una matriz sintética). La regla 13 del `CLAUDE.md` ahora pide generar y copiar este fichero con cada matriz.
- Comando: `uv run --project ai-module-py python tools/experiments/texts.py --out experiments/e13-textos.md --scenarios demo,faults --rep 1 actual=experiments/e12-cierre:actual qwen3-14b-fp8=experiments/e13-qwen3-14b-fp8 qwen3-32b-awq=experiments/e13-qwen3-32b-awq qwen3-30b-a3b-2507=experiments/e13-qwen3-30b-a3b-2507 ministral-3-14b=experiments/e13-ministral-3-14b gpt-oss-20b-low=experiments/e13-gpt-oss-20b-low`.

## 9. Ficheros y copias
Nuevos: `tools/experiments/texts.py`, `ai-module-py/tests/test_texts.py`, `experiments/e13-gpt-oss-20b-low{,-repro}/`, `experiments/e13-gpt-oss-20b-low-{vs-e12,uso}.md`, `experiments/e13-textos.md`. Modificados: `ai-module-py/src/ai_module/agent/profiles.py`, `tools/vllm/serve.sh`, `model-profiles/qwen3-14b-fp8.yaml`, `ai-module-py/tests/{test_profiles,test_serve_sh}.py`, `CLAUDE.md` (regla 13), `ai-module-py/CLAUDE.md`, `docs/quien_decide_que.md` (§3 bis: `server.env`; sin cambios de reparto), `docs/fases/fase13.md`. Fuera del repo: `~/llm-bench/nivel1_e4.py` y los `nivel1_{gpt-oss-20b-low,qwen3-14b-fp8}.*` (copiados a `results/bench/`).
Copias en `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`: `docs/fases/`, `experiments/` (`e13-textos.md`, `e13-gpt-oss-20b-low*`, `eval.md`/`informe.md` de las dos nuevas), `bench/`, `snapshots/fase13_1/` y `snapshots-limpias/fase13_1/` (las dos comprobaciones de la regla 15 en el apartado siguiente).

## 10. Mensaje de commit propuesto
```
feat: phase 13.1 - gpt-oss-20b matrix, per-profile server env, review texts

Level 1 compares text after normalising Unicode dashes and spaces; gpt-oss-20b
(low) then passes and matches the current baseline in the six scenarios.
Profiles can set server.env (validated, exported only to that server);
qwen3-14b-fp8 gets VLLM_USE_DEEP_GEMM=0. New tools/experiments/texts.py extracts
alert, chat and report texts of several matrices for quality review (with test).
```
