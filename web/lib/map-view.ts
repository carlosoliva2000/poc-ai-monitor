// Cámara del mapa (zoom y paneo) y estelas partidas por huecos. Funciones puras, con pruebas.

export type Rect = { x: number; y: number; w: number; h: number }
export type Camera = {
  zoom: number
  /** Centro en coordenadas SVG (x, -y); `null`: el centro de la vista base. */
  center: { x: number; y: number } | null
}

export const MIN_ZOOM = 0.5
export const MAX_ZOOM = 40
export const HOME: Camera = { zoom: 1, center: null }

export const clampZoom = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z))

/** Píxeles por unidad SVG a zoom 1: la vista base cabe entera en el contenedor. */
export function fitScale(base: Rect, width: number, height: number): number {
  if (width <= 0 || height <= 0 || base.w <= 0 || base.h <= 0) return 1
  return Math.min(width / base.w, height / base.h)
}

/** Región visible: tiene la proporción del contenedor (sin franjas) y el zoom pedido. */
export function visibleRect(base: Rect, cam: Camera, width: number, height: number): Rect {
  const px = fitScale(base, width, height) * cam.zoom
  const w = width > 0 ? width / px : base.w
  const h = height > 0 ? height / px : base.h
  const c = cam.center ?? { x: base.x + base.w / 2, y: base.y + base.h / 2 }
  return { x: c.x - w / 2, y: c.y - h / 2, w, h }
}

/** El centro no sale de `limit` (la ruta y lo visto, con margen): no se puede «perder» el mapa. */
export function clampCenter(limit: Rect, c: { x: number; y: number }) {
  return {
    x: Math.min(limit.x + limit.w, Math.max(limit.x, c.x)),
    y: Math.min(limit.y + limit.h, Math.max(limit.y, c.y)),
  }
}

/** Rectángulo (coordenadas SVG: x, -y) que contiene los puntos (x, y del mundo), con un margen. */
export function rectOf(pts: { x: number; y: number }[], margin = 0): Rect {
  if (pts.length === 0) return { x: -margin, y: -margin, w: 2 * margin, h: 2 * margin }
  let xmin = Infinity
  let xmax = -Infinity
  let ymin = Infinity
  let ymax = -Infinity
  for (const p of pts) {
    xmin = Math.min(xmin, p.x)
    xmax = Math.max(xmax, p.x)
    ymin = Math.min(ymin, p.y)
    ymax = Math.max(ymax, p.y)
  }
  return { x: xmin - margin, y: -ymax - margin, w: xmax - xmin + 2 * margin, h: ymax - ymin + 2 * margin }
}

/** Unión de dos rectángulos. */
export function unionRect(a: Rect, b: Rect): Rect {
  const x = Math.min(a.x, b.x)
  const y = Math.min(a.y, b.y)
  return { x, y, w: Math.max(a.x + a.w, b.x + b.w) - x, h: Math.max(a.y + a.h, b.y + b.h) - y }
}

/** Cámara que encuadra `target` en el contenedor, respecto a la vista base (`reset view`). */
export function frameCamera(base: Rect, target: Rect, width: number, height: number): Camera {
  const fit = fitScale(base, width, height)
  if (fit <= 0) return HOME
  return {
    zoom: clampZoom(fitScale(target, width, height) / fit),
    center: { x: target.x + target.w / 2, y: target.y + target.h / 2 },
  }
}

/** Cambia el zoom por `factor` manteniendo fijo el punto `at` (coordenadas SVG) de la pantalla. */
export function zoomAt(limit: Rect, cam: Camera, view: Rect, factor: number, at?: { x: number; y: number }): Camera {
  const zoom = clampZoom(cam.zoom * factor)
  const real = zoom / cam.zoom
  const c = cam.center ?? { x: view.x + view.w / 2, y: view.y + view.h / 2 }
  if (!at) return { zoom, center: clampCenter(limit, c) }
  return { zoom, center: clampCenter(limit, { x: at.x - (at.x - c.x) / real, y: at.y - (at.y - c.y) / real }) }
}

