# Fase 6 · infraestructura para comparar modelos (23/10/2026)

Objetivo: ejecutar la PoC con distintos modelos y configuraciones, muchas veces, **sin tocar `agents.yaml` ni `agent-assets/`** (huella `e28d071e856efb09`, comprobada al final: sin cambios), y comparar los resultados. **Esta fase no hace los experimentos**: solo la infraestructura, las pruebas automáticas y una prueba corta con el LLM real (apartado 6). Contratos sin cambios (v0.10).

## 1. Qué se ha hecho
| Punto | Qué | Dónde |
|---|---|---|
| 1 · Regla de vLLM | La prohibición de tocar vLLM se sustituye por tu regla (solo `serve.sh`, solo perfiles, un servidor, puerto 8000 libre, PID guardado, 27B híbridos prohibidos, parar si algo se cuelga, `HF_HUB_OFFLINE=1`). Se añaden `model-profiles/`, `tools/` y `experiments/` a «Estructura». | `CLAUDE.md` |
| 2 · Referencias | Copiados tal cual el traspaso, las comparativas de los niveles 0 y 1 y `vLLM_candidatos_comprobacion.md`. | `docs/modelos/` |
| 3 · `serve.sh` | Arranca y para el servidor de un perfil; espera a `/health`; log, PID, versión y tiempo en `runs/_servers/`; espera a que la GPU se libere al parar. Ver §3. | `tools/vllm/serve.sh` |
| 4 · Perfiles | 7 perfiles, validados con lista blanca; se aplican en memoria sobre `agents.yaml`. `eval.md` anota perfil, huellas y parámetros efectivos (y cada ejecución guarda `profile.json`). | `model-profiles/`, `ai-module-py/src/ai_module/agent/profiles.py` |
| 5 · Razonamiento | (a) `enable_thinking` por petición según el perfil; (b) texto y tokens del razonamiento en la traza; (c) se devuelve al modelo dentro de la invocación como `reasoning_content`. Comprobado con el vLLM real (apartado 6). | `agent/llm.py`, `agent/engine.py`, `agent/trace.py`, `llm_check.py` |
| 6 · No latinos | Sección «Caracteres no latinos» de `eval.md` (monitor, informe, chat-monitor, chat-report y razonamiento) y `non_latin` en `eval.json`. Solo se mide. | `evaluate.py` |
| 7 · Lanzador | `run_matrix.py` y `compare.md`; modo `--fake` con el servidor LLM falso. | `tools/experiments/run_matrix.py`, `ai_module/compare.py`, `ai_module/testing/fake_llm.py` |
| 8 · Prueba corta | Hecha: apartado 6. | |

Cambios pequeños fuera de lo pedido, necesarios para que el conjunto funcione: `platform_app.app --wait-timeout`, `platform_app.run --profile/--wait-timeout` (la espera de la plataforma sale del perfil), `python -m ai_module --profile`, `presence_penalty` explícito en cada petición (0 por defecto; en `actual` el cuerpo de la petición lleva ahora `presence_penalty: 0`, que es lo que vLLM ya aplicaba), el servidor LLM falso pasa de `tests/` a `ai_module/testing/fake_llm.py` (submódulo de prueba), `eval.json` guarda por etiqueta `causes` y `closures` (para la estabilidad) y `.gitignore` (añadidas `runs/_servers/` y `experiments/**` con `!experiments/*/compare.md`; no se ha quitado ninguna línea).

