# Fase 4 · web, y dos arreglos previos (esperar a los cierres y supersedes sin cambios)

Fecha: 22/10/2026. Estado: **terminada, pendiente de tu revisión**. Contrato **v0.9** (cambios de texto y de comportamiento; modelos Pydantic y esquemas JSON sin cambios: se ha vuelto a exportar y `git status` no muestra diferencias). **`agent-assets/` y `agents.yaml` no se han tocado**: huella `40e5049dbf83198c`, igual que en la 3.1.

## 1. Parte 0 · dos arreglos antes de la web

### (a) «Esperar al agente» también espera los cierres
- `platform/src/platform_app/player.py` (`_on_ai_event`): el reproductor se pausa con `DetectionRaised`, `DetectionUpdated` **y `DetectionCleared`** y se reanuda cuando el monitor ha respondido a cada uno (evento de `ai-monitor` con su `event_id` como `causation_id`: `AnomalyDetected`, `AlertClosed` o `DetectionAcknowledged`, también la determinista y la de fallback). El resto no cambia (90 s de reloj como tope, una pausa del usuario no se levanta sola).
- `contracts/eventos.md` → v0.9: §4 («Cada evento de detección recibe respuesta») y regla 2 de `publish_alert` en §7. Actualizados `docs/01_definicion.md` (descripción del interruptor) y `platform/CLAUDE.md`.
- Pruebas (`platform/tests/test_player.py`): la que decía «no pausa con un cierre» pasa a `…pauses_on_a_cleared_detection_and_resumes_with_the_alert_closed`, y una nueva reanuda un cierre con un `DetectionAcknowledged` determinista.

### (b) Guardrail: `supersedes` que no cambia nada
- `ai-module-py/src/ai_module/agent/guardrails.py`: `publish_alert` con `supersedes` se rechaza si la causa y la severidad son las de la alerta sustituida: «No cambia nada respecto a ai-XXXX (misma causa y severidad): usa acknowledge_detection con alert_id ai-XXXX». Es siempre activo (hace cumplir la tabla del contrato; no es una ayuda con interruptor, y `agents.yaml` no se toca).
- Choque con la recuperación excluyente: esa regla manda «severity medium y supersedes X». Si X sigue abierta y **ya es `medium`**, el mensaje pasa a «Es la recuperación del … de X, que ya es medium: no cambia nada, usa acknowledge_detection con alert_id X», para que las dos reglas no se contradigan (la recuperación sobre una alerta alta, que es lo que pasa en `demo`, no cambia).
- Pruebas: `test_supersedes_must_change_the_cause_or_the_severity` (`test_guardrails.py`) y `test_recovery_of_a_gps_alert_that_is_already_medium_is_an_acknowledgement` (`test_coherence.py`). El helper `alert()` de `test_monitor_state.py` admite ahora `severity`.

### Informe más sencillo
`report_facts.py`: el estado de una anomalía dice «cerrada por el monitor a T+X»; el paréntesis «la última detección de la cadena terminó a T+Y» solo aparece si X − Y > 5 s (`CLOSE_GAP_S`), que es lo que pasa sin «esperar al agente». Prueba nueva `test_status_only_explains_the_gap_when_the_closure_is_late`; `ai-module-py/CLAUDE.md` §5 actualizado.

### Resultado de `demo` (16×, esperando al agente; `runs/demo/20261022-102442/`, la ejecución de control pedida)
| | R9 (`fase3.md`) | Fase 3.1 (`20261022-094440`) | Ahora (`20261022-102442`) |
|---|---|---|---|
| Causas y cadenas | WIND · GPS_SPOOFING (con su recuperación en la misma cadena) · HIJACK | igual | **igual** (A1 `ai-0002`; A2 `ai-0008`→`ai-0011`; A3 `ai-0018`) |
| Cierres | el modelo cerraba 34–46 s simulados tarde | T+03:12 · T+04:28 · T+08:07 (el fin de las detecciones era T+02:36 · T+03:54 · T+07:21) | **T+02:36 · T+03:55 · T+07:21**: a la hora del fin de su detección (o 1 s después) |
| Secuestro | 1.ª ejecución: una alerta y un reconocimiento; 2.ª y 3.ª: dos alertas (`supersedes` sin cambios) | dos alertas (`ai-0018` y `ai-0021`) | **una alerta (`ai-0018`) y un `DetectionAcknowledged` a la actualización de T+05:41** |
| `eval.md` | 3/3 | 3/3 | 3/3 · 0 fallbacks · 0 alertas abiertas · 0 esperas agotadas · 0 detecciones sin respuesta |
| Rechazos de guardrails | 4 | 3 | 3 (el veto nuevo no llegó a dispararse: el modelo reconoció directamente) |
| Tokens del monitor (prompt / salida) | 236.961 / 3.698 | 178.428 / 3.306 | 186.242 / 3.076 (máximo de prompt en una llamada: 8.535) |

No ha empeorado nada. El informe de esa ejecución dice «cerrada por el monitor a T+02:36», «… a T+03:54» y «… a T+07:21», sin paréntesis.

## 2. Parte 1 · la web

### Qué se ha hecho (`web/`)
Interfaz de v0 copiada (sin `node_modules`, `.next` ni capturas), adaptada y conectada a la plataforma. Aspecto de v0 conservado.
- **Se ha quitado:** `lib/sim/scenario.ts`, `dispatcher.ts`, `context.ts`, `hooks/use-simulation.ts`, `app/api/agent/route.ts`, `ai`, `@ai-sdk/react` y `@vercel/analytics` (y su `<Analytics/>`), el rótulo del modelo y `generator: 'v0.app'`. **Nada sale a la red** (regla 1): las fuentes IBM Plex ya no se piden a Google (`next/font/google`) sino a `@fontsource/*` autoalojadas; los scripts de `package.json` llevan `NEXT_TELEMETRY_DISABLED=1`; escucha solo en `127.0.0.1:3000`; `ignoreBuildErrors` se ha quitado y `tsc` y `next build` pasan.
- **Cliente** (`hooks/use-platform.ts`): `ws://127.0.0.1:8100/ws`, `hello` como `web`, suscripción a `citadel.pub.evt.>`, reconexión, y recuperación del timeline (`GET /api/timeline`) al conectar (se puede abrir la web a mitad de una ejecución). Envía `control` (cargar, play, pausa, paso, reinicio, velocidad, esperar al agente, modo interactivo, fallos) y publica `OperatorMessage`. Los eventos llegan en ráfagas y se vuelcan al estado cada 100 ms. `GET /api/scenarios`, `GET /api/plan` al cambiar de ejecución y `GET /api/truth` solo con la capa «verdad» activa (cada segundo mientras corre).
- **Mapa** (`drone-map.tsx`): **y hacia el norte** (se pinta `-y`); ruta planificada discontinua con waypoints, estela del GPS, puntos del GPS (huecos si no hay fix), puntos del radar, dron con su rumbo, verdad (apagada por defecto, en la leyenda «solo simulador, el agente no la ve»), flecha del viento (empuja hacia `from_deg + 180`) y resalte de la zona mientras hay una detección abierta. **Panel de capas** con casillas que se recuerdan en `localStorage` (con `try/catch`). Una fuente en `mute` atenúa su capa (y su casilla de telemetría).
- **Panel de fallos** (`fault-panel.tsx`): interruptor «Modo interactivo» (en `state.interactive`); con él apagado los controles están deshabilitados; «Silenciar» por fuente, «Pérdida de GPS» solo para el GPS, fallos en curso (fuente, tipo y origen) y las marcas de `FaultInjected`/`FaultCleared`/`InteractiveModeChanged` en la barra de progreso y el timeline («el agente no ve estos eventos, solo sus efectos»).
- **Controles**: escenario, play/pausa/paso/reinicio, velocidades 0,5–16×, «Esperar al agente» y «Modo interactivo», y barra de progreso con marcas (detecciones, alertas, cierres, fallos). **Aviso de espera**: cuando el último `SimulationPaused` es `waiting_agent` y el estado es `paused`, aparece una franja distinta de la pausa del usuario: «Esperando al monitor: analizando det-XXXX…» (o «el cierre de det-XXXX»; el id es el de la detección sin respuesta más antigua), con «pausa automática, no es una pausa del usuario»; desaparece al reanudarse. La cabecera pasa a «Esperando al monitor».
- **Telemetría** (x, y, velocidad, rumbo, fix, desviación de la ruta, distancia GPS–radar, viento, enlace con `controller_id`, batería) y **timeline** con filtro por fuente (GPS y radar ocultos por defecto; los eventos `sim` se ven, marcados).
- **Consola del agente**, pestañas **Monitor** e **Informe** (quién habla: detector, monitor, informe y operador):
  - *Monitor*: tira de alertas por episodio (A1, A2…; **una cadena de `supersedes` es una sola alerta**), detecciones del detector (alta, actualización y cierre), «analizando det-…» con puntos mientras el monitor trabaja, alertas (causa, severidad, confianza, resumen) con desplegable (explicación, recomendación, evidencias y **los `checks` como lista de sí/no**; «—» cuando no se miró el enlace), **marca «Sustituye a ai-XXXX (misma alerta, A2)»**, cierres, y reconocimientos («sigue la alerta X», «sin alerta» o «sin diagnóstico» si `fallback`). Abajo, el chat con el monitor en streaming.
  - *Informe*: el `ReportGenerated` en Markdown (`react-markdown` + `remark-gfm` por las tablas) y el chat con el agente de informe.
