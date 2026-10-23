'use client'

import { memo, useEffect, useMemo, useRef } from 'react'
import type { ActiveFault, PlanFile, TruthFile } from '@/lib/contracts'
import type { Derived } from '@/lib/derive'
import type { Layers } from './layers-panel'

type DroneMapProps = {
  plan: PlanFile | null
  data: Derived
  truth: TruthFile | null
  layers: Layers
  faults: ActiveFault[]
  running: boolean
  speed: number
}

type Bounds = { xmin: number; xmax: number; ymin: number; ymax: number }
const RADAR = 'oklch(0.55 0.12 195)'

function niceStep(span: number) {
  const target = span / 8
  for (const s of [10, 20, 50, 100, 200, 250, 500, 1000, 2000]) if (s >= target) return s
  return 5000
}

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

/**
 * Mapa x,y con **y hacia el norte** (en el SVG se pinta `-y`). Cada capa se pinta por separado
 * para poder ocultarla. Una fuente en `mute` atenúa su capa; en `loss` los puntos del GPS salen
 * huecos (sin fix, posición estimada).
 */
export const DroneMap = memo(function DroneMap({ plan, data, truth, layers, faults, running, speed }: DroneMapProps) {
  const b = useBounds(plan, data, truth)
  const spanX = Math.max(b.xmax - b.xmin, 200)
  const spanY = Math.max(b.ymax - b.ymin, 200)
  const pad = Math.max(spanX, spanY) * 0.07
  const u = Math.max(spanX, spanY) / 100 // unidad de dibujo (m) para tamaños de símbolos y texto
  const view = `${b.xmin - pad * 1.6} ${-b.ymax - pad} ${spanX + pad * 2.6} ${spanY + pad * 2}`
  const step = niceStep(Math.max(spanX, spanY))

  const muted = (s: string) => faults.some((f) => f.source === s && f.mode === 'mute')
  const gpsLost = faults.some((f) => f.source === 'gps' && f.mode === 'loss')

  const grid = useMemo(() => {
    const xs: number[] = []
    const ys: number[] = []
    for (let x = Math.ceil(b.xmin / step) * step; x <= b.xmax; x += step) xs.push(x)
    for (let y = Math.ceil(b.ymin / step) * step; y <= b.ymax; y += step) ys.push(y)
    return { xs, ys }
  }, [b.xmin, b.xmax, b.ymin, b.ymax, step])

  const planned = plan?.waypoints.map((w) => `${w.x},${-w.y}`).join(' ') ?? ''
  const trail = useMemo(() => data.gps.map((p) => `${p.x},${-p.y}`).join(' '), [data.gps])
  const truthLine = useMemo(() => truth?.trajectory.map((p) => `${p.x},${-p.y}`).join(' ') ?? '', [truth])
  const drone = data.gps[data.gps.length - 1] ?? null
  const since = data.openDetections.length ? Math.min(...data.openDetections.map((d) => d.since)) : null
  const highlight = useMemo(
    () => (since === null ? '' : data.gps.filter((p) => p.t >= since).map((p) => `${p.x},${-p.y}`).join(' ')),
    [data.gps, since],
  )
  const transitionMs = Math.max(60, Math.round(1000 / speed))

  // Los puntos pintados se limitan para no saturar el SVG a 16×.
  const gpsDots = useMemo(() => data.gps.slice(-1500), [data.gps])
  const radarDots = useMemo(() => data.radar.slice(-800), [data.radar])

  const wind = data.wind?.payload
  const windTo = wind ? (wind.from_deg + 180) % 360 : 0

  return (
    <div className="relative h-full w-full">
      <svg
        viewBox={view}
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
            <text key={`lx${x}`} x={x} y={-b.ymin + u * 3} textAnchor="middle">
              {x}
            </text>
          ))}
          {grid.ys.map((y) => (
            <text key={`ly${y}`} x={b.xmin - u * 0.8} y={-y + u * 0.5} textAnchor="end">
              {y}
            </text>
          ))}
          <text x={b.xmax} y={-b.ymax - u} textAnchor="end">
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

        {layers.gpsTrail && data.gps.length > 1 && (
          <polyline
            points={trail}
            fill="none"
            className="stroke-accent"
            strokeWidth={3}
            vectorEffect="non-scaling-stroke"
            strokeLinejoin="round"
            strokeLinecap="round"
            style={{ opacity: muted('gps') ? 0.3 : 1 }}
          />
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
                <text x={u * 1.8} y={-u * 1.6} fontSize={u * 1.7} className="fill-foreground font-mono font-medium">
                  {w.id}
                </text>
              </g>
            )
          })}

        {drone && (
          <g
            style={{
              transform: `translate(${drone.x}px, ${-drone.y}px)`,
              transition: running ? `transform ${transitionMs}ms linear` : 'none',
              opacity: muted('gps') ? 0.4 : 1,
            }}
          >
            {layers.highlight && data.openDetections.length > 0 && <circle r={u * 3.2} fill="none" className="stroke-destructive" strokeWidth={2} vectorEffect="non-scaling-stroke" />}
            <circle r={u * 2.4} className={running ? 'animate-pulse fill-accent/15' : 'fill-accent/15'} />
            <g transform={`rotate(${drone.heading})`}>
              <polygon points={`0,${-u * 1.9} ${u * 1.3},${u * 1.4} 0,${u * 0.7} ${-u * 1.3},${u * 1.4}`} className={gpsLost ? 'fill-card stroke-accent' : 'fill-accent stroke-card'} strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            </g>
          </g>
        )}
      </svg>

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
