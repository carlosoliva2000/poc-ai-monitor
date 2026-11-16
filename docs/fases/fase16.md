# Fase 16 · Comando de viento del instructor

Escrito para: Carlos. Perfil `actual` (Qwen3-14B-AWQ sin razonamiento, T=0). Contrato v0.18, aditivo. Git solo de lectura. Tres pasos y una prueba de extremo a extremo con el modelo.

## Resumen

| Paso | Resultado |
|---|---|
| 1 · Contrato y simulador (sin GPU) | `InstructorCommand` (`evt` + `sim`), `control` → `instructor`, `commands:` en el escenario, viento del instructor en el simulador, escenario `nominal-wind-cmd`, etiquetas. Contratos 189, plataforma 283, módulo 705. |
| 2 · Panel «Instructor» en la web (sin GPU) | Panel desplegable, viento activo con lo que le queda, marca en el timeline. Web: 61 pruebas, `pnpm typecheck` y `pnpm build` limpios; capturas a 1920×1080. |
| 3 · Agente del instructor (LLM) | Pestaña «Instructor» con tarjeta Confirm / Edit / Discard; agente `chat_instructor` con `propose_wind` y `propose_cancel_wind`. Guion de las 9 frases (las 8 pedidas, con «Stronger» dos veces) 9/9 bien, estable en 27 de 27; latencia mediana 0,6 s. |
| Extremo a extremo | `nominal-wind-cmd` ✅ 1/1; pasada en directo con comando del panel y del chat, las dos con alerta `WIND`; `demo` 3/3. |

**Una decisión de Carlos en el camino:** `nominal-wind-cmd` quedó a **T+01:35** y no a T+01:00. A T+01:00 el dron va por el primer tramo casi de cara al viento del norte y solo se desvía 12,9 m (el detector abre a 30 m). Medido: T+01:35 del norte 48,2 m; T+01:20 del norte 44,1 m; T+01:00 del oeste 41,9 m. Elegiste T+01:35, igual que el episodio de `demo`.

## Paso 1 · Contrato y simulador

**Contrato v0.18** (`contracts/eventos.md`, `contracts/python`, `contracts/schemas/`):
- Evento **`InstructorCommand`** (id `cmd-`, topic `citadel.pub.evt.sim.instructor.InstructorCommand.v1`, source `platform-player`, dominio `sim`): `command` (`set_wind` | `cancel_wind`), `params`, `issued_by` (`panel` | `llm` | `scenario`) y `text` (la frase original si viene del LLM). Pensado para que luego quepan otros comandos sin romperlo. El módulo de IA no se suscribe a él.
- **`WindCommandParams`** (m/s y grados): `from_deg` 0–360 (360 = 0), `speed_mps` 0–40, `gust_mps` entre la velocidad y 60, `ramp_s` mayor que 0 y hasta 120, `duration_s` mayor que 0 y hasta 1800 o `null` (hasta nuevo aviso). Qué hace cada uno está dicho en el contrato, en el panel y en el prompt: velocidad y dirección empujan al dron; la rampa suaviza la subida y la bajada; la racha no empuja, solo la mide la estación y cuenta para que el viento sea «notable».
- `control` → `instructor` del WebSocket (solo `web`, solo con el modo interactivo encendido, como `fault`); `commands:` opcional en el YAML (los 8 escenarios no cambian ni `runs/`); `ConversationId.INSTRUCTOR`, `OperatorMessage.context` y `AgentReply.proposal`, opcionales.

**Simulador:** el viento del instructor es un episodio más aplicado **después** de los del escenario, así que **sustituye** al viento que haya (no se suma): sube con su rampa desde el viento de ese instante, dura `duration_s` y baja con la misma rampa. Un `set_wind` nuevo relevó al anterior sin saltos y `cancel_wind` baja el activo con su rampa; cancelar sin viento activo es un error. No gasta números aleatorios: la estación lo mide con su ruido de siempre y el dron se desvía con la física de siempre; el comando va en la línea temporal después de los fallos de ese instante.

**Etiquetas** (ningún agente las ve): un comando programado lo etiqueta el generador como un episodio de viento (`A1`, `ROUTE_DEVIATION`, `WIND`, ventana del comando); uno en directo lo etiqueta la evaluación a partir de los `InstructorCommand` del timeline (`A101`…, solo los que no son de `scenario`). La ventana acaba por duración, por el siguiente comando o por el fin del vuelo.

