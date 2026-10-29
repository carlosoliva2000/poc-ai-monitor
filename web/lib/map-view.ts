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

/** El centro no sale de la vista base: no se puede «perder» el mapa. */
export function clampCenter(base: Rect, c: { x: number; y: number }) {
  return {
    x: Math.min(base.x + base.w, Math.max(base.x, c.x)),
    y: Math.min(base.y + base.h, Math.max(base.y, c.y)),
  }
}

/** Cambia el zoom por `factor` manteniendo fijo el punto `at` (coordenadas SVG) de la pantalla. */
export function zoomAt(base: Rect, cam: Camera, view: Rect, factor: number, at?: { x: number; y: number }): Camera {
  const zoom = clampZoom(cam.zoom * factor)
  const real = zoom / cam.zoom
  const c = cam.center ?? { x: view.x + view.w / 2, y: view.y + view.h / 2 }
  if (!at) return { zoom, center: clampCenter(base, c) }
  return { zoom, center: clampCenter(base, { x: at.x - (at.x - c.x) / real, y: at.y - (at.y - c.y) / real }) }
}

/** Desplaza el centro `dx`, `dy` unidades SVG. */
export function panBy(base: Rect, cam: Camera, view: Rect, dx: number, dy: number): Camera {
  const c = cam.center ?? { x: view.x + view.w / 2, y: view.y + view.h / 2 }
  return { zoom: cam.zoom, center: clampCenter(base, { x: c.x + dx, y: c.y + dy }) }
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

/** Paso «bonito» de la rejilla para una extensión visible. */
export function niceStep(span: number) {
  const target = span / 8
  for (const s of [1, 2, 5, 10, 20, 50, 100, 200, 250, 500, 1000, 2000]) if (s >= target) return s
  return 5000
}
