# Traspaso al repo: selección del modelo LLM de la PoC (23/10/2026)

Para quien retome las pruebas desde `poc-ai-monitor`. Resume lo medido en el banco (WSL, `~/llm-bench`), lo que NO hay que repetir y lo que falta (niveles 2 y 3). Los archivos citados están en `C:\CITADEL\_CLAUDE\llmfit\`.

## 1. Objetivo
Elegir un modelo local mejor que `Qwen/Qwen2.5-14B-Instruct-AWQ` para la PoC, probando también con razonamiento. Después, con el modelo elegido, ir quitando ayudas/guardrails (ver `docs/mejoras_futuras.md`, «Liberar al agente»). El motivo: con Qwen2.5 le cuesta encadenar llamadas a herramientas.

## 2. Hardware y entorno
- HP ZBook Fury G1i, 128 GB RAM, RTX PRO 5000 Blackwell Laptop 24 GB (23,89 GiB). WSL2 Ubuntu-24.04 ve ~62 GiB de RAM.
- vLLM 0.31.0 en el venv `~/vllm`, con `VLLM_USE_FLASHINFER_SAMPLER=0`.
- `--max-model-len 32768` (el prompt máximo del monitor mide ~9.739 tokens; margen ~2,7×).

## 3. Candidatos y estado
| Clave | Modelo | Parser de tools | Estado |
|---|---|---|---|
| `actual` | Qwen/Qwen2.5-14B-Instruct-AWQ | hermes (sin razonamiento) | Nivel 0 OK; **nivel 1 FALLA** |
| `qwen3-14b` | Qwen/Qwen3-14B-AWQ | hermes + reasoning `qwen3` | Nivel 0 y 1 OK |
| `qwen3-30b-a3b` | Qwen/Qwen3-30B-A3B-GPTQ-Int4 | hermes + reasoning `qwen3` | Nivel 0 y 1 OK |
| `qwen3.5-27b` | Qwen/Qwen3.5-27B-GPTQ-Int4 | qwen3_coder, `--language-model-only` | **Aparcado**: se cuelga en «Capturing CUDA graphs 0/51» |
| `qwen3.8-27b-amd` | amd/Qwen3.8-27B-Quark-AWQ-INT4-W4A16 | qwen3_coder | **NO REPETIR**: Windows se cayó dos veces (BSOD `0x00020001 HYPERVISOR_ERROR`) con este intento |
| Mistral Small 24B | — | mistral | Sin cuantización AWQ/GPTQ verificada; sin probar |

**Advertencia:** no lanzar `qwen3.8-27b-amd` ni reintentar los 27B híbridos sin hablar antes con Carlos. Detalle en `bench/resultados/cuelgues_sistema.txt` y `bench/resultados/nivel0/`.

## 4. Cómo se sirve un modelo
`serve_candidato.sh <clave>`: arranca vLLM con los parsers y flags de la tabla anterior, comprueba cada flag contra `vllm serve --help=all` y copia logs y tiempos a `arranques\`. Lee la cabecera del script para ver los argumentos exactos (p. ej. `--think`). Las notas de parsers y versiones mínimas están en `vLLM_candidatos_comprobacion.md`.

Razonamiento en los Qwen3: `--reasoning-parser qwen3`. Se desactiva por petición con `chat_template_kwargs {"enable_thinking": false}` o con `--default-chat-template-kwargs`. El campo de salida se llama `reasoning`. Qwen recomienda, en modo razonamiento, **no usar decodificación voraz** (0,6 / top_p 0,95 / top_k 20), y `presence_penalty` 1,5 en cuantizados.

## 5. Resultados del nivel 1 (API y tools, casos sintéticos en inglés)
Fuente: `bench/resultados/nivel1/comparativa_nivel1.md` y `raw/`.
- `qwen3-14b` y `qwen3-30b-a3b`: 5/5 en todos los casos, con y sin razonamiento; `tool_choice` `required` y por nombre funcionan con razonamiento; sin fugas de `<think>` ni `<tool_call>`.
- `actual` falla dos casos reales: **6b** (llamada paralela con marcadores inventados `"${event.lat}"`) y **7** (comillas mal escapadas `\\\"` y «señal» → «seal»).
- Velocidad medida: ~64 tok/s (`actual`), ~65 (`qwen3-14b`), 151–159 (`qwen3-30b-a3b`). Las estimaciones de llmfit no sirven para velocidad.
- `qwen3-30b-a3b` contestó en español a un usuario en español pese a «Always answer in English» (0/5 en todos los modos); `qwen3-14b` obedeció.
- Con `max_tokens` 800 y razonamiento, la respuesta más larga del 30B llegó a 751 tokens (la del 14B, a 527). Ninguna se cortó, pero el margen es corto: subirlo en los niveles siguientes.
- Limitación: el nivel 1 usa temperatura 0 y casos cortos; no mide variabilidad ni la PoC.

