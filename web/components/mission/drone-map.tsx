'use client'

import { LocateFixed, Maximize, Minus, Navigation, Plus } from 'lucide-react'
import { memo, useEffect, useMemo, useRef, useState } from 'react'
import type { ActiveFault, PlanFile, TruthFile } from '@/lib/contracts'
import type { Derived } from '@/lib/derive'
import { clampZoom, fitScale, fixAge, HOME, niceStep, panBy, segmentTrail, visibleRect, zoomAt, type Camera, type Rect } from '@/lib/map-view'
import { cn } from '@/lib/utils'
import type { Layers } from './layers-panel'

type DroneMapProps = {
  plan: PlanFile | null
  data: Derived
  truth: TruthFile | null
  layers: Layers
  faults: ActiveFault[]
  running: boolean
  speed: number
  /** Instante actual de la simulación (para la antigüedad del último fix). */
  simTime: number
}

type Bounds = { xmin: number; xmax: number; ymin: number; ymax: number }
const RADAR = 'oklch(0.55 0.12 195)'
const GPS_GAP_S = 1.5 // más de 1,5 periodos sin posición del GPS = hueco
const RADAR_GAP_S = 3
const ZOOM_STEP = 1.5

/** Límites del mapa: la ruta planificada más todo lo visto, solo crecen (para que no baile). */
function useBounds(plan: PlanFile | null, data: Derived, truth: TruthFile | null): Bounds {
  const ref = useRef<{ plan: PlanFile | null; b: Bounds }>({ plan: null, b: { xmin: 0, xmax: 1, ymin: 0, ymax: 1 } })
  if (ref.current.plan !== plan) {
    const pts = plan ? [...plan.waypoints, ...plan.trajectory] : [{ x: 0, y: 0 }]
    ref.current = { plan, b: boundsOf(pts) }
  }
  const grow = (pts: { x: number; y: number }[], from: number) => {
    const b = ref.current.b
    for (let i = from; i < pts.length; i++) {
      b.xmin = Math.min(b.xmin, pts[i].x)
      b.xmax = Math.max(b.xmax, pts[i].x)
      b.ymin = Math.min(b.ymin, pts[i].y)
      b.ymax = Math.max(b.ymax, pts[i].y)
    }
  }
  grow(data.gps, 0)
  grow(data.radar, 0)
  if (truth) grow(truth.trajectory, 0)
  const b = ref.current.b
  const round = (v: number, up: boolean) => (up ? Math.ceil(v / 100) * 100 : Math.floor(v / 100) * 100)
  return { xmin: round(b.xmin, false), xmax: round(b.xmax, true), ymin: round(b.ymin, false), ymax: round(b.ymax, true) }
}

function boundsOf(pts: { x: number; y: number }[]): Bounds {
  return {
    xmin: Math.min(...pts.map((p) => p.x)),
    xmax: Math.max(...pts.map((p) => p.x)),
    ymin: Math.min(...pts.map((p) => p.y)),
    ymax: Math.max(...pts.map((p) => p.y)),
  }
}

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
 * estimada). El icono del dron es la **posición conocida** (la última del GPS); con la verdad
 * activa, otro icono (contorno) marca la posición real.
 *
 * Cámara: rueda = zoom hacia el cursor, arrastrar = paneo, botones + / − / restablecer / centrar
 * y «seguir al dron» (sigue al icono conocido; arrastrar lo desactiva). El tamaño de símbolos y
 * letreros es constante en pantalla, sea cual sea el zoom.
 */
