# Fase 9.2 · Pulido de la web

Escrito para: el equipo que revisa la fase (Carlos). Solo web y una defensa en profundidad del cliente del bus del módulo de IA. **Contratos sin cambios** (`git status` limpio en `contracts/`), `agent-assets/`, detector, guardrails, evaluación, escenarios y `runs/<escenario>/` sin cambios (huella de `agent-assets` `da0582239a3a3c9a`, la de las ejecuciones anteriores). Sin dependencias nuevas.

## Qué se cambió

1. **Resalte de detecciones.** Un «tubo» magenta (`--highlight`, `oklch(0.58 0.25 328)`, lejos del naranja del GPS a 48°, del verde azulado del radar a 195° y del azul de la ruta a 262°) bajo las estelas y los puntos. Tres trazos sobre el tramo del GPS desde que se abrió la detección más antigua: borde opaco (ancho + 3 px), interior con el color de fondo del mapa (si no, el borde se vería a través del relleno y saldría una banda maciza) y relleno al 22 %. Ancho 12 px (12–16 con el zoom: `SIZES.highlight`), unas 4–10 veces la estela del GPS (1,25–3 px) en lugar de los 5 px de la 9.1. El icono conocido lleva un anillo del mismo color mientras hay una detección abierta; la leyenda usa la misma muestra.
2. **Telemetría que no se corta.** Celdas con el ancho de su contenido (`flex-wrap` + `flex-auto`, sin `truncate`) y `title` con el valor completo. Formato más corto: `3d · 14 sat` y `12.0 m/s · 245°`. De 1280 px de ancho en adelante cabe en una fila; a 1024 px (inicio de `lg`) pasa a dos filas sin cortar nada.
3. **«Follow the drone» suave.** Los dos iconos y la cámara se pintan a la frecuencia de la pantalla, sin pasar por el volcado de 100 ms ni por React (ver «Cómo funciona»).
4. **Lista blanca de `op` en el cliente del bus del módulo de IA** (`bus_client.py`): `_EXPECTED_OPS = {event, state, error}`; cualquier otro mensaje se descarta antes de validarlo, registrando solo su `op`, y se valida con un `TypeAdapter` que solo conoce esos tres mensajes. No nombra «truth» (`test_agent_code_never_reads_labels_or_truth` sigue en verde). Prueba: `test_unknown_ops_are_dropped_without_errors` (`op` desconocido, mensaje sin `op` y JSON que no es un objeto: se entrega solo el evento, sin excepción ni reconexión).
5. **Receptor muerto desde la web**: repetido, ver «Resultados».
6. **Carpeta de resultados.** `results/` tenía `docs/fases/`, `fases/` y `docs-fases/` (vacía). `fases/` no tenía nada que no estuviera en `docs/fases/` (`diff -rq`: iguales; el único extra, `quien_decide_que.md`, está en `docs/fases/`). Copiado `fase9_1.md` a `docs/fases/` y **borradas** `fases/` y `docs-fases/` (no hizo falta `_to_delete/`). La regla 13 del `CLAUDE.md` raíz dice ahora dónde va cada cosa (`docs/fases/` → `results/docs/fases/`, capturas en `results/capturas/faseN/`) y que no se crean otras carpetas para los informes.

## Cómo funciona el movimiento (punto 3)

