# Lo que hay que saber de los spikes 0, 1 y 2 (13–15/10/2026)

Resumen para esta PoC. Los resultados completos están en `C:\CITADEL\_CLAUDE\spikes\spike{0,1,2}\` (no hace falta leerlos).

## Servidor (spike 0)
- vLLM 0.31.0 en WSL, `Qwen/Qwen2.5-14B-Instruct-AWQ`, `--max-model-len 32768`, `--enable-auto-tool-choice --tool-call-parser hermes`, `127.0.0.1:8000`. ≈ 65 tokens/s de generación.
- Sin `--generation-config vllm`, el servidor aplica el `generation_config.json` del modelo como valores por defecto (`temperature 0.7`, `top_k 20`, `top_p 0.8`): **envía siempre la temperatura de forma explícita** (0 en el monitor para que sea reproducible; 0,7 / `top_p` 0,8 en informe y chats). Al no enviar `top_k`, se queda el 20 del modelo.
- Con `tool_choice` por nombre, vLLM devuelve `finish_reason="stop"` aunque haya llamada. Con `auto` y `required`, `"tool_calls"`. Por eso: **detectar llamadas con `message.tool_calls`**, y en esta PoC, solo `auto`.

## Clientes (spike 1)
- `openai` (Python, 3.31.0) y `openai-java` (4.81.0) cubrieron todos los casos contra este servidor **sin remedios**, con las mismas llamadas y la misma latencia (manda el servidor).
- Latencia de referencia con este modelo: una respuesta simple ≈ 1,4 s; un bucle de tres tools ≈ 11 s. Un diagnóstico del monitor con 3–5 tools tardará del orden de 10–20 s: por eso existe «esperar al agente».
- **La forma de definir las tools cambia el comportamiento del modelo** (orden de claves, `strict`, `$schema`…): con la misma información, otra forma hizo que el modelo anotara dos veces. Por eso se envían los esquemas de `agent-assets/tools.json` tal cual.
- Con un prompt poco guiado («¿es plausible el último movimiento?») el 14B **no encadenaba** las tools (0 de 20); con un prompt que guiaba la comparación, sí (20 de 20). Aquí el prompt de sistema y las skills dicen explícitamente qué tool usar en cada paso. Si aun así no carga las skills, existe el modo guiado.
- `max_tokens` está marcado como obsoleto en el SDK en favor de `max_completion_tokens`; ⚠️ no se ha comprobado que vLLM 0.31.0 acepte este último. Usa `max_tokens` (funcionó en el spike) salvo que compruebes lo contrario.
- LangChain4j 1.22.0 necesitó forzar HTTP/1.1 para hablar con vLLM (no aplica en Python; anotado para el futuro módulo Java).

## Detector aprendido (spike 2)
- Isolation Forest entrenado en Python y puntuado en Java con ONNX Runtime: misma puntuación, ≈ 0,5 ms por muestra (100 árboles). Características por evento de posición: `dt_s, dist_m, implied_speed_mps, declared_speed_mps, speed_gap_mps, heading_change_deg` (necesita los dos eventos anteriores de la misma fuente). Entrenado con vuelos a 12–18 m/s y 1 Hz: por eso el dron de la PoC vuela a 15 m/s y el GPS reporta a 1 Hz. Queda como mejora (`docs/mejoras_futuras.md`).
