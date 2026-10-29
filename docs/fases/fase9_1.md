# Fase 9.1 · Ajustes de la web

Escrito para: el equipo que revisa la fase (Carlos). Contrato **v0.12**. Solo web y, para el icono real en directo, lo mínimo de plataforma y contrato. `agent-assets/`, detector, guardrails, evaluación, escenarios y `runs/<escenario>/` sin cambios (`git status` limpio en ellos).

## Qué se cambió
1. **Rumbo conocido frente al real.** Sin cambio de datos: `title` en cada icono y en su entrada de la leyenda («Known position · GPS course over ground», «True position · nose heading»). Se quita el letrero «true position» del mapa (a petición). **Pendiente de contrato:** el `heading_deg` de `PositionUpdated` del GPS es en realidad un **rumbo sobre el suelo** (`bearing_deg(vel)` en `sensors.gps_payload`); el radar ya lo llama `course_deg`. No se renombra ahora. El de `/api/truth` es el rumbo del morro; la diferencia es el ángulo de deriva.
2. **Icono real independiente** de «Truth trail» (capa propia, apagada por defecto; clave `poc-layers-v2`, así que las capas guardadas se reinician una vez). La línea de puntos solo con los dos iconos visibles.
3. **Leyenda por grupos** (cuadros con título pequeño): Plan · Tracks · Points · Drone · Overlays (+ «Coordinates»). Una fila a 1920 px y dos a 1440 y 1280.
4. **Tamaños:** `scaledPx = clamp(base·√zoom, mín, máx)` en px de pantalla. Unidad (iconos, base, waypoints, puntos) 4,5 px (3,5–8); estela GPS 2 px (1,25–3); ruta, radar y verdad 1,5 px (1–2,5); resalte 5 px (3,5–8); letreros 11 px (10–13). La Fase 9 usaba 9 px fijos y trazos de 2–3 px; la 4, ≈ 4,5 px. Medido: ×0,5 → 3,5 px; ×1,1 → 4,8; ×2,5 → 7,2; ×8,5 y ×40 → 8 (máximo).
5. **Mapa más alto** (`clamp(420px, 60dvh, 900px)`: 646 px a 1080 de alto) y **asa vertical** entre la columna izquierda y la consola (arrastrar, flechas, doble clic = 420 px; mínimos 340 y 560 px; se recuerda). No complicó el layout de la Fase 9: la asa es un hijo absoluto de la consola y el grid sigue de dos columnas (`--console-w`). Medido: 420 → 680 → 340 px, y 490 px tras recargar.
6. **Rejilla «infinita»:** líneas en toda la vista (10–2500 m según el zoom; 250 m a zoom normal), sin recuadro. **La vista no se recoloca sola:** la base es la ruta planificada; solo «Reset view» (ruta + datos) o cargar otro escenario la cambian. «Coordinates» (apagada por defecto) y barra de escala siempre visible. Medido en `demo`: la vista antes del secuestro, a mitad y al final es idéntica.
7. **Icono real sin retraso** (contrato abajo). A 16×, sobre T+60…T+160 (antes del engaño del GPS), la distancia en pantalla entre el icono conocido y el real es de mediana 1,1 px, p90 3,1 px y máximo 4,8 px (a 4×: 3,0 / 4,3 / 5,3 px). Con el sondeo de 0,5 s de la Fase 9 el icono real iba hasta 8 s de simulación por detrás a 16×. Animación ≤ 100 ms.
8. **Zoom solo con botones y Ctrl (⌘) + rueda.** La rueda sola desplaza; aviso «Use Ctrl + wheel to zoom» la primera vez por carga (visible 1,5 s). Comprobado: sin Ctrl el zoom no cambia y el aviso sale solo la primera vez; con Ctrl 0,88 → 1,39.
9. **Timeline más alto** (opción «alto = alto de la columna»): en `lg` mide `100cqh` (la columna izquierda es un contenedor de tamaño). Al bajar del todo ocupa 1030 de 1031 px y se ven 29 filas (antes 3–4). Sin romper el final de página: `layout` sigue midiendo franja 0 px.
10. **Filtros del timeline:** Type y Topic con **All** y **None**; «None» es «solo los marcados» (lo que aparezca después también queda oculto: `KeyFilter {only, keys}`). Fuentes con **All**, **None** y **Default**; Default = todo menos **GPS y radar** (el `DEFAULTS` que ya había). Se lee también el formato guardado de la Fase 9.

