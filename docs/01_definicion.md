# PoC `poc-ai-monitor`: definición

> Creado el 16/10/2026 a partir de la conversación entre Carlos Oliva y Claude (proyecto CITADEL). Es la referencia de diseño de la PoC: el `CLAUDE.md` de la raíz resume las reglas y este documento explica el porqué. Si algo de aquí contradice a `contracts/eventos.md`, mandan los contratos; avisa a Carlos.

## 1. Para qué es

Enseñar al equipo de MDO (David, Francesco, Jesús…) cómo la **IA puede funcionar como extensión de un worker**: un módulo que se suscribe a eventos del bus, detecta que algo no cuadra, **publica un evento de alerta** con la causa probable y su explicación, y al terminar el ejercicio genera un informe. El ejemplo es un dron, porque el MVP de MDO es un escenario de drones.

Lo que se quiere demostrar, en este orden:
1. El módulo de IA **consume eventos canónicos** del bus y **publica eventos**; no actúa sobre nada más (coherente con que MDO no orquesta).
2. Un agente con **tools, skills y tres prompts** (orquestación, objetivo y salida), lo que pidió David.
3. La IA **diagnostica causas cruzando fuentes** (GPS, radar, meteorología, enlace de mando), no solo dice «algo va mal».
4. El diseño se puede **portar a Java** sin reescribir las tools, los prompts ni las skills.

**No es** predecir la trayectoria del dron, ni controlarlo, ni un producto. Plazo: una o dos jornadas de trabajo con Claude Code; se enseña la semana del 19/10/2026.

## 2. Decisiones tomadas (16/10/2026)

| Tema | Decisión |
|---|---|
| Lenguajes | Plataforma y módulo de IA en **Python** (3.12, `uv`, `ruff`); web en **JS** (se parte de la interfaz de v0, Next.js). El módulo de IA se portará a Java más adelante |
| Bus | **Sin NATS.** Bus en memoria dentro de la plataforma, con topics y comodines al estilo NATS, expuesto por **WebSocket** a la web y al módulo de IA (proceso aparte) |
| Simulación | **Solo hacia adelante**: play, pausa, paso (siguiente evento), reinicio y velocidad. Sin retroceso ni salto a un instante |
| Fallos manuales | Desde la web se puede **silenciar y reactivar en directo** una fuente (GPS, radar, meteo, enlace, batería) para ver si el agente reacciona. También se pueden programar en el YAML del escenario |
| Dron | **Uno** (`d1`), plano **x,y en metros** (x hacia el este, **y hacia el norte**), sin mapa |
| Generador | Propio y sencillo: plan por waypoints + **controlador** que lo sigue + perturbaciones. Todo se genera de antemano con semilla |
| Anomalías implementadas | **Viento, secuestro y spoofing de GPS.** El diseño admite más (jamming, replay…), que quedan como mejora |
| Segunda fuente | **Radar de tierra** que ve la posición real; más estación meteorológica, enlace de mando y batería (ruido) |
| Detector | **Reglas con histéresis** (sin entrenamiento). El Isolation Forest del spike 2 queda como mejora detrás del mismo puerto |
| LLM | vLLM local de Carlos, `Qwen/Qwen2.5-14B-Instruct-AWQ`, Chat Completions. **Nada sale a la nube** |
| Librería | **`openai` (SDK oficial) con el bucle del agente escrito a mano.** Motivo: existe el SDK oficial equivalente en Java (`openai-java`) y ya se probaron los dos contra este vLLM en el spike 1. LangChain Python y LangChain4j son proyectos distintos con API distinta |
| Agentes | **Dos**, con el mismo motor: **monitor** (tiempo real) e **informe** (al final). Se puede **chatear con los dos** |
| Sesión del monitor | **Opción B:** una llamada nueva por cada detección, con un resumen del estado inyectado; lo anterior lo consulta con tools. La opción A (una conversación durante toda la simulación) queda como mejora para comparar |
| Tools | Siete para el monitor (más una del informe). Las tools de datos viven en la **plataforma** y se llaman por HTTP; así el módulo Java las usará sin reescribirlas. MCP, en una segunda fase |
| Skills | Ficheros Markdown cargados **a demanda** por el agente (`load_skill`). Organizadas por síntoma, más una de formato del informe |
| Telemetría externa | Ninguna (nada de LangSmith ni similares). Trazas propias en JSONL |
| Repo | `poc-ai-monitor` en GitLab `citadel/labs`. Un solo repo para todos los componentes. **El agente no hace commits**: los hace Carlos |
| Idioma | Código (identificadores, nombres de ficheros de código, logs) en **inglés**; comentarios y docstrings en **español**. Nombres de tools, skills, prompts, eventos y campos en inglés; el **contenido** de prompts y skills, los textos para personas (web, alertas, informe) y la documentación, en español |
| Temperatura | **0 para el monitor** (decisiones reproducibles y evaluación comparable entre ejecuciones). Informe y chats con los valores que recomienda el modelo en su `generation_config.json` (0,7 / `top_p` 0,8 / `top_k` 20), para un texto más natural. Configurable por agente en `agents.yaml` |

