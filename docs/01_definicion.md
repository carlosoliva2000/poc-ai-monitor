# PoC `poc-ai-monitor`: definición

> Creado el 16/10/2026 (proyecto CITADEL). Es la referencia de diseño de la PoC. Si algo de aquí contradice a `contracts/eventos.md`, mandan los contratos.

## 1. Para qué es

Enseñar al equipo de MDO (David, Francesco, Jesús…) cómo la **IA puede funcionar como extensión de un worker**: un módulo que se suscribe a eventos del bus, detecta que algo no cuadra, **publica un evento de alerta** con la causa probable y su explicación, y al terminar el ejercicio genera un informe. El ejemplo es un dron, porque el MVP de MDO es un escenario de drones.

Lo que se quiere demostrar, en este orden:
1. El módulo de IA **consume eventos canónicos** del bus y **publica eventos**; no actúa sobre nada más (coherente con que MDO no orquesta).
2. Un agente con **tools, skills y tres prompts** (orquestación, objetivo y salida), lo que pidió David.
3. La IA **diagnostica causas cruzando fuentes** (GPS, radar, meteorología, enlace de mando), no solo dice «algo va mal».
4. El diseño se puede **portar a Java** sin reescribir las tools, los prompts ni las skills.

**No es** predecir la trayectoria del dron, ni controlarlo, ni un producto. Plazo: una o dos jornadas de trabajo; se enseña la semana del 19/10/2026.

## 2. Decisiones tomadas (16/10/2026)

| Tema | Decisión |
|---|---|
| Lenguajes | Plataforma y módulo de IA en **Python** (3.12, `uv`, `ruff`); web en **JS** (se parte de la interfaz de v0, Next.js). El módulo de IA se portará a Java más adelante |
| Bus | **Sin NATS.** Bus en memoria dentro de la plataforma, con topics y comodines al estilo NATS, expuesto por **WebSocket** a la web y al módulo de IA (proceso aparte) |
| Simulación | **Un solo motor que simula en directo**, paso a paso (0,1 s), con la misma física y los mismos sensores que el generador. **Solo hacia adelante**: play, pausa, paso (siguiente evento), reinicio y velocidad. Sin retroceso ni salto a un instante |
| Fallos | Dos tipos: **`mute`** (cualquier fuente: deja de publicarse y el dron vuela igual) y **`loss`** (solo GPS: el dron navega a estima y se desvía de verdad). Se programan en el YAML del escenario y, con el **modo interactivo** encendido (apagado por defecto), se activan y terminan en directo desde la web o el visor para ver si el agente reacciona |
| Dron | **Uno** (`d1`), plano **x,y en metros** (x hacia el este, **y hacia el norte**), sin mapa |
| Generador | Propio y sencillo: plan por waypoints + **controlador** que lo sigue + perturbaciones, en un **simulador incremental** (estado + paso) con semilla. Lo usan el reproductor en directo y la generación de `runs/<escenario>/`, que es el resultado esperado **sin intervenciones** (pruebas, gráficas, evaluación) |
| Anomalías implementadas | **Viento, secuestro y spoofing de GPS**, más la **pérdida de GPS** (jamming) como fallo `loss`. El diseño admite más (replay…), que quedan como mejora |
| Segunda fuente | **Radar de tierra** que ve la posición real; más estación meteorológica, enlace de mando y batería (ruido) |
| Detector | **Cuatro reglas con histéresis** (sin entrenamiento): desviación de ruta, discrepancia entre fuentes, fuente silenciosa y GPS degradado. El Isolation Forest del spike 2 queda como mejora detrás del mismo puerto |
| LLM | vLLM local de Carlos, `Qwen/Qwen2.5-14B-Instruct-AWQ`, Chat Completions. **Nada sale a la nube** |
| Librería | **`openai` (SDK oficial) con el bucle del agente escrito a mano.** Motivo: existe el SDK oficial equivalente en Java (`openai-java`) y ya se probaron los dos contra este vLLM en el spike 1. LangChain Python y LangChain4j son proyectos distintos con API distinta |
| Agentes | **Dos**, con el mismo motor: **monitor** (tiempo real) e **informe** (al final). Se puede **chatear con los dos** |
| Sesión del monitor | **Opción B:** una llamada nueva por cada detección, con un resumen del estado inyectado; lo anterior lo consulta con tools. La opción A (una conversación durante toda la simulación) queda como mejora para comparar |
| Tools | Ocho para el monitor (más una del informe). Las tools de datos viven en la **plataforma** y se llaman por HTTP; así el módulo Java las usará sin reescribirlas. MCP, en una segunda fase |
| Skills | Ficheros Markdown cargados **a demanda** por el agente (`load_skill`). Organizadas por síntoma, más una de formato del informe |
| Telemetría externa | Ninguna (nada de LangSmith ni similares). Trazas propias en JSONL |
| Repo | `poc-ai-monitor` en GitLab `citadel/labs`. Un solo repo para todos los componentes. **El agente no hace commits**: los hace Carlos |
| Idioma | Código (identificadores, nombres de ficheros de código, logs) en **inglés**; comentarios y docstrings en **español**. Nombres de tools, skills, prompts, eventos y campos en inglés; el **contenido** de prompts y skills, los textos para personas (web, alertas, informe) y la documentación, en español |
| Temperatura | **0 para el monitor** (decisiones reproducibles y evaluación comparable entre ejecuciones). Informe y chats con los valores que recomienda el modelo en su `generation_config.json` (0,7 / `top_p` 0,8 / `top_k` 20), para un texto más natural. Configurable por agente en `agents.yaml` |

