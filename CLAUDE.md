# poc-ai-monitor

Eres el agente que construye la PoC `poc-ai-monitor` del proyecto CITADEL (Indra). Es una **demo funcional**, no un producto: tiene que funcionar, verse bien y poder explicarse. Se enseña al equipo de MDO la semana del 19/10/2026 y se programa en una o dos jornadas.

**Qué es:** un simulador de un dron que publica eventos en un bus, y un **módulo de IA** (extensión de un worker) que los vigila: un detector de reglas avisa de que algo no cuadra, un **agente monitor** (LLM con tools y skills) diagnostica la causa y publica una alerta, y un **agente de informe** cuenta al final lo que pasó. Se puede chatear con los dos. La web enseña el dron moviéndose, los eventos y lo que dice cada agente.

**Lee antes de escribir código:** `docs/01_definicion.md` (diseño y porqués), `contracts/eventos.md` (**fuente de verdad** de eventos, topics, WebSocket y API de tools), `agent-assets/` (prompts, skills y `tools.json`), `scenarios/` y `ref/`. Las mejoras que **no** se hacen ahora están en `docs/mejoras_futuras.md`.

## Estructura
```
contracts/        eventos.md (fuente de verdad) + python/ (modelos Pydantic, paquete local) + schemas/ (JSON Schema exportado)
platform/         Python: generador, controlador, gráficas, reproductor, bus, timeline, tools de datos, API y WebSocket
ai-module-py/     Python: cliente del bus, detector de reglas, motor de agente, monitor, informe, chats, guardrails, trazas, evaluación
agent-assets/     Compartido con el futuro módulo Java: prompts/, skills/, tools.json
web/              JS: la interfaz de v0 adaptada (Next.js)
scenarios/        nominal, viento, secuestro, spoofing, fallos y demo (YAML con semilla)
runs/             Salida del generador y de cada ejecución (no se versiona salvo ejemplos pequeños)
docs/  ref/       Diseño, mejoras futuras y referencias
```
Cada carpeta de componente tiene su propio `CLAUDE.md` con lo específico.

## Entorno
- WSL 2, Ubuntu 24.04. Python 3.12 con **`uv`** (un proyecto por componente: `platform/` y `ai-module-py/`, que dependen de `contracts/python` como ruta local). Node y pnpm para la web: compruébalos en la Fase 0; si faltan y hace falta `sudo`, **no lo uses**: dile a Carlos el comando exacto y espera.
- **vLLM** en `http://127.0.0.1:8000/v1` con `Qwen/Qwen2.5-14B-Instruct-AWQ`, `--max-model-len 32768`, `--enable-auto-tool-choice --tool-call-parser hermes`. **Lo arranca y lo para Carlos. Tú no lo arrancas, no lo paras y no lo configuras.** Hace falta desde la Fase 3; en las fases 0–2 puede estar parado (en la Fase 0, si no responde, anótalo y sigue).
- Puertos: plataforma **8100** (API + `/ws`), web **3000**, vLLM 8000. Todo en `127.0.0.1`.
- Puedes **leer** (sin modificar) `~/spike1/` (herramientas de formato: `py/ruff.toml`, `py/hook_py.sh`, `.claude/settings.json`) y `/mnt/c/Proyectos/interfaz-de-simulacion-dron/` (la interfaz de v0, que se copia a `web/`).