## 3. Arquitectura

```
                 PLATAFORMA  (hace el papel de MDO; Python, un proceso, FastAPI, puerto 8100)
 scenarios/*.yaml ─► generador ─► runs/<escenario>/  (plan, verdad, eventos, etiquetas)
                                       │
                     reproductor (reloj simulado: play/pausa/paso/velocidad/esperar al agente)
                                       │ publica en orden de sim_time
                     bus en memoria (topics + comodines) ──► timeline (todo lo publicado)
                                       │                      ▲
                     REST: /api/tools/{nombre} (tools de datos, con corte en el instante actual)
                                       │ WebSocket /ws
               ┌───────────────────────┴───────────────────────┐
         WEB (JS, puerto 3000)                       MÓDULO DE IA (Python, proceso aparte; luego Java)
  mapa x,y, timeline, controles,             detector de reglas ─► DetectionRaised/Cleared (al bus)
  consola del monitor y del informe,         agente monitor ─► AnomalyDetected / AlertClosed (al bus)
  chats con los dos agentes                  agente de informe ─► ReportGenerated (al bus)
                                             chats ─► AgentReply (al bus)
                                                   │ Chat Completions
                                             vLLM 127.0.0.1:8000 (WSL, lo gestiona Carlos)
```

Reparto: la plataforma es el «mundo» (simulación, bus, historial y servicios de datos); el módulo de IA es la **extensión del worker** (detecta, razona, publica). Se comunican **solo** por el bus (WebSocket) y por la API de tools (HTTP). La web solo habla con la plataforma.

## 4. Generador y controlador

### 4.1 Capas
1. **Plan:** waypoints (base → WP1 … WPn → base), velocidad de crucero, altitud, radio de aceptación del waypoint.
2. **Trayectoria planificada:** el controlador vuela el plan **sin perturbaciones**. Da, en cada instante, posición, velocidad y rumbo previstos (`plan.json`). Es lo que se pinta primero para comprobar que el plan tiene sentido.
3. **Trayectoria real:** el mismo controlador con perturbaciones (viento, secuestro, spoofing). Es la verdad (`truth.json`); **el agente nunca la ve**.
4. **Lo que se reporta:** GPS del dron, radar, meteorología, enlace, batería y misión, con su ruido y sus periodos (`events.jsonl`).
5. **Etiquetas:** qué anomalía hubo, cuándo y qué causa debería concluir el agente (`labels.json`). Solo para evaluar.