- **Datos en directo** (`hooks/use-platform.ts`): un almacén `live` (`lib/motion.ts`) recibe, en cuanto llegan, las `PositionUpdated` del GPS, los mensajes `truth` y el reloj de simulación (un ancla por cada `state`). Ya no hay `setLiveTruth` a 10 Hz: el icono real no provoca renders de React.
- **Bucle `requestAnimationFrame`** (`drone-map.tsx`, `paint`): interpola y escribe en el DOM el `transform` de los dos iconos, de la línea que los une y del grupo del mundo. Esos atributos **no van en el JSX**, así el render de 100 ms no los pisa; un `useLayoutEffect` repite el dibujo tras cada render y asigna lo ya confirmado que lee el bucle (ver «Un fallo encontrado»).
- **Interpolación** (`Track.sampleAt`): entre las dos muestras que rodean el instante de pintado; **sin extrapolar** (tras la última se queda en la última). Los dos iconos usan **el mismo instante** (reloj − retraso). Un hueco de más de 1,5 s de simulación sin GPS, o un salto de más de 40 m + 40 m/s·dt (recuperación, engaño), no se anima: mantiene la anterior y salta. Si el tiempo retrocede (reinicio), se vacía. El rumbo se interpola por el camino corto.
- **Reloj** (`SimClock`): avanza con el reloj de pared a la velocidad de la simulación entre dos `state`, no avanza en pausa y nunca retrocede salvo reinicio; en marcha corrige solo el 15 % del error por mensaje (ver abajo).
- **Cámara de «seguir»**: el `viewBox` lo fija React en cada render; entre renders, el bucle desplaza el grupo del mundo (`translate`) lo que avanza la posición interpolada, y compensa los rótulos pegados al borde (coordenadas, «N ↑»). La rejilla se pinta con un margen (60 m + el tamaño de la vista).
- **Cambio respecto a lo propuesto en el plan.** (a) La cámara no escribe el `viewBox` en cada fotograma, sino un `transform` del grupo del mundo: el atributo tampoco lo controla React, pero así el render de 100 ms no descoloca rejilla ni coordenadas. (b) **Retraso**: una muestra del GPS (1 s de simulación) a 0,5×–4×, pero a 16× son 2,4 s de simulación (`max(1 s, 0,15 s de reloj × velocidad)` = 150 ms de reloj): los eventos llegan en ráfagas cada 100 ms y, con una sola muestra de retraso, el icono se quedaría sin la siguiente posición entre ráfagas. (c) **Sin suavizado de la cámara**: el icono queda fijo en el centro de la pantalla y la variación que queda entre fotogramas es el ruido real de las posiciones del GPS (cada tramo entre muestras tiene su velocidad); suavizarla solo haría bailar al icono respecto a la pantalla.
- **Pausa**: el icono se queda donde estaba (como mucho una muestra por detrás de la última posición, 2,4 s de simulación a 16×) y sigue desde ahí al reanudar, sin saltos atrás.

## Orden de pintado del SVG (de abajo arriba)

1. **Rejilla**: la referencia más tenue; todo va encima.
2. **Resalte (tubo)**: marca una zona, no es un dato; bajo todos los datos para no taparlos, y su borde sobresale por los lados de las estelas.
3. **Truth trail**: referencia de la demo, bajo lo medido.
4. **Ruta planificada**: referencia discontinua, bajo las estelas que se comparan con ella.
5. **Puntos del radar** y 6. **estela del radar**: fuente secundaria, bajo el GPS.
7. **Estela del GPS**: la fuente principal, sobre el radar.
8. **Puntos del GPS**: sobre su propia estela, para que se vean.
9. **Waypoints y letreros**: sobre las estelas para que los ids se lean.
10. **Línea conocido–real**: bajo los iconos que une.
11. **Icono real** (contorno discontinuo): bajo el conocido.
12. **Icono conocido**, con el anillo del resalte y «last fix…»: el protagonista.
13. **Coordenadas y «N ↑»**: texto con halo pegado al borde, encima de todo (antes estaban bajo los datos).

Fuera del SVG, en HTML: barra de escala, viento, botones y aviso de la rueda.

## Un fallo encontrado al medir (y corregido)

La primera medida «después» mostraba el movimiento sin saltos a 10 Hz de los commits en general, pero con restos: a ×20 y 4×, los fotogramas con un render de React se movían un 30 % más que el resto y había paradas de 2–3 fotogramas seguidas de un salto. Dos causas:
1. El bucle leía la vista (`view`) asignada **durante el render**, pero el `viewBox` del DOM cambia al hacer **commit**: un fotograma entre las dos cosas daba un salto de cámara. Ahora lee un valor asignado en el `useLayoutEffect` (lo ya confirmado).
2. El reloj se reanclaba del todo con cada `state` (cada 0,5 s) y la latencia del mensaje varía decenas de ms: el icono se frenaba y luego se ponía al día. Ahora corrige el 15 % del error (`SimClock.GAIN`); hay una prueba (`la latencia variable de los state…`) que falla con reanclaje total y pasa con la corrección gradual.

Tras los dos arreglos, el exceso en fotogramas con commit es del 3 % a ×20 y 4× (8,8 frente a 8,6 px).

## Medida de suavidad

`node scripts/capture.mjs smooth <carpeta>`: `wind` con «seguir» activado y 10 s de muestreo por fotograma (`requestAnimationFrame`, Chromium sin cabeza, 60 fps). Se mide en pantalla la posición de la base (fija en el mundo) y del icono conocido: cámara = −Δ(base); la medida no depende de cómo se mueva la cámara, y se aplicó igual al código de la 9.1 (compilado aparte desde `HEAD`, sin tocar git) y al nuevo. Desplazamiento de la cámara por fotograma (px); el icono respecto al mapa da lo mismo (con «seguir» la cámara sigue al icono).

