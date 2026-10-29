'use client'

import { LocateFixed, Maximize, Minus, Navigation, Plus } from 'lucide-react'
import { memo, useEffect, useMemo, useRef, useState } from 'react'
import type { ActiveFault, PlanFile, TruthFile, TruthMessage } from '@/lib/contracts'
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
import { cn } from '@/lib/utils'
import type { Layers } from './layers-panel'

type DroneMapProps = {
  plan: PlanFile | null
  data: Derived
  /** Traza de la verdad (`/api/truth`); solo con la capa «Truth trail». */
  truth: TruthFile | null
  /** Última posición real en directo (mensaje `truth`); solo con la capa «True position». */
  liveTruth: TruthMessage | null
  runId: string | null
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
const TRUE_MOVE_MS = 100 // el icono real se anima como mucho lo que tarda en llegar el siguiente envío

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
 * Vista: la rejilla cubre toda la vista a cualquier zoom y la vista **no se recoloca sola**: la
 * vista base es la ruta planificada; solo «reset view» (ruta + datos) o cargar otro escenario la
 * cambian. Cámara: Ctrl + rueda = zoom hacia el cursor (la rueda sola desplaza la página),
 * arrastrar = paneo, botones + / − / restablecer / centrar y «seguir al dron». Los tamaños crecen
 * con la raíz del zoom, entre un mínimo y un máximo en píxeles (`SIZES`).
 */
export const DroneMap = memo(function DroneMap({ plan, data, truth, liveTruth, runId, layers, faults, running, speed, simTime }: DroneMapProps) {
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
  const trueDrone = layers.truthDrone && liveTruth && liveTruth.run_id === runId ? liveTruth : null

  // Cámara efectiva: con «seguir», el centro es el icono conocido (no el real).
  const effective: Camera = follow && drone ? { zoom: cam.zoom, center: { x: drone.x, y: -drone.y } } : cam
  const view = visibleRect(base, effective, size.w, size.h)
  const ppu = size.w > 0 && size.h > 0 ? fitScale(base, size.w, size.h) * effective.zoom : 0 // px por unidad SVG (= m)
  const px = (v: number) => (ppu > 0 ? v / ppu : v) // píxeles de pantalla → unidades SVG
  const zoom = effective.zoom
  const u = px(scaledPx(SIZES.unit, zoom)) // unidad de dibujo: iconos, base, waypoints y puntos
  const labelSize = px(scaledPx(SIZES.label, zoom))
  const gpsW = scaledPx(SIZES.gpsTrail, zoom)
  const lineW = scaledPx(SIZES.line, zoom)
  const highlightW = scaledPx(SIZES.highlight, zoom)
  const step = gridStep(Math.max(view.w, view.h))
  const viewBox = `${view.x} ${view.y} ${view.w} ${view.h}`
  const bar = scaleBar(ppu)

  // El último estado, para los manejadores nativos (rueda y arrastre).
  const latest = useRef({ limit, view, effective, ppu, follow })
  latest.current = { limit, view, effective, ppu, follow }

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

  // Rejilla «infinita»: líneas en toda la vista (x del mundo = x del SVG; y del mundo = -y del SVG).
  const grid = useMemo(() => {
    const xs: number[] = []
    const ys: number[] = []
    for (let x = Math.ceil(view.x / step) * step; x <= view.x + view.w; x += step) xs.push(x)
    for (let y = Math.ceil(-(view.y + view.h) / step) * step; y <= -view.y; y += step) ys.push(y)
    return { xs, ys }
  }, [step, view.x, view.y, view.w, view.h])

  const planned = plan?.waypoints.map((w) => `${w.x},${-w.y}`).join(' ') ?? ''
  const gpsSegments = useMemo(() => segmentTrail(data.gps, GPS_GAP_S, (p) => (p.fix === 'none' ? 'none' : 'fix')), [data.gps])
  const radarSegments = useMemo(() => segmentTrail(data.radar, RADAR_GAP_S), [data.radar])
  const truthLine = useMemo(() => (truth ? points(truth.trajectory) : ''), [truth])
  const since = data.openDetections.length ? Math.min(...data.openDetections.map((d) => d.since)) : null
  const highlight = useMemo(() => (since === null ? '' : points(data.gps.filter((p) => p.t >= since))), [data.gps, since])
  const transitionMs = Math.max(60, Math.round(1000 / speed))

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
  const showLink = !!(drone && layers.drone && trueDrone && Math.hypot(drone.x - trueDrone.x, drone.y - trueDrone.y) > u * 2)

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
        <g className="stroke-grid" data-testid="grid" data-step={step}>
          {grid.xs.map((x) => (
            <line key={`gx${x}`} x1={x} y1={view.y} x2={x} y2={view.y + view.h} strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
          {grid.ys.map((y) => (
            <line key={`gy${y}`} x1={view.x} y1={-y} x2={view.x + view.w} y2={-y} strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
        </g>
        <g className="fill-muted-foreground font-mono" fontSize={px(10)}>
          {layers.coordinates && (
            <g data-testid="coordinates">
              {grid.xs
                .filter((x) => x > view.x + edge && x < view.x + view.w - edge)
                .map((x) => (
                  <text key={`lx${x}`} x={x} y={view.y + view.h - px(5)} textAnchor="middle" {...halo}>
                    {x}
                  </text>
                ))}
              {grid.ys
                .filter((y) => -y > view.y + edge && -y < view.y + view.h - edge)
                .map((y) => (
                  <text key={`ly${y}`} x={view.x + px(5)} y={-y + px(3.5)} textAnchor="start" {...halo}>
                    {y}
                  </text>
                ))}
            </g>
          )}
          <text x={view.x + px(8)} y={view.y + px(16)} fontSize={px(11)} {...halo}>
            N ↑
          </text>
        </g>

        {layers.truth && truth && truth.trajectory.length > 1 && (
          <polyline points={truthLine} fill="none" className="stroke-foreground/70" strokeWidth={lineW} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        )}

        {layers.plan && plan && (
          <polyline points={planned} fill="none" className="stroke-primary" strokeWidth={lineW} strokeDasharray="7 5" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        )}

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

        {layers.highlight && highlight && (
          <polyline points={highlight} fill="none" className="stroke-destructive" strokeOpacity={0.5} strokeWidth={highlightW} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
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

        {showLink && trueDrone && drone && (
          <line x1={drone.x} y1={-drone.y} x2={trueDrone.x} y2={-trueDrone.y} className="stroke-foreground/50" strokeWidth={1.25} strokeDasharray="2 3" vectorEffect="non-scaling-stroke" data-testid="drone-link" />
        )}

        {trueDrone && (
          <g
            data-testid="true-drone"
            style={{
              transform: `translate(${trueDrone.x}px, ${-trueDrone.y}px)`,
              transition: running && !follow ? `transform ${TRUE_MOVE_MS}ms linear` : 'none',
            }}
          >
            <title>True position · nose heading</title>
            <g transform={`rotate(${trueDrone.heading_deg})`}>
              <polygon points={`0,${-u * 1.9} ${u * 1.3},${u * 1.4} 0,${u * 0.7} ${-u * 1.3},${u * 1.4}`} className="fill-card/40 stroke-foreground" strokeWidth={lineW + 0.5} strokeDasharray="3 2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            </g>
          </g>
        )}

        {drone && layers.drone && (
          <g
            data-testid="known-drone"
            style={{
              transform: `translate(${drone.x}px, ${-drone.y}px)`,
              transition: running && !follow ? `transform ${transitionMs}ms linear` : 'none',
              opacity: dim ? 0.4 : 1,
            }}
          >
            <title>Known position · GPS course over ground</title>
            {layers.highlight && data.openDetections.length > 0 && <circle r={u * 3.2} fill="none" className="stroke-destructive" strokeWidth={lineW + 0.5} vectorEffect="non-scaling-stroke" />}
            <circle r={u * 2.4} className={running ? 'animate-pulse fill-accent/15' : 'fill-accent/15'} />
            <g transform={`rotate(${drone.heading})`}>
              <polygon points={`0,${-u * 1.9} ${u * 1.3},${u * 1.4} 0,${u * 0.7} ${-u * 1.3},${u * 1.4}`} className={hollow ? 'fill-card stroke-accent' : 'fill-accent stroke-card'} strokeWidth={lineW + 0.5} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            </g>
            {dim && (
              <text y={u * 4.6} fontSize={labelSize} textAnchor="middle" className="fill-foreground font-mono" data-testid="fix-age" {...halo}>
                last fix {age} s ago
              </text>
            )}
          </g>
        )}
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