### 4.2 Modelo del dron (sencillo, en 2D)
- Estado: posición (x, y), rumbo, velocidad respecto al aire. Integración con paso de 0,1 s.
- Límites: velocidad de crucero ~15 m/s (para poder reutilizar el Isolation Forest del spike 2 en el futuro, que se entrenó con 12–18 m/s a 1 Hz), aceleración máxima, velocidad de giro máxima (deg/s).
- **Controlador (guiado con punto de mira sobre el tramo):** proyecta la **posición que cree tener** (la del GPS) sobre el tramo pendiente y apunta a un punto `lookahead_m` por delante, con el giro limitado; cambia al siguiente waypoint cuando el GPS dice que está dentro del radio de aceptación. No compensa el viento de forma integral: con viento lateral queda un error estacionario de `lookahead · tan(asin(w/v))`, que es justo lo que hace visible el viento (≈ 8 m con 2 m/s; ≈ 50 m con 12 m/s). Perseguir directamente el waypoint **no vale**: con 3 m/s de viento ya da desviaciones de 100 m (comprobado).
- **Viento:** vector que se suma a la velocidad (deriva). El controlador corrige solo, porque sigue el tramo.
- **Secuestro:** desde `t_inicio`, el objetivo del controlador pasa a ser un punto que no está en el plan. Si el escenario lo indica, en `t_fin` se recupera el control y el dron **vuelve a seguir el tramo pendiente** (se reincorpora a la ruta). Pista: el `LinkStatus` cambia (otro `controller_id`, RSSI distinto).
- **Referencia comprobada:** `ref/simcheck_controlador.py` implementa esta física sin sensores ni eventos. Con los YAML del paquete da: nominal ≤ 13 m; viento ≈ 52 m; spoofing con la verdad a ≈ 75 m y el GPS < 10 m hasta el fin del engaño; secuestro ≈ 700 m y reincorporación. El generador debe reproducir esa física (con su ruido encima).
- **Spoofing:** desde `t_inicio`, el GPS reportado = posición real + un desfase que crece despacio en una dirección. Como el controlador se guía por el GPS, **el dron cree ir bien y se desvía de verdad**; el radar ve la posición real. En `t_fin` el desfase desaparece de golpe (el GPS «salta» a la verdad) y el controlador corrige.

### 4.3 Fuentes y periodos

| Fuente | Evento | Periodo | Ruido / notas |
|---|---|---|---|
| GPS del dron (`d1-gps`) | `PositionUpdated` | 1 s | σ ≈ 1,5 m; lleva velocidad y rumbo de navegación |
| Radar de tierra (`radar-1`) | `TrackUpdated` | 2 s | σ ≈ 8 m; sin sesgo; ve la posición real |
| Estación meteo (`meteo-1`) | `WindReported` | 10 s | velocidad media, racha y dirección **de procedencia** (convención meteorológica) |
| Enlace de mando (`d1-link`) | `LinkStatus` | 5 s | `controller_id`, RSSI, latencia |
| Batería (`d1-bat`) | `BatteryStatus` | 10 s | ruido de fondo: el agente debería ignorarla |
| Misión (`d1-mission`) | `MissionPlanned`, `MissionStarted`, `WaypointReached`, `MissionCompleted` | por suceso | `WaypointReached` lo decide el dron con **su** GPS (bajo spoofing «alcanza» puntos que no ha alcanzado) |

### 4.4 Qué deja ver cada anomalía

| Anomalía | Trayectoria real | GPS frente a radar | Otras pistas | Regla que salta | Causa que debería concluir el agente |
|---|---|---|---|---|---|
| Viento | Deriva y el controlador corrige | Coinciden | `WindReported` fuerte; la deriva va a favor del viento | Desviación de ruta | `WIND` (física, sin intervención) |
| Secuestro | Se va a un punto fuera del plan, con rumbo firme | Coinciden | Sin viento fuerte; cambio en `LinkStatus` | Desviación de ruta | `HIJACK` (posible toma de control) |
| Spoofing | El dron cree ir bien y se desvía de verdad | Divergen: el GPS dice «en ruta», el radar no | Sin viento | Discrepancia entre fuentes (la de ruta **no**, porque el GPS va sobre el plan) | `GPS_SPOOFING` |
| Fuente silenciada (manual o programada) | No cambia: los eventos ya están generados; solo se dejan de publicar los de esa fuente | Si se silencia el radar, ya no se pueden comparar | El resto de fuentes siguen llegando | Fuente silenciosa | `SENSOR_FAULT` (qué fuente; si el enlace sigue vivo, el fallo es del sensor y no de las comunicaciones) |

Un detalle que da juego en la demo: **con el radar silenciado durante el spoofing, el engaño es invisible** (no hay segunda fuente con la que comparar). El agente debería decirlo si se le pregunta.