| Zoom · velocidad | Antes: mediana / p95 / máx. · quietos | Después: mediana / p95 / máx. · quietos |
|---|---|---|
| ×8 · 1× | 0 / 0 / 41,7 · 98 % | 0,48 / 0,70 / 4,2 · 9,5 % |
| ×8 · 4× | 0 / 33,9 / 54,3 · 93 % | 2,53 / 3,52 / 9,1 · 2,5 % |
| ×8 · 16× | 0 / 75,7 / 93,7 · 83 % | 9,80 / 13,1 / 15,3 · 0 % |
| ×20 · 1× | 0 / 0 / 140,6 · 98 % | 1,62 / 2,35 / 9,6 · 6,0 % |
| ×20 · 4× | 0 / 114,3 / 183,3 · 93 % | 8,58 / 11,7 / 30,4 · 2,5 % |
| ×20 · 16× | 0 / 259,2 / 317,6 · 83 % | 33,3 / 43,7 / 51,0 · 0 % |

Antes el icono y la cámara se quedaban quietos 8 de cada 10 fotogramas (y 98 % a 1×) y saltaban hasta 318 px de golpe; ahora se mueven en todos los fotogramas, con p95 ≈ 1,3–1,5× la mediana. Los «quietos» que quedan a 1× son fotogramas en que el icono avanza menos de 0,05 px. La variación entre fotogramas que queda (cv 0,27–0,34 a 4× y 16×) es el ruido de las posiciones del GPS. Datos en `results/capturas/fase9_2/smooth_antes/` y `smooth_despues/` (`smooth.json`).

**«Seguir» en los casos límite** (`followcheck.json`, a ×8, 4×): en pausa 98 % de fotogramas quietos (máx. 2,3 px); reanudar sin saltos atrás (máx. 6,5 px frente a 8,8 en marcha); con el GPS callado 96 % quietos (máx. 3,0 px); al volver el GPS, un solo fotograma de salto (el hueco no se anima); tras reiniciar, otro. (Una primera pasada con la espera del agente activa y sin monitor dejó pausadas las fases del GPS callado y no valió; se repitió con el `setup` corregido.) Al cargar otro escenario o reiniciar, «seguir» y el zoom se restablecen (cambia el plan), como antes de esta fase.

## Resultados

- **Pruebas:** `pnpm typecheck`, `pnpm test` (45: las 30 de la 9.1, 14 de `lib/motion.ts` —reparto en el tiempo a 0,5×–16×, sin extrapolar, huecos y saltos, pausa, reinicio, rumbo, reloj— y una de la latencia variable), `pnpm build`: en verde. Python: `contracts` 130 (+1 omitida), `platform` 220, `ai-module-py` 360 (+1 de la lista blanca); `ruff` limpio. Tras el último ajuste del registro del cliente del bus se repitieron las pruebas del cliente del bus y de aislamiento (37).
- **Resalte** (`capturas/fase9_2/highlight/`): `wind` y `demo`, solo estela GPS, solo puntos GPS, solo estela radar y todas, a ×0,5, ×1 y ×4 (24 capturas). Con borde y relleno se distingue desde lejos con cualquier combinación. Las capturas se toman a T+140 s, con unas 35 muestras de detección abiertas.
- **Telemetría** (`capturas/fase9_2/telemetry/`, `telemetry.json`): 1024×768, 1280×800, 1366×768, 1440×900, 1536×960 y 1920×1080; por el DOM, `scrollWidth ≤ clientWidth` en todas las celdas. 1 fila desde 1280 px, 2 filas a 1024.
- **Pruebas completas desde la web** (`capturas/fase9_2/e2e/<escenario>_<velocidad>x/`, 1536×960, perfil `actual`, «esperar al agente», módulo de IA completo): `wind` y `demo` a 1×, 4× y 16×. Las seis: 0 errores de página, 0 cortes en la telemetría, resalte visible mientras hay detección abierta, «seguir» a ×8 sin saltos (máx. 3,7–15,5 px por fotograma), la simulación llega a «Finished» y las cinco con la espera del informe lo generan (`demo`: 4 detecciones, 4 alertas, 2 reconocimientos; `wind`: 1, 1, 0). En `wind` a 16× el contador del informe se leyó antes de que llegara (el script se corrigió después: espera hasta 3 minutos); no es un fallo del informe.
- **Receptor muerto desde la web** (`capturas/fase9_2/deadgps/`): `nominal` en modo interactivo, versión final, en los dos órdenes (A: silencio y luego pérdida, se quita primero el silencio y luego la pérdida; B: al revés). Orden A: `FaultInjected mute` T+41, `SOURCE_SILENT` T+45, `loss` T+47, se quita el silencio T+61 y llega `GPS_DEGRADED` T+62, se quita la pérdida T+77. Orden B: `loss` T+131 (`GPS_DEGRADED`), `mute` T+137 (`SOURCE_SILENT`), se quita la pérdida T+151 y luego el silencio T+172. El icono conocido se queda quieto en el último fix con «last fix N s ago» y la verdad sigue su camino. Esta pasada tenía `--detector-only`, por eso el monitor muestra «analysing… (queued)»: nadie responde.
- **`demo` por línea de comandos** (`--speed 16 --wait-agent --evaluate`, perfil `actual`, `runs/demo/20261029-142200/`): ✅ 3/3 anomalías diagnosticadas · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 sin respuesta · 0 alertas abiertas al final · 2 frases que contradicen los checks. **Mismos resultados que en la 9.1.** Los **1063 eventos del mundo son idénticos** a `runs/demo/events.jsonl` (ninguno extra, mismo contenido salvo `seq` e `ingestion_time`).
- **Revisor de contratos:** sin incumplimientos. Sin cambios de contrato sin reflejar; el módulo de IA sigue sin poder pedir ni recibir `truth` (la plataforma lo rechaza y el cliente lo descarta por `op`); la web pide `truth_feed` solo con «True position» activa. Aviso aplicado: el descarte registra solo el `op`. Avisos no aplicados (inocuos): un `else if` en línea nueva en `use-platform.ts` y un `truth_feed {active:false}` al montar.
- **Copias y instantáneas:** `docs/fases/` en `results/docs/fases/` (`diff -rq` sin diferencias salvo `quien_decide_que.md`, que solo está allí), capturas en `results/capturas/fase9_2/`, `eval.md` e `informe.md` de `runs/demo/20261029-142200/` en `results/runs/`, e instantáneas `snapshots/fase9_2/` (361 ficheros) y `snapshots-limpias/fase9_2/` (324 ficheros). Los dos `grep` de la regla 15 sobre la limpia: **sin hallazgos**, nada que corregir.
- **Servicios:** `serve.sh stop` hecho, puertos 8000, 8100 y 3000 libres y `nvidia-smi` en **0 MiB** (sin procesos de cómputo).