- `scripts/capture.mjs` (Playwright, Chromium en `~/.cache/ms-playwright`): conduce la web como una persona y saca las capturas (`demo`, `radar`, `gps`). La prueba se puede repetir.

### Pasa el revisor de contratos
Sin bloqueantes. Lo que señaló y lo que he hecho:
1. **El reconocimiento determinista de un cierre cuya alerta ya estaba cerrada publicaba `alert_id` con esa alerta cerrada**, y el contrato dice «la alerta abierta a la que pertenece, o `null`». **Corregido** en `monitor.py` (`alert_id` solo si la alerta sigue abierta; la razón sigue diciendo cuál era) y probado. Cambia lo que pinta la web («sin alerta» en vez de «sigue la alerta X» para una cerrada).
2. **La recuperación excluyente impone `severity medium` y eso no estaba en §7** (solo en la skill), y el código no lo verifica (solo comprueba `cause` y `supersedes`). **Documentado en §7**, sin cambiar el código: una recuperación con otra severidad sobre una alerta abierta que no sea `medium` sigue pasando. Si quieres que se verifique, es un cambio pequeño pero de comportamiento.
3. Web (corregido): `event_time` del `OperatorMessage` perdía los milisegundos (ahora solo se quita `.000`); `sim_time` salía del último `state` (cada 0,5 s de reloj): ahora el máximo entre ese y el del último evento; si no se puede enviar (sin conexión o sin escenario) se muestra un error y **no se borra el texto**; y la recuperación del timeline ya no vacía lo que llega por el socket (carrera al reconectar).
4. `web/AGENTS.md` (lo genera `next dev`) no está en la lista de exclusión de la regla 15: lo he borrado y añadido a `web/.gitignore` (no entra en las instantáneas). Si `next dev` lo regenera, sigue ignorado.
5. Conforme: la web solo habla con `127.0.0.1:8100` (HTTP y WS), sin `ai`/`@ai-sdk`/`@vercel`, sin CDN; tipos de `web/lib/contracts.ts` iguales a los modelos Pydantic; `/api/truth` solo con la capa; y arriba, rumbo y viento. El revisor **no pudo ejecutar nada** (sin Bash): las pruebas y `tsc` los he corrido yo (apartado 5).

### Las tres pruebas con el LLM real
Ejecuciones desde la web (una sola pestaña) con `scripts/capture.mjs`; `eval.md` con `ai_module.evaluate runs/<escenario>/<run_id>` al terminar. **Para estas ejecuciones no existe `run_meta.json` (lo escribe `run.py`), así que el `eval.md` pone «esperar al agente: n/d · velocidad: n/d»**; el resto es completo.

1. **`demo` a 4× con «esperar al agente», sin inyectar fallos** (`runs/demo/20261022-110035/`): **3/3**, 0 fallbacks, 0 alertas abiertas, 0 esperas agotadas. Alertas: `ai-0002` WIND (T+01:46) · `ai-0131` GPS_SPOOFING alta (T+03:12) → `ai-0134` GPS_SPOOFING media, sustituye (T+03:42) · `ai-0141` HIJACK (T+05:38) y un reconocimiento a su actualización (T+05:41). Cierres: T+02:36, T+03:54, T+07:21. Lo mismo que la ejecución de control de la Parte 0.
   - **Duración medida:** 220 s de reloj de pared en total con las dos preguntas a los chats: simulación terminada a los 201 s, informe a los 213 s. Sin esperar al agente, 4× son 139 s (556 s / 4): las 9 esperas suman ≈ 62 s (media 6,7 s, máxima 14,5 s, la de la recuperación del spoofing). Los chats respondieron en 2,5 s (monitor) y 3,2 s (informe); al tener sus propias tareas no frenan al monitor.
2. **`nominal` a 4×, radar silenciado desde la web** (`runs/nominal/20261022-110427/`): modo interactivo, «Silenciar Radar» en T+00:41, el detector abre `SOURCE_SILENT radar` a T+00:49, **el monitor publica `SENSOR_FAULT`** (confianza 0,6) a la misma hora simulada (7 s de reloj), al reactivarlo (T+01:11) el detector cierra y el monitor cierra la alerta a T+01:12. 1/1 en `eval.md`. Captura `11_sensor_fault.png` y `12_radar_cierre.png`.
3. **`nominal` a 4×, pérdida de GPS manual, solo para anotar** (`runs/nominal/20261022-110640/`, y la ejecución anterior `…104231`): el dron navega a estima y la estela se separa del radar y de la ruta; el detector abre `GPS_DEGRADED` (T+00:41), luego `SOURCE_DISCREPANCY` y, al recuperarse, `ROUTE_DEVIATION`. El monitor acierta la causa en las tres (`GPS_JAMMING`) pero **abre dos cadenas** (`ai-0002`→`ai-0008` por un lado y `ai-0005` por otro): es el pendiente F2. En la ejecución `…104231` la cadena de `ai-0005` quedó **abierta hasta el final** (el monitor reconoció su cierre con `acknowledge_detection`, el pendiente de «alertas abiertas»); en `…110640` el monitor la cerró. El pendiente **F3** (GPS callado dentro de una cadena de jamming) no se puede provocar con esta prueba: la pérdida manual publica con `fix: none`, no calla. Sin arreglar, como pediste.

## 3. Cómo se ejecuta
Con vLLM en marcha (lo arrancas tú). Tres terminales, en la raíz del repo:
```bash
uv run --project platform python -m platform_app.app --port 8100                          # 1. plataforma (API + /ws)
uv run --project ai-module-py python -m ai_module --platform http://127.0.0.1:8100        # 2. módulo de IA (detector y agentes)
cd web && pnpm install && pnpm demo                                                        # 3. web (build + start) en http://127.0.0.1:3000   [Fase 4.1: antes `pnpm dev`]
```
Una vez: `pnpm exec playwright install chromium` (solo para `scripts/capture.mjs`). Node v24.22.0 y pnpm 12.14.0 (v0 declaraba `pnpm@12.3.4`: se ha quitado el campo `packageManager`).
Comprobaciones: `(cd contracts/python && uv run pytest -q)` · `(cd platform && uv run pytest -q)` · `(cd ai-module-py && uv run pytest -q)` · `ruff check . && ruff format --check .` en `platform/` y `ai-module-py/` · `(cd web && pnpm typecheck && pnpm build)`. Capturas: `node scripts/capture.mjs demo|radar|gps <carpeta>`.

## 4. Guion de demo de 10 minutos
**Preparación (antes de que entre nadie):** los tres procesos arrancados, vLLM calentado, **una sola pestaña** (los ids `ops-` de los mensajes los calcula la web como «máximo visto + 1»: con dos pestañas pueden repetirse y la plataforma rechazaría el mensaje; no es un error, es una limitación), la ventana a pantalla completa (≥ 1600 px de ancho), el modo interactivo apagado (desde la Fase 4.1 cada carga lo apaga; no hace falta comprobarlo) y la web arrancada con `pnpm demo` (sin el indicador de desarrollo de Next.js) y «Mostrar verdad» apagado.
**Escenario `demo`, velocidad 4×, «Esperar al agente» encendido.** Duración estimada: **≈ 4 min de simulación** (3,7 min medidos con los chats) **+ ≈ 6 min de explicación = 10 min**. Pulsa «Pausar» cuando quieras hablar más de lo que dura una espera; en cada anomalía el reproductor se pausa solo.