### 4.5 Gráficas (comprobación antes de la web)
`plot_scenario.py` sobre la salida del generador, sin reproducir nada:
- `plan_xy.png`: **solo lo planificado**: waypoints numerados y trayectoria planificada con flechas orientadas por el rumbo y coloreadas por la velocidad (barra de color).
- `scenario_xy.png`: lo planificado en tono claro, la trayectoria real con flechas por rumbo y color por velocidad, los puntos de GPS y de radar, y las zonas de anomalía.
- `scenario_time.png`: en el tiempo, desviación respecto al plan (del GPS y de la verdad), distancia GPS–radar y viento, con las ventanas de `labels.json` sombreadas.
- Opcional: animación con `FuncAnimation` mientras no hay web.

## 5. Reproductor y bus

- **Reloj simulado:** `sim_time` en segundos desde 0. Velocidades 0,5×, 1×, 2×, 4×, 8× y 16×. **Paso** = publicar el siguiente evento y quedarse en pausa.
- **Esperar al agente** (interruptor): cuando se publica un `DetectionRaised` o `DetectionUpdated`, el reproductor se pausa hasta que llega un evento del monitor con ese `causation_id` (o pasan 90 s de reloj). Así, a 8× se ven todas las alertas. Sin el interruptor, el agente va con retraso y se mide.
- **Bus:** `publish(evento)` y `subscribe(patrón, handler)`; comodines `*` (un segmento) y `>` (el resto), como NATS. El bus pone `ingestion_time` (reloj de pared) a cada evento. Todo lo que no sea efímero se guarda en el **timeline**.
- **Timeline:** en memoria y volcado a `runs/<escenario>/<ejecución>/timeline.jsonl`. Es lo que consultan las tools.
- **Fallos (silenciar fuentes):** el reproductor tiene una lista de fuentes silenciadas. Mientras una fuente lo está, sus eventos se **descartan al publicar** (no llegan al bus ni al timeline). Se cambia desde la web (`control` con `action: "fault"`). Los fallos **programados** en el YAML (`faults`) los aplica ya el generador: quita de `events.jsonl` los eventos de esa fuente en la ventana y escribe ahí los `FaultInjected`/`FaultCleared` con `origin: scenario` (así las pruebas del detector sobre `events.jsonl` también los ven). Cada cambio publica `FaultInjected` / `FaultCleared` en el dominio `sim`: la web y la evaluación los ven; **el agente no** (ninguna tool devuelve eventos del dominio `sim`), igual que no ve la verdad. Como los eventos ya están generados, silenciar el GPS corta el **reporte** al bus, no la navegación del dron (no cambia su trayectoria).

## 6. Detector de reglas (con histéresis)

Cada regla tiene dos estados (normal y en alerta) y dos umbrales. **Abre** un episodio al pasar el umbral alto y publica `DetectionRaised` **una vez**; no vuelve a avisar mientras dure, salvo que empeore claramente (`DetectionUpdated` con más severidad); lo **cierra** cuando el valor baja del umbral bajo durante unos segundos (`DetectionCleared`). Así el monitor recibe una petición por problema, no una por segundo.

| Regla | Mide | Abre | Cierra | Empeora |
|---|---|---|---|---|
| `ROUTE_DEVIATION` | Distancia del GPS a la ruta planificada (polilínea) | > 30 m | < 15 m durante 5 s | > 80 m |
| `SOURCE_DISCREPANCY` | Distancia GPS–radar (GPS interpolado al instante del radar, media de las 3 últimas) | > 25 m | < 12 m durante 6 s | > 80 m |
| `SOURCE_SILENT` | Tiempo sin eventos de una fuente, por fuente (lleva `source` en la detección) | GPS > 3 s; radar > 6 s; enlace > 15 s; meteo > 30 s; batería > 30 s | al llegar el siguiente evento de esa fuente | — |

Mientras el radar está en silencio (o su último dato tiene más de 6 s), `SOURCE_DISCREPANCY` no se evalúa: no se compara con datos viejos. Lo mismo `ROUTE_DEVIATION` con el GPS.

Los umbrales son configurables y se ajustan con los escenarios. Criterio duro: en `nominal.yaml` **no salta ninguna regla**.

## 7. Agentes

