# La interfaz que generó v0 (revisada el 16/10/2026)

Origen: `C:\Proyectos\interfaz-de-simulacion-dron` (`/mnt/c/Proyectos/interfaz-de-simulacion-dron` desde WSL). Next.js 16.4, React 19, Tailwind 4, shadcn, pnpm. Dos capturas de cómo se ve, en esa carpeta.

## Qué hace hoy (y por qué no sirve tal cual)
- **Todo vive en el navegador.** `lib/sim/scenario.ts` genera un escenario fijo (semilla 2611): waypoints en un plano 1000×600 con **y hacia abajo**, ruta real = la planificada recorrida a ~12 m/s con un paseo aleatorio lateral de ±4 m y una «ráfaga» que es una curva de 70 m dibujada a mano en un tramo. No hay controlador.
- **El «agente» del dispatcher no es un LLM.** `lib/sim/dispatcher.ts` agrupa eventos en lotes (10 posiciones o cualquier evento no posicional) y les asigna un análisis escrito con reglas y textos fijos, **calculado antes de reproducir**. Falla donde más se nota: tras desviarse ~70 m dice «WP3 alcanzado. Transición al siguiente tramo sin incidencias», porque ese lote no lleva posiciones.
- El único LLM es el chat del operador (`app/api/agent/route.ts`, `claude-haiku-5.5` por el AI Gateway de Vercel): **no se puede usar** (sale a la nube) y en las capturas sale «Agente LLM: error» porque no hay clave.
- El reloj es un `requestAnimationFrame` en `hooks/use-simulation.ts`; hay paso adelante y reinicio, no paso atrás.

## Qué se reutiliza
- `components/mission/`: `mission-console.tsx` (composición), `mission-header.tsx`, `drone-map.tsx` (SVG del plano, ruta discontinua, estela, waypoints, zona), `sim-controls.tsx` (botones y velocidades), `telemetry-strip.tsx`, `event-timeline.tsx` (con filtro para ocultar posiciones), `agent-console.tsx` (pestañas Todo/Dispatcher/Operador, burbujas por quién habla, sugerencias de preguntas).
- `lib/sim/geometry.ts` (distancia a la ruta, rumbo, formato T+mm:ss) y `lib/sim/event-meta.ts` (colores y etiquetas por tipo de evento): adaptarlos a los tipos de `contracts/eventos.md`.
- El aspecto general (cabecera con estado, mapa grande, controles debajo, consola a la derecha) está bien para la demo.