## Quién decide qué

`docs/quien_decide_que.md` contrastado con el código: sin cambios en lo que decide cada pieza; solo se añadió una línea (el cliente del bus del módulo de IA descarta por `op` lo que no espera).

## Cómo se ejecuta

`pnpm dev` / `pnpm build && pnpm start` en `web/`, plataforma y módulo de IA como siempre. Capturas: `node scripts/capture.mjs highlight|telemetry|smooth|followcheck|fase9_2|deadgps <carpeta>` (cabecera del script). `smooth` admite `SMOOTH_ONLY=zoom:velocidad` y `SMOOTH_DUMP=1` (vuelca los fotogramas). Un detalle del script que me costó una pasada: «Wait for the agent» se conserva entre cargas y `setup` solo sabía encenderlo; ahora fija el valor pedido (con el módulo en `--detector-only`, una ejecución con la espera encendida se queda esperando 90 s por detección).

## Límites y pendientes

- La medida se hizo en Chromium sin cabeza a 60 fps; en una pantalla de otra frecuencia los px por fotograma cambian (la velocidad en pantalla es la misma).
- A 16× el retraso del icono conocido es de 2,4 s de simulación (150 ms de reloj), no de una muestra.
- La variación entre fotogramas que queda es el ruido de las posiciones del GPS, que la interpolación reproduce con fidelidad.
- Con «seguir» y un zoom muy alto (×40) a 16×, la cámara se mueve más que la vista entre dos renders; el margen de la rejilla (60 m + tamaño de la vista) cubre ese caso, pero solo se probó hasta ×20.
- Siguen pendientes de la 9.1: renombrar `heading_deg` del GPS (es un rumbo sobre el suelo) en una versión futura del contrato, y `truth_feed` sin autenticar (el tipo de cliente lo declara el cliente).

## Mensaje de commit propuesto
```
feat: phase 9.2 - web polish (detection highlight, telemetry, smooth follow)

Web: magenta "tube" highlight with border and fill under the trails, telemetry
cells sized by content with full values in titles, and icons and follow camera
rendered at display rate (requestAnimationFrame) by interpolating between the
last two received positions, without extrapolating. The paint loop reads only
committed view values and the simulation clock corrects gradually, so frames
neither jump nor stall. Documented paint order.
AI module: the bus client drops any WebSocket message whose op is not in its
whitelist (event, state, error).
No contract changes.
```