### 7.1 Un motor, varias configuraciones
Un único motor de agente (bucle de tool calling a mano con `openai`) que recibe: prompt de orquestación (sistema), prompt de objetivo (plantilla por invocación), prompt o esquema de salida, lista de tools, índice de skills y tope de iteraciones. Se instancia cuatro veces:

| Instancia | Cuándo | Tools | Salida | Memoria |
|---|---|---|---|---|
| **Monitor** | Con cada `DetectionRaised`/`Updated`/`Cleared` | Las 7 del monitor | `publish_alert` / `close_alert` (JSON validado) | **Opción B:** sin historial; resumen de estado inyectado |
| **Chat del monitor** | Con cada `OperatorMessage` al monitor | Las de lectura + `load_skill` | Texto en streaming | Conversación (últimos N mensajes) |
| **Informe** | Con `SimulationFinished` (cuando el monitor ha vaciado su cola) | Las de lectura + `get_flight_summary` + `load_skill` | Markdown (skill `report-format`) | Sin historial |
| **Chat del informe** | Con cada `OperatorMessage` al informe, tras el informe | Las de lectura + `load_skill` | Texto en streaming | Conversación |

El monitor solo ve hasta el instante actual; el informe ve la simulación entera.

### 7.2 Tools

| Tool | Dónde vive | Qué hace |
|---|---|---|
| `get_events(source, type, last_n, since, until)` | Plataforma | Eventos de una fuente, compactos. `until` nunca pasa del instante actual |
| `get_mission_plan()` | Plataforma | Waypoints, velocidad prevista y hora estimada de paso |
| `get_track_metrics(since, until)` | Plataforma | **Calculado** a partir de los eventos: desviación respecto al plan del GPS y del radar, distancia GPS–radar, dirección de la deriva, rumbo de avance frente al rumbo al siguiente waypoint, velocidad media, ids usados |
| `get_my_alerts(only_open)` | Plataforma | Alertas publicadas por el monitor y su estado (reconstruido de los eventos) |
| `get_flight_summary()` | Plataforma | Solo informe: duración, distancia, waypoints alcanzados, detecciones y alertas |
| `publish_alert(...)` | Módulo de IA | Única acción del monitor: publica `AnomalyDetected` tras validarlo |
| `close_alert(alert_id, reason)` | Módulo de IA | Publica `AlertClosed` (los eventos no se modifican) |
| `load_skill(name)` | Módulo de IA | Devuelve el contenido de una skill |

Las tools de datos viven en la plataforma (`POST /api/tools/{nombre}`) porque son servicios del «mundo»: el módulo Java las llamará igual, y en la fase de MCP se exponen tal cual como servidor MCP. Los esquemas que ve el modelo están en `agent-assets/tools.json` (formato OpenAI), compartidos por Python y Java.

`get_track_metrics` da la información masticada a propósito: un 14B se equivoca con la geometría. Queda como experimento quitarla (bandera `disabled_tools`) para ver si el agente se apaña con `get_events`.

### 7.3 Skills
Ficheros `agent-assets/skills/<nombre>/SKILL.md` con cabecera (`name`, `description`). En el prompt de sistema va **solo el índice**; el agente carga la que necesite con `load_skill`.
- `route-deviation`: árbol de diagnóstico cuando salta `ROUTE_DEVIATION` (viento, secuestro, desconocido).
- `source-discrepancy`: cuando salta `SOURCE_DISCREPANCY` o `SOURCE_SILENT` (spoofing, fallo de sensor, fuente que deja de informar).
- `report-format`: estructura del informe final.

**Modo guiado** (interruptor, apagado por defecto): el módulo precarga la skill que corresponde al tipo de detección. Se activa solo si el modelo no llama a `load_skill` por sí mismo; la evaluación cuenta cuántas veces lo hace.

### 7.4 Los tres prompts (lo que pidió David)
- **Orquestación** (sistema): rol, qué puede y qué no (solo alerta y recomienda; no actúa), que no ve el futuro, índice de skills, cómo usar las tools, que cite evidencias por id, tope de iteraciones.
- **Objetivo** (por invocación): la detección concreta, el instante, y el resumen del estado (alertas abiertas, últimas decisiones).
- **Salida:** el esquema de `publish_alert` / `AnomalyDetected` (enumerados de causa y severidad).

