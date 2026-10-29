'use client'

import { LocateFixed, Maximize, Minus, Navigation, Plus } from 'lucide-react'
import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { ActiveFault, PlanFile, TruthFile } from '@/lib/contracts'
import type { Derived } from '@/lib/derive'
import {
  clampZoom,
  fitScale,
  fixAge,
  frameCamera,
  gridStep,
  HOME,
  padRect,
  panBy,
  rectOf,
  scaleBar,
  scaledPx,
  segmentTrail,
  SIZES,
  unionRect,
  visibleRect,
  zoomAt,
  type Camera,
  type Rect,
} from '@/lib/map-view'
import { renderTime, type Live } from '@/lib/motion'
import { cn } from '@/lib/utils'
import type { Layers } from './layers-panel'

type DroneMapProps = {
  plan: PlanFile | null
  data: Derived
  /** Traza de la verdad (`/api/truth`); solo con la capa «Truth trail». */
  truth: TruthFile | null
  /** Posiciones en directo (GPS y mensajes `truth`) y reloj de simulación: las lee el bucle de dibujo. */
  live: Live
  layers: Layers
  faults: ActiveFault[]
  running: boolean
  speed: number
  /** Instante actual de la simulación (para la antigüedad del último fix). */
  simTime: number
}

const RADAR = 'oklch(0.55 0.12 195)'
const GPS_GAP_S = 1.5 // más de 1,5 periodos sin posición del GPS = hueco
const RADAR_GAP_S = 3
const ZOOM_STEP = 1.5
const HINT_MS = 1500
const HIGHLIGHT = 'var(--highlight)'
const WORLD_MARGIN_M = 60 // la rejilla se pinta más allá de la vista: la cámara de «seguir» se mueve entre dos renders

/** Tamaño del contenedor, medido con `ResizeObserver`. */
function useSize(ref: React.RefObject<HTMLDivElement | null>) {
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight })
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [ref])
  return size
}

const points = (pts: { x: number; y: number }[]) => pts.map((p) => `${p.x},${-p.y}`).join(' ')

/**
 * Mapa x,y con **y hacia el norte** (en el SVG se pinta `-y`). Cada capa se pinta por separado
 * para poder ocultarla. Una fuente en `mute` atenúa su capa y deja el icono en la última
 * posición con su antigüedad; en `loss` los puntos del GPS salen huecos (sin fix, posición
 * estimada). El icono del dron es la **posición conocida** (la última del GPS, rumbo sobre el
 * suelo); con su capa activa, otro icono (contorno) marca la **posición real** (rumbo del morro),
 * que llega en directo por el WebSocket.
 *
 * Movimiento: los iconos y la cámara de «seguir» **no pasan por React**. Un bucle
 * `requestAnimationFrame` interpola entre las dos últimas posiciones recibidas (`lib/motion.ts`) y
 * escribe directamente en el DOM (`transform` de los iconos, de la línea que los une y del grupo
 * del mundo): esos atributos no van en el JSX, así el render de cada 100 ms no los pisa. La
 * cámara de «seguir» no toca el `viewBox` (lo fija React): desplaza el grupo del mundo la
 * diferencia entre la posición interpolada y el centro de la última vista.
 *
 * Orden de pintado, de abajo arriba: rejilla · resalte (tubo) · verdad · ruta · puntos y estela del
 * radar · estela y puntos del GPS · waypoints · línea conocido–real · icono real · icono conocido ·
 * coordenadas y «N ↑».
 *
 * Vista: la rejilla cubre toda la vista a cualquier zoom y la vista **no se recoloca sola**: la
 * vista base es la ruta planificada; solo «reset view» (ruta + datos) o cargar otro escenario la
 * cambian. Cámara: Ctrl + rueda = zoom hacia el cursor (la rueda sola desplaza la página),
 * arrastrar = paneo, botones + / − / restablecer / centrar y «seguir al dron». Los tamaños crecen
 * con la raíz del zoom, entre un mínimo y un máximo en píxeles (`SIZES`).
 */
