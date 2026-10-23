# Mejoras futuras (no se hacen ahora)

Anotadas el 16/10/2026 durante el diseño. Sirven de lista para la Fase 5 y para cuando la PoC pase a la extensión de IA del worker.

## Agente
- **Memoria del monitor, opción A frente a B.** Ahora es la B (una llamada nueva por detección, con el estado inyectado). Probar la A (una conversación durante toda la simulación) y comparar latencia por invocación, tokens, calidad del diagnóstico y si llega al límite de contexto.
- **Sin `get_track_metrics`.** Desactivarla (`disabled_tools` en `agents.yaml`) y ver si el agente diagnostica solo con `get_events`. Si no, ¿basta con una tool de distancia entre puntos? ¿Escala con varios radares?
- **Modo guiado:** medir cuántas veces el modelo carga la skill por sí mismo; si falla a menudo, valorar el modo guiado o un modelo mejor.
- **Modelos:** ver la sección «Liberar al agente» (más abajo), que sustituye a esta entrada. Pendientes aparte: modelos razonadores y Mistral (R0–R6 de `Spikes_IA_worker_definicion.md`) y la fiabilidad de tools con el muestreo del modelo.
- **Narración periódica** del monitor (resumen cada N segundos simulados), además de las alertas.

## Detección
- **Isolation Forest del spike 2** detrás del mismo puerto del detector (sirve tal cual: 15 m/s y 1 Hz). Detectaría saltos, velocidades imposibles y huecos; no el viento ni el secuestro. Entrenarlo con vuelos `nominal` generados por el propio generador.
- Más anomalías ya previstas en los contratos: **replay** (posiciones o marcas de tiempo repetidas), batería anómala, fallo del radar, jamming con GPS degradado pero no perdido (más ruido, sesgo, `hdop` alto sin perder el fix).
- Varios radares; varios drones (el MVP de David tiene dos y contempla choques).
- **Fallos más ricos desde la web:** degradar una fuente (más ruido, sesgo, `hdop` alto) en lugar de solo silenciarla. (Ya hecho: el simulador en directo, el modo interactivo y la pérdida de GPS que afecta a la navegación.)
- **Inyectar viento, secuestro o spoofing en directo** desde la web o el visor (hoy solo se programan en el YAML; en directo solo se inyectan los fallos `mute` y `loss`).
- **Alertas del monitor en el visor sin web:** pintar en el visor de matplotlib las alertas `AnomalyDetected` del monitor (causa, severidad y resumen) junto a las detecciones.

