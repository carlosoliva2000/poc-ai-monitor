# cloud-adapter/

Cliente LLM alternativo del módulo de IA para **E5** (comparar el monitor con modelos de Claude). Paquete aparte, **fuera de la instantánea limpia** (regla 15: nombra al proveedor). El módulo lo carga solo si el perfil fija `llm.adapter: "cloud_adapter.claude_llm:ClaudeLlm"`; el núcleo no importa nada de aquí.

- `src/cloud_adapter/claude_llm.py`: `ClaudeLlm` (SDK oficial `anthropic`, API de mensajes con tools) detrás de `LlmClient`. Convierte los `messages` de Chat Completions a bloques, reenvía los bloques de razonamiento sin modificar (`LlmResponse.raw_blocks`), usa `block_binding.prefix_mismatch_behavior = "drop_block"` con razonamiento adaptativo (y quita los bloques con `between_tools`), pone la caché en el final del sistema y en el último bloque, reintenta 429/5xx/529/conexión con retroceso y lanza `FatalLlmError` ante lo que repetir no arregla. **No envía `temperature`, `top_p` ni `top_k`.**
- La clave se lee de `~/.config/poc-ai-monitor/anthropic.key` (permisos 600, se comprueba) y **no se muestra, no se copia ni se exporta al entorno**; los tests comprueban que no sale en `repr` ni en los errores.
- Tests (sin red, con un cliente falso): `uv run --project ai-module-py --with-editable ./cloud-adapter pytest -q cloud-adapter/tests`. Incluyen los de `tools/experiments/e5_tables.py` y `e5_style.py`.
- Perfiles: `model-profiles/claude-{haiku,sonnet}-5-5[-a0|-b]` (A = ayudas de `actual`, A0 = sin razonamiento previo, B = sin ayudas); tiempos más altos solo en ellos. Informe: `docs/fases/e5.md`.