**Escenario `nominal-wind-cmd`** = `nominal` + `set_wind` a T+01:35 (del norte, 12 m/s, rachas 16, 60 s, rampa 10 s). Determinista (dos generaciones iguales), los eventos anteriores al comando son idénticos a `nominal` y el ruido del enlace y de la batería también. El detector avisa `ROUTE_DEVIATION` a T+01:47 (31,1 m) y cierra a T+02:41 (máximo 49,3 m). Cambia en `runs/`: solo `runs/nominal-wind-cmd/` (nuevo, con sus PNG); el resto, idéntico tras regenerar los nueve.

**Pruebas:** contratos (validación, evento, mensaje, topics y fuentes del chat, escenario), plataforma (`test_instructor.py`: rangos, rampa, duración, cancelación, relevo, determinismo, etiquetas, reproductor; `test_api.py`: WebSocket y que un cliente `ai-module` con los patrones del módulo no recibe el comando), módulo (`test_bus_client.py`: el comando no casa con ningún patrón; `test_evaluate.py`: etiquetas en directo).

## Paso 2 · Panel «Instructor»

`instructor-panel.tsx` y `lib/instructor.ts` (con pruebas): desplegable (se recuerda abierto o cerrado) junto al de fallos, que no cambia. Rosa de 16 rumbos (botones) más grados, velocidad, racha, duración (o «Until cancelled») y rampa, con la ayuda corta, validación del formulario con los rangos del contrato, «Apply» y «Cancel wind» y la línea «Instructor wind: from N (0°), 12 m/s, gusts 16 m/s, 60 s, ramp 10 s · since T+01:36 · 55 s left». Con el modo interactivo apagado, todo deshabilitado y lo dice. El comando sale por el WebSocket (`control` → `instructor`), como los fallos. En el timeline el `InstructorCommand` va como evento del simulador (naranja, texto `set_wind: from N (0°), 12 m/s, …`) y en la barra de progreso.

Capturas (`experiments/fase16/capturas/`, 1920×1080): `01_panel_plegado`, `02_panel_desplegado`, `03_viento_activo`.

## Paso 3 · Agente del instructor

- **`agents.yaml`**: agente `chat_instructor` (T=0, `top_p` 1, streaming, `tool_choice: auto`, 4 iteraciones), sin tools de datos ni skills. **`tools.json`**: `propose_wind(from_direction, speed_mps, gust_mps?, duration_s?, until_cancelled?, ramp_s?)` y `propose_cancel_wind`. **Prompt** `chat_instructor_system.md`, en inglés y corto.
- **`ai_module/instructor.py`**: el LLM pasa el rumbo **tal como lo dijo el instructor** y el **código** lo convierte a grados (`NE`, `north-east`, `from the north-east`, `225`, `225°`…), rellena lo que falta y lo dice (`defaults_used`: racha = 1,3 × velocidad, 60 s, rampa 10 s), valida con los mismos rangos que la plataforma y devuelve los errores al modelo. **No publica nada**: la propuesta válida va en `AgentReply.proposal`.
- **Web**: pestaña «Instructor» junto a Monitor e Informe. La pregunta lleva `context.active_wind` (el módulo no ve el comando; para «Stronger» y «Remove the wind»). La tarjeta enseña «Wind from N (0°), 12 m/s, gusts 16 m/s, 60 s, ramp 10 s · Filled in by default: ramp_s» con **Confirm** (manda el comando con `issued_by: llm` y la frase original), **Edit** (abre el panel con esos valores) y **Discard**. Sin modo interactivo no se puede confirmar.
- **No ve al monitor ni el monitor a él:** el `OperatorMessage` del instructor lleva source `web-instructor`, así que `get_events` con `operator` no lo devuelve; el comando va en el dominio `sim` y el módulo no lo recibe.

### Guion con el modelo (sin web, `tools/experiments/instructor_script.py`, vLLM `actual`)

Todas con T=0. Latencia = de la pregunta a la respuesta completa (mediana 0,6 s, de 0,2 s a 1,7 s en 27 ejecuciones).