export const DroneMap = memo(function DroneMap({ plan, data, truth, layers, faults, running, speed, simTime }: DroneMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const size = useSize(containerRef)
  const [cam, setCam] = useState<Camera>(HOME)
  const [follow, setFollow] = useState(false)

  const b = useBounds(plan, data, truth)
  const spanX = Math.max(b.xmax - b.xmin, 200)
  const spanY = Math.max(b.ymax - b.ymin, 200)
  const pad = Math.max(spanX, spanY) * 0.07
  const base: Rect = { x: b.xmin - pad * 1.6, y: -b.ymax - pad, w: spanX + pad * 2.6, h: spanY + pad * 2 }

  const muted = (s: string) => faults.some((f) => f.source === s && f.mode === 'mute')
  const drone = data.gps[data.gps.length - 1] ?? null
  const trueDrone = layers.truth && layers.truthDrone && truth && truth.trajectory.length > 0 ? truth.trajectory[truth.trajectory.length - 1] : null

  // Cámara efectiva: con «seguir», el centro es el icono conocido (no el real).
  const effective: Camera = follow && drone ? { zoom: cam.zoom, center: { x: drone.x, y: -drone.y } } : cam
  const view = visibleRect(base, effective, size.w, size.h)
  const ppu = size.w > 0 && size.h > 0 ? fitScale(base, size.w, size.h) * effective.zoom : 0 // px por unidad SVG
  const u = ppu > 0 ? 9 / ppu : Math.max(spanX, spanY) / 100 // unidad de dibujo: ≈9 px en pantalla
  const step = niceStep(Math.max(view.w, view.h))
  const viewBox = `${view.x} ${view.y} ${view.w} ${view.h}`

  // El último estado, para los manejadores nativos (rueda y arrastre).
  const latest = useRef({ base, view, effective, ppu, follow })
  latest.current = { base, view, effective, ppu, follow }

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const { base, view, effective, ppu, follow } = latest.current
      if (ppu <= 0) return
      const factor = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 16 : 1) * 0.0015)
      const rect = el.getBoundingClientRect()
      const at = follow ? undefined : { x: view.x + (e.clientX - rect.left) / ppu, y: view.y + (e.clientY - rect.top) / ppu }
      setCam(zoomAt(base, effective, view, factor, at))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
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
    setCam(panBy(latest.current.base, d.cam, d.view, -dx / latest.current.ppu, -dy / latest.current.ppu))
  }
  const endDrag = () => {
    drag.current = null
  }

  const zoomBy = (factor: number) => setCam(zoomAt(base, effective, view, factor))
  const reset = () => {
    setCam(HOME)
    setFollow(false)
  }
  const center = () => {
    if (!drone) return
    setCam({ zoom: clampZoom(cam.zoom), center: { x: drone.x, y: -drone.y } })
    setFollow(false)
  }

  const grid = useMemo(() => {
    const xs: number[] = []
    const ys: number[] = []
    const top = -view.y
    const bottom = -(view.y + view.h)
    for (let x = Math.ceil(Math.max(b.xmin, view.x) / step) * step; x <= Math.min(b.xmax, view.x + view.w); x += step) xs.push(x)
    for (let y = Math.ceil(Math.max(b.ymin, bottom) / step) * step; y <= Math.min(b.ymax, top); y += step) ys.push(y)
    return { xs, ys }
  }, [b.xmin, b.xmax, b.ymin, b.ymax, step, view.x, view.y, view.w, view.h])

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

  // Etiquetas de los ejes: junto al borde del mapa si se ve y, si no, pegadas al borde de la vista.
  const labelY = Math.min(-b.ymin + u * 3, view.y + view.h - u * 0.7)
  const leftOutside = b.xmin - view.x > u * 6
  const labelX = leftOutside ? b.xmin - u * 0.8 : view.x + u * 0.7
  const halo = { stroke: 'var(--card)', strokeWidth: u * 0.45, paintOrder: 'stroke' } as const

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
    >
      <svg
        viewBox={viewBox}
        className="h-full w-full"
        role="img"
        aria-label={drone ? `x,y map (y towards the north). Drone at x ${drone.x.toFixed(0)}, y ${drone.y.toFixed(0)}.` : 'x,y map with the planned route.'}
      >
        <rect x={b.xmin} y={-b.ymax} width={spanX} height={spanY} className="fill-card" />
        <g className="stroke-grid">
          {grid.xs.map((x) => (
            <line key={`gx${x}`} x1={x} y1={-b.ymax} x2={x} y2={-b.ymin} strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
          {grid.ys.map((y) => (
            <line key={`gy${y}`} x1={b.xmin} y1={-y} x2={b.xmax} y2={-y} strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
        </g>
        <g className="fill-muted-foreground font-mono" fontSize={u * 1.5}>
          {grid.xs.map((x) => (
            <text key={`lx${x}`} x={x} y={labelY} textAnchor="middle" {...halo}>
              {x}
            </text>
          ))}
          {grid.ys.map((y) => (
            <text key={`ly${y}`} x={labelX} y={-y + u * 0.5} textAnchor={leftOutside ? 'end' : 'start'} {...halo}>
              {y}
            </text>
          ))}
          <text x={Math.min(b.xmax, view.x + view.w - u)} y={Math.max(-b.ymax - u, view.y + u * 2)} textAnchor="end" {...halo}>
            N ↑
          </text>
        </g>
        <rect x={b.xmin} y={-b.ymax} width={spanX} height={spanY} fill="none" className="stroke-border" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />

        {layers.truth && truth && truth.trajectory.length > 1 && (
          <polyline points={truthLine} fill="none" className="stroke-foreground/70" strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        )}

        {layers.plan && plan && (
          <polyline points={planned} fill="none" className="stroke-primary" strokeWidth={2} strokeDasharray="8 6" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
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
                <polyline key={i} points={points(s.points)} fill="none" stroke={RADAR} strokeWidth={2} strokeOpacity={0.85} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
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
                  strokeWidth={3}
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
          <polyline points={highlight} fill="none" className="stroke-destructive" strokeOpacity={0.55} strokeWidth={8} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
        )}

        {layers.gpsPoints && (
          <g style={{ opacity: muted('gps') ? 0.25 : 1 }}>
            {gpsDots.map((p, i) =>
              p.fix === 'none' ? (
                <circle key={i} cx={p.x} cy={-p.y} r={u * 0.5} fill="none" className="stroke-accent" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
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
                  <circle r={u * 1.4} className="fill-card stroke-primary" strokeWidth={2} vectorEffect="non-scaling-stroke" />
                ) : (
                  <rect x={-u} y={-u} width={u * 2} height={u * 2} transform="rotate(45)" className={reached ? 'fill-primary stroke-primary' : 'fill-card stroke-primary'} strokeWidth={2} vectorEffect="non-scaling-stroke" />
                )}
                <text x={u * 1.8} y={-u * 1.6} fontSize={u * 1.7} className="fill-foreground font-mono font-medium" {...halo}>
                  {w.id}
                </text>
              </g>
            )
          })}

        {trueDrone && (
          <g data-testid="true-drone">
            {drone && layers.drone && Math.hypot(drone.x - trueDrone.x, drone.y - trueDrone.y) > u * 2 && (
              <line x1={drone.x} y1={-drone.y} x2={trueDrone.x} y2={-trueDrone.y} className="stroke-foreground/50" strokeWidth={1.5} strokeDasharray="2 3" vectorEffect="non-scaling-stroke" />
            )}
            <g transform={`translate(${trueDrone.x} ${-trueDrone.y})`}>
              <g transform={`rotate(${trueDrone.heading_deg})`}>
                <polygon points={`0,${-u * 1.9} ${u * 1.3},${u * 1.4} 0,${u * 0.7} ${-u * 1.3},${u * 1.4}`} className="fill-none stroke-foreground" strokeWidth={2} strokeDasharray="3 2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
              </g>
              <text y={u * 3.6} fontSize={u * 1.5} textAnchor="middle" className="fill-foreground font-mono" {...halo}>
                true position
              </text>
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
            {layers.highlight && data.openDetections.length > 0 && <circle r={u * 3.2} fill="none" className="stroke-destructive" strokeWidth={2} vectorEffect="non-scaling-stroke" />}
            <circle r={u * 2.4} className={running ? 'animate-pulse fill-accent/15' : 'fill-accent/15'} />
            <g transform={`rotate(${drone.heading})`}>
              <polygon points={`0,${-u * 1.9} ${u * 1.3},${u * 1.4} 0,${u * 0.7} ${-u * 1.3},${u * 1.4}`} className={hollow ? 'fill-card stroke-accent' : 'fill-accent stroke-card'} strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            </g>
            {dim && (
              <text y={u * 4.4} fontSize={u * 1.5} textAnchor="middle" className="fill-foreground font-mono" data-testid="fix-age" {...halo}>
                last fix {age} s ago
              </text>
            )}
          </g>
        )}
      </svg>

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