### 7.5 Guardrails
- El JSON de `publish_alert` se valida con Pydantic; si no valida, la tool devuelve el error y el modelo reintenta (cuenta como iteración).
- Los `evidence_event_ids` tienen que existir en el timeline y ser anteriores o iguales al instante de la invocación.
- Causa y severidad, de listas cerradas; `confidence` entre 0 y 1.
- Tope de 8 iteraciones. Si se agota sin publicar, el módulo publica un `AnomalyDetected` con `cause: UNKNOWN` y `fallback: true`.
- Las tools de datos fuerzan el corte temporal en la plataforma (el agente no puede pedir el futuro).
- Temperatura de `agents.yaml`, enviada **siempre de forma explícita** (si no se envía, vLLM aplica la del `generation_config.json` del modelo). Llamadas detectadas por `message.tool_calls`, nunca por `finish_reason`. Nada de `tool_choice` por nombre (`auto`).

### 7.6 Trazas
Cada invocación de cada agente se guarda en `runs/.../llm_trace.jsonl`: mensajes enviados, llamadas a tools con argumentos y resultado, tokens, latencia, iteraciones y si cargó skills. La web lo muestra en la consola del agente.

## 8. Evaluación (contra `labels.json`)
`evaluate.py runs/<escenario>/<ejecución>` produce `eval.md`:
- Por anomalía etiquetada: ¿se detectó? (regla y `sim_time`), retraso de detección, ¿se diagnosticó con la causa correcta?, confianza, retraso de diagnóstico (en tiempo simulado y en reloj de pared).
- Falsas alarmas: detecciones o alertas fuera de las ventanas etiquetadas (en `nominal`, cualquiera).
- Fallos (programados o manuales, de los `FaultInjected`): para cada uno, si saltó `SOURCE_SILENT` de esa fuente y si el monitor publicó `SENSOR_FAULT` (o lo que concluyera) y con cuánto retraso. Se listan aunque no tengan etiqueta previa.
- Del agente: iteraciones, tools usadas, skills cargadas por sí mismo, reintentos por JSON inválido, fallbacks, latencia de cada llamada al LLM.

## 9. Fases (con punto de parada al final de cada una)

| Fase | Qué | Criterio para pasar |
|---|---|---|
| 0 | Repo, entornos, contratos en código (Pydantic) y esquemas JSON exportados | Los ejemplos de `contracts/eventos.md` validan |
| 1 | Generador, controlador y gráficas | **Carlos revisa las gráficas.** `nominal` sin desvíos > 15 m; cada anomalía se ve en las gráficas como en la tabla 4.4 |
| 2 | Plataforma: reproductor (con fallos manuales), bus, WebSocket, timeline y tools de datos. Detector de reglas en el módulo de IA. Ejecución por terminal | `nominal` sin detecciones; cada escenario dispara la regla esperada una vez por episodio; `fallos` dispara `SOURCE_SILENT` de la fuente correcta |
| 3 | Motor de agente, monitor, informe, chats, guardrails, trazas y evaluación | `demo.yaml` diagnosticado con la causa correcta en las tres anomalías (o el fallo documentado) |
| 4 | Web conectada a la plataforma | Demo completa en el navegador |
| 5 | Extras si queda tiempo (ver `docs/mejoras_futuras.md`) | — |

## 10. Relación con el resto del proyecto
- **MDO:** topics con la taxonomía de David (13/10/2026): `<namespace>.<clasification>.<type>.<domain>.<routing>.<event>.<version>`. El bus en memoria imita NATS para poder cambiarlo después.
- **A09 (Centralised Timeline):** cada evento lleva `event_time` (del origen, aquí simulado), `ingestion_time` (del bus) y `sim_time` (equivale a `relativeTime`).
- **Spike 1:** mismas reglas de cliente (Chat Completions, temperatura explícita, `message.tool_calls`); `annotate_event` pasa a ser `publish_alert`.
- **Spike 2:** el Isolation Forest es la mejora natural del detector (mismas características por evento de posición).
- **Java:** se portará solo el módulo de IA. Prompts, skills y esquemas de tools están en `agent-assets/`, fuera del código; las tools de datos se llaman por HTTP.