| # | Frase | Llamada | Propuesta validada | Latencia |
|---|---|---|---|---|
| 1 | Wind from the north-east at 8 m/s on the drone | `propose_wind(north-east, 8)` | `set_wind` 45°, 8 m/s, racha 10,4, 60 s, rampa 10 s (por defecto: racha, duración, rampa) | 1,7 s |
| 2 | Put a 12 m/s wind from the north with gusts of 16 for one minute | `propose_wind(north, 12, gust 16, 60 s)` | 0°, 12 m/s, racha 16, 60 s, rampa 10 s (por defecto: rampa) | 1,6 s |
| 3 | West wind, 10 m/s, for 2 minutes | `propose_wind(west, 10, 120 s)` | 270°, 10 m/s, racha 13, 120 s, rampa 10 s (por defecto: racha y rampa) | 1,4 s |
| 4 | Wind from 225 degrees, 8 m/s, gusts 12, ramp up in 20 seconds | `propose_wind(225, 8, gust 12, ramp 20)` | 225°, 8 m/s, racha 12, 60 s, rampa 20 s (por defecto: duración) | 1,7 s |
| 5 | Remove the wind (con viento activo) | `propose_cancel_wind()` | `cancel_wind` | 0,8 s |
| 6a | Stronger (sin viento activo) | ninguna | ninguna: «Please provide the new wind speed in m/s and mention the current wind if there is one.» | 0,3 s |
| 6b | Stronger (con viento activo de 12 m/s) | ninguna | ninguna: pregunta la nueva velocidad en m/s | 0,3 s |
| 7 | Wind from the south | ninguna | ninguna: «Please provide the wind speed in m/s.» | 0,2 s |
| 8 | East wind at 100 m/s | ninguna | ninguna: «…exceeds the maximum allowed limit of 40 m/s. Please provide a wind speed between 0 and 40 m/s.» | 0,6 s |

Texto completo de las respuestas, con las 3 repeticiones por frase: `experiments/fase16/instructor-guion.md` (27 de 27 iguales a la tabla).

**Lo que salió mal y se corrigió:** en la primera pasada la 7 («Wind from the south») **inventó 0 m/s** y propuso un viento de 0 m/s con los valores por defecto. Se añadió al prompt que la velocidad es el único valor que no se inventa («ask for the speed; do not use 0») y en las 3 repeticiones siguientes pregunta. **Límites que quedan, sin tapar:** (a) en la 8 el modelo contesta sin llamar a la tool (el prompt ya da el límite de 25 m/s), así que el rechazo del código ante fuera de rango se prueba con tests, no con el modelo; (b) en la 6b no cita el viento activo aunque el prompt lo pide («mention the current wind if there is one»); (c) «Stronger» no se interpreta como orden relativa: se pregunta la velocidad (propuesta en `docs/mejoras_futuras.md`).

## Prueba de extremo a extremo (perfil `actual`)

1. **`nominal-wind-cmd` ×1** con «esperar al agente» a 16× (`runs/nominal-wind-cmd/20261112-152026/eval.md`): detector `ROUTE_DEVIATION` a T+01:47 (31,1 m), el monitor publica `WIND` (`medium`, confianza 0,8) a T+01:48 con la estación («Wind reported from N (352°)… gusts up to 9.7 m/s (met-0010)»; `wind_notable` y `wind_with_drift` verdaderos), cierra a T+02:41 cuando el dron vuelve a la ruta. **Etiqueta ✅ 1/1**, 0 falsas alarmas, 0 fallbacks, 0 frases que contradicen los checks, 0 checks que no cuadran. La traza del monitor no menciona el comando en ningún sitio.
2. **Pasada en directo por la web** (`nominal` a 4×, «esperar al agente», interactivo; `capture.mjs fase16`, 1920×1080): comando del **panel** (del norte, 12 m/s, rachas 16, 60 s, rampa 10 s) a T+01:36: la estación mide 11,5–12,4 m/s y rachas de hasta 16,3, `ROUTE_DEVIATION` a T+01:48 (31,5 m, máximo 49,2), alerta `WIND` `medium` a T+01:48, cierre a T+02:42. Comando del **chat del instructor** («Wind from the north at 12 m/s with gusts of 16 for one minute»): la tarjeta propone «Wind from N (0°), 12 m/s, gusts 16 m/s, 60 s, ramp 10 s» (rampa por defecto), se confirma a T+03:04 (`issued_by: llm`, con la frase original en el evento), `ROUTE_DEVIATION` a T+03:25 (30,7 m, máximo 32,3) y alerta `WIND` `medium` a T+03:25, cierre a T+04:08. Capturas: `04_alerta_wind_panel`, `05_tarjeta_propuesta`, `06_propuesta_confirmada`, `07_alerta_wind_chat` (+ las del paso 2).
   - **A 12 m/s sí hay desviación suficiente para el detector, pero el segundo comando va justo:** a T+03:04 el dron va por el tramo WP1→WP2 y la desviación máxima fue 32,3 m (umbral 30 m). El primero, a T+01:36, llegó a 49,2 m. Para una demo con margen, es mejor poner el comando antes de T+02:00 o con más de 12 m/s.