export const DroneMap = memo(function DroneMap({ plan, data, truth, live, layers, faults, running, simTime }: DroneMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const size = useSize(containerRef)
  const [cam, setCam] = useState<Camera>(HOME)
  const [follow, setFollow] = useState(false)
  const [hint, setHint] = useState(false)
  const hintShown = useRef(false)

  // Vista base: la ruta planificada; no crece con los datos.
  const base: Rect = useMemo(() => {
    const route = plan ? rectOf([...plan.waypoints, ...plan.trajectory]) : rectOf([{ x: 0, y: 0 }])
    return padRect(route, Math.max(route.w, route.h, 200) * 0.1)
  }, [plan])
  // Otro escenario: vuelve a la vista de su ruta.
  useEffect(() => {
    setCam(HOME)
    setFollow(false)
  }, [plan])

  // Lo visto (solo para no perderse al hacer paneo y para «reset view»).
  const dataRect = useMemo(() => rectOf([...data.gps, ...data.radar, ...(truth?.trajectory ?? [])]), [data.gps, data.radar, truth])
  const seen = useMemo(() => unionRect(base, dataRect), [base, dataRect])
  const limit = useMemo(() => padRect(seen, Math.max(seen.w, seen.h) * 0.5), [seen])

  const muted = (s: string) => faults.some((f) => f.source === s && f.mode === 'mute')
  const drone = data.gps[data.gps.length - 1] ?? null

  // Cámara efectiva: con «seguir», el centro es la posición interpolada del icono conocido (no la real).
  const followPos = follow ? (live.gps.sampleAt(renderTime(live, performance.now())) ?? (drone ? { x: drone.x, y: drone.y } : null)) : null
  const effective: Camera = followPos ? { zoom: cam.zoom, center: { x: followPos.x, y: -followPos.y } } : cam
  const view = visibleRect(base, effective, size.w, size.h)
  const ppu = size.w > 0 && size.h > 0 ? fitScale(base, size.w, size.h) * effective.zoom : 0 // px por unidad SVG (= m)
  const px = (v: number) => (ppu > 0 ? v / ppu : v) // píxeles de pantalla → unidades SVG
  const zoom = effective.zoom
  const u = px(scaledPx(SIZES.unit, zoom)) // unidad de dibujo: iconos, base, waypoints y puntos
  const labelSize = px(scaledPx(SIZES.label, zoom))
  const gpsW = scaledPx(SIZES.gpsTrail, zoom)
  const lineW = scaledPx(SIZES.line, zoom)
  const highlightW = scaledPx(SIZES.highlight, zoom)
  const haloPx = 3 // borde del resalte, en px
  const step = gridStep(Math.max(view.w, view.h))
  const viewBox = `${view.x} ${view.y} ${view.w} ${view.h}`
  const bar = scaleBar(ppu)

  // El último estado, para los manejadores nativos (rueda y arrastre) y el bucle de dibujo.
  const latest = useRef({ limit, view, effective, ppu, follow })
  latest.current = { limit, view, effective, ppu, follow }
  // Lo que lee el bucle de dibujo: solo lo ya **confirmado** en el DOM (se asigna en el `useLayoutEffect`).
  // Si leyera `view` del render, un fotograma entre el render y el commit mezclaría la vista nueva con el
  // `viewBox` viejo y la cámara daría un salto.
  const committed = useRef({ view, follow, drone, u, showTrue: layers.truthDrone, showKnown: layers.drone })

  // Elementos que escribe el bucle de dibujo (sin atributos equivalentes en el JSX).
  const worldRef = useRef<SVGGElement>(null)
  const xLabelsRef = useRef<SVGGElement>(null)
  const yLabelsRef = useRef<SVGGElement>(null)
  const northRef = useRef<SVGGElement>(null)
  const knownRef = useRef<SVGGElement>(null)
  const knownRotRef = useRef<SVGGElement>(null)
  const trueRef = useRef<SVGGElement>(null)
  const trueRotRef = useRef<SVGGElement>(null)
  const linkRef = useRef<SVGLineElement>(null)

  /** Un fotograma: posiciones interpoladas de los dos iconos (mismo instante) y desplazamiento de la cámara. */
  const paint = useRef(() => {})
  paint.current = () => {
    const { view, follow, drone, u, showTrue, showKnown } = committed.current
    const t = renderTime(live, performance.now())
    const known = live.gps.sampleAt(t) ?? (drone ? { x: drone.x, y: drone.y, heading: drone.heading } : null)
    const real = showTrue ? live.truth.sampleAt(t) : null
    if (knownRef.current && known) {
      knownRef.current.setAttribute('transform', `translate(${known.x} ${-known.y})`)
      knownRotRef.current?.setAttribute('transform', `rotate(${known.heading})`)
    }
    if (trueRef.current) {
      trueRef.current.setAttribute('visibility', real ? 'visible' : 'hidden')
      if (real) {
        trueRef.current.setAttribute('transform', `translate(${real.x} ${-real.y})`)
        trueRotRef.current?.setAttribute('transform', `rotate(${real.heading})`)
      }
    }
    if (linkRef.current) {
      const apart = known && real && showKnown && Math.hypot(known.x - real.x, known.y - real.y) > u * 2
      linkRef.current.setAttribute('visibility', apart ? 'visible' : 'hidden')
      if (apart && known && real) {
        linkRef.current.setAttribute('x1', String(known.x))
        linkRef.current.setAttribute('y1', String(-known.y))
        linkRef.current.setAttribute('x2', String(real.x))
        linkRef.current.setAttribute('y2', String(-real.y))
      }
    }
    // Cámara de «seguir»: el viewBox es el del último render; el mundo se desplaza lo que ha avanzado el dron.
    const dx = follow && known ? known.x - (view.x + view.w / 2) : 0
    const dy = follow && known ? -known.y - (view.y + view.h / 2) : 0
    worldRef.current?.setAttribute('transform', `translate(${-dx} ${-dy})`)
    // Los rótulos pegados al borde de la pantalla compensan ese desplazamiento.
    xLabelsRef.current?.setAttribute('transform', `translate(0 ${dy})`)
    yLabelsRef.current?.setAttribute('transform', `translate(${dx} 0)`)
    northRef.current?.setAttribute('transform', `translate(${dx} ${dy})`)
  }
  // Tras cada render, antes de pintar en pantalla: lo que se acaba de montar queda ya en su sitio.
  const commits = useRef(0)
  useLayoutEffect(() => {
    committed.current = { view, follow, drone, u, showTrue: layers.truthDrone, showKnown: layers.drone }
    paint.current()
    if (containerRef.current) containerRef.current.dataset.commit = String(++commits.current)
  })
  useEffect(() => {
    let id = 0
    const loop = () => {
      paint.current()
      id = requestAnimationFrame(loop)
    }
    id = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(id)
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    let timer: number | undefined
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) {
        // La rueda sola desplaza la página; se avisa una vez de cómo hacer zoom.
        if (!hintShown.current) {
          hintShown.current = true
          setHint(true)
          timer = window.setTimeout(() => setHint(false), HINT_MS)
        }
        return
      }
      e.preventDefault()
      const { limit, view, effective, ppu, follow } = latest.current
      if (ppu <= 0) return
      const factor = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 16 : 1) * 0.0015)
      const rect = el.getBoundingClientRect()
      const at = follow ? undefined : { x: view.x + (e.clientX - rect.left) / ppu, y: view.y + (e.clientY - rect.top) / ppu }
      setCam(zoomAt(limit, effective, view, factor, at))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => {
      el.removeEventListener('wheel', onWheel)
      window.clearTimeout(timer)
    }
  }, [])

  const drag = useRef<{ x: number; y: number; cam: Camera; view: Rect; moved: boolean } | null>(null)
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    const { effective, view } = latest.current
    drag.current = { x: e.clientX, y: e.clientY, cam: effective, view, moved: false }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || latest.current.ppu <= 0) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    if (!d.moved && Math.hypot(dx, dy) < 4) return
    d.moved = true
    setFollow(false)
    setCam(panBy(latest.current.limit, d.cam, d.view, -dx / latest.current.ppu, -dy / latest.current.ppu))
  }
  const endDrag = () => {
    drag.current = null
  }

  const zoomBy = (factor: number) => setCam(zoomAt(limit, effective, view, factor))
  // «Reset view»: encuadra la ruta y todo lo visto hasta ahora.
  const reset = () => {
    setCam(frameCamera(base, padRect(seen, Math.max(seen.w, seen.h) * 0.05), size.w, size.h))
    setFollow(false)
  }
  const center = () => {
    if (!drone) return
    setCam({ zoom: clampZoom(cam.zoom), center: { x: drone.x, y: -drone.y } })
    setFollow(false)
  }

  // Rejilla «infinita»: líneas en toda la vista y un margen (x del mundo = x del SVG; y del mundo = -y del SVG).
  const grid = useMemo(() => {
    const m = WORLD_MARGIN_M + Math.max(view.w, view.h)
    const x0 = view.x - m
    const x1 = view.x + view.w + m
    const y0 = view.y - m
    const y1 = view.y + view.h + m
    const xs: number[] = []
    const ys: number[] = []
    for (let x = Math.ceil(x0 / step) * step; x <= x1; x += step) xs.push(x)
    for (let y = Math.ceil(-y1 / step) * step; y <= -y0; y += step) ys.push(y)
    return { xs, ys, x0, x1, y0, y1 }
  }, [step, view.x, view.y, view.w, view.h])

  const planned = plan?.waypoints.map((w) => `${w.x},${-w.y}`).join(' ') ?? ''
  const gpsSegments = useMemo(() => segmentTrail(data.gps, GPS_GAP_S, (p) => (p.fix === 'none' ? 'none' : 'fix')), [data.gps])
  const radarSegments = useMemo(() => segmentTrail(data.radar, RADAR_GAP_S), [data.radar])
  const truthLine = useMemo(() => (truth ? points(truth.trajectory) : ''), [truth])
  const since = data.openDetections.length ? Math.min(...data.openDetections.map((d) => d.since)) : null
  const highlight = useMemo(() => (since === null ? '' : points(data.gps.filter((p) => p.t >= since))), [data.gps, since])

  // Los puntos pintados se limitan para no saturar el SVG a 16×.
  const gpsDots = useMemo(() => data.gps.slice(-1500), [data.gps])
  const radarDots = useMemo(() => data.radar.slice(-800), [data.radar])

  const wind = data.wind?.payload
  const windTo = wind ? (wind.from_deg + 180) % 360 : 0

  const halo = { stroke: 'var(--card)', strokeWidth: px(3), paintOrder: 'stroke' } as const
  const edge = px(26) // las coordenadas no se pintan pegadas a una esquina

  const age = drone ? fixAge(simTime, drone.t) : 0
  const dim = muted('gps')
  const hollow = drone?.fix === 'none'

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full cursor-grab touch-none select-none active:cursor-grabbing"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      data-testid="drone-map"
      data-zoom={effective.zoom.toFixed(2)}
      data-follow={follow}
      data-view={`${view.x.toFixed(0)},${view.y.toFixed(0)},${view.w.toFixed(0)},${view.h.toFixed(0)}`}
      data-unit-px={scaledPx(SIZES.unit, zoom).toFixed(2)}
    >
      <svg
        viewBox={viewBox}
        className="h-full w-full"
        role="img"
        aria-label={drone ? `x,y map (y towards the north). Drone at x ${drone.x.toFixed(0)}, y ${drone.y.toFixed(0)}.` : 'x,y map with the planned route.'}
      >
        <g ref={worldRef}>
          {/* 1 · Rejilla: la referencia más tenue; todo va encima. */}
          <g className="stroke-grid" data-testid="grid" data-step={step}>
            {grid.xs.map((x) => (
              <line key={`gx${x}`} x1={x} y1={grid.y0} x2={x} y2={grid.y1} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            ))}
            {grid.ys.map((y) => (
              <line key={`gy${y}`} x1={grid.x0} y1={-y} x2={grid.x1} y2={-y} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            ))}
          </g>

          {/* 2 · Resalte de la detección («tubo»): marca una zona, no es un dato; va bajo todos los datos para no
              taparlos y su borde sobresale por los lados de las estelas. Borde opaco, interior con el fondo del
              mapa (para que el borde no se vea a través del relleno) y relleno translúcido. */}
          {layers.highlight && highlight && (
            <g data-testid="highlight" fill="none" strokeLinejoin="round" strokeLinecap="round">
              <polyline points={highlight} stroke={HIGHLIGHT} strokeWidth={highlightW + haloPx} vectorEffect="non-scaling-stroke" />
              <polyline points={highlight} stroke="var(--card)" strokeWidth={highlightW} vectorEffect="non-scaling-stroke" />
              <polyline points={highlight} stroke={HIGHLIGHT} strokeOpacity={0.22} strokeWidth={highlightW} vectorEffect="non-scaling-stroke" />
            </g>
          )}

          {/* 3 · Verdad: referencia de la demo, bajo los datos medidos. */}
          {layers.truth && truth && truth.trajectory.length > 1 && (
            <polyline points={truthLine} fill="none" className="stroke-foreground/70" strokeWidth={lineW} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          )}

          {/* 4 · Ruta planificada: referencia discontinua, bajo las estelas que se comparan con ella. */}
          {layers.plan && plan && (
            <polyline points={planned} fill="none" className="stroke-primary" strokeWidth={lineW} strokeDasharray="7 5" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          )}

          {/* 5 · Puntos del radar y 6 · su estela: fuente secundaria, bajo el GPS. */}
          {layers.radarPoints && (
            <g style={{ opacity: muted('radar') ? 0.25 : 1 }} fill={RADAR}>
              {radarDots.map((p, i) => (
                <circle key={i} cx={p.x} cy={-p.y} r={u * 0.45} opacity={0.75} />
              ))}
            </g>
          )}
          {layers.radarTrail && (
            <g style={{ opacity: muted('radar') ? 0.3 : 1 }} data-testid="radar-trail">
              {radarSegments.map((s, i) =>
                s.points.length > 1 ? (
                  <polyline key={i} points={points(s.points)} fill="none" stroke={RADAR} strokeWidth={lineW} strokeOpacity={0.85} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
                ) : null,
              )}
            </g>
          )}

          {/* 7 · Estela del GPS (la fuente principal, sobre el radar) y 8 · sus puntos, sobre su propia estela. */}
          {layers.gpsTrail && (
            <g style={{ opacity: muted('gps') ? 0.3 : 1 }} data-testid="gps-trail">
              {gpsSegments.map((s, i) =>
                s.points.length > 1 ? (
                  <polyline
                    key={i}
                    points={points(s.points)}
                    fill="none"
                    className="stroke-accent"
                    strokeWidth={gpsW}
                    strokeDasharray={s.key === 'none' ? '3 5' : undefined}
                    vectorEffect="non-scaling-stroke"
                    strokeLinejoin="round"
                    strokeLinecap={s.key === 'none' ? 'butt' : 'round'}
                  />
                ) : null,
              )}
            </g>
          )}
          {layers.gpsPoints && (
            <g style={{ opacity: muted('gps') ? 0.25 : 1 }}>
              {gpsDots.map((p, i) =>
                p.fix === 'none' ? (
                  <circle key={i} cx={p.x} cy={-p.y} r={u * 0.5} fill="none" className="stroke-accent" strokeWidth={1.25} vectorEffect="non-scaling-stroke" />
                ) : (
                  <circle key={i} cx={p.x} cy={-p.y} r={u * 0.4} className="fill-accent" />
                ),
              )}
            </g>
          )}

          {/* 9 · Waypoints y sus letreros: sobre las estelas para que los ids sigan legibles. */}
          {layers.waypoints &&
            plan?.waypoints.map((w, i) => {
              if (i === plan.waypoints.length - 1) return null // la vuelta a la base
              const isBase = w.id === 'BASE'
              const reached = data.reached.has(w.id)
              return (
                <g key={`${w.id}${i}`} transform={`translate(${w.x} ${-w.y})`}>
                  {isBase ? (
                    <circle r={u * 1.4} className="fill-card stroke-primary" strokeWidth={lineW + 0.5} vectorEffect="non-scaling-stroke" />
                  ) : (
                    <rect x={-u} y={-u} width={u * 2} height={u * 2} transform="rotate(45)" className={reached ? 'fill-primary stroke-primary' : 'fill-card stroke-primary'} strokeWidth={lineW + 0.5} vectorEffect="non-scaling-stroke" />
                  )}
                  <text x={u * 1.8} y={-u * 1.6} fontSize={labelSize} className="fill-foreground font-mono font-medium" {...halo}>
                    {w.id}
                  </text>
                </g>
              )
            })}

          {/* 10 · Línea conocido–real: por debajo de los dos iconos que une. Su geometría la escribe el bucle de dibujo. */}
          {layers.drone && layers.truthDrone && (
            <line ref={linkRef} visibility="hidden" className="stroke-foreground/50" strokeWidth={1.25} strokeDasharray="2 3" vectorEffect="non-scaling-stroke" data-testid="drone-link" />
          )}

          {/* 11 · Icono real (contorno discontinuo): bajo el conocido. Posición y rumbo, del bucle de dibujo. */}
          {layers.truthDrone && (
            <g ref={trueRef} visibility="hidden" data-testid="true-drone">
              <title>True position · nose heading</title>
              <g ref={trueRotRef}>
                <polygon points={`0,${-u * 1.9} ${u * 1.3},${u * 1.4} 0,${u * 0.7} ${-u * 1.3},${u * 1.4}`} className="fill-card/40 stroke-foreground" strokeWidth={lineW + 0.5} strokeDasharray="3 2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
              </g>
            </g>
          )}

          {/* 12 · Icono conocido, con el anillo del resalte y «last fix…»: el protagonista, arriba de los datos. */}
          {drone && layers.drone && (
            <g ref={knownRef} data-testid="known-drone" opacity={dim ? 0.4 : 1}>
              <title>Known position · GPS course over ground</title>
              {layers.highlight && data.openDetections.length > 0 && <circle r={u * 3.2} fill="none" stroke={HIGHLIGHT} strokeWidth={lineW + 1} vectorEffect="non-scaling-stroke" />}
              <circle r={u * 2.4} className={running ? 'animate-pulse fill-accent/15' : 'fill-accent/15'} />
              <g ref={knownRotRef}>
                <polygon points={`0,${-u * 1.9} ${u * 1.3},${u * 1.4} 0,${u * 0.7} ${-u * 1.3},${u * 1.4}`} className={hollow ? 'fill-card stroke-accent' : 'fill-accent stroke-card'} strokeWidth={lineW + 0.5} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
              </g>
              {dim && (
                <text y={u * 4.6} fontSize={labelSize} textAnchor="middle" className="fill-foreground font-mono" data-testid="fix-age" {...halo}>
                  last fix {age} s ago
                </text>
              )}
            </g>
          )}

          {/* 13 · Coordenadas y «N ↑»: texto con halo pegado al borde de la pantalla, encima de todo. */}
          <g className="fill-muted-foreground font-mono" fontSize={px(10)}>
            {layers.coordinates && (
              <g data-testid="coordinates">
                <g ref={xLabelsRef}>
                  {grid.xs
                    .filter((x) => x > view.x + edge && x < view.x + view.w - edge)
                    .map((x) => (
                      <text key={`lx${x}`} x={x} y={view.y + view.h - px(5)} textAnchor="middle" {...halo}>
                        {x}
                      </text>
                    ))}
                </g>
                <g ref={yLabelsRef}>
                  {grid.ys
                    .filter((y) => -y > view.y + edge && -y < view.y + view.h - edge)
                    .map((y) => (
                      <text key={`ly${y}`} x={view.x + px(5)} y={-y + px(3.5)} textAnchor="start" {...halo}>
                        {y}
                      </text>
                    ))}
                </g>
              </g>
            )}
            <g ref={northRef}>
              <text x={view.x + px(8)} y={view.y + px(16)} fontSize={px(11)} {...halo}>
                N ↑
              </text>
            </g>
          </g>
        </g>
      </svg>

      {hint && (
        <div className="pointer-events-none absolute inset-x-0 top-1/2 flex -translate-y-1/2 justify-center" role="status" data-testid="wheel-hint">
          <span className="rounded-md bg-foreground/80 px-3 py-1.5 text-xs text-background">Use Ctrl + wheel to zoom</span>
        </div>
      )}

      {bar && (
        <div className="pointer-events-none absolute bottom-2 left-3 flex flex-col items-start gap-0.5 font-mono text-[10px] text-muted-foreground" data-testid="scale-bar">
          <span className="rounded-sm bg-card/80 px-1">{bar.meters >= 1000 ? `${bar.meters / 1000} km` : `${bar.meters} m`}</span>
          <span className="block h-1.5 border-x border-b border-foreground/70" style={{ width: bar.px }} />
        </div>
      )}

      <div
        className="absolute bottom-2 right-2 flex flex-col items-end gap-1"
        onPointerDown={(e) => e.stopPropagation()}
        onPointerMove={(e) => e.stopPropagation()}
      >
        <span className="rounded-sm bg-card/90 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground" aria-live="off">
          ×{effective.zoom < 10 ? effective.zoom.toFixed(1) : effective.zoom.toFixed(0)}
        </span>
        <div className="flex flex-col overflow-hidden rounded-md border border-border bg-card/90">
          <MapButton label="Zoom in" onClick={() => zoomBy(ZOOM_STEP)}>
            <Plus aria-hidden="true" />
          </MapButton>
          <MapButton label="Zoom out" onClick={() => zoomBy(1 / ZOOM_STEP)}>
            <Minus aria-hidden="true" />
          </MapButton>
          <MapButton label="Reset view" onClick={reset}>
            <Maximize aria-hidden="true" />
          </MapButton>
          <MapButton label="Center on the drone" onClick={center} disabled={!drone}>
            <LocateFixed aria-hidden="true" />
          </MapButton>
          <MapButton label="Follow the drone" pressed={follow} onClick={() => setFollow((f) => !f)} disabled={!drone}>
            <Navigation aria-hidden="true" />
          </MapButton>
        </div>
      </div>

      {layers.wind && (
        <div
          className="pointer-events-none absolute right-3 top-3 flex items-center gap-2 rounded-md border border-border bg-card/90 px-2 py-1 text-xs"
          style={{ opacity: muted('meteo') ? 0.35 : 1 }}
        >
          <svg viewBox="-12 -12 24 24" className="size-8" aria-hidden="true">
            <g transform={`rotate(${windTo})`} className="fill-muted-foreground">
              <polygon points="0,-10 6,2 2,2 2,10 -2,10 -2,2 -6,2" />
            </g>
          </svg>
          <div className="flex flex-col font-mono leading-tight">
            {wind ? (
              <>
                <span className="text-foreground">{wind.speed_mps.toFixed(1)} m/s</span>
                <span className="text-muted-foreground">
                  gust {wind.gust_mps.toFixed(1)} · from {wind.from_deg.toFixed(0)}°
                </span>
              </>
            ) : (
              <span className="text-muted-foreground">wind: no data</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
})

function MapButton({ label, onClick, children, pressed, disabled }: { label: string; onClick: () => void; children: React.ReactNode; pressed?: boolean; disabled?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex size-7 items-center justify-center text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 [&_svg]:size-4',
        pressed && 'bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground',
      )}
    >
      {children}
    </button>
  )
}
