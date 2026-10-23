# Candidatos de modelo: qué dice la documentación sobre servirlos con vLLM

> 23/10/2026 · Comprobado en fichas de Hugging Face, recetas y documentación de vLLM, y notas de la versión v0.31.0 (la que tienes en WSL). **No se ha ejecutado nada**: es lectura de documentación. Lo marcado con ⚠️ no está confirmado.
> Base: tu comando actual = `vllm serve Qwen/Qwen2.5-14B-Instruct-AWQ --max-model-len 32768 --enable-auto-tool-choice --tool-call-parser hermes`, con `VLLM_USE_FLASHINFER_SAMPLER=0`.

## 1. Lo que cambia respecto a tu configuración actual
1. **Modo razonamiento (Qwen3 y siguientes): viene activado por defecto.** El modelo escribe `<think>…</think>` antes de responder. Con el parser de razonamiento de vLLM (`--reasoning-parser qwen3`, desde vLLM 0.9.0) el razonamiento sale en un campo aparte y `content` queda limpio. Sin parser, el `<think>` se mezcla con la respuesta y puede romper la lectura de las tools.
2. **Desactivarlo:** por petición, `"chat_template_kwargs": {"enable_thinking": false}` (en el SDK de OpenAI, dentro de `extra_body`). A nivel de servidor, la receta de vLLM para Qwen3.6 usa `--default-chat-template-kwargs '{"enable_thinking": false}'`; para Qwen3 solo está documentado el cambio por petición o con una plantilla sin razonamiento (⚠️ el flag de servidor debería valer también, pero no lo pone la ficha de Qwen3).
3. **Para una comparación justa con el modelo actual** (Qwen2.5 no razona): probar primero con razonamiento desactivado. Con razonamiento activado es otra prueba, con más latencia y tokens (relacionado con las pruebas R0–R6 que tienes pendientes).
4. **Muestreo recomendado por Qwen (modelos cuantizados):** sin razonamiento, temperatura 0,7, top_p 0,8, top_k 20, min_p 0 y **presence_penalty 1,5**; con razonamiento, 0,6 a 1,0 según el modelo, top_p 0,95, top_k 20, y **no usar decodificación voraz**. ⚠️ Habría que ver qué temperatura usa hoy la PoC.
5. **`tool_choice: required` y por nombre** (que usa la PoC) funcionan con cualquier modelo soportado, mediante salidas estructuradas (la primera vez puede tardar unos segundos en compilar la gramática).

## 2. Candidato por candidato
| Candidato | `--tool-call-parser` | `--reasoning-parser` | Versión mínima de vLLM | Particularidades |
|---|---|---|---|---|
| **Qwen/Qwen3-14B-AWQ** | `hermes` (guía de Qwen para Qwen3) | `qwen3` | ≥ 0.8.5 (parser `qwen3`: ≥ 0.9.0) | Contexto nativo 32.768 (más, con YaRN, no hace falta). Soporta `/think` y `/no_think`. Es el cambio más sencillo: mismo parser que el actual. |
| **Qwen/Qwen3.5-27B-GPTQ-Int4** | `qwen3_coder` (ficha) ⚠️ | `qwen3` | La ficha pide una versión de desarrollo (nightly) de cuando salió; la receta de Qwen3.6 pide ≥ 0.17.0. Tu 0.31.0 debería valer ⚠️ | Híbrido (Gated DeltaNet + atención), con codificador de visión: añadir `--language-model-only` para ahorrar memoria. La ficha usa `--quantization moe_wna16`, que parece heredado de una variante MoE ⚠️: probar **sin** ese flag y añadirlo solo si falla la carga. No admite `/think` ni `/nothink`. La receta de Qwen3.6 dice que GPTQ-Int4 cabe en una GPU de 24 GB. |
| **amd/Qwen3.8-27B-Quark-AWQ-INT4-W4A16** | no indicado ⚠️ (probablemente `qwen3_coder`, como Qwen3.5/3.6) | `qwen3` | Sin versión mínima. Pide soporte W4A16 de Quark: el PR #48606 **sí está** en las notas de la v0.31.0; el #46110, que cita la ficha, **no aparece** en ellas ⚠️ | Su comando lleva `--trust-remote-code` (ejecuta código del repositorio: revisarlo antes). Formato INT4 por grupos de 128, algoritmo AWQ. Es de AMD y no consta que se haya probado con CUDA ⚠️. |
| **Qwen/Qwen3-30B-A3B-GPTQ-Int4** (MoE) | `hermes` (como Qwen3) ⚠️ | `qwen3` | ≥ 0.8.4 | Requiere `transformers` ≥ 4.51. La ficha no nombra parser de herramientas. |
| **Mistral Small 3.1/3.2 24B** | `mistral` | — | — | Los lanzamientos oficiales traen dos formatos (mistral-common por defecto o Transformers); la documentación de vLLM da plantillas ajustadas por los ID de llamada de 9 dígitos. No he encontrado una cuantización AWQ/GPTQ verificada: pendiente de buscar. |

## 3. Resuelto: el nombre del parser de Qwen3.5/3.6/3.8
Comprobado en tu instalación (`vllm serve --help=all`, 23/10/2026): la lista de `--tool-call-parser` de tu vLLM incluye **`qwen3_coder`** y **`qwen3_xml`**, además de `hermes` y `mistral`. Por tanto `qwen3_coder` (el de la ficha de Qwen3.5 y la receta de Qwen3.6) es válido. Queda por ver si es el que mejor funciona con estos modelos frente a `qwen3_xml`: son parsers de llamadas en formato XML y no el JSON de hermes, así que hay que repetir las pruebas de herramientas del spike 0.

## 4. Comandos para probar (en este orden)
Común: `source ~/vllm/bin/activate`, `export VLLM_USE_FLASHINFER_SAMPLER=0`, y parar el servidor actual (puerto 8000).

**1) Qwen3-14B-AWQ**
```
vllm serve Qwen/Qwen3-14B-AWQ --host 127.0.0.1 --port 8000 --max-model-len 32768 \
  --enable-auto-tool-choice --tool-call-parser hermes \
  --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}'
```
**2) Qwen3.5-27B-GPTQ-Int4** 
```
vllm serve Qwen/Qwen3.5-27B-GPTQ-Int4 --host 127.0.0.1 --port 8000 --max-model-len 32768 \
  --language-model-only --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}'
```
**3) amd/Qwen3.8-27B-Quark-AWQ-INT4-W4A16** (⚠️ soporte)
```
vllm serve amd/Qwen3.8-27B-Quark-AWQ-INT4-W4A16 --host 127.0.0.1 --port 8000 --max-model-len 32768 \
  --language-model-only --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}'
```
(añadir `--trust-remote-code` solo si vLLM lo exige, tras leer el código del repo).

Qué mirar en cada arranque: que llegue a `/health`, la línea de memoria de KV del log, y `finish_reason` y `message.tool_calls` del spike 0. Después, la `demo` 3/3 y las métricas de `eval.md`.

## 5. Pendiente de confirmar
- Nombre válido del parser de Qwen3.5/3.6/3.8 en 0.31.0 (§3).
- Si el flag `--default-chat-template-kwargs` existe tal cual en 0.31.0 (aparece en la receta de Qwen3.6, no en la ficha de Qwen3).
- Si `--quantization moe_wna16` hace falta en el 27B denso.
- Soporte real del Quark W4A16 de AMD en CUDA con tu GPU Blackwell.
- Mistral: cuantización y flags de formato.