| Min | Qué haces | Qué dices (y quién decide) |
|---|---|---|
| 0:00–1:30 | Pantalla inicial: mapa, controles, consola. Carga `demo`, 4×, esperar al agente. Enseña las capas (ruta, radar, viento) y que «Mostrar verdad» está apagado. | Un simulador publica eventos en un bus; **el detector de reglas** dice *que* algo va mal, **el monitor (LLM con tools y skills)** *por qué*, y el **agente de informe** lo cuenta al final. El agente nunca ve la verdad. Cada detección tiene respuesta. |
| 1:30–3:30 | **Play.** A los ≈ 30 s de reloj (T+01:46) salta el aviso «Esperando al monitor: analizando det-0001…». Cuando llegue la alerta, desplegar «Razonamiento…». **Chat del monitor:** «¿Por qué crees que es viento?» | **Viento.** Detector: `ROUTE_DEVIATION` (30,5 m). Las tools calculan los hechos (`wind.notable`, `wind.with_drift`, GPS y radar coinciden); **el modelo elige `WIND`** y escribe el texto; el **guardrail** lo habría vetado si los hechos no lo apoyaran. Enseña los `checks` sí/no. Explica el aviso de espera: es la pausa de la demo, no del sistema (a 16× o sin esperar, el agente va con retraso y se mide). Cierre a T+02:36: lo decide el modelo (cuando es la última detección de la alerta). |
| 3:30–6:00 | Siguen T+03:12 (alerta `GPS_SPOOFING`) y T+03:42. **Activa «Mostrar verdad»**: la verdad sigue la ruta mientras la estela del GPS se separa. Enseña la marca **«Sustituye a ai-…»** y la tira A2 («2 alertas»). Desactiva la verdad. | **Spoofing.** Detector: `SOURCE_DISCREPANCY` (GPS y radar 31 m). **Causa: el modelo** (el guardrail solo comprueba que sus `checks` cuadren; elegir `GPS_SPOOFING` es suyo). **Recuperación (T+03:42, `ROUTE_DEVIATION`): la causa la pone el guardrail**: solo acepta la causa de la alerta del GPS reciente, con `supersedes`; el modelo suele proponer otra cosa y el rechazo de una frase le dice qué publicar, y él solo redacta. Una cadena = **una sola alerta** (alta → media). El cierre de `det-0003` lo responde el código (sin LLM). |
| 6:00–7:30 | T+05:38 secuestro; T+05:41 actualización a alta (reconocimiento, sin alerta nueva). **Chat del monitor:** «¿Qué has mirado del enlace?» | **Secuestro.** Modelo: `HIJACK`; el guardrail exige que **haya mirado el enlace** (`link_checked`) y que declare bien `link_anomalous`, pero **no exige que sea anómalo**: decidirlo es del modelo. Al subir de severidad **no se abre otra alerta**: si el modelo no cambia causa ni severidad, el guardrail rechaza el `supersedes` y obliga a reconocer (`DetectionAcknowledged`). |
| 7:30–9:00 | Fin de la simulación; en ≈ 10 s llega el informe: pestaña **Informe**, cronología y anomalías. **Chat del informe:** «¿Cuál fue la anomalía más grave y por qué?» | **Informe.** Los hechos (horas, severidades, estados, cadenas, cifras del monitor) **los escribe el código**; el modelo solo redacta el resumen, «qué se vio», la valoración y las recomendaciones. Es un 14B: la valoración es genérica. No cuentes que «acierta»: no tiene la verdad. |
| 9:00–10:00 | Cierre: ayudas al modelo y qué se quita con uno mejor; opcional, si sobran 2 min: otra carga, `nominal`, modo interactivo, **«Silenciar Radar»** → `SENSOR_FAULT` → reactivar → cierre. | `docs/quien_decide_que.md`: el 14B no ejecuta un árbol de decisión largo; funcionó **calcular hechos en código, obligar a declarar las comprobaciones y vetar lo incoherente**. Lo que no depende del modelo (contrato, respuesta garantizada, trazas, evaluación) se lleva tal cual a Java. |

**Fuera del guion: la pérdida de GPS manual** (F2/F3 pendientes: dos cadenas y alguna alerta que puede quedar abierta). No la enseñes en directo.
**Plan B si algo falla en directo** (vLLM caído, el modelo tarda, la web se queda sin datos): las capturas en `results/capturas/fase4/demo/` (`00_inicio` … `10_verdad`, en el orden del guion) y el `eval.md` y el `informe.md` de la ejecución buena `runs/demo/20261022-110035/` (copiados a `results/`); y si solo falla el LLM, `uv run --project platform python -m platform_app.run --scenario demo --speed 16 --detector-only` (sin LLM). Si la web pierde la conexión, se reconecta sola y recupera el timeline; recargar la página también.

## 5. Pruebas
`contracts/python` 127 passed, 1 skipped · `platform` 204 passed · `ai-module-py` 283 passed (incluye la e2e) · `ruff check` y `ruff format --check` limpios · `pnpm typecheck` y `pnpm build` correctos · huella de `agent-assets` `40e5049dbf83198c` sin cambios.

## 6. Problemas y lo que no funciona
- **Pérdida de GPS manual** (F2 y F3 de `fallos`): ver el punto 3 de las pruebas. Pendiente conocido, sin arreglar.
- ~~`eval.md` de las ejecuciones desde la web con «n/d»~~: resuelto en la 4.1 (la plataforma escribe `run_meta.json`). El evaluador sigue poniendo la etiqueta sintética `F101` al fallo manual.
- ~~Saltos en los ids `ai-`~~: resuelto en la 4.1 (`chk-` y `act-` para los efímeros).
- ~~El modo interactivo se conservaba entre cargas~~: resuelto en la 4.1 (cada `load` y `reset` lo apaga).
- Con dos pestañas abiertas, los ids `ops-` pueden repetirse y la plataforma rechaza el segundo mensaje (el error sale en la franja roja de la web).
- Mapa: los límites solo crecen durante una ejecución (en `secuestro` el mapa se ensancha cuando el dron se va); el selector de escenario no autocarga ninguno.
- `next dev` regenera `web/AGENTS.md` (ignorado en git).
- Nada se atascó más de 30 minutos. `playwright install` sin `--with-deps` funcionó (las librerías del sistema ya estaban).

## 7. URLs consultadas (regla 8)
- Telemetría de Next.js: https://nextjs.org/telemetry — «You may also opt-out by setting an environment variable: `NEXT_TELEMETRY_DISABLED=1`.»; no recoge variables de entorno, rutas ni contenido de ficheros (recoge versión, comando invocado e información general de la máquina; está activada por defecto salvo que se desactive, de ahí la variable en los scripts).
- react-markdown: https://github.com/remarkjs/react-markdown — `<Markdown remarkPlugins={[remarkGfm]}>`; `remark-gfm` añade tablas, tachado, listas de tareas y URLs; «escapes HTML» por defecto («secure by default»), y no se usa `rehype-raw`. Versiones comprobadas con `pnpm view`: react-markdown 10.1.0, remark-gfm 4.0.1.
- Fontsource: https://fontsource.org/docs/getting-started/install — importaciones por peso (`@fontsource/<familia>/400.css`). ⚠️ La página usa Open Sans de ejemplo: que exista `@fontsource/ibm-plex-sans/400.css` lo he comprobado instalando el paquete (5.3.0) y compilando, no en la documentación.
- Playwright: https://playwright.dev/docs/browsers — instalación de navegadores por argumento y caché en `~/.cache/ms-playwright`. ⚠️ La página no muestra literalmente `playwright install chromium` ni dice que `--with-deps` necesite administrador (solo `install-deps`/proxy en Linux); no usé `--with-deps` precisamente por si pedía `sudo`.

## 8. Qué queda
- ~~Decidir si el guardrail verifica la severidad `medium` de la recuperación~~: hecho en la 4.1.
- Lo de la Fase 3: F2/F3 de `fallos`, las alertas abiertas, los chats con tools y el informe genérico (`docs/quien_decide_que.md` §5).
- Fase 5 (extras de `docs/mejoras_futuras.md`) solo si lo pides.