3. **`demo` ×1** (sin comandos, no regresión): **3/3**, 0 falsas alarmas, 0 fallbacks, 0 esperas agotadas, 0 alertas abiertas al final, `runs/demo/20261112-152537/eval.md`.

## Corrección posterior: el agente «proponía» sin llamar a la herramienta

**Qué se vio** (conversación de Carlos, `runs/nominal/20261112-160212/llm_trace.jsonl`): tras un par de turnos, el chat del instructor contestaba «I propose a wind from the east at 25 m/s… by default» **sin llamar a `propose_wind`** (la web decía «no tool calls»): no había tarjeta que confirmar. De las 7 órdenes de viento de esa conversación, **5 no llamaron a la tool** (la primera y la quinta sí).

**Causa (comprobada en la traza):** el historial del chat guardaba solo el texto de cada respuesta, sin la llamada a la tool ni su resultado. Con dos turnos de «I propose…» en el historial, el modelo imitaba ese texto en vez de llamar a la tool. Mi guion de 27 de 27 no lo vio porque reiniciaba el historial en cada frase: probé las frases sueltas y no una conversación. Además repetía «by default» sin que el código hubiera rellenado nada.

**Corrección (sin `tool_choice: required`, a petición de Carlos):**
1. **Historial fiel**: se guarda el intercambio completo (pregunta, llamada a la tool, resultado y respuesta), así que lo que el modelo imita es una llamada real; el historial cortado por delante no empieza nunca por un resultado de tool.
2. **Guard en el código**: si la respuesta da por hecha una propuesta (cifras de viento con «gust/ramp/default/confirm», o «propose»/«please confirm») y no hubo llamada a la tool, se descarta esa respuesta, se recuerda una vez que hay que llamar a la tool y, si aun así no lo hace, se contesta un texto fijo («I could not prepare a proposal. Say the wind again…») en vez de fingir. La traza anota `retried_without_tool`.
3. **El texto de una propuesta lo escribe el código** (`describe_proposal`): «Wind from E (90°), 25 m/s, gusts 32.5 m/s, 20 s, ramp 10 s. Filled in by default: gust_mps, ramp_s. Confirm it, edit it or discard it.»; «por defecto» solo sale de lo que el código rellenó. Prompt: una línea más (cada propuesta necesita su llamada, aunque haya otra parecida antes).

**Prueba** (`instructor_script.py --keep-history`, una conversación seguida de 10 turnos con tus frases, ×3): **27 de 27 órdenes de viento llaman a la tool** y «stronger» pregunta la nueva velocidad sin proponer. Con el arreglo a medias (solo el guard y el texto del código, con el historial aún de solo texto) fallaban 4 de 9 órdenes: el modelo pasó a imitar el texto nuevo del código. No se mide cuántas veces saltó el reintento (el script no lo guarda); los tests del módulo cubren el reintento y el respaldo (33 en `test_instructor.py`).

## Límite de velocidad subido a 40 m/s

El 25 m/s lo propuse yo en el contrato (no es un límite físico del simulador). Por petición de Carlos, **velocidad 0–40 m/s y racha hasta 60 m/s** (la racha por defecto, 1,3 × velocidad, llega a 52): `poc_contracts.commands`, `web/lib/instructor.ts`, prompt, `tools.json`, contrato y esquemas re-exportados. Con más de 15 m/s (la velocidad de crucero del dron) de cara, el dron no avanza contra el viento: la misión puede acabar por `timeout` (900 s). No se ha probado a 40 m/s con el simulador.