## 2. Perfiles
Cada perfil lleva en un comentario la URL de la ficha oficial. Fichas leídas hoy (https://huggingface.co/Qwen/Qwen3-14B-AWQ y https://huggingface.co/Qwen/Qwen3-30B-A3B-GPTQ-Int4, `README.md`, sección Best Practices): **thinking** `Temperature=0.6`, `TopP=0.95`, `TopK=20`, `MinP=0`, «DO NOT use greedy decoding»; **non-thinking** `Temperature=0.7`, `TopP=0.8`, `TopK=20`, `MinP=0`; `presence_penalty` entre 0 y 2 y «We strongly recommend setting this value to 1.5 for quantized models» (con la advertencia de que un valor alto puede mezclar idiomas). La ficha no recomienda `repetition_penalty`. `min_p 0` es el valor por defecto de vLLM y no se envía. El `generation_config.json` de la caché local (leído) trae 0,6 / 0,95 / 20 para los dos Qwen3, sin `repetition_penalty`; el de Qwen2.5 trae 0,7 / 0,8 / 20 y 1,05. No he leído la ficha de Qwen2.5 (el perfil `actual` no cambia nada).

| Perfil | Servidor | Razonamiento | Muestreo (los 4 agentes salvo lo dicho) |
|---|---|---|---|
| `actual` | Qwen2.5-14B-AWQ, `hermes` | no se envía | el de `agents.yaml` |
| `qwen3-14b-t0`, `qwen3-30b-a3b-t0` | Qwen3-14B-AWQ / Qwen3-30B-A3B-GPTQ-Int4, `hermes` + `--reasoning-parser qwen3` | `false` | el de `agents.yaml` (monitor y chats a 0; informe 0,7 / 0,8) con `repetition_penalty` 1,05 explícito |
| `qwen3-14b-qwen`, `qwen3-30b-a3b-qwen` | ídem | `false` | 0,7 / 0,8 / top_k 20 / presence 1,5 / repetition 1,0 |
| `qwen3-14b-think`, `qwen3-30b-a3b-think` | ídem | `true` | 0,6 / 0,95 / top_k 20 / presence 1,5 / repetition 1,0; `max_tokens` 4000 (informe 6000, decisión tuya); tiempos **provisionales**: monitor 300 s por invocación y 90 s por llamada, chats 240 / 120, informe 300 / 240, espera de la plataforma 330 s |

Los tres perfiles Qwen3 de un mismo modelo comparten servidor (misma sección `server`), así que `run_matrix` no reinicia entre ellos.

## 3. `tools/vllm/serve.sh`
```
tools/vllm/serve.sh start <perfil> [--dry-run] [--timeout S]
tools/vllm/serve.sh stop [--gpu-timeout S]
tools/vllm/serve.sh status
tools/vllm/serve.sh gpu-idle      # mide la memoria de GPU en reposo (antes del primer arranque)
```
- Los argumentos de `vllm serve` salen del perfil (`python -m ai_module.agent.profiles serve-args`). Antes de arrancar: perfil válido y modelo no vetado (salida 2); modelo en la caché de Hugging Face, si no pregunta (salida 4, sin red: `HF_HUB_OFFLINE=1`); puerto 8000 libre, y **si lo ocupa un servidor que no es el mío avisa y sale sin tocar nada** (salida 3); flags comprobados contra `vllm serve --help=all`.
- El PID va en `runs/_servers/vllm.pid`; solo se actúa sobre un PID vivo cuyo comando contiene `vllm`. Log en `runs/_servers/<fecha>_<perfil>.log` y `<fecha>_<perfil>.json` (perfil, modelo, PID, segundos hasta `/health`, versión). Si el proceso muere al arrancar, enseña las 60 últimas líneas (salida 5); si el log no avanza 300 s o se pasa del tope (900 s), para **mi** servidor y sale (salida 6). Nunca reintenta.
- Razonamiento: el servidor arranca con `--reasoning-parser qwen3` y **sin** `--default-chat-template-kwargs`; cada petición lleva `enable_thinking`.
- `stop`: SIGTERM al grupo de procesos, 60 s de espera, SIGKILL solo si sigue siendo mío. Después **espera a que la GPU se libere** (salida 7 si no): criterio principal `nvidia-smi --query-gpu=memory.used` ≤ reposo medido con `gpu-idle` + margen (512 MiB, `GPU_MARGIN_MIB`), tope de 120 s (`GPU_TIMEOUT_S`). `--query-compute-apps` solo se anota en el log.
- **Qué devuelve `nvidia-smi` en este WSL (medido hoy):** en reposo, `memory.used` = **0 MiB** (24463 MiB totales); con `Qwen3-14B-AWQ` cargado (`max_model_len` 32768), `memory.used` = **21336 MiB**, y `--query-compute-apps=pid,used_memory` devolvió **`21070, [N/A]`** (un PID, sin memoria por proceso; no era el PID del servidor, 20850, que sería el proceso padre). Es decir, aquí `compute-apps` no salió vacío, pero no sirve para decidir: el PID no coincide con el nuestro y no da memoria. Tras `stop`, `memory.used` volvió a 0 MiB al primer sondeo.

## 4. Lanzador y comparativa
```
uv run --project ai-module-py python tools/experiments/run_matrix.py \
    --profiles qwen3-14b-t0,qwen3-30b-a3b-t0 --scenarios demo,wind --reps 3 [--id etiqueta]
uv run --project ai-module-py python tools/experiments/run_matrix.py --resume <id>     # salta las ok
uv run --project ai-module-py python tools/experiments/run_matrix.py --fake --profiles … # sin GPU
uv run --project ai-module-py python tools/experiments/run_matrix.py --dry-run …        # solo el plan
uv run --project ai-module-py python -m ai_module.compare experiments/<id>              # regenera compare.md
```
Otros: `--keep-server` (no parar al final), `--ask CONV:CUÁNDO:TEXTO` (sustituye a las preguntas por defecto), `--no-ask`, `--run-timeout S` (1800 por ejecución), `--platform-port`.

- Recorre perfil por perfil (para cambiar de servidor lo menos posible). Si la sección `server` del perfil es la del servidor en marcha, lo reutiliza; si no, `serve.sh stop` (espera a que se libere la GPU) y `serve.sh start`. **Antes del primer arranque** ejecuta `gpu-idle`. Comprueba `/health` entre ejecuciones: si el servidor cae, si no arranca o si la GPU no se libera, **para la matriz sin reintentar** (salida 3) y deja lo hecho. Al final, para el servidor (salvo `--keep-server`) y genera `compare.md` aunque falle.
- Cada ejecución: `platform_app.run --scenario S --speed 16 --wait-agent --evaluate --profile P` con las preguntas: en `demo`, las tres del guion («Why do you think it is wind?» al monitor a T+110 s, «What did you look at on the link?» a T+342 s, «Which was the most serious anomaly and why?» al informe al final); en los otros cinco, solo la última al informe (decisión tuya).
- `experiments/<id>/`: `manifest.json` (argumentos, perfiles con huella y servidor, huella de `agent-assets`, versión de vLLM, del SDK `openai` y del repo —`git rev-parse HEAD` y si hay cambios sin guardar, solo lectura—, estado de cada ejecución), `runs/<perfil>/<escenario>/r<k>/` (`eval.md`, `eval.json`, `llm_trace.jsonl`, `timeline.jsonl`, `informe.md`, `run_meta.json`, `profile.json`), `logs/` y `compare.md`. Solo `compare.md` se versiona.
- `compare.md`, por escenario y una fila por perfil: aciertos por etiqueta k/N (✅), etiquetas con una sola cadena k/N, falsas alarmas, fallbacks, alertas abiertas, frases que contradicen, no latinos (monitor / informe / chats), rechazos de guardrails, cortes por longitud (monitor / informe / chats), latencia p50 / p95 por llamada del monitor (y por invocación), tokens medios por ejecución (prompt / respuesta / razonamiento; si vLLM no da los tokens de razonamiento, los caracteres) y estabilidad: firma de cada repetición = por etiqueta, las causas de sus avisos en orden, número de cadenas y cierres, más las alertas abiertas; «estable (N/N)» o «k/N iguales — otras: …». Al final, el detalle de cada repetición. Las ejecuciones sin resultado cuentan como fallo en los k/N.

## 5. Razonamiento: lo que se ha comprobado (⚠️ de la petición)
Con el vLLM 0.31.0 real, Qwen3-14B-AWQ y `llm_check --profile qwen3-14b-t0` (apartado 6):
- **vLLM 0.31 sí pasa el razonamiento de entrada a la plantilla, con los dos nombres.** Misma conversación (usuario → asistente con tool call → resultado de la tool), `max_tokens` 1: `prompt_tokens` sin el campo = 199; con `reasoning` = +624; con `reasoning_content` = +624. El motor usa `reasoning_content` (constante `REASONING_INPUT_FIELD`). No ha hecho falta buscar otra vía.
- **El recordatorio corta la cadena, confirmado:** con un mensaje de usuario al final (lo que añade el motor), el campo suma 0 tokens: la plantilla ya no lo enseña. Anotado en el docstring del motor. Los intentos fallidos de solo texto no se guardan en `messages`, así que su razonamiento tampoco (queda en la traza).
- `usage.completion_tokens_details.reasoning_tokens` **sí viene** (420 de 427 tokens en la prueba). El razonamiento en streaming llega en `delta.reasoning` y no se entrega a la web.
- El razonamiento de turnos anteriores de un chat no vuelve al modelo (el historial guarda solo respuestas finales; además la plantilla lo descartaría).
- Los chats y el informe, al no tener tools, hacen una sola llamada: el razonamiento solo se traza.

## 6. Comprobaciones
### Automáticas (sin LLM real)
| Comprobación | Resultado |
|---|---|
| `contracts/python` pytest | 128 passed, 1 skipped (igual) |
| `platform` pytest | **208 passed** (+2) |
| `ai-module-py` pytest (incluye 2 e2e con el LLM falso: la demo de siempre y una matriz completa de 2 modelos × 2 repeticiones con cambio de servidor) | **346 passed** (+42; las dos e2e incluidas, 3 min 11 s) |
| `ruff check` y `ruff format --check` (repositorio entero) | limpios (157 ficheros) |
| `serve.sh` con un `vllm` y un `nvidia-smi` falsos | 7 pruebas: `--dry-run`, modelo vetado, modelo fuera de la caché, servidor ajeno (no se toca), arranque/reutilización/negativa a un segundo servidor/parada, GPU que no se libera, servidor que muere al arrancar |
| Huella de `agent-assets` | `e28d071e856efb09` (sin cambios; una prueba la compara con el comando `find … \| sha256sum`) |

Pruebas nuevas: `test_profiles.py`, `test_serve_sh.py`, `test_compare.py`, `test_run_matrix.py`, más casos en `test_engine.py` (razonamiento en la traza, devuelto al modelo, cortado por el recordatorio, no al streaming), `test_evaluate.py` (no latinos, cortes, cabecera de perfil, espera del perfil) y `test_run_checks.py` de la plataforma.

### Prueba corta con el LLM real (punto 8)
1. `serve.sh gpu-idle` → 0 MiB. `serve.sh start qwen3-14b-t0` → PID 20850, **listo en 78 s** (versión `0.31.0`; 1 min 30 s con las comprobaciones).
2. `llm_check --profile qwen3-14b-t0`: **15 de 15 ✅**. Las 9 de siempre (tool calls con y sin streaming, `include_usage`, `timeout`, `extra_body`, `required`, `max_tokens`, `max_completion_tokens`, temperatura 0 determinista) y las 6 de razonamiento: pedido (`reasoning` 1120 caracteres, 420 `reasoning_tokens`), apagado (vacío), `required` con razonamiento (tool call + 366 caracteres), streaming (`delta.reasoning`), **la plantilla recibe el razonamiento devuelto (+624 tokens con `reasoning` y con `reasoning_content`)** y el recordatorio lo corta (+0 tokens). Nota: las 9 de siempre no envían `enable_thinking`, así que corren con el razonamiento por defecto del servidor (activo).
3. `run_matrix --id e-prueba-corta --profiles qwen3-14b-t0 --scenarios nominal --reps 1`: **ok en 36 s**. `nominal`: ✅ 0 falsas alarmas, 0 fallbacks, 0 alertas abiertas; informe y chat del informe contestaron (2719 tokens de prompt y 324 de respuesta en total); sin caracteres no latinos. Reutilizó el servidor ya arrancado (`gpu-idle` avisó de que había uno en marcha, sin consecuencias) y **lo paró al final** (`GPU free: 0 MiB <= 512 MiB`). Estado final: `serve.sh status` → sin servidor, puerto 8000 libre, 0 MiB. **Nada más con el LLM real.** El `compare.md` de esta prueba queda en `experiments/e-prueba-corta/compare.md`.

## 7. Problemas y avisos
- **Escritura en git (regla 12), sin querer:** al mover `tests/fake_llm_server.py` ejecuté `git rm --cached` sobre ese fichero, que modifica el índice. El estado es `D  ai-module-py/tests/fake_llm_server.py` (borrado preparado) en lugar de ` D`. No lo he deshecho (cualquier arreglo escribiría también en git); el fichero ya no existe en el árbol de trabajo y su contenido está en `ai_module/testing/fake_llm.py`. Tu commit lo recoge igual.
- El hook de ruff avisó de líneas largas y de un `try/except/pass` en ficheros nuevos; corregido en el momento. Un script de parcheo mío abortó a medias en `evaluate.py` y dejó `llm.py` con una línea duplicada (error de sintaxis); reparado antes de seguir. No ha llegado nada roto al resultado.
- Las 9 comprobaciones previas de `llm_check` corren con el razonamiento activo en el servidor (por defecto); en el perfil `-t0` la PoC lo apaga por petición. No cambia ningún resultado, pero conviene saberlo al leerlas.
- Límites de esta fase: los tiempos de los perfiles `-think` son provisionales y **no se han ejecutado nunca con el modelo real**; el 30B-A3B no se ha arrancado en esta fase (solo se ha comprobado su `--dry-run`: mismo comando que el del banco (hermes + `--reasoning-parser qwen3`) y flags aceptados por este vLLM); ningún perfil Qwen3 se ha probado en un escenario con anomalías.
- Cuelgues: ninguno (ni de Windows, WSL o vLLM) durante la prueba corta.

## 8. Plan de experimentos (siguientes fases; una variable cada vez)
Cada matriz con `--reps 3`, los seis escenarios (`nominal,wind,hijack,spoofing,faults,demo`) salvo que se diga otra cosa. Si Windows, WSL o vLLM se cuelgan: parar y avisar. Tras cada matriz: leer `compare.md` y las trazas dudosas, y escribir un informe corto.
- **E0 · referencia.** `--profiles actual`. Repite la línea base con la métrica nueva (no latinos, cortes, estabilidad) y el mismo lanzador. Criterio: demo 3/3 (referencia de la 5.2), `faults` 2/3 (F2 y F3 conocidos). Sirve también para ver la variabilidad real a temperatura 0.
- **E1 · solo cambia el modelo.** `--profiles qwen3-14b-t0,qwen3-30b-a3b-t0` (sin razonamiento, temperatura 0, repetition 1,05, todas las ayudas como hoy). Compara con E0: aciertos, cadenas, fallbacks, contradicciones, no latinos (el 30B contestó en español a un usuario en español en el nivel 1), latencia y tokens. Primera ejecución de cada modelo con `demo` ×1 para vigilar la carga.
- **E2 · muestreo de Qwen.** `--profiles qwen3-14b-qwen,qwen3-30b-a3b-qwen` (comparten servidor con E1: conviene lanzarlos en la misma matriz que E1 para no reiniciar). Pregunta: ¿la temperatura 0,7 con presence 1,5 degrada la reproducibilidad (estabilidad) o mejora algo (fallos de formato, bucles)?
- **E3 · razonamiento.** Primero `--profiles qwen3-14b-think,qwen3-30b-a3b-think --scenarios demo --reps 1` para **medir** latencia por llamada y por invocación, tokens de razonamiento y cortes por longitud, y fijar `max_invocation_s`, `llm_timeout_s`, `max_tokens` y la espera de la plataforma de los perfiles `-think` (nueva huella de perfil; condición: monitor + 15 < espera). Después, la matriz completa ×3. Pregunta: ¿el razonamiento sustituye alguna ayuda o solo añade latencia?
- **Después (Fase 8 en adelante):** con el mejor perfil, quitar ayudas en el orden de `docs/mejoras_futuras.md` («Liberar al agente») con perfiles que cambien un interruptor cada vez (`agents.monitor.coherence_guardrail: false`, etc.), parando en el primer paso en que algún escenario empeora.

## 9. Qué queda
- Ejecutar E0–E3.
- Pendientes de la 5.3 sobre el chino en el chat del monitor: ahora se mide; el guardrail de idioma se decide con datos de E1–E3.
- Fijar los tiempos de los perfiles `-think` (E3).
- `docs/quien_decide_que.md`: añadido el §3 bis (qué pone un perfil); no cambia quién decide qué.

## 10. Copias (reglas 13 y 15)
Copiados a `/mnt/c/CITADEL/_CLAUDE/poc-ai-monitor/results/`: `docs/fases/` y `docs/modelos/` (en `docs/`), los PNG, `eval.md` e `informe.md` de `runs/` (incluidas las ejecuciones nuevas de `nominal`), el `compare.md` de la prueba corta (`experiments/e-prueba-corta_compare.md`), `snapshots/fase6/` y `snapshots-limpias/fase6/`. Las dos comprobaciones de la regla 15 (palabras prohibidas y nombres propios) **salen vacías**; no ha hecho falta corregir nada. Como en la 5.1, `git ls-files` aún lista `ai-module-py/tests/fake_llm_server.py` (borrado preparado en el índice) y `cp` puede avisar de que no existe: es inofensivo.

## 11. Mensaje de commit propuesto
```
feat: phase 6 - infrastructure to compare models

- model-profiles/: 7 profiles (actual, Qwen3-14B and Qwen3-30B-A3B with Qwen
  sampling, temperature 0 or reasoning) applied in memory over agents.yaml; the
  frozen agent-assets are untouched (hash e28d071e856efb09)
- tools/vllm/serve.sh: start/stop a profile's vLLM server (one at a time, never
  touches a foreign server, waits for the GPU to be free)
- engine: per-request reasoning switch, reasoning text and tokens in the trace,
  reasoning returned to the model inside an invocation (vLLM 0.31 passes
  reasoning_content to the template; the reminder message cuts the chain)
- evaluate: profile and effective parameters in the header, non-Latin characters,
  length cuts and reasoning tokens
- tools/experiments/run_matrix.py + compare.md: profiles x scenarios x repetitions,
  manifest, stability; --fake mode with the fake LLM server (ai_module/testing)
- platform: --wait-timeout; run.py --profile
- docs: phase 6 report with the experiment plan E0-E3, model references
```