## 9. Copias (reglas 13 y 15)
`docs/fases/`, los PNG de `runs/*/`, los `eval.md` e `informe.md` de las ejecuciones, las capturas de la web (`results/capturas/fase4/{demo,radar,gps}/`), la instantánea del código en `snapshots/fase4/` y la limpia en `snapshots-limpias/fase4/`. Las dos comprobaciones de la regla 15 sobre `snapshots-limpias/fase4/` salen **vacías** (sin coincidencias); no ha habido que corregir ningún fichero (el único hallazgo previsible, `web/AGENTS.md`, se excluyó por `.gitignore` antes de copiar). `runs/<escenario>/` (plan, verdad, eventos y PNG) no cambia: no se ha tocado el generador.

## Fase 4.1 · ajustes para la demo (22/10/2026)
Contrato **v0.10**. Huella de `agent-assets` nueva: **`3b066bf7a0d69baa`** (la anterior era `40e5049dbf83198c`; solo cambia `prompts/monitor_output.md`; `agents.yaml` no se toca).

### 1. Guardrail de recuperación: también `severity medium` (y un fallo mío que apareció al probarlo)
`check_coherence` comprueba ahora las **tres** cosas de la recuperación: causa de la alerta del GPS reciente, `supersedes` (si sigue abierta) y `severity medium`. Pruebas: `test_gps_recovery_must_be_published_with_severity_medium` y `test_gps_recovery_with_a_closed_alert_also_needs_severity_medium`. §7 del contrato lo dice sin la salvedad anterior.

**Fallo mío de la Parte 0, corregido.** El veto «No cambia nada respecto a ai-XXXX» (Fase 4, punto b) se comprobaba **antes** que la regla de la recuperación. Si el modelo probaba la recuperación con `supersedes` y severidad `high` (la de la alerta alta), el veto le decía «usa `acknowledge_detection`» y la recuperación perdía su alerta `supersedes` (alta → media). Lo vi en la línea base del punto 6: con el prompt original, 1 de 3 `demo` reconocía la recuperación en vez de sustituir la alerta (`runs/demo/20261022-114207`); en las ejecuciones de la Fase 4 había salido siempre bien, por suerte del modelo. Ahora el veto genérico se comprueba **al final** (solo si la coherencia no ha puesto otro error), así que en una recuperación manda el mensaje «Es la recuperación del …: publica cause …, severity medium y supersedes …». Prueba de regresión con `severity high` en `test_coherence.py`. Cambio de comportamiento: no cambia ninguna causa, solo qué mensaje de rechazo recibe el modelo.

### 2. Ids de los eventos efímeros
`AgentReplyChunk` lleva `chk-NNNN` y, **ampliando lo pedido**, `AgentActivity` lleva `act-NNNN`, cada uno con su contador. Hacía falta lo segundo: cada invocación publica dos `AgentActivity` (empieza y termina), que también gastaban ids `ai-`, así que las alertas saltaban de numeración aun sin chat (`ai-0002` → `ai-0008` en `demo`). Cambia el `id_prefix` en `EVENT_SPECS` (la fuente de verdad en Pydantic), §1 del contrato (regla 2) y las pruebas que usaban ids `ai-` para efímeros (contratos, plataforma y módulo de IA; tres pruebas del monitor usaban `ai-0001` como id de una alerta preexistente y chocaban con el primer id real). Resultado: en las `demo` del punto 6 las alertas salen `ai-0001`, `ai-0003`/`ai-0004`, `ai-0007`; ya no hay saltos por actividad ni por chat.

### 3. `run_meta.json` lo escribe la plataforma
- Modelo nuevo `RunMeta` (`contracts/python`, esquema `contracts/schemas/files/run_meta.json`, §8.6 del contrato con su ejemplo validado): `speed`, `wait_agent` e `interactive` al primer play o paso y, en `*_changes`, cada cambio durante la ejecución con su `sim_time`.
- `Player` lo escribe en `runs/<escenario>/<run_id>/run_meta.json` al primer play o paso, en cada cambio y al volcar el timeline (una carga sin ejecutar no deja carpeta). `run.py` ya no escribe nada (`write_run_meta` borrado; arranca su propia plataforma, que lo escribe). La duración en reloj ya no se guarda: `eval.md` la saca del timeline (como hacía para las ejecuciones sin meta).
- `evaluate.py` pone en la cabecera valores y cambios: `esperar al agente: sí → no (a T+02:00) · velocidad: 4× → 8× (a T+01:00) · modo interactivo: no → sí (a T+00:30)`; la sección «Sin esperar al agente» sale salvo que se haya esperado durante toda la ejecución. Pruebas en `test_player.py` (valores iniciales, cambios, sin duplicados, y que se reescribe al terminar) y `test_evaluate.py`. Ejemplo real: `runs/demo/20261022-115728/eval.md` → «esperar al agente: sí · velocidad: 4× · modo interactivo: no · duración en reloj: 222 s».

### 4. `load` y `reset` apagan el modo interactivo
`Player.load` pone `interactive = False`; si estaba encendido, el timeline nuevo empieza con `SimulationStarted` y un `InteractiveModeChanged` con `interactive: false` (también si se encendió antes de cargar nada). La velocidad y «esperar al agente» se conservan. Contrato (§4, §5), `platform/CLAUDE.md` y `web/CLAUDE.md` actualizados. Tres pruebas antiguas encendían el modo antes de cargar: ahora lo hacen después. Comprobado desde la web (captura `capture_log.json`): modo encendido antes de cargar → «tras cargar, modo interactivo = false».