## Contrato v0.12 (`contracts/eventos.md` §5)
- `truth_feed` (cliente → plataforma, `active: bool`): solo clientes `web`; otro tipo recibe `error` («only clients of type web can receive the truth»).
- `truth` (plataforma → cliente): `run_id`, `t`, `x`, `y`, `heading_deg` (morro), `course_deg`, `speed_mps` de la última muestra con `t` ≤ `sim_time`. **No es un evento:** sin sobre ni topic, fuera del bus y del timeline, ninguna tool lo ve. Solo a clientes `web` con el feed activo; cada 0,1 s de reloj, al activarlo y tras cada cambio de estado. **`state` no cambia** y sigue yendo a todos (comprobado en `Hub.broadcast_state`).
- Cambios: `ws.py` (`TruthFeed`, `TruthMessage`), esquemas `ws/*.json` regenerados, `Player.truth_now`, `Hub.broadcast_truth` y `_truth_ticker` en `app.py`. La web lo pide solo con «True position» activa y lo reenvía al reconectar. La traza «Truth trail» sigue con `/api/truth`.
- **Pruebas** (`platform/tests/test_api.py`): un `ai-module` suscrito a `citadel.>` recibe `error` al pedirlo y ningún `truth` aunque la web sí; sin pedirlo no llega; con `t` ≤ `sim_time`; `truth_feed` antes del `hello` falla; `load` empuja la muestra inicial.
- **Revisor de contratos:** sin incumplimientos (documento, Pydantic, esquemas, plataforma y web coherentes; el módulo de IA no puede recibirlo ni pedirlo). Avisos: (a) documentación de `platform/CLAUDE.md` y `web/CLAUDE.md` desfasada → corregida; (b) el tipo del cliente lo declara el propio cliente en `hello` (sin autenticación; ya era así con `control`), la garantía depende de que `ai-module-py` mande siempre `ai-module`; (c) `bus_client.messages()` valida con `ServerMessage`, que ahora incluye `truth`: no llega nunca, pero un descarte explícito sería defensa en profundidad. **No se hizo:** la prueba de aislamiento `test_agent_code_never_reads_labels_or_truth` prohíbe que el módulo de IA nombre «truth»; queda como pendiente decidir cómo (p. ej. descartar por `op`); (d) hueco de pruebas, cubierto con la prueba nueva.

## Cómo se ejecuta
`pnpm dev` / `pnpm build && pnpm start` en `web/`, plataforma y módulo de IA como siempre. Capturas: `node scripts/capture.mjs fase9_1|truthlag|compare <carpeta>`.

## Resultados
- `pnpm typecheck`, `pnpm test` (30 pruebas: escala de tamaños, paso de la rejilla, barra de escala, encuadre, ancho de la consola, filtros All/None/Default y «solo los marcados»), `pnpm build`: en verde. Python: `contracts` 130 (+1 omitida), `platform` 220 (+3), `ai-module-py` 359; `ruff` limpio. En una pasada intermedia `test_agent_code_never_reads_labels_or_truth` falló por un cambio mío en el módulo de IA (descrito arriba); revertido.
- **`demo` por línea de comandos** (`--speed 16 --wait-agent --evaluate`, perfil `actual`, `runs/demo/20261029-123137/`): ✅ 3/3 anomalías diagnosticadas · 0 falsas alarmas · 0 fallbacks · 0 esperas agotadas · 0 sin respuesta · 0 alertas abiertas al final · 2 frases que contradicen los checks (la Fase 9 tuvo 1; es una medición del LLM, no de este cambio). **Los 1063 eventos del mundo son idénticos a `runs/demo/events.jsonl`**; sin `tcl-` ni `truth` en el timeline; `agent-assets/`, `scenarios/` y `runs/<escenario>/` sin cambios en `git status`.
- Capturas en `results/capturas/fase9_1/` (1920×1080; `70_*` y `71_*` a 1440×900 y 1280×720): `00`/`01` (mapa alto y leyenda), `10` (viento, dos iconos), `20`–`25` (tamaños ×0,5 … ×40), `30`/`31` (rejilla sin y con coordenadas, escala), `32` (aviso de la rueda), `40`/`41` (secuestro a mitad y al final, misma vista), `50` (timeline al bajar), `51`–`54` (filtros), `60`/`61` (consola ancha y estrecha), `70`/`71`, `80_icono_real_*` (16× y 4×, `truthlag.json`), `comparacion/` (Fase 4 y Fase 9 al lado). Las vistas de la Fase 9 no se podían regenerar al mismo zoom: se comparan con las capturas que existen (03 ≈ ×3,2, 07 ≈ ×2,3) contra ×2,5 y ×1,7.
- No se repitió `nominal` con el receptor muerto desde la web en esta pasada (`deadgps`): solo se ajustó su script a las capas nuevas; sin cambios de comportamiento del simulador (220 pruebas de plataforma, con las combinaciones de `loss`+`mute`).
- Servicios: `serve.sh stop` hecho, puerto 8000 libre y `nvidia-smi` en **187 MiB** (por debajo de la referencia de 339 MiB; sin procesos de cómputo).

## Límites y pendientes
- **`heading_deg` del GPS** es un rumbo sobre el suelo (ver punto 1): renombrar en una versión futura del contrato.
- `truth_feed` no se autentica (el tipo de cliente lo declara el cliente).
- Descarte explícito de `truth` en el cliente del módulo de IA (ver revisor, c).
- Los tooltips son `title` nativos: no salen en las capturas (se verifican por el DOM, en `capture_log.json`).
- La leyenda ocupa dos filas por debajo de ~1500 px de ancho de columna.
- `setLiveTruth` se llama en cada mensaje (10/s) sin pasar por el volcado de 100 ms; sin efecto visible.

## Mensaje de commit propuesto
```
feat: phase 9.1 - web adjustments and live true position (contracts v0.12)

Web: grouped legend, independent true-position layer, smaller icons and strokes
that scale with the square root of the zoom, taller map and resizable console,
infinite grid with a view that does not move by itself, coordinates layer and
scale bar, Ctrl + wheel zoom with a one-time hint, full-height timeline and
All/None/Default filters.
Contracts v0.12: truth_feed / truth WebSocket messages (web clients only, outside
the bus) so the true-position icon is not delayed at 16x.
```