## 3. Arquitectura

```
                 PLATAFORMA  (hace el papel de MDO; Python, un proceso, FastAPI, puerto 8100)
 scenarios/*.yaml ─► simulador incremental (paso 0,1 s) ─► runs/<escenario>/ (plan, verdad, eventos, etiquetas:
                                       │                    el resultado esperado sin intervenciones)
                     reproductor (reloj simulado: play/pausa/paso/velocidad/esperar al agente,
                                  fallos en modo interactivo; ejecuta el simulador en directo)
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
4. **Lo que se reporta:** GPS del dron, radar, meteorología, enlace, batería y misión, con su ruido y sus periodos (`events.jsonl`: lo que produce el simulador sin intervenciones; el reproductor en directo produce lo mismo).
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
| Radar de tierra (`radar-1`) | `TrackUpdated` | 2 s | σ ≈ 5 m; sin sesgo; ve la posición real |
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
| Fuente silenciada, `mute` (manual o programada) | No cambia: el dron vuela igual; solo se deja de publicar esa fuente | Si se silencia el radar, ya no se pueden comparar | El resto de fuentes siguen llegando | Fuente silenciosa | `SENSOR_FAULT` (qué fuente; si el enlace sigue vivo, el fallo es del sensor y no de las comunicaciones) |
| Pérdida de GPS, `loss` (manual o programada) | **El dron navega a estima** (sin conocer el viento) y se desvía de verdad; puede dar por alcanzados waypoints que no ha alcanzado | Divergen: el GPS publica la estima (sobre el plan), el radar ve la desviación real | `fix: none`, `sats: 0`, `hdop` alto; sin spoofing (en el spoofing el GPS parece sano) | GPS degradado (primer segundo), discrepancia entre fuentes (después) y, al recuperarse el GPS (la posición salta a la real), desviación de ruta | `GPS_JAMMING` (o `SENSOR_FAULT` si solo está degradado y no hay discrepancia) |

Un detalle que da juego en la demo: **con el radar silenciado durante el spoofing, el engaño es invisible** (no hay segunda fuente con la que comparar). El agente debería decirlo si se le pregunta. Lo mismo con la pérdida de GPS: aunque el radar calle, `fix: none` delata el fallo, pero no se puede confirmar cuánto se ha desviado el dron.

El `ROUTE_DEVIATION` que salta cuando el GPS recupera la verdad (al acabar el spoofing o una pérdida de GPS) es **esperado**: en la evaluación cuenta como acierto si el monitor lo atribuye a la causa de esa anomalía (`GPS_SPOOFING`; `GPS_JAMMING` o `SENSOR_FAULT` en la pérdida) y como fallo de diagnóstico si lo atribuye a otra.

### 4.5 Gráficas (comprobación antes de la web)
`plot_scenario.py` sobre la salida del generador, sin reproducir nada:
- `plan_xy.png`: **solo lo planificado**: waypoints numerados y trayectoria planificada con flechas orientadas por el rumbo y coloreadas por la velocidad (barra de color).
- `scenario_xy.png`: lo planificado en tono claro, la trayectoria real con flechas por rumbo y color por velocidad, los puntos de GPS y de radar, y las zonas de anomalía.
- `scenario_time.png`: en el tiempo, desviación respecto al plan (del GPS y de la verdad), distancia GPS–radar y viento, con las ventanas de `labels.json` sombreadas.
- Opcional: animación con `FuncAnimation` mientras no hay web.

## 5. Reproductor y bus

- **Simulación en directo:** el reproductor **no lee `events.jsonl`**: ejecuta el simulador incremental paso a paso (0,1 s) con la misma física y los mismos sensores que el generador, y publica lo que va saliendo. No hay un segundo modo de «reproducir desde archivo». `runs/<escenario>/events.jsonl` sigue generándose con el mismo simulador y es el **resultado esperado sin intervenciones**: en directo y sin intervenciones, los eventos son idénticos (el ruido de todas las fuentes se saca siempre en el mismo orden, aunque una fuente esté silenciada o en fallo). Sirve para las pruebas, las gráficas, el desarrollo offline del detector y del agente y la evaluación.
- **Reloj simulado:** `sim_time` en segundos desde 0. Velocidades 0,5×, 1×, 2×, 4×, 8× y 16×. **Paso** = publicar el siguiente evento y quedarse en pausa.
- **Esperar al agente** (interruptor): cuando se publica un `DetectionRaised` o `DetectionUpdated`, el reproductor se pausa hasta que llega un evento del monitor (`AnomalyDetected`, `DetectionAcknowledged` o `AlertClosed`) con el `event_id` de esa detección como `causation_id` (o pasan 90 s de reloj). Así, a 8× se ven todas las alertas. Sin el interruptor, el agente va con retraso y se mide.
- **Bus:** `publish(evento)` y `subscribe(patrón, handler)`; comodines `*` (un segmento) y `>` (el resto), como NATS. El bus pone `ingestion_time` (reloj de pared) a cada evento. Todo lo que no sea efímero se guarda en el **timeline**.
- **Timeline:** en memoria y volcado a `runs/<escenario>/<ejecución>/timeline.jsonl`. Es lo que consultan las tools.
- **Modo interactivo** (interruptor `interactive`, apagado por defecto; `control` → `interactive`, visible en `state`): apagado, la plataforma **rechaza** los `fault` con un error claro y la ejecución sale idéntica a `events.jsonl`; encendido, se aceptan. Se puede cambiar en cualquier momento y cada cambio se registra en el timeline (`InteractiveModeChanged`, dominio `sim`).
- **Fallos:** dos tipos. **`mute`** (cualquier fuente): la fuente deja de publicarse (sus eventos no llegan al bus ni al timeline) y el dron vuela igual. **`loss`** (solo GPS): el dron **navega a estima**: integra su velocidad respecto al aire sin conocer el viento, el controlador sigue el plan con esa estimación (puede dar por alcanzados waypoints que no ha alcanzado) y la trayectoria real se va desviando; mientras dura, el GPS publica `PositionUpdated` con la posición estimada, `fix: "none"`, `sats: 0` y `hdop` alto; al recuperarse, la posición salta a la real y el controlador corrige. El enlace de mando, el radar, la meteo y la batería solo tienen `mute`. Los fallos **programados** en el YAML (`faults`, con `mode`) los aplica el propio simulador (con `origin: scenario`), así que están también en `events.jsonl`; los **manuales** (`control` → `fault`, solo con el modo interactivo) los aplica el reproductor desde el instante actual (`origin: manual`). Cada cambio publica `FaultInjected` / `FaultCleared` en el dominio `sim`: la web y la evaluación los ven; **el agente no** (ninguna tool devuelve eventos del dominio `sim`), igual que no ve la verdad. El LLM nunca ve el dominio `sim`; el módulo de IA (código, no el LLM) puede usar el ciclo de vida de la ejecución (`SimulationStarted`, `SimulationReset` y `SimulationFinished`) para reiniciarse y para lanzar el informe.
- **Verdad en curso:** `GET /api/truth` sirve la verdad de la simulación en curso hasta el instante actual (solo para la web, el visor y la evaluación).

## 6. Detector de reglas (con histéresis)

Cada regla tiene dos estados (normal y en alerta) y dos umbrales. **Abre** un episodio al pasar el umbral alto y publica `DetectionRaised` **una vez**; no vuelve a avisar mientras dure, salvo que empeore claramente (`DetectionUpdated` con más severidad); lo **cierra** cuando el valor baja del umbral bajo durante unos segundos (`DetectionCleared`). Así el monitor recibe una petición por problema, no una por segundo.

| Regla | Mide | Abre | Cierra | Empeora |
|---|---|---|---|---|
| `ROUTE_DEVIATION` | Distancia del GPS a la ruta planificada (polilínea) | > 30 m | < 15 m durante 5 s | > 80 m |
| `SOURCE_DISCREPANCY` | Distancia GPS–radar (GPS interpolado al instante del radar, media de las 3 últimas) | > 25 m | < 12 m durante 6 s | > 80 m |
| `SOURCE_SILENT` | Tiempo sin eventos de una fuente, por fuente (lleva `source` en la detección) | GPS > 3 s; radar > 6 s; enlace > 15 s; meteo > 30 s; batería > 30 s | al llegar el siguiente evento de esa fuente | — |
| `GPS_DEGRADED` | Calidad del último `PositionUpdated` (`source: gps`; `value` = `hdop`) | `fix` distinto de `3d`, `sats` < 6 o `hdop` > 3 | 5 s de lecturas normales | `fix: none` (severidad `high`) |

Mientras el radar está en silencio (o su último dato tiene más de 6 s), `SOURCE_DISCREPANCY` no se evalúa: no se compara con datos viejos. Lo mismo `ROUTE_DEVIATION` con el GPS.

Los umbrales son configurables y se ajustan con los escenarios. Criterio duro: en `nominal.yaml` **no salta ninguna regla**.

## 7. Agentes

### 7.1 Un motor, varias configuraciones
Un único motor de agente (bucle de tool calling a mano con `openai`) que recibe: prompt de orquestación (sistema), prompt de objetivo (plantilla por invocación), prompt o esquema de salida, lista de tools, índice de skills y tope de iteraciones. Se instancia cuatro veces:

| Instancia | Cuándo | Tools | Salida | Memoria |
|---|---|---|---|---|
| **Monitor** | Con cada `DetectionRaised`/`Updated`/`Cleared` (los `Cleared` que no cambian nada, sin LLM) | Las 8 del monitor | `publish_alert` / `acknowledge_detection` / `close_alert` (JSON validado): **cada aviso recibe una respuesta** | **Opción B:** sin historial; resumen de estado inyectado |
| **Chat del monitor** | Con cada `OperatorMessage` al monitor | Las de lectura + `load_skill` | Texto en streaming | Conversación (últimos N mensajes) |
| **Informe** | Con `SimulationFinished` (cuando el monitor ha vaciado su cola) | **Ninguna**: el módulo le inyecta en el prompt el resultado de `get_flight_summary`, cada anomalía (cadena de alertas) con lo que vio el detector y lo que dijo el monitor, y los retrasos, fallbacks, rechazos de los guardrails y ayudas activas, y hace una sola llamada | Solo cuatro apartados en Markdown (resumen, «qué se vio» de cada anomalía, valoración del monitor y recomendaciones; estructura de la skill `report-format`, inyectada). **Los hechos** (cabecera, cronología, T+ de detección, alerta y cierre, severidad, estado, evidencias, cifras del monitor y limitaciones) **los escribe el módulo** de forma determinista y monta el informe | Sin historial |
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
| `publish_alert(...)` | Módulo de IA | Publica `AnomalyDetected` tras validarlo (alerta nueva, o `supersedes` si cambia la causa o la severidad de una abierta) |
| `acknowledge_detection(detection_ids, alert_id?, reason)` | Módulo de IA | Responde a un aviso sin crear alerta: `DetectionAcknowledged` con la alerta abierta a la que pertenece, o sin `alert_id` si no hace falta alerta |
| `close_alert(alert_id, reason)` | Módulo de IA | Publica `AlertClosed` (los eventos no se modifican) |
| `load_skill(name)` | Módulo de IA | Devuelve el contenido de una skill |

Las tools de datos viven en la plataforma (`POST /api/tools/{nombre}`) porque son servicios del «mundo»: el módulo Java las llamará igual, y en la fase de MCP se exponen tal cual como servidor MCP. Los esquemas que ve el modelo están en `agent-assets/tools.json` (formato OpenAI), compartidos por Python y Java.

`get_track_metrics` da la información masticada a propósito: un 14B se equivoca con la geometría. Queda como experimento quitarla (bandera `disabled_tools`) para ver si el agente se apaña con `get_events`.

### 7.3 Skills
Ficheros `agent-assets/skills/<nombre>/SKILL.md` con cabecera (`name`, `description`). En el prompt de sistema va **solo el índice**; el agente carga la que necesite con `load_skill`.
- `route-deviation`: árbol de diagnóstico cuando salta `ROUTE_DEVIATION` (viento, secuestro, recuperación tras un engaño o una pérdida del GPS, desconocido).
- `source-discrepancy`: cuando salta `SOURCE_DISCREPANCY`, `SOURCE_SILENT` o `GPS_DEGRADED` (spoofing, pérdida o interferencia del GPS, fallo de sensor, fuente que deja de informar).
- `report-format`: estructura del informe final y qué parte escribe el modelo.

**Modo guiado** (interruptor, apagado por defecto): el módulo precarga la skill que corresponde al tipo de detección. Se activa solo si el modelo no llama a `load_skill` por sí mismo; la evaluación cuenta cuántas veces lo hace.

### 7.4 Los tres prompts (lo que pidió David)
- **Orquestación** (sistema): rol, qué puede y qué no (solo alerta y recomienda; no actúa), que no ve el futuro, índice de skills, cómo usar las tools, que cite evidencias por id, tope de iteraciones.
- **Objetivo** (por invocación): la detección concreta, el instante, y el resumen del estado (alertas abiertas, últimas decisiones).
- **Salida:** el esquema de `publish_alert` / `AnomalyDetected` (enumerados de causa y severidad).

### 7.5 Guardrails
- El JSON de `publish_alert` se valida con Pydantic (causas y severidades de listas cerradas, `confidence` entre 0 y 1, `summary` de 160 caracteres como máximo); si no valida, la tool devuelve el error y el modelo reintenta (cuenta como iteración). Lo mismo con cualquier rechazo de los guardrails siguientes.
- Cada `evidence_event_ids` tiene que existir (en un índice local de los eventos de `air`, `env`, `ai` y `ops` recibidos por el WebSocket, que no incluye el dominio `sim`) y tener `sim_time` menor o igual que el instante de la invocación. Los ids que existen pero el modelo no ha visto en la invocación no se rechazan: se cuentan en la traza.
- Las `detection_ids` existen; `supersedes` apunta a una alerta abierta; sin `supersedes`, se rechaza si una de las detecciones ya está en una alerta abierta. `acknowledge_detection`: el `alert_id` existe y está abierto, y cada detección es del lote y aún no tiene respuesta. `close_alert`: la alerta existe, está abierta y no le quedan detecciones abiertas.
- Tope de 8 iteraciones, un tiempo máximo por invocación y un recordatorio si el modelo contesta con texto sin responder a todos los avisos. **Garantía de respuesta:** si al terminar queda un aviso sin respuesta, el módulo la publica él mismo (`fallback: true`): en un `DetectionRaised` sin ninguna alerta abierta, un `AnomalyDetected` con `cause: UNKNOWN`; en cualquier otro caso, un `DetectionAcknowledged` con `alert_id: null`. Si el que queda sin respuesta es el `DetectionCleared` de la última detección abierta de una alerta, el módulo cierra la alerta con un `AlertClosed` («todas sus detecciones se han cerrado»). Un `DetectionCleared` que no cambia nada (a la alerta le quedan detecciones abiertas, o no tiene alerta, o ya está cerrada) se responde con un `DetectionAcknowledged` determinista, sin LLM.
- Las tools de datos fuerzan el corte temporal en la plataforma (el agente no puede pedir el futuro) y el módulo pone `until` = instante de la invocación si falta o es mayor.
- Parámetros de muestreo de `agents.yaml` (`temperature`, `top_p`, y en `extra_body` `top_k` y `repetition_penalty`), enviados **siempre de forma explícita** (si no se envían, vLLM aplica los del `generation_config.json` del modelo). `repetition_penalty` 1,05 (el valor del modelo) en todos los agentes: con 1,0 y temperatura 0 (decodificación voraz) apareció un bucle de repetición. `top_k`: −1 en el monitor (con temperatura 0 no influye) y 20 en informe y chats. Llamadas detectadas por `message.tool_calls`, nunca por `finish_reason`.
- **Hechos calculados y comprobaciones.** `get_track_metrics` entrega el viento de la ventana y hechos ya calculados (`wind.notable`, `wind.with_drift`, `gps_radar.disagreed`, `gps_max_step_m`) para que el modelo no compare números ni ángulos. `publish_alert` lleva un objeto `checks` (obligatorio, antes de `cause`) y un **guardrail de coherencia**: cada valor de `checks` debe coincidir con los resultados de las tools de la invocación y con el estado, y la causa ser coherente (`WIND` exige viento notable y a favor de la deriva; `HIJACK`, haber mirado el enlace; la recuperación del GPS sobre un `ROUTE_DEVIATION`, alerta del GPS reciente y discrepancia o salto del GPS). Cada ayuda tiene un interruptor en `agents.yaml` (`monitor.*`) para poder quitarla con un modelo mejor.
- **Recuperación excluyente.** En un `ROUTE_DEVIATION`, si el estado tiene una alerta del GPS reciente (abierta o cerrada hace 60 s o menos) y se cumple `gps_radar.disagreed` o `gps_max_step_m` ≥ 30, la única causa aceptada es la de esa alerta, con `supersedes` = esa alerta si sigue abierta; el rechazo lo dice («Es la recuperación del GPS_SPOOFING de ai-0002: publica cause GPS_SPOOFING, severity medium y supersedes ai-0002») y la línea del estado del prompt lo anticipa.
- **Ids que el módulo rellena y corte por repetición.** Con una sola detección pendiente en el lote, `detection_ids` es opcional en `publish_alert` y `acknowledge_detection`; en un aviso de cierre, `alert_id` es opcional en `close_alert` y `acknowledge_detection`; un id equivocado se rechaza indicando el correcto. Si el modelo repite por segunda vez una llamada idéntica a otra ya rechazada, el motor corta la invocación (`end_reason: repeated_rejection`) y el módulo aplica el fallback.
- **Chats sin tools** (`chat.tools_enabled: false` en `agents.yaml`, el valor de la demo): los chats no reciben tools y su sistema lleva el estado, las alertas (con explicación, comprobaciones y evidencias) y los últimos hechos de `get_track_metrics`. Con `true` mantienen sus tools.
- **`tool_choice`:** `auto` por defecto; `required` para un agente cuya respuesta es siempre una tool call (el monitor, que acaba siempre en `publish_alert`, `acknowledge_detection` o `close_alert`); nunca forzar por nombre. Con `required`, vLLM impone la llamada con decodificación guiada (structured outputs): el modelo no puede contestar con texto ni escribir la llamada como texto. Con `auto`, vLLM la extrae del texto y el 14B a veces la escribe en un bloque de código (sin `tool_calls`). En la **última iteración permitida** el motor ofrece solo las `final_tools` del agente (las tres respuestas del monitor), sin forzar ninguna por nombre, para que no siga encadenando tools de datos hasta el tope.
- **Nota para el módulo Java:** el equivalente de `tool_choice: required` en `openai-java` es `ChatCompletionToolChoiceOption` con el modo `required` (`ChatCompletionCreateParams.toolChoice`); `top_k` y `repetition_penalty` no son parámetros de OpenAI y hay que mandarlos como propiedades adicionales del cuerpo (`putAdditionalBodyProperty`). Con `required`, la respuesta llega con `content` vacío y `tool_calls` relleno. El resto del bucle (iteraciones, recordatorio, última iteración con `final_tools`, garantía de respuesta) es lógica propia y se porta tal cual.
- Un intento del modelo que es solo texto, cuando se le envía un recordatorio, **no se guarda** en los `messages` (el modelo lo imitaría): lo sustituye el recordatorio. En la traza sí queda.

### 7.6 Trazas
Cada invocación de cada agente se guarda en `runs/<escenario>/<run_id>/llm_trace.jsonl` (una línea por invocación): parámetros enviados, tools ofrecidas, `messages` completos, y por cada llamada la latencia, los tokens, las tool calls con argumentos y resultado, y si se recortó; skills cargadas (por el modelo o por el modo guiado), rechazos de guardrails, fallbacks y eventos publicados. El timeline sigue creciendo en `timeline.jsonl` después de `SimulationFinished` (últimas respuestas, informe y chats). La web lo muestra en la consola del agente.

## 8. Evaluación (contra `labels.json`)
`evaluate.py runs/<escenario>/<ejecución>` produce `eval.md`:
- Por anomalía etiquetada: ¿se detectó? (regla y `sim_time`), retraso de detección, ¿se diagnosticó con la causa correcta?, confianza, retraso de diagnóstico (en tiempo simulado y en reloj de pared).
- Falsas alarmas: detecciones o alertas fuera de las ventanas etiquetadas (en `nominal`, cualquiera).
- Fallos (programados o manuales, de los `FaultInjected`): para cada uno, si saltó la regla esperada (`SOURCE_SILENT` de esa fuente en un `mute`; `GPS_DEGRADED` y `SOURCE_DISCREPANCY` en una pérdida de GPS) y si el monitor publicó `SENSOR_FAULT` (o `GPS_JAMMING` en la pérdida) y con cuánto retraso. Se listan aunque no tengan etiqueta previa.
- Del agente: iteraciones, tools usadas, skills cargadas por sí mismo, reintentos por JSON inválido, fallbacks, latencia de cada llamada al LLM.

## 9. Fases (con punto de parada al final de cada una)

| Fase | Qué | Criterio para pasar |
|---|---|---|
| 0 | Repo, entornos, contratos en código (Pydantic) y esquemas JSON exportados | Los ejemplos de `contracts/eventos.md` validan |
| 1 | Generador, controlador y gráficas | **Carlos revisa las gráficas.** `nominal` sin desvíos > 15 m; cada anomalía se ve en las gráficas como en la tabla 4.4 |
| 2 | Plataforma: simulador incremental y reproductor en directo (con modo interactivo y fallos `mute`/`loss`), bus, WebSocket, timeline y tools de datos. Detector de reglas en el módulo de IA. Visor en directo sin web. Ejecución por terminal | `nominal` sin detecciones; cada escenario dispara la regla esperada una vez por episodio; `fallos` dispara `SOURCE_SILENT` de la fuente correcta y, en la pérdida de GPS, `GPS_DEGRADED` y después `SOURCE_DISCREPANCY` |
| 3 | Motor de agente, monitor, informe, chats, guardrails, trazas y evaluación | `demo.yaml` diagnosticado con la causa correcta en las tres anomalías (o el fallo documentado) |
| 4 | Web conectada a la plataforma | Demo completa en el navegador |
| 5 | Extras si queda tiempo (ver `docs/mejoras_futuras.md`) | — |

## 10. Relación con el resto del proyecto
- **MDO:** topics con la taxonomía de David (13/10/2026): `<namespace>.<clasification>.<type>.<domain>.<routing>.<event>.<version>`. El bus en memoria imita NATS para poder cambiarlo después.
- **A09 (Centralised Timeline):** cada evento lleva `event_time` (del origen, aquí simulado), `ingestion_time` (del bus) y `sim_time` (equivale a `relativeTime`).
- **Spike 1:** mismas reglas de cliente (Chat Completions, temperatura explícita, `message.tool_calls`); `annotate_event` pasa a ser `publish_alert`.
- **Spike 2:** el Isolation Forest es la mejora natural del detector (mismas características por evento de posición).
- **Java:** se portará solo el módulo de IA. Prompts, skills y esquemas de tools están en `agent-assets/`, fuera del código; las tools de datos se llaman por HTTP.
