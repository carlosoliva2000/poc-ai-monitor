# Prompts para Claude Code (pegar tal cual)

Cada bloque es una fase. Al terminar cada una, el agente para y deja `docs/fases/faseN.md`. Puedes hacer `/clear` entre fases.

## Fase 0 · preparación
```
Lee CLAUDE.md, docs/01_definicion.md, contracts/eventos.md, scenarios/README.md, agent-assets/agents.yaml y ref/02_lecciones_spikes.md. Antes de nada, ejecuta `uname -a && pwd && git status` y dime qué sale. Después haz la Fase 0 tal como la describe CLAUDE.md: comprueba versiones y que vLLM responde (`curl -s http://127.0.0.1:8000/v1/models`), crea la estructura, los proyectos uv de platform/ y ai-module-py/, el paquete contracts/python con los modelos Pydantic de contracts/eventos.md (sobre, payloads, enumerados, mensajes del WebSocket y resultados de las tools), el script que exporta contracts/schemas/*.json y una prueba que valide todos los ejemplos JSON del documento. Configura ruff y el hook de formato reutilizando los de ~/spike1. Escribe docs/fases/fase0.md y para.
```

## Fase 1 · generador y gráficas
```
Lee CLAUDE.md, docs/01_definicion.md (§4), scenarios/README.md, platform/CLAUDE.md, ref/simcheck_controlador.py y docs/fases/fase0.md. Haz la Fase 1: generador con el controlador y la física de ref/simcheck_controlador.py más el ruido y las fuentes de §4.3, salida en runs/<escenario>/ para los seis escenarios, y plot_scenario.py con las tres figuras (empieza por plan_xy.png, solo lo planificado). Pruebas: determinismo y criterios de aceptación de scenarios/README.md. Escribe docs/fases/fase1.md con una tabla escenario → criterio → valor medido, y la lista de PNG generados con su ruta. Para: Carlos tiene que revisar las gráficas antes de seguir.
```

## Fase 2 · plataforma y detector
```
Lee CLAUDE.md, docs/01_definicion.md (§5 y §6), contracts/eventos.md, platform/CLAUDE.md, ai-module-py/CLAUDE.md y docs/fases/fase1.md. Haz la Fase 2. Reparte el trabajo en dos subagentes en paralelo, cada uno dueño de su carpeta y sin tocar contracts/: (1) platform/: reproductor, bus con comodines, timeline, API REST, WebSocket y tools de datos con corte temporal; (2) ai-module-py/: cliente del bus y detector de reglas con histéresis, probado primero sobre runs/<escenario>/events.jsonl. Después integra tú: un comando que ejecute un escenario de principio a fin a 16× sin LLM e imprima detecciones. Comprueba con los seis escenarios que nominal no dispara nada, que cada anomalía dispara su regla una vez por episodio y que fallos.yaml dispara SOURCE_SILENT de la fuente correcta; comprueba también que un fallo manual (control fault por el WebSocket) lo dispara. Pasa el subagente revisor-contratos. Escribe docs/fases/fase2.md (comandos, tabla escenario → detecciones con sim_time, problemas) y para.
```

## Fase 3 · agentes
```
Lee CLAUDE.md, docs/01_definicion.md (§7 y §8), contracts/eventos.md, ai-module-py/CLAUDE.md, todo agent-assets/, ref/02_lecciones_spikes.md y docs/fases/fase2.md. Haz la Fase 3: motor de agente (bucle a mano con el SDK openai), monitor (opción B, cola de un trabajador, modo guiado desactivado), informe, los dos chats en streaming, guardrails, trazas y evaluate.py. Prueba primero el monitor con viento.yaml, luego spoofing.yaml y secuestro.yaml, y por último demo.yaml con «esperar al agente» activado. Si el modelo no diagnostica bien, ajusta primero los prompts y las skills de agent-assets/ (anota cada cambio y por qué) y solo después prueba el modo guiado; no cambies de modelo. Pasa el subagente revisor-contratos. Escribe docs/fases/fase3.md con eval.md de cada escenario (incluido fallos.yaml), el informe de demo y dos trazas representativas resumidas, y para.
```

## Fase 4 · web
```
Lee CLAUDE.md, web/CLAUDE.md, ref/03_frontend_v0.md, contracts/eventos.md (§3–§6) y docs/fases/fase3.md. Haz la Fase 4: copia la interfaz de v0 a web/, quita la simulación del navegador y el SDK de Vercel, conéctala a la plataforma por el WebSocket y la API, y añade las vistas de web/CLAUDE.md (mapa con y hacia el norte y panel de capas, panel de fallos, consola con pestañas Monitor e Informe y sus chats). Arranca plataforma, módulo de IA y web y comprueba la demo completa con demo.yaml a 4× con «esperar al agente». Prueba también a silenciar el radar y el GPS desde la web y comprueba que el monitor reacciona. Escribe docs/fases/fase4.md con los tres comandos de arranque y lo que no funcione, y para.
```