## Reglas (obligatorias)
1. **Solo `localhost`.** Red hacia fuera solo para instalar dependencias y leer documentación. **Nada de servicios en la nube**: ni LLM, ni telemetría (no instales ni actives LangSmith, Vercel Analytics ni similares; quita `@vercel/analytics` y el SDK `ai` de la web).
2. **Los contratos mandan.** Eventos, topics, mensajes del WebSocket y API de tools son los de `contracts/eventos.md`. Si hace falta cambiarlos, cambia el documento, los modelos Pydantic, los esquemas JSON exportados y **todos** los componentes que los usan, en el mismo commit, y díselo a Carlos.
3. **Separación estricta:** el módulo de IA y la web solo hablan con la plataforma por el WebSocket y la API HTTP. Nada de importar código de `platform/` desde `ai-module-py/` (solo `contracts/python`). Así el módulo de IA se podrá sustituir por uno en Java.
4. **El agente nunca ve la verdad.** `truth.json`, `labels.json` y los eventos del dominio `sim` (estado del reproductor y `FaultInjected`/`FaultCleared`) solo los usan las gráficas, la evaluación y la web. Ninguna tool los expone.
5. **Corte temporal en la plataforma:** las tools de datos nunca devuelven eventos con `sim_time` posterior al instante actual de la simulación, pida lo que pida el agente.
6. **Cliente LLM:** SDK oficial `openai` de Python, **Chat Completions**, bucle de tools escrito a mano (como el caso f del spike 1). Temperatura y `top_p` de `agents.yaml`, **siempre explícitos** en cada petición (monitor a 0; informe y chats a 0,7 / 0,8). Detecta llamadas con `message.tool_calls` no vacío, **nunca** con `finish_reason`. `tool_choice: "auto"` (nada de forzar por nombre). Sin frameworks de agentes (ni LangChain, ni Agents SDK, ni PydanticAI).
7. **Prompts, skills y esquemas de tools se leen de `agent-assets/`**, no se escriben en el código. Puedes mejorarlos, pero en esos ficheros.
8. **Nada de afirmaciones sin comprobar** sobre librerías (versiones, comportamiento, licencias): se confirman en la documentación oficial y se anota la URL en el informe de la fase. Si no se puede, ⚠️.
9. **Reproducible:** el generador es determinista con la semilla del escenario. Las gráficas y las evaluaciones se pueden regenerar con un comando.
10. **Código sencillo y legible**, con tipos. Formato con `ruff` (reutiliza la configuración del spike 1) desde el principio. Pruebas con `pytest` para lo determinista (generador, controlador, detector, bus, tools, guardrails). El LLM no se prueba con aserciones exactas; se evalúa (ver evaluación).
11. **Si te atascas más de 30 minutos** en algo, anótalo (qué intentaste, error literal) en el informe de la fase y sigue con lo siguiente o pregunta.
12. **Git, solo lectura.** No ejecutes nada que escriba en git: ni `git add`, ni `commit`, ni `push`, ni ramas, `stash`, `reset` o `checkout`. Puedes usar `git status`, `git diff` y `git log`. Los commits los hace Carlos al revisar cada fase; en `docs/fases/faseN.md` deja un mensaje de commit propuesto.
13. **Copia para revisión:** en cada punto de parada copia `docs/fases/`, los PNG de `runs/*/`, los `eval.md` e `informe.md` de las ejecuciones a `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/` (créala con `mkdir -p`; respeta la estructura de carpetas). Además, copia una **instantánea del código** a `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/snapshots/faseN/` con `dest=/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/snapshots/faseN && mkdir -p "$dest" && git ls-files -co --exclude-standard -z | xargs -0 cp --parents -t "$dest"` (solo lee git: copia lo versionado y lo nuevo no ignorado, sin `.venv`, `runs/` ni `.tools/`). Es lo único que escribes fuera del repo. No leas nada más de `/mnt/c` salvo las carpetas permitidas en «Entorno».
14. **Idioma:** código en **inglés** (identificadores, nombres de módulos y ficheros de código, mensajes de log); **comentarios y docstrings en español**. Tools, skills, prompts, eventos y campos tienen nombres en inglés (ya están así en `agent-assets/` y en los contratos); el contenido de prompts y skills, los textos para personas (web, alertas, informe) y la documentación, en español.

## Fases y puntos de parada
**Para al final de cada fase y espera a que Carlos conteste.** Cada fase termina escribiendo `docs/fases/faseN.md` (qué se hizo, cómo se ejecuta, resultados, problemas con su error literal, URLs consultadas, qué queda): Carlos puede hacer `/clear` entre fases.

- **Fase 0 · preparación.** Versiones (`python3`, `uv`, `node`, `pnpm`, `git`), `curl -s 127.0.0.1:8000/v1/models`. Estructura de carpetas. `contracts/python` con los modelos Pydantic de `contracts/eventos.md` y un script que exporte `contracts/schemas/*.json`; prueba que todos los ejemplos del documento validan. Configuración de `ruff` y del hook de formato.
- **Fase 1 · generador.** Controlador del dron, perturbaciones, fuentes, salida en `runs/<escenario>/` y `plot_scenario.py`. Pruebas del controlador. **Para y enséñale las gráficas a Carlos** (rutas de los PNG): aquí se decide si la física y los escenarios tienen sentido.
- **Fase 2 · plataforma y detector.** Reproductor (con fallos manuales: silenciar fuentes), bus con comodines, timeline, API y WebSocket, tools de datos; en `ai-module-py`, el cliente del bus y el detector de reglas. Un comando que ejecute un escenario de principio a fin sin LLM e imprima los eventos de detección. Pruebas del bus, de las tools (incluido el corte temporal) y del detector sobre los seis escenarios.
- **Fase 3 · agentes.** Motor de agente, monitor, informe, chats (en streaming), guardrails, trazas y `evaluate.py`. Ejecuta `demo.yaml` con «esperar al agente» y enséñale a Carlos `eval.md`, el informe generado y dos trazas representativas.
- **Fase 4 · web.** Copia la interfaz de v0 a `web/`, quita la simulación del navegador y conéctala al WebSocket (ver `web/CLAUDE.md`). Prueba la demo completa.
- **Fase 5 · extras.** Solo si Carlos lo pide, de `docs/mejoras_futuras.md`.

## Trabajo en paralelo
Las fases 0 y 1 van en secuencia, en la sesión principal. Con los contratos congelados (Fase 0) y el generador aprobado (Fase 1), la plataforma, el módulo de IA y la web se pueden repartir entre **subagentes**, **cada uno dueño de su carpeta** (no editan las de otros ni `contracts/`). El módulo de IA puede avanzar contra `runs/<escenario>/events.jsonl` y un bus falso mientras la plataforma no esté. La integración y la prueba de extremo a extremo las hace la sesión principal. Si un subagente necesita cambiar un contrato, para y lo dice.

## Cuándo parar y preguntar
- vLLM no responde o responde distinto de lo descrito.
- Algo exige `sudo`, tocar vLLM o salir de las carpetas permitidas.
- Hace falta cambiar un contrato, o un escenario no puede producir lo que pide la tabla 4.4 de la definición.
- El modelo no consigue diagnosticar una anomalía tras ajustar prompts y skills de forma razonable (documenta qué probaste; **no** cambies de modelo).