## 6. Qué falta

### Nivel 2: peticiones reales sin ejecutar la PoC
- Reproducir, por pasos de decisión, peticiones reales del monitor contra cada modelo: se da el historial exacto de la traza y se mira qué hace el modelo (herramienta esperada, argumentos válidos contra el esquema, `required`).
- **Las trazas de `results/trazas/` (R3–R9, 21/10/2026) están en castellano**, anteriores a la Fase 5. Contienen `messages`, `calls`, `sampling` e `iterations` completos, pero el nombre de las tools solo aparece en `tools_offered`; los esquemas están en `agent-assets/tools.json`. Para el nivel 2 conviene **generar trazas nuevas en inglés con `actual` como referencia** (la Fase 5.2 las ejecutó pero en `results/` solo están `eval.md` e `informe.md`, no las trazas).
- Medir: llamada bien formada, herramienta esperada, esquema válido, latencia, tokens, y qué ocurre con el contexto máximo.

### Nivel 3: la PoC completa
- `uv run --project platform python -m platform_app.run --scenario <esc> --speed 16 --wait-agent --evaluate`, después `ai_module.evaluate runs/<esc>/<run_id>` y `ai_module.llm_check`.
- Escenarios: `demo`, `faults`, `wind`, `hijack` (y `nominal`, `spoofing`). Referencia con Qwen2.5: `demo` 3/3, `faults` 2/3 (fallan F2 y F3, ver `poc-ai-monitor_pendientes.md`).
- **Cambiar de modelo sin editar `agents.yaml` congelado** (huella de `agent-assets` `e28d071e856efb09` en la 5.2): comprobar si hay variable de entorno o configuración externa para URL, nombre del modelo y parámetros extra; si no, añadirla como cambio pequeño del repo y avisar.
- **Muestreo:** `actual` hereda `repetition_penalty` 1,05 del `generation_config` del modelo; los Qwen3 no. Fijarlo explícitamente (la traza actual lleva `extra_body: {top_k: -1, repetition_penalty: 1.05}`) o la comparación mezcla dos variables.
- `max_tokens`: subir de 800 para razonamiento.

### Orden recomendado (separar variables)
1. Solo cambia el modelo, con todas las ayudas como hoy; comparar con la referencia de Qwen2.5.
2. Con el mejor o los dos mejores, quitar ayudas de la más a la menos intrusiva (`monitor.*` en `agents.yaml`; chats, `chat.tools_enabled`).
3. El razonamiento, como eje aparte, con muestreo recomendado y `max_tokens` mayor.
4. La Fase 5.3 aplazada (guardrail de idioma por caracteres chinos, guardrail de prosa) se repasa con el modelo nuevo; puede no hacer falta.

## 7. Reglas
- No modificar archivos existentes del banco ni `agents.yaml` congelado; resultados en archivos nuevos.
- Lanzar modelos de uno en uno. Registrar `vllm` y logs de cada arranque en `arranques\`.
- Si Windows o WSL se cuelgan, parar y avisar; no repetir el mismo intento.
- HF_TOKEN de Carlos: caducaba el 23/10/2026; no guardarlo en ningún archivo.

## 8. Archivos para pasar al repo
- Este documento.
- `serve_candidato.sh`, `vLLM_candidatos_comprobacion.md`, `contexto_real_PoC.md`, `Resultados_llmfit_final.md`.
- `bench\CLAUDE.md`, `bench\resultados\nivel0\comparativa_nivel0.md`, `bench\resultados\nivel1\comparativa_nivel1.md` (más `nivel1.py` y `nivel1_driver.py` como ejemplo de driver).
- `bench\resultados\cuelgues_sistema.txt` (solo para el contexto de los cuelgues).
- Los logs de `arranques\` solo si hace falta depurar un arranque.