## Integración y arquitectura
- **MCP:** exponer las tools de datos de la plataforma como servidor MCP (Streamable HTTP) con el SDK oficial de Python, y consumirlas desde el módulo de IA. En Java, el cliente MCP de LangChain4j (Streamable HTTP, verificado en su documentación el 16/10/2026).
- **Módulo de IA en Java** con `openai-java` (misma estructura que el Python: bucle a mano, mismos `agent-assets/`), pasando la misma evaluación. Ver `Java_modulo_IA_worker.md` (puertos `LlmPort`, `DetectorPort`).
- **Refactor con LangChain4j:** probar el módulo Java con [LangChain4j agents](https://docs.langchain4j.dev/tutorials/agents/) (`langchain4j-agentic`, marcado experimental en su documentación a 16/10/2026) o con AI Services, y comparar cuánto cambia frente al bucle a mano.
- **NATS de verdad** en lugar del bus en memoria (los topics ya siguen la taxonomía de David); integración con el Worker Core SDK de Jesús.
- Retroceso y salto a un instante en el reproductor (descartado para la PoC).
- **Observabilidad:** OpenTelemetry o Langfuse autoalojado en lugar del JSONL propio (nunca LangSmith en la nube).
- **Visor con historial:** que el visor en directo recupere lo ya publicado al conectarse a mitad de ejecución, pidiéndolo a `GET /api/timeline` (hoy empieza a pintar desde que se conecta).

## Refactorización
- **Mover la constante `BASE`** (id del waypoint base) de `generator/controller.py` a `poc_contracts`, para que `tools/summary.py` no dependa del generador.

## Uso exclusivo del LLM por configuración
Un `llm_max_concurrency` global en `agents.yaml` con un semáforo compartido por el monitor, el informe y los chats, para dar el LLM en exclusiva al monitor (hoy los chats compiten con él por la caché KV de vLLM). Los tiempos máximos de una invocación contarían desde que el monitor consigue el LLM. Sin «esperar al agente», necesita además un mensaje nuevo del módulo a la plataforma en el contrato (para avisar de que el agente está esperando turno). No se implementa ahora.

## Texto fiable del monitor
El texto de las alertas (resumen, explicación, recomendación, razón de cierre) lo escribe el modelo y **puede contradecir los `checks` que él mismo declaró**: en la demo de viento decía «GPS y radar discrepan 13,8 m» y «empuja en dirección contraria a la deriva» con `gps_radar_disagreed = no` y `wind_with_drift = sí`. Con temperatura 0 el error se repite siempre. Pedirle que escriba sin nombres de campo (Fase 4.1) lo empeoró, porque `disagreed=false` y `with_drift=true` le servían de ancla; se revirtió (Fase 4.3).

**Lo que hay hoy es provisional, no una solución:**
- La web quita de lo que muestra los paréntesis que solo contienen `campo=valor` o `campo: valor` (el evento, `eval.md` y el informe conservan el original). Es presentación: **no arregla frases como «discrepan 13,8 m»**.
- `evaluate.py` mide las «frases que contradicen los checks» con tres reglas simples (contrario a la deriva o al viento con la deriva a favor, «contra la deriva», «discrepan <cifra>» sin «poco» con GPS y radar sin discrepar) y las lista en `eval.md`. **Solo vigila; no impide publicar.** Con reglas tan simples habrá falsos negativos (otras formulaciones) y algún falso positivo.

**Investigar:**
- **(a) Explicación estructurada.** El código monta con plantillas las frases de hechos (a partir de los `checks` y de `get_track_metrics`, como ya hace el informe) y el modelo solo escribe una interpretación corta. Es lo que se hizo en los chats (Fase 4.2) y en el informe (Fase 3.1), y ahí el fallo desapareció; aquí cambia el contrato (`explanation` pasaría a llevar dos partes) y qué ve la web.
- **(b) Verificar el texto contra los `checks` antes de publicarlo.** O con reglas (la métrica de `evaluate.py` convertida en guardrail: el rechazo diría la frase y el check que contradice) o con un segundo modelo que haga de juez. Con reglas es determinista pero cubre solo lo que se haya escrito; con juez cubre más, pero es un 14B comprobando a otro 14B (o el mismo) y cuesta una llamada por alerta.
- **(c) Un modelo mejor.** Ver «Liberar al agente»: comprobar si escribe bien **sin el ancla de los nombres de campo**, es decir, con el prompt de castellano llano de la 4.1 y la métrica en 0.

## Liberar al agente
Con `Qwen2.5-14B-Instruct-AWQ` el monitor necesita varias **ayudas** (lista y motivos en `docs/fases/fase3.md`, «Ayudas al modelo añadidas en esta fase»). Cada una tiene un interruptor en `agent-assets/agents.yaml` (`monitor.*`, todos activados por defecto) y `eval.md` anota en su cabecera cuáles estaban activas. La mejora es **probar modelos más modernos y quitar las ayudas** hasta ver cuáles sobran.

**Candidatos** (por ejemplo, la familia Qwen3 en variantes *instruct*, aunque tengan menos parámetros):
- `Qwen/Qwen3-30B-A3B-Instruct-2507`: solo modo *non-thinking* (no genera `<think>`), 30,5 B en total y 3,3 B activos. ⚠️ Con los datos de Qwen, **no cabe en 24 GB** sin cuantizar (Transformers: ≈ 58 GB en BF16, ≈ 30 GB en FP8) y no consta una versión AWQ oficial: habría que comprobar una cuantización de 4 bits de la comunidad antes de contar con ella.
- `Qwen/Qwen3-14B-AWQ` y `Qwen/Qwen3-8B` (AWQ o FP8): existen oficiales; **tienen modo thinking por defecto**, que se apaga con `chat_template_kwargs: {"enable_thinking": false}` en la petición. ⚠️ El aviso de Qwen: con `--reasoning-parser` ese interruptor no es compatible (vLLM 0.8.5); para desactivar el thinking del todo hay una plantilla de chat propia.
- ⚠️ Una variante `Qwen3-4B-Instruct-2507` o una `Qwen3-14B-AWQ-2507`: **no verificadas** (no aparecen en las páginas consultadas).

**Antes de empezar, confirmar** (resultados de la consulta; ⚠️ = no confirmado en la documentación):
- *Parser de tools:* Qwen recomienda `--enable-auto-tool-choice --tool-call-parser hermes` también para Qwen3 («We recommend using Hermes-style tool use for Qwen3»); la lista de modelos de la página de vLLM sobre tool calling menciona Qwen2.5 y QwQ, no Qwen3 (https://qwen.readthedocs.io/en/latest/framework/function_call.html, https://qwen.readthedocs.io/en/latest/deployment/vllm.html, https://docs.vllm.ai/en/latest/features/tool_calling/). `qwen3_xml` es para los Qwen3-Coder, no para Qwen3 general.
- *Memoria en 24 GB:* la única tabla oficial (https://qwen.readthedocs.io/en/latest/getting_started/speed_benchmark.html) es de Transformers en una H20 de 96 GB, con 30.720 tokens de entrada: Qwen3-8B ≈ 11 GB en AWQ-INT4 (13,6 GB FP8); Qwen3-14B ≈ 15,3 GB en AWQ-INT4 (20,8 GB FP8); Qwen3-30B-A3B ≈ 33 GB en FP8. ⚠️ No hay cifras para 32.768 tokens ni para vLLM (que además reserva memoria según `--gpu-memory-utilization`): hay que medirlo con el servidor real y la caché KV.
- *Contexto:* ⚠️ sin `--max-model-len` vLLM usa el `max_position_embeddings` del modelo (40.960 en Qwen3; 262.144 en el 2507): pasar siempre `--max-model-len 32768`.
- *Muestreo:* Qwen recomienda para *non-thinking* temperatura 0,7, `top_p` 0,8, `top_k` 20 y, para los cuantizados, `presence_penalty` 1,5; «no usar decodificación voraz» en thinking. El monitor va a temperatura 0 (decisiones reproducibles): comprobar que no degenera sin ayuda (ver `repetition_penalty` en `agents.yaml`).

**Infraestructura (Fase 6):** los perfiles de `model-profiles/` ya permiten cambiar modelo, muestreo, razonamiento, tiempos y estos interruptores sin tocar `agents.yaml`, y `tools/experiments/run_matrix.py` repite y compara (`docs/fases/fase6.md`).

**Método.** Una variable cada vez, repitiendo los seis escenarios (`run.py --scenario … --speed 16 --wait-agent --evaluate`) y **comparando los `eval.md`** con el paso anterior (causa por etiqueta, una cadena por episodio, falsas alarmas, fallbacks, tools y skills, latencias). Orden, de la ayuda más intrusiva a la menos:
1. `coherence_guardrail: false`
2. `require_checks: false`
3. `computed_facts: false`
4. `final_iteration_response_tools_only: false`
5. `tool_choice: auto`
6. skills originales (las anteriores a la reescritura para este modelo; están en el historial de git de `agent-assets/skills/`)
Se para en el primer paso en que algún escenario empeora y se deja esa ayuda puesta. Las que no son ayudas (cierre determinista, solo `detection_id`, `repetition_penalty`) no se tocan.

### Probar el monitor con modelos de Claude
Para ver hasta dónde llega un modelo potente con **todas las ayudas apagadas** (el techo de lo que el diseño pide al modelo). **Exige una excepción explícita a la regla 1 («solo `localhost`»), que decide Carlos**: los datos del vuelo saldrían de la máquina hacia la API de Anthropic; hay que decidir antes qué datos y con qué condiciones.

**Cómo.** Con el SDK nativo `anthropic`, como un **segundo adaptador en `llm.py`** detrás del mismo puerto (`LlmClient`), eligiéndolo con `provider: vllm | anthropic` en `agents.yaml`. El bucle de tools, las tools, los guardrails y la evaluación **no cambian**. Por qué el SDK nativo y no la capa de compatibilidad con `openai`: la capa ignora `strict`, no admite la caché de prompts y no devuelve el razonamiento (https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk).

**Lo que cambia con los modelos 5.5** (https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide y https://platform.claude.com/docs/en/models/haiku-5-5/migration-guide, consultadas el 22/10/2026):
- `temperature`, `top_p` y `top_k` dan **error 400 en Sonnet 5.5**, así que se omiten: hace falta un **perfil de muestreo por proveedor** (hoy `agents.yaml` los fija siempre, regla 6, pensada para vLLM).
- Sonnet 5.5 **no admite `tool_choice` `any` ni por nombre**: va con `auto` y las tools con `strict: true` (esquema garantizado).
- El **razonamiento adaptativo** va activado por defecto, con el nivel en `output_config.effort` (`low`…`max`) y un resumen opcional (`display: "summarized"`) para las trazas.
- ⚠️ **Por comprobar en la documentación:** cómo se devuelven los bloques de razonamiento en un bucle de tools (qué hay que reenviar en la petición siguiente y cómo se guardan en la traza).

**Modelos, en este orden** (https://platform.claude.com/docs/en/models/overview, consultada el 22/10/2026; precios por millón de tokens de entrada / salida):
1. `claude-haiku-5-5` (desde 0,10 $ / 0,50 $; el más rápido; esfuerzo por defecto `medium`). Es el único de los tres que acepta `tool_choice` `any`, pero entonces **responde sin razonar**: probar primero `auto` + `strict` con razonamiento y, solo si falla el formato, `any`.
2. Si Haiku no llega, `claude-sonnet-5-5` (2 $ / 10 $; esfuerzo por defecto `high`; solo `auto` + `strict`).
3. `claude-opus-5-5` (4 $ / 20 $) **solo como techo**, si Sonnet también falla, y **avisando antes** de usarlo.

**Método.** En cada modelo: primero con **todas las ayudas apagadas** (los cinco interruptores de `monitor.*`, `chat.tools_enabled` y, si se quiere medir también el informe, sin los datos inyectados), **una ejecución por escenario** (repetir solo `demo` o lo que falle) y **usando la caché de prompts**. Si un modelo potente falla, **revisar primero el diseño** (datos que faltan, instrucciones contradictorias o etiquetas discutibles, como F3 de `faults`) antes de encender ninguna ayuda. Medir tokens y coste con lo que ya da `eval.md` (tokens por agente y máximo de prompt); hay que añadirle los tokens de caché y el **coste estimado** con los precios de arriba, y anotarlos en cada `eval.md`.