/** Desplaza el centro `dx`, `dy` unidades SVG. */
export function panBy(limit: Rect, cam: Camera, view: Rect, dx: number, dy: number): Camera {
  const c = cam.center ?? { x: view.x + view.w / 2, y: view.y + view.h / 2 }
  return { zoom: cam.zoom, center: clampCenter(limit, { x: c.x + dx, y: c.y + dy }) }
}

export type Segment<T> = { key: string; points: T[] }

/**
 * Parte una serie de muestras en tramos: un tramo nuevo cuando el hueco entre dos muestras supera
 * `maxGap` s (fuente callada) —sin unir los dos puntos— o cuando cambia `key` (p. ej. `fix`), y
 * en ese caso el tramo nuevo repite el último punto para que la línea no tenga un salto.
 */
export function segmentTrail<T extends { t: number }>(points: T[], maxGap: number, key: (p: T) => string = () => ''): Segment<T>[] {
  const out: Segment<T>[] = []
  let current: Segment<T> | null = null
  let prev: T | null = null
  for (const p of points) {
    const k = key(p)
    if (current === null || prev === null || p.t - prev.t > maxGap) {
      current = { key: k, points: [p] }
      out.push(current)
    } else if (k !== current.key) {
      current = { key: k, points: [prev, p] }
      out.push(current)
    } else {
      current.points.push(p)
    }
    prev = p
  }
  return out
}

/** Segundos desde la última posición recibida (nunca negativo). */
export function fixAge(simTime: number, lastFixTime: number): number {
  return Math.max(0, Math.round(simTime - lastFixTime))
}

/** Paso de la rejilla (m) para la extensión visible: unas 8 líneas; 100/250/500/1000 a zoom normal. */
export function gridStep(span: number) {
  const target = span / 8
  for (const s of [10, 25, 50, 100, 250, 500, 1000, 2500]) if (s >= target) return s
  return 5000
}

/** Tamaño en píxeles de pantalla a ×1 y límites. A ×4 o más alcanza el máximo. */
export type SizeSpec = { base: number; min: number; max: number }
export const SIZES = {
  unit: { base: 4.5, min: 3.5, max: 8 }, // iconos del dron, base, waypoints y puntos
  gpsTrail: { base: 2, min: 1.25, max: 3 },
  line: { base: 1.5, min: 1, max: 2.5 }, // ruta, estela del radar y de la verdad
  highlight: { base: 12, min: 12, max: 16 }, // ancho del «tubo» de una detección: 4–6 veces la estela del GPS
  label: { base: 11, min: 10, max: 13 },
} as const satisfies Record<string, SizeSpec>

/** `base · √zoom`, con mínimo y máximo: al alejar no quedan enormes ni al acercar, diminutos. */
export function scaledPx(spec: SizeSpec, zoom: number): number {
  return Math.min(spec.max, Math.max(spec.min, spec.base * Math.sqrt(zoom)))
}

/** Barra de escala: la longitud «bonita» (1, 2, 5 × 10ⁿ m) más larga que cabe en `maxPx`. */
export function scaleBar(pxPerMeter: number, maxPx = 140): { meters: number; px: number } | null {
  if (!(pxPerMeter > 0)) return null
  let best = 0
  for (let e = -2; e <= 5; e++) for (const m of [1, 2, 5]) {
    const meters = m * 10 ** e
    if (meters * pxPerMeter <= maxPx) best = Math.max(best, meters)
  }
  return best > 0 ? { meters: best, px: best * pxPerMeter } : null
}

/** Ancho de la consola del agente: la columna izquierda conserva al menos `MIN_LEFT` px. */
export const MIN_CONSOLE = 340
export const MIN_LEFT = 560
export const DEFAULT_CONSOLE = 420
export function clampConsoleWidth(width: number, viewport: number): number {
  const max = Math.max(MIN_CONSOLE, viewport - MIN_LEFT)
  return Math.round(Math.min(max, Math.max(MIN_CONSOLE, width)))
}

/** Rectángulo ampliado `margin` por cada lado. */
export function padRect(r: Rect, margin: number): Rect {
  return { x: r.x - margin, y: r.y - margin, w: r.w + 2 * margin, h: r.h + 2 * margin }
}