## Pruebas

Contratos 189 (1 omitida), plataforma 283, web 61 + `pnpm typecheck` + `pnpm build`, módulo de IA 705 (3 min 33 s, 0 fallos; incluye el e2e con LLM falso). `ruff check` y `ruff format` limpios. Los esquemas (`contracts/schemas/`) se re-exportaron: nuevos `commands`, `ProposeWindArgs` y `InstructorCommand`.

## Problemas

- **Dos errores míos de operación:** (1) un `pkill -f` con el patrón del propio comando mató mi shell (el mismo tropiezo que anotó la Fase 15; después paré por PID). (2) Maté con prisa una tanda de pruebas del módulo creyendo que estaba colgada: tarda unos 4 minutos y estaba avanzando; dejó un `platform_app.run` vivo en el puerto de prueba 8199 que luego hizo fallar dos tests por «puerto en uso». Paré esos procesos por PID (eran míos) y repetí la tanda entera.
- **`json.dump` reformateó `tools.json` entero** al añadir las dos tools; lo restauré desde `git show HEAD:…` (solo lectura) y añadí las dos entradas como texto: el diff final son 27 líneas.

## Quién decide qué (contrastado con el código)

`docs/quien_decide_que.md` actualizado (fila nueva «Instructor y su agente» y un caso en §2): el **instructor** decide qué viento y cuándo; el **LLM** solo interpreta y propone; el **código** convierte el rumbo, rellena (y lo dice), valida y vuelve a validar en la plataforma; la **web** solo publica el comando al confirmar; el **monitor** sigue decidiendo la causa del viento sin que le lleguen el comando ni este chat.

## Ficheros

Nuevos: `contracts/python/src/poc_contracts/commands.py`, `scenarios/nominal-wind-cmd.yaml`, `runs/nominal-wind-cmd/`, `ai-module-py/src/ai_module/instructor.py`, `agent-assets/prompts/chat_instructor_system.md`, `web/components/mission/{instructor-panel,proposal-card}.tsx`, `web/lib/instructor.ts`, `tools/experiments/instructor_script.py` y los tests (`test_commands.py`, `test_instructor.py` del módulo y de la plataforma, `lib/instructor.test.ts`). Modificados: contratos (`eventos.md` v0.18, `enums`, `payloads`, `scenario`, `topics`, `tools`, `ws`, esquemas), plataforma (`generator/{disturbances,sensors,simulator,build}.py`, `player.py`, `app.py`), módulo (`chat.py`, `module.py`, `evaluate.py`), `agent-assets/{agents.yaml,tools.json}`, web (`mission-console`, `agent-console`, `chat-panel`, `sim-controls`, `lib/{contracts,derive,format}.ts`, `hooks/use-platform.ts`, `scripts/capture.mjs`), `scenarios/README.md`, `docs/` y los `CLAUDE.md`.

## URLs consultadas

Ninguna (código propio; sin librerías nuevas).

## Mensaje de commit propuesto
```
feat: phase 16 - instructor wind command (contract v0.18), instructor panel and agent

InstructorCommand (sim domain, cmd- ids): set_wind / cancel_wind with from_deg, speed_mps,
gust_mps, ramp_s and duration_s, issued by the panel, an LLM proposal that the instructor
confirmed, or the scenario (commands: in the YAML). The wind of the instructor replaces the
scenario wind (ramp up and down, handover without jumps). The AI module does not subscribe to
it: the monitor finds the wind through its effects. Wind labels for scheduled and live commands.
Scenario nominal-wind-cmd (set_wind at T+01:35).

Web: collapsible Instructor panel (16-point rose, m/s, duration, ramp, apply/cancel, active
wind) and an Instructor chat tab with a proposal card (Confirm / Edit / Discard). Agent
chat_instructor with propose_wind and propose_cancel_wind: the LLM interprets, the code converts
the compass point to degrees, fills defaults (and says so) and validates; nothing is published
until the instructor confirms.
```
