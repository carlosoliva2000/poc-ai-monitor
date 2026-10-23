# web/

Interfaz de la demo. Se parte de la que generó v0 (`/mnt/c/Proyectos/interfaz-de-simulacion-dron/`, Next.js + React + Tailwind, pnpm): **cópiala aquí** (sin `node_modules`, `.next` ni las capturas) y adáptala. Lee `ref/03_frontend_v0.md` antes de tocarla.

## Qué se quita
- `lib/sim/scenario.ts`, `lib/sim/dispatcher.ts`, `lib/sim/context.ts` y `hooks/use-simulation.ts`: la simulación, los análisis precalculados y el reloj ya no viven en el navegador.
- `app/api/agent/route.ts` y las dependencias `ai`, `@ai-sdk/react` y `@vercel/analytics`: el chat va por el bus hacia nuestro agente; nada sale a la nube.

## Qué se añade
- **Cliente WebSocket** (`hooks/use-platform.ts`): conecta a `ws://127.0.0.1:8100/ws`, `hello` como `web`, se suscribe a `citadel.pub.evt.>`, mantiene en estado los eventos recibidos y el último `state`. Envía `control` (cargar escenario, play, pausa, paso, reinicio, velocidad, esperar al agente, modo interactivo, fallos) y publica `OperatorMessage`.
- `GET /api/plan` al cargar un escenario (ruta planificada); `GET /api/truth` (la verdad de la simulación en curso, hasta el instante actual) solo si se activa la capa «verdad».

## Vistas
- **Mapa x,y** (reutiliza `drone-map.tsx`): ojo, **y hacia el norte** (en v0 y crecía hacia abajo): invierte el eje al pintar. Ruta planificada (discontinua) con waypoints; estela del GPS (lo que dice el dron); puntos del radar (otro color); dron con su rumbo; resalte de la zona mientras hay una detección abierta. Interruptor **«Mostrar verdad»** (trayectoria real, para la demo; en la leyenda: «solo simulador, el agente no la ve»). Flecha de viento con el último `WindReported`.
- **Panel de capas** (casillas, junto a la leyenda del mapa; se recuerdan en `localStorage` con `try/catch`): ruta planificada, waypoints, estela del GPS, puntos del GPS, puntos del radar, verdad (apagada por defecto), viento, resalte de detecciones. Cada capa se pinta por separado para poder ocultarla.
- **Panel de fallos** («Inyectar fallo»): con un **interruptor «Modo interactivo»** (`control` → `interactive`, estado en `state.interactive`, apagado por defecto; **cada carga o reinicio de escenario lo apaga**, con su `InteractiveModeChanged`, así que hay que volver a encenderlo). Con el modo apagado, los controles de fallo están deshabilitados (la plataforma rechazaría el `fault` con un error, que la web muestra). Encendido: un interruptor **«Silenciar» (`mute`)** por fuente (GPS, radar, meteo, enlace, batería) y un botón **«Pérdida de GPS» (`loss`)** que solo existe para el GPS; envían `control` → `fault` con `{source, mode, active}`. Muestra los fallos en curso (de `state.active_faults`: fuente, tipo y origen «manual» o «programado») y marca en la barra de progreso y en el timeline los `FaultInjected`/`FaultCleared` y los `InteractiveModeChanged` (en la leyenda: «el agente no ve estos eventos, solo sus efectos»). Mientras una fuente está en `mute`, su capa se atenúa; en `loss` los puntos del GPS se pintan huecos (sin fix, posición estimada) y se ve cómo la verdad se separa de la ruta.
- **Controles** (`sim-controls.tsx`): selector de escenario, play/pausa, paso, reinicio, velocidad (0,5–16×) y los interruptores «Esperar al agente» y «Modo interactivo». Barra de progreso con marcas de detecciones y alertas.
- **Telemetría** (`telemetry-strip.tsx`): x, y, velocidad, rumbo, distancia GPS–radar, viento, enlace (`controller_id`), batería.
- **Timeline de eventos** (`event-timeline.tsx`): todos los eventos con filtros por fuente (ocultar GPS y radar por defecto).
- **Consola del agente** (`agent-console.tsx`), dos pestañas:
  - **Monitor:** detecciones del detector, actividad del agente («analizando det-0002…», con `AgentActivity`), alertas (`AnomalyDetected`: causa, severidad, confianza, resumen; desplegable con explicación, recomendación y evidencias), cierres (`AlertClosed`) y reconocimientos (`DetectionAcknowledged`: «sigue la alerta X», «sin alerta», o «sin diagnóstico» si `fallback`). Cada detección tiene respuesta; una cadena de alertas por `supersedes` es una sola alerta. Abajo, el chat con el monitor en streaming.
  - **Informe:** el `ReportGenerated` renderizado en Markdown y el chat con el agente de informe.
  - Distingue claramente quién habla: detector, monitor, informe y operador.

## Notas
- **Idioma (Fase 5): todos los textos de la interfaz están en inglés** (etiquetas, botones, leyendas, avisos, pestañas, nombres de causas, severidades y checks, preguntas sugeridas, errores) y las cifras salen con punto decimal (`toFixed`). `<html lang="en">`. Los textos del monitor y de los chats llegan ya en inglés del módulo de IA.
- Puerto 3000. Comprueba versiones de Node y pnpm en la Fase 0 (v0 declara `pnpm@12.3.4` en `package.json`); si no cuadran, usa las instaladas y anótalo.
- Mantén el aspecto de v0; no hace falta rediseñar.

## Estado (Fase 4)
- Arranque: `pnpm install` y `pnpm dev` (3000, solo `127.0.0.1`, sin telemetría de Next.js); `pnpm build` y `pnpm typecheck` para comprobarla. Las fuentes IBM Plex vienen de `@fontsource/*` (autoalojadas: nada se descarga del navegador).
- Código: `hooks/use-platform.ts` (WebSocket y API HTTP; los eventos llegan en ráfagas y se vuelcan al estado cada 100 ms), `lib/contracts.ts` (tipos del contrato, a mano), `lib/derive.ts` (de la lista de eventos saca estela, detecciones, cadenas de alertas, respuestas pendientes y chats) y `components/mission/`.
- El aviso «Waiting for the monitor: analysing det-XXXX…» sale cuando el último `SimulationPaused` es `waiting_agent` y el estado es `paused`; el id sale de la detección sin respuesta más antigua.
- Los ids `ops-` los calcula la web («máximo visto + 1»): con dos pestañas abiertas pueden repetirse y la plataforma rechazaría el mensaje. Una sola pestaña.
- `scripts/capture.mjs` (Playwright, Chromium en `~/.cache/ms-playwright`) conduce la web y saca capturas: `node scripts/capture.mjs demo|radar|gps <carpeta>` con plataforma, módulo de IA y web en marcha.
- `lib/clean-text.ts` (`stripFieldValues`, con pruebas: `pnpm test`): al mostrar la explicación, la recomendación, la razón de cierre y los reconocimientos del monitor, quita los paréntesis que solo contienen `campo=valor` o `campo: valor`. Es un parche de presentación: el evento, `eval.md` y el informe conservan el texto original, y no arregla frases falsas.