### 5. Web: sin indicador de desarrollo y `pnpm demo`
`devIndicators: false` en `next.config.mjs` (https://nextjs.org/docs/app/api-reference/config/next-config-js/devIndicators: «To hide the indicator entirely, set `devIndicators` to `false`»; ⚠️ la página no dice si afecta a `next start`; lo he comprobado en las capturas, donde ya no sale el botón «N»). Script `pnpm demo` = `export NEXT_TELEMETRY_DISABLED=1 && next build && next start -H 127.0.0.1 -p 3000`. La demo y las capturas de la 4.1 se hicieron con él. **Aviso de telemetría:** una vez lancé `pnpm exec next build` a mano sin la variable (para comprobar el build), y `next telemetry status` indica que sin la variable la telemetría anónima de Next.js está activa, así que ese build pudo enviar un evento anónimo (versión, comando, información general de la máquina y duración del build según https://nextjs.org/telemetry). Fue una sola vez; el resto (scripts `dev`, `build`, `start`, `demo`) lleva la variable. Si quieres, `pnpm exec next telemetry disable` lo apaga para tu usuario (escribe en tu configuración de usuario: no lo he hecho).

### 6. Prompt del monitor en castellano llano (reversible)
`agent-assets/prompts/monitor_output.md` pide que la explicación, la recomendación y la razón de cierre se escriban «en castellano llano, … sin nombres de campos ni de herramientas y sin expresiones del tipo campo=valor, y con las cifras siempre con su unidad». **Redacté la instrucción sin citar `disagreed=false` ni `wind.mean_speed_mps`** (aunque lo proponías): la lección de la Fase 3 es que nombrar lo que no quieres lo ceba. Original guardado en el scratchpad para revertir.

`demo` a 16× con «esperar al agente», 3/3 en todas (`eval.md` de cada una):
| Configuración | Ejecuciones | Causas | Cadenas (una por anomalía) | Cierres | Recuperación del spoofing |
|---|---|---|---|---|---|
| Prompt nuevo, guardrail **antes** de arreglar el orden | `…113557`, `…113752`, `…113951` | WIND · GPS_SPOOFING · HIJACK ×3 | 1·1·1 ×3 | T+02:36 · T+03:54/55 · T+07:21/22 ×3 | `supersedes` en 2; **reconocida en 1** |
| Prompt original, guardrail antes de arreglar el orden (línea base) | `…114207`, `…114403`, `…114603` | ×3 igual | ×3 igual | ×3 igual | `supersedes` en 2; reconocida en 1 |
| **Prompt nuevo, guardrail corregido (definitivo)** | `…114934`, `…115132`, `…115325` | ×3 igual | ×3 igual | ×3 igual | **`supersedes` en las 3** |
El prompt nuevo **no cambia** causas, cadenas ni cierres, y la variación de la recuperación estaba en el orden de los vetos, no en el prompt (la misma 1 de 3 salió con el original): por eso se queda, con la huella nueva. Efecto en el texto, contando coincidencias de nombres de campo o `campo=valor` (`wind.notable`, `disagreed=false`, `gps_radar`…) en explicaciones, recomendaciones y razones de cierre: **18 en 31 textos con el original frente a 3 en 33 con el nuevo (solo `controller_id`)**. Antes: «GPS y radar coinciden (gps_radar.disagreed=false) … (wind.notable=true) … (wind.with_drift=true)»; ahora: «ahora GPS y radar coinciden. La distancia entre GPS y radar es estable y menor (6,8 m)…». Lo que sigue pasando: cifras con punto decimal («6.8 m») en vez de coma, y la fiabilidad del 14B en el razonamiento no cambia (un chat dijo que el viento sopla «en dirección opuesta a la deriva» cuando era a favor; los checks y el guardrail sí lo corrigen en las alertas, no en los chats).

### Demo desde la web a 4× con `pnpm demo` (`runs/demo/20261022-115728/`)
3/3, 0 fallbacks, 0 alertas abiertas, 0 esperas agotadas: `ai-0001` WIND (T+01:46), `ai-0004` GPS_SPOOFING alta (T+03:12) → `ai-0005` GPS_SPOOFING media, sustituye (T+03:42), `ai-0008` HIJACK (T+05:38) con un reconocimiento a su actualización; cierres T+02:36, T+03:54 y T+07:21. Duración medida: simulación terminada a los 205 s de reloj, informe a los 218 s, 223 s con las dos preguntas a los chats; 8 esperas visibles que suman 63 s. Capturas en `results/capturas/fase4_1/demo/` (sin el indicador de Next.js, con `act-`/`chk-` sin saltos de ids y con el aviso de espera).

### Pruebas de la 4.1
contracts 128 passed, 1 skipped · platform 206 passed · ai-module-py 286 passed · `ruff check` y `ruff format --check` limpios · `pnpm typecheck` y `next build` correctos · 57 esquemas exportados (nuevo: `files/run_meta.json`; sin cambios en los demás).

### Copias de la 4.1 (reglas 13 y 15)
`docs/fases/`, los PNG de `runs/*/`, los `eval.md` e `informe.md` (incluidas las nueve `demo` del punto 6), las capturas en `results/capturas/fase4_1/demo/`, `snapshots/fase4_1/` y `snapshots-limpias/fase4_1/`; las dos comprobaciones de la regla 15 salen vacías.

### Qué queda de la 4.1
- Las cifras del modelo siguen con punto decimal en las explicaciones; no se ha pedido.
- Decisión tuya: `pnpm exec next telemetry disable` para tu usuario.

### Mensaje de commit propuesto (Fase 4.1; el de la Fase 4 está al final del documento)
```
feat: phase 4.1 - demo adjustments, run_meta written by the platform and contracts v0.10

- ai-module-py: the GPS recovery guardrail also checks severity medium and takes precedence over
  the generic "supersedes changes nothing" veto; evaluation header shows run_meta with its changes
- platform: the player writes run_meta.json (speed, wait-for-agent and interactive mode with their
  changes) and load/reset turn the interactive mode off; run.py no longer writes it
- contracts: v0.10 - chk- and act- ids for the ephemeral events, RunMeta model and schema,
  interactive mode off on load
- web: Next.js dev indicator off and a pnpm demo script (build + start on 127.0.0.1:3000)
- agent-assets: monitor output prompt asks for plain Spanish in explanations, recommendations and
  closing reasons (new freeze hash 3b066bf7a0d69baa)
```

## Fase 4.2 · solo los chats (el monitor no se toca) (22/10/2026)
Contrato sin cambios (v0.10). Huella de `agent-assets` nueva: **`9df401059abcaff2`** (la anterior, `3b066bf7a0d69baa`). Cambian `agents.yaml` y los dos prompts `chat_*_system_notools.md`; `monitor_*`, las skills y las herramientas no.

### El fallo y lo que de verdad lo causaba
En la demo `20261022-115728` el chat del monitor dijo que el viento «sopla en dirección opuesta a la deriva (4,9°)»; 4,9° es una diferencia que significa «a favor» (y el check `wind_with_drift` de la alerta decía `sí`). Con los chats a 0,7 de temperatura era variación del muestreo (en la Fase 4 salió bien).

Mi primer intento fue el que pedías: temperatura 0 y hechos con su interpretación. **No bastó: las tres ejecuciones dieron exactamente la misma respuesta mala** («empuja en dirección contraria a la deriva del dron (4,9° diferencia)»), ahora de forma determinista, aun con «La deriva va a favor del viento: sí» en el prompt (ejecuciones `20261022-125754`, `…125955` y `…130156`). Reconstruí el prompt de un chat con un timeline real en un banco aparte (scratchpad, no entra en el repo) y fui quitando cosas:
| Variante del prompt del chat | Respuesta a «¿por qué viento?» / «¿a favor o en contra?» |
|---|---|
| hechos con sí/no + ángulos de procedencia y deriva (326°, 151°) + explicación en prosa del monitor | «contraria a la deriva» (la repite) |
| + regla «si la explicación contradice los checks, valen los checks» | igual: la ignora |
| + frase de «a favor» más explícita («empuja en el mismo sentido en que se aleja») | «la dirección del viento (326°) coincide con la dirección opuesta a la deriva (151°)»: compara él los ángulos de procedencia y deriva |
| sin ángulos sueltos, con la explicación en prosa | «a favor» en la causa, **pero «en contra de la deriva» si se le pregunta directamente** |
| **sin ángulos sueltos y sin la explicación en prosa** | «a favor (4,9°)» en las cuatro formulaciones probadas, ×3 |
**La causa estaba en la prosa del monitor, no en los hechos:** la explicación de la alerta `ai-0001` (texto del monitor, que no se toca) decía «empuja en dirección contraria a la deriva (4,9°)», contradiciendo sus propios checks (`deriva a favor del viento: sí`), y el chat la repetía por encima de lo que dicen los hechos. Es la misma clase de fallo que el guardrail ya veta en las alertas (declaración que no cuadra con las tools), pero la prosa libre no se puede comprobar.

### Qué se ha hecho
1. **Temperatura 0 en los dos chats** (`agents.yaml`, con nota «responden sobre hechos»): `temperature: 0`, `top_p: 1.0` y `top_k: -1` explícitos, como el monitor (`repetition_penalty` 1,05 se hereda). Pruebas de muestreo actualizadas (`test_assets`, `test_engine`, `test_e2e`); el informe sigue a 0,7 / 0,8.
2. **Hechos con su interpretación** (`ai_module/chat_facts.py`, puro): cada hecho que exige una comparación lleva el sí o el no al lado, con las cifras, **sin nombres de campos**, y calculado con las mismas reglas que el guardrail: `metric_facts` (nuevo, en `guardrails.py`) es lo que ahora usa también `expected_checks`, así que el chat y los `checks` de la alerta no pueden discrepar. Ejemplo real:
   `- El viento es notable: sí (media 3,9 m/s, racha 9,7 m/s).` · `- La deriva va a favor del viento: sí (el viento empuja en el mismo sentido en que el dron se aleja de la ruta; diferencia de 4,9° entre las dos direcciones).` · `- GPS y radar discrepan: no (distancia media de 6,6 m, máxima de 9,0 m).` · `- Salto brusco del GPS (típico de la recuperación tras un engaño o una pérdida): no (…14,8 m).` · `- El enlace de mando es anómalo: sí (el controlador pasa de GCS-1 a UNK-4F2A desde T+05:35; señal entre -78 y -61 dBm; latencia entre 37 y 123 ms; lo miró el monitor a T+05:42).`
   Cuando falta una fuente se dice («no se puede saber»), no se inventa.
3. **Dos decisiones mías fuera de lo pedido, por lo que se ve arriba** (revísalas):
   - **Sin ángulos sueltos:** se quitan «sopla desde 326°» y «la deriva se dirige hacia 151°» (puestos uno junto a otro, el 14B los compara él y se confunde). Las cifras que sí se mantienen: velocidades del viento, distancias GPS–radar, desviaciones, saltos, latencias, señal.
   - **El chat recibe las alertas sin la explicación en prosa del monitor** (`describe_alerts_detail(explanation=False)`), con resumen, recomendación, comprobaciones (sí/no) y evidencias. Para no perder lo que sí aportaba (el enlace: «¿qué has mirado del enlace?»), el módulo guarda ahora los eventos de enlace que mira el monitor (`rt.last_link`) y los convierte en el hecho de arriba. El resumen de una alerta sigue siendo texto del monitor (ver «Lo que queda»).
   Los prompts `chat_*_system_notools.md` explican que cada hecho ya trae su sí o no («úsala tal cual y no vuelvas a comparar números ni ángulos»).
4. **Pruebas sin LLM** (`tests/test_chat_facts.py`, 8, y una más en `test_round9.py`): la inyección contiene las frases (viento notable, a favor, GPS y radar, salto, enlace anómalo) con sus cifras y sin nombres de campos ni ángulos; el sí/no cambia con los hechos; faltan datos → «no se puede saber»; el chat y los `checks` salen de las mismas reglas (`metric_facts` frente a `expected_checks`, en las tres combinaciones); el sistema de **los dos chats** lleva las frases; el enlace lleva su veredicto; las alertas del chat no llevan la prosa; el monitor recuerda el enlace que miró. Total `ai-module-py`: 295 passed.

### Resultado con el LLM: `demo` a 16×, «esperar al agente», tres veces, con las preguntas del guion (§4) en sus instantes
Preguntas: al monitor, tras la alerta de viento (sim T+01:50) «¿Por qué crees que es viento?»; al monitor, tras el secuestro (T+05:42) «¿Qué has mirado del enlace?»; al informe, al terminar «¿Cuál fue la anomalía más grave y por qué?» (las del guion; el guion no tiene más preguntas a los chats).

**Alertas del monitor: iguales que en la 4.1** (`eval.md` de `20261022-130833`, `20261022-131031`, `20261022-131231`): 3/3 en las tres, 0 fallbacks, 0 alertas abiertas, 0 esperas agotadas, 0 detecciones sin respuesta; WIND `ai-0001` (T+01:46) · GPS_SPOOFING `ai-0004` alta (T+03:13) → `ai-0005` media con `supersedes` (T+03:42/43) · HIJACK `ai-0008` (T+05:38) con un reconocimiento a su actualización; cierres T+02:36, T+03:54/55 y T+07:21. Los ids salen `ai-0001`…`ai-0008` sin saltos (4.1). El texto de los resúmenes de las alertas varía de una ejecución a otra, como en la 4.1.

**Chat del monitor · «¿Por qué crees que es viento?» · T+01:50 (justo tras la alerta de viento)**
- Ejecución 1 (`20261022-130833`):
  > La alerta ai-0001 "WIND" fue generada porque el dron se está desviando de su ruta planificada en dirección al viento. Existe una notable velocidad del viento (media 3,9 m/s, racha 9,7 m/s) que empuja al dron, lo que se refleja en una deriva favorable al viento (diferencia de 4,9° entre las direcciones). La desviación respecto a la ruta planificada es consistente con la dirección del viento, con una media de 10,1 m para el GPS y 10,9 m para el radar. Recomendación: vigilar que el dron recupere la ruta planificada.
- Ejecución 2 (`20261022-131031`):
  > La alerta ai-0001 "WIND" fue generada porque el dron se está desviando de su ruta planificada en dirección al viento. Existe una notable velocidad del viento (media 3,9 m/s, racha 9,7 m/s) que empuja al dron, lo que se refleja en una deriva favorable al viento (diferencia de 4,9° entre las direcciones). La desviación respecto a la ruta planificada es consistente con la dirección del viento, con una media de 10,1 m para el GPS y 10,9 m para el radar. Recomendación: vigilar que el dron recupere la ruta planificada.
- Ejecución 3 (`20261022-131231`):
  > La alerta ai-0001 "Desviación por viento" se activó debido a una notable velocidad del viento, con una media de 3,9 m/s y ráfagas de hasta 9,7 m/s. Además, la dirección del viento coincide con la deriva del dron, ya que el dron se está desviando en la misma dirección en que sopla el viento, con una diferencia de 4,9° entre ambas direcciones. Esto sugiere que el viento está influyendo en la trayectoria del dron, causando la desviación observada.

**Chat del monitor · «¿Qué has mirado del enlace?» · T+05:42 (tras el secuestro)**
- Ejecución 1 (`20261022-130833`):
  > He revisado varias características del enlace de mando:
  > - El controlador pasó de GCS-1 a UNK-4F2A desde T+05:35.
  > - La señal varía entre -78 y -61 dBm.
  > - La latencia está entre 37 y 123 ms.
  > 
  > Estos cambios indican que el enlace de mando es anómalo, sugiriendo un posible secuestro del dron. Recomendación: verificar el enlace de mando y tomar medidas para recuperar el control del dron.
- Ejecución 2 (`20261022-131031`):
  > He revisado varias características del enlace de mando:
  > - El controlador pasó de GCS-1 a UNK-4F2A desde T+05:35.
  > - La señal varía entre -78 y -61 dBm.
  > - La latencia oscila entre 37 y 123 ms.
  > 
  > Estos cambios indican que el enlace de mando es anómalo, sugiriendo un posible secuestro del dron. Recomendación: Verificar el enlace de mando y tomar medidas para recuperar el control del dron.
- Ejecución 3 (`20261022-131231`):
  > He revisado varias características del enlace de mando:
  > - El controlador pasó de GCS-1 a UNK-4F2A desde T+05:35.
  > - La señal varía entre -78 y -61 dBm.
  > - La latencia oscila entre 37 y 123 ms.
  > Estos cambios indican que el enlace de mando es anómalo, lo que apoya la alerta de secuestro (ai-0008).

**Chat del informe · «¿Cuál fue la anomalía más grave y por qué?» · al terminar (T+09:16)**
- Ejecución 1 (`20261022-130833`):
  > La anomalía más grave fue la posible hijacking del dron (alerta ai-0008). Esta anomalía fue clasificada como una alta severidad y tuvo una confianza del 85%. La razón principal es que implicaba una potencial pérdida de control del dron debido a un enlace de mando anómalo, lo que podría poner en riesgo tanto la integridad del dron como la seguridad general de la misión. La alerta permaneció abierta durante casi dos minutos, lo que indica una situación crítica que requiere una rápida acción para asegurar el control del dron.
- Ejecución 2 (`20261022-131031`):
  > La anomalía más grave fue la alerta de secuestro del dron (ai-0008). Esta anomalía fue considerada la más crítica porque implicaba que alguien pudo haber tomado el control del dron, lo que representa un riesgo significativo para la seguridad del dron y cualquier información sensible que pudiera estar transmitiendo. La alerta fue abierta a T+05:38 y cerrada a T+07:21, y se basó en un cambio inesperado en el controller_id del enlace de mando y una alta latencia en la comunicación del dron.
- Ejecución 3 (`20261022-131231`):
  > La anomalía más grave fue el secuestro del dron (alerta ai-0008). Esta anomalía fue considerada la más crítica porque implicaba un riesgo potencialmente peligroso para la seguridad del dron. El secuestro del dron fue detectado por cambios anómalos en el enlace de mando, específicamente un cambio inesperado en el controller_id y una alta latencia, lo que indicaba que alguien podría haber tomado el control del dron.

### Contraste con `eval.md`, los checks y los eventos (cada dato de las respuestas)
- **Viento:** media 3,9 m/s, racha 9,7 m/s, diferencia de 4,9° y «a favor» coinciden con el `get_track_metrics` del monitor (trazas) y con los checks de `ai-0001` (`viento notable: sí`, `deriva a favor del viento: sí`). ✅ ×3. Las ejecuciones 1 y 2 añaden «una media de 10,1 m para el GPS y 10,9 m para el radar»: es la desviación **media** de esa ventana (el máximo es 30,5 m, la cifra del detector y de la alerta); cierto pero fácil de confundir con la de 30,5 m, no es una contradicción.
- **Enlace:** `GCS-1` → `UNK-4F2A` desde T+05:35 (`lnk-0067` a 335 s) ✅; señal «entre -78 y -61 dBm» (reales −60,7 a −78,5: el redondeo del chat) ✅; latencia «37–123 ms» (37,3 a 123,1) ✅; alerta HIJACK `ai-0008` ✅ ×3.
- **Informe:** anomalía más grave = el secuestro (A3, alta, confianza 0,85, T+05:38) ✅ ×3. Detalles: ejecución 1, «alerta abierta durante casi dos minutos» (abierta de T+05:38 a T+07:21 = 1 min 43 s: **impreciso**, no contradice a `eval.md`); ejecución 2, «abierta a T+05:38 y cerrada a T+07:21» ✅; ejecución 3 sin horas. Ninguna contradice los checks ni `eval.md`. Rasgos de lenguaje del 14B («hijacking», «controller_id») sin importancia.
- **Ninguna respuesta contradice `eval.md` ni los checks.** El fallo de la 4.1 no se reproduce en ninguna (0 de 3; antes de quitar la prosa, 3 de 3).

### Lo que queda
- **El resumen de la alerta sigue siendo texto del monitor y puede equivocarse** (la ejecución `20261022-125754` dio `ai-0004`: «GPS y radar discrepan 14,9 m; viento de 1,9 m/s contra la deriva», con el check `deriva a favor del viento: sí`). Sale en la consola de la web y el chat lo ve. El monitor no se ha tocado; si se pregunta por esa alerta, el chat puede repetirlo. Arreglarlo es del monitor (o un check de coherencia sobre la prosa, que no existe).
- **`CLAUDE.md` (raíz), regla 6:** dice «informe y chats a 0,7 / 0,8». Ya no es cierto para los chats (0, 1,0 y `top_k` −1). No lo he editado (es tu fichero de instrucciones): cámbialo tú o dime que lo haga.
- Los chats con tools (`chat.tools_enabled: true`) no reciben nada de esto: la demo los usa sin tools.
- Hecho aparte: el banco de pruebas del prompt (scratchpad) no está en el repo.

### Pruebas de la 4.2 y copias
contracts 128 passed, 1 skipped · platform 206 passed · ai-module-py 295 passed · `ruff check` y `ruff format --check` limpios · huella `9df401059abcaff2` (y `runs/<escenario>/` sin cambios: no se ha tocado el generador). Copias de las reglas 13 y 15 (`snapshots/fase4_2/`, `snapshots-limpias/fase4_2/`, `eval.md` e `informe.md` de las ejecuciones; las dos comprobaciones de la 15 salen vacías); la web no ha cambiado y no hay capturas nuevas.

### Mensaje de commit propuesto (Fase 4.2)
```
feat: phase 4.2 - chats answer on interpreted facts at temperature 0

- agent-assets: both chats at temperature 0 (top_p 1.0, top_k -1); no-tools chat prompts say that
  each fact already carries its yes/no (new freeze hash 9df401059abcaff2)
- ai-module-py: chat_facts - facts injected into the chats with their interpretation and figures,
  computed with the monitor guardrail rules (metric_facts shared with expected_checks), the link
  the monitor looked at included, no field names or loose bearings; chats receive the alerts
  without the monitor's free-text explanation, which could contradict its own checks
- tests: injection contains the phrases (both chats), same rules as the checks, link fact, alerts
  without prose, sampling of the chats
```

## Fase 4.3 · revertir el castellano llano, limpiar la presentación y medir las frases falsas (22/10/2026)
Contrato sin cambios (v0.10). Huella de `agent-assets` nueva: **`cd2925fe198331cc`** (`find agent-assets -type f | sort | xargs sha256sum | sha256sum`; la de la 4.2 era `9df401059abcaff2`, la de la 4.1 `3b066bf7a0d69baa`). Cambia solo `prompts/monitor_output.md`, que vuelve a ser el de las fases 3, 3.1 y 4; los cambios de los chats de la 4.2 (`agents.yaml`, prompts `chat_*_system_notools.md`, `chat_facts.py`) se quedan.

### 1. Revertida la frase del punto 6 de la 4.1
Borrada de `agent-assets/prompts/monitor_output.md` exactamente la frase «Escribe la explicación, la recomendación y la razón de cierre en castellano llano… (por ejemplo «viento de 3,9 m/s» o «31 m de diferencia entre el GPS y el radar»).» con el espacio que la separaba de la anterior (comprobado que aparecía una sola vez). `sha256sum agent-assets/prompts/monitor_output.md` = **`149a6f28b612093a8af816e572958168dd763005bfd71942551e9cbcfd0dc8c4`**, el de las fases 3, 3.1 y 4. (Antes de borrar daba `d3c1bbf7…`, el de la 4.1; la comprobación se hace después del borrado, como pedías.)

### 2. Web: paréntesis `campo=valor` fuera de lo que se pinta
`web/lib/clean-text.ts` (`stripFieldValues`) quita los paréntesis cuyo **único contenido** son expresiones `campo=valor` o `campo: valor`, y se aplica a la explicación y la recomendación de la alerta, la razón de cierre y la razón de los reconocimientos (en `monitor-feed.tsx`; la razón de cierre también en el resumen de una línea del timeline). El evento, `eval.md` y el informe conservan el original; el resumen de la alerta no se toca (no estaba en la lista).
Reglas, para que se puedan discutir:
- Con `=` vale cualquier identificador (`disagreed=false`, `wind.notable=true`); con `:` solo identificadores con guion bajo o punto (`wind.mean_speed_mps: 1,9 m/s`), para no comerse «(nota: algo)». Así he cubierto `(disagreed=false)`, que no lleva ni guion bajo ni punto aunque era tu primer ejemplo de la 4.1.
- Varias expresiones en un paréntesis (`(a=1, b.c: 2 m)`) se quitan juntas.
- El valor tiene que ser **simple** (hasta tres palabras: `true`, `4,9°`, `1,9 m/s`); si hay más, es prosa y se deja.
- Se deja intacto todo paréntesis con prosa, horas (`(T+01:46)`) o contenido mezclado, **también `(sin cambios en controller_id, rssi_dbm o latency_ms)`** (nombres de campo, pero no `campo=valor`).
- Se quita el espacio de antes (o el de después si está al principio) y no se tocan los demás espacios.
Con los textos reales de `20261022-143322`: «discrepan poco (disagreed=false), pero la desviación de la ruta es notable (max=30.5 m). El viento es notable (notable=true) y empuja en la dirección de la deriva (with_drift=true)» → «discrepan poco, pero la desviación de la ruta es notable. El viento es notable y empuja en la dirección de la deriva»; «coinciden (gps_radar.disagreed=false)» → «coinciden».
**Prueba:** `web/lib/clean-text.test.ts`, 6 pruebas con el ejecutor de Node (`pnpm test` = `node --test "lib/**/*.test.ts"`; la web no tenía ejecutor y no he añadido dependencias; Node 24 ejecuta TypeScript, y he activado `allowImportingTsExtensions` en `tsconfig.json` para importar `./clean-text.ts`). Cubren: `=` con y sin punto, `:` con cifras y unidades (coma y punto decimal), varias expresiones, varios paréntesis, lo que no se debe tocar y los bordes (vacío, paréntesis al principio).
**Límite:** es un parche. No arregla frases falsas («discrepan 13,8 m» sigue ahí), solo quita ruido.

### 3. `docs/mejoras_futuras.md` · «Texto fiable del monitor»
Sección nueva con lo provisional (limpieza y métrica) y las tres líneas a investigar: (a) explicación estructurada con plantillas, (b) verificar el texto contra los checks (reglas o juez), (c) un modelo mejor sin el ancla de los nombres de campo.

### 4. Métrica «frases que contradicen los checks» (`evaluate.py`)
Sobre el **resumen, la explicación y la recomendación** de cada `AnomalyDetected`, frase a frase, contra los `checks` **de esa misma alerta** (los reconocimientos y los cierres no llevan checks propios y no se evalúan). Reglas (`contradicting_rules`):
1. `wind_with_drift = sí` y la frase tiene «contrari…» u «opuest…» a menos de 60 caracteres de «deriva» o «viento».
2. `wind_with_drift = sí` y la frase dice «contra la deriva», «contra el viento» o «contra él» (visto en las trazas: «viento de 1,9 m/s contra la deriva», «la deriva del dron va contra el viento»).
3. `gps_radar_disagreed = no` y la frase dice «discrepan <cifra>» (o «la discrepancia … es de <cifra>») **sin «poco»** ni «no discrepan».
Dos excepciones que he puesto yo (**revísalas**): un «no» a menos de 35 caracteres delante sin coma de por medio niega la frase («no empuja en dirección contraria a la deriva» es correcto con la deriva a favor; aparece en las trazas); y «contraria a la ruta/al plan» **no cuenta**, porque habla de la ruta y los checks no dicen nada de ella. Esto último lo decidí tras ver que sin la excepción la alerta del secuestro de **todas** las `demo` («el viento empuja el dron en dirección contraria a la ruta planificada») daba 1 y la métrica no medía el fallo del viento. Si prefieres la regla literal, es quitar `TO_ROUTE`.
`eval.md` lleva la sección «Frases que contradicen los checks» (alerta, hora, campo, regla y frase) y el contador en la línea de resumen; `eval.json`, la lista. El evento no se toca. **Pruebas** (`test_evaluate.py`, +6): frases que contradicen (deriva a favor, «contra», «opuesto», discrepancia con cifra), frases que no (a favor, negadas, «contraria a la ruta», «discrepan poco», «no discrepan», «discrepan ligeramente de la ruta»), que cada regla solo se aplica si el check lo dice (con `no`, `None` o sin checks no salta), y la sección de `eval.md` y `eval.json`, con y sin frases.
**La métrica sobre las ejecuciones que ya existían** (`demo`, solo cuenta frases de alertas):
| Ejecuciones | Prompt | Frases (por ejecución) |
|---|---|---|
| 4.1 línea base `…114207`, `…114403`, `…114603` | original | 0 · 0 · 0 |
| 4.1 `…113557`, `…113752`, `…113951` | castellano llano | 0 · 0 · 2 |
| 4.1 `…114934`, `…115132`, `…115325` | castellano llano | 0 · 2 · 2 |
| 4.1 web 4× `…115728` | castellano llano | 2 |
| 4.2 `…130833`, `…131031`, `…131231` | castellano llano | 4 · 2 · 2 |
Con el prompt de castellano llano, 7 de 10 ejecuciones tienen frases que contradicen los checks (16 frases en total: «discrepan 13,8 m» y «contraria a la deriva» en la alerta de viento; «viento de 1,9 m/s contra la deriva» en la del spoofing); con el original, 0 de 3 (la línea base de la 4.1) y 0 de 4 en esta fase (punto 5 y demo web). Lo cual confirma lo que dijiste de los nombres de campo, aunque son muestras pequeñas (una por escenario y tres por configuración).

### 5. `demo` a 16× con «esperar al agente», tres veces (`20261022-143322`, `…143517`, `…143717`)
**Iguales a la 4.1 en todo y la métrica en 0 en las tres** (`eval.md`): ✅ 3/3 anomalías, 0 falsas alarmas, 0 fallbacks, 0 esperas agotadas, 0 detecciones sin respuesta, 0 alertas abiertas, **0 frases que contradicen los checks**.
| | Causas | Cadenas (una por anomalía) | Cierres | Recuperación | Secuestro |
|---|---|---|---|---|---|
| ×3 | `ai-0001` WIND (T+01:46) · `ai-0003` GPS_SPOOFING alta (T+03:12) → `ai-0004` GPS_SPOOFING media con `supersedes` (T+03:42) · `ai-0007` HIJACK (T+05:38) | 1·1·1 | T+02:36 · T+03:54 · T+07:21 | **`supersedes` sustituye la alerta alta (3/3)** | **un reconocimiento** a su actualización (T+05:41, `det-0007` → `ai-0007`) |
Como en la 4.1 con el prompt original, los textos llevan los nombres de campo («discrepan poco (disagreed=false) … (notable=true) … (with_drift=true)»); la web los quita al pintar. Los ids salen sin saltos (`ai-0001`, `0003`/`0004`, `0007`). Cada texto lo ha comprobado la métrica: ninguna frase contradice su alerta.

### 6. `CLAUDE.md` y `quien_decide_que.md`
- Regla 6 de `CLAUDE.md`: «monitor y chats a 0; informe a 0,7 / 0,8» (me lo pediste; es el único cambio en ese fichero).
- `docs/quien_decide_que.md`: estado y huella nuevos; el monitor «escribe todo el texto y **puede contradecir sus checks**»; fila de la evaluación con la métrica; la ayuda de los prompts ya no incluye el castellano llano; sección nueva «El texto de las alertas no está verificado» (la métrica vigila, la web solo limpia la presentación, los chats no lo repiten, soluciones en mejoras futuras). Contrastado con el código: coincide.
- `ai-module-py/CLAUDE.md` y `web/CLAUDE.md` anotan la métrica y `clean-text.ts`.

### Demo desde la web a 4× con `pnpm demo` (`runs/demo/20261022-144059/`)
`pnpm demo` (build + start en 127.0.0.1:3000), plataforma y módulo de IA arrancados a mano; `node scripts/capture.mjs demo …`. ✅ 3/3, 0 fallbacks, 0 alertas abiertas, 0 esperas agotadas, **0 frases que contradicen los checks**; `ai-0001` WIND (T+01:46), `ai-0004` GPS_SPOOFING alta (T+03:12) → `ai-0005` media con `supersedes` (T+03:42), `ai-0008` HIJACK (T+05:38); cierres T+02:36, T+03:54, T+07:21. Simulación terminada a los 205 s de reloj, informe a los 218 s; 8 esperas visibles, 63 s. **Captura de la alerta de viento desplegada: `results/capturas/fase4_3/demo/03_alerta_desplegada_checks.png`** (explicación sin los paréntesis `campo=valor`: «El GPS y el radar discrepan poco, pero la desviación de la ruta es notable. El viento es notable y empuja en la dirección de la deriva.»; sale entera `(sin cambios en controller_id, rssi_dbm o latency_ms)`; los checks coinciden con el texto). Resto de capturas de la demo en esa carpeta. Los procesos que arranqué (plataforma, módulo de IA, web) están parados; vLLM no se ha tocado.

### Pruebas de la 4.3
contracts 128 passed, 1 skipped · platform 206 passed · ai-module-py **301 passed** (+6) · web `pnpm test` 6 passed · `ruff check` y `ruff format --check` limpios en los tres · `pnpm typecheck` y `pnpm build` correctos · esquemas JSON sin cambios · `runs/<escenario>/` sin cambios (el generador no se ha tocado).

### Copias de la 4.3 (reglas 13 y 15)
`docs/fases/`, los PNG de `runs/*/`, los `eval.md` e `informe.md` (incluidas las cuatro `demo` de la 4.3), las capturas en `results/capturas/fase4_3/demo/`, `snapshots/fase4_3/` y `snapshots-limpias/fase4_3/`; las dos comprobaciones de la regla 15 salen vacías (detalle abajo si no).

### Lo que queda
- **El texto de las alertas sigue sin verificarse**: la métrica solo mide y, con reglas tan simples, tendrá falsos negativos. Líneas en `docs/mejoras_futuras.md`, «Texto fiable del monitor».
- La limpieza de la web deja paréntesis con nombres de campo sin `=` ni `:` (por ejemplo `(sin cambios en controller_id, rssi_dbm o latency_ms)`), por tu regla; y el resumen de la alerta no se limpia. Dime si quieres ampliarlo.
- Las cifras del modelo siguen con punto decimal en algunas explicaciones («30.5 m»).
- Decisión tuya, pendiente desde la 4.1: `pnpm exec next telemetry disable`.

### Mensaje de commit propuesto (Fase 4.3)
```
feat: phase 4.3 - monitor prompt reverted, presentation cleanup and contradiction metric

- agent-assets: monitor output prompt back to the original wording (new freeze hash
  cd2925fe198331cc); the plain-Spanish instruction made the monitor contradict its own checks
- web: strip parentheses that only contain field=value or field: value from the monitor texts
  (explanation, recommendation, closing reason, acknowledgements); the event, the evaluation
  and the report keep the original text; node test runner with tests
- ai-module-py: evaluation counts and lists the alert sentences that contradict the alert's own
  checks (three explicit rules)
- docs: temperature rule for the chats, who-decides-what and a future-improvements section on
  reliable monitor text
```

## 10. Mensaje de commit propuesto
```
feat: phase 4 - web connected to the platform; wait-for-agent also waits for closures; contracts v0.9

- web: v0 interface adapted (map with y north, layers panel, fault panel, controls with the
  waiting-for-the-monitor notice, telemetry, timeline, monitor and report tabs with streaming
  chats, alert checks as yes/no and supersedes marks); WebSocket and HTTP client; self-hosted
  fonts and no telemetry; Playwright capture script
- platform: with "wait for the agent" the player also pauses on DetectionCleared and resumes with
  the monitor's reply
- ai-module-py: publish_alert rejects a supersedes that changes neither cause nor severity;
  deterministic acknowledgement of an already closed alert carries a null alert_id; the report
  only explains the closing gap when it exceeds 5 s
- contracts: v0.9 (text and behaviour only; models and schemas unchanged)
- docs: who-decides-what updated; phase report with the demo script
```
