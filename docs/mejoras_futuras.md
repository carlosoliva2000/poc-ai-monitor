# Mejoras futuras (no se hacen ahora)

Anotadas el 16/10/2026 durante el diseño. Sirven de lista para la Fase 5 y para cuando la PoC pase a la extensión de IA del worker.

## Agente
- **Memoria del monitor, opción A frente a B.** Ahora es la B (una llamada nueva por detección, con el estado inyectado). Probar la A (una conversación durante toda la simulación) y comparar latencia por invocación, tokens, calidad del diagnóstico y si llega al límite de contexto.
- **Sin `get_track_metrics`.** Desactivarla (`disabled_tools` en `agents.yaml`) y ver si el agente diagnostica solo con `get_events`. Si no, ¿basta con una tool de distancia entre puntos? ¿Escala con varios radares?
- **Modo guiado:** medir cuántas veces el modelo carga la skill por sí mismo; si falla a menudo, valorar el modo guiado o un modelo mejor.
- **Modelos:** Qwen3-14B-AWQ, modelos razonadores y Mistral (pendientes R0–R6 de `Spikes_IA_worker_definicion.md`). Fiabilidad de tools con muestreo del modelo (pendiente del spike 0).
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
