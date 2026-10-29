// Movimiento suave de los iconos y de la cámara. Funciones y clases puras, con pruebas.
//
// Las posiciones llegan a saltos (el GPS, a 1 Hz de simulación, y la verdad, cada 0,1 s de reloj) y
// en ráfagas. Para pintarlas a la frecuencia de la pantalla se interpola entre las dos últimas
// muestras recibidas, con un retraso de como mucho una muestra, y sin extrapolar hacia delante: el
// icono nunca se pinta más allá de la última posición recibida.

export type Sample = { t: number; x: number; y: number; heading: number }

/** Tiempo de pared (s) que se espera, como mínimo, a que llegue la siguiente ráfaga de eventos. */
export const BURST_WALL_S = 0.15

/**
 * Retraso (s de simulación) con el que se pinta: una muestra del GPS y, a velocidades altas, lo que
 * dura una ráfaga (los eventos llegan en bloques cada 100 ms de reloj: a 16× son 1,6 s de simulación).
 */
export function renderDelay(speed: number, periodS: number): number {
  return Math.max(periodS, BURST_WALL_S * speed)
}

/**
 * Reloj de simulación estimado en el navegador a partir de los mensajes `state` (que llegan cada
 * 0,5 s y al cambiar algo). Entre dos mensajes avanza con el reloj de pared a la velocidad
 * de la simulación; en pausa no avanza. En marcha corrige el error poco a poco (`GAIN`). Nunca retrocede salvo reinicio (un salto atrás mayor que
 * la tolerancia): una corrección pequeña solo lo detiene un momento.
 */
export class SimClock {
  private sim = 0
  private wall = 0
  private speed = 1
  private running = false
  private last = 0
  private has = false

  /** Salto atrás (s de simulación) que se considera ruido de la estimación y no un reinicio. */
  static tolerance(speed: number): number {
    return 1 + 0.3 * speed
  }

  /** Fracción del error que se corrige con cada `state`: la latencia de cada mensaje varía unas decenas de ms y
   *  reanclar del todo haría que el icono se frenase y luego se pusiera al día. */
  static readonly GAIN = 0.15

  sync(sim: number, speed: number, running: boolean, wallMs: number): void {
    const hard = !this.has || running !== this.running || speed !== this.speed || !running || Math.abs(sim - this.rawNow(wallMs)) > SimClock.tolerance(speed)
    const backwards = this.has && sim < this.last - SimClock.tolerance(Math.max(speed, this.speed))
    // En marcha y sin cambios, solo se corrige una parte del error; si no, se ancla al valor recibido.
    this.sim = hard ? sim : this.rawNow(wallMs) + (sim - this.rawNow(wallMs)) * SimClock.GAIN
    this.wall = wallMs
    this.speed = speed
    this.running = running
    if (!this.has || backwards) this.last = sim
    this.has = true
  }

  private rawNow(wallMs: number): number {
    return this.running ? this.sim + ((wallMs - this.wall) / 1000) * this.speed : this.sim
  }

  /** Olvida todo (otra ejecución). */
  reset(): void {
    this.has = false
    this.last = 0
  }

  now(wallMs: number): number {
    if (!this.has) return 0
    this.last = Math.max(this.last, this.rawNow(wallMs))
    return this.last
  }
}

export type TrackOptions = {
  /** Si entre dos muestras pasa más de esto (s de simulación), la fuente ha callado: salto sin animar. */
  maxGapS: number
  /** Distancia (m) a partir de la cual dos muestras separadas `dt` s son un salto (recuperación, engaño…). */
  maxJumpM?: (dt: number) => number
}

type Stored = Sample & { broken: boolean }

const MAX_STORED = 6

/** Ángulo interpolado por el camino corto (grados, 0–360). */
export function lerpAngle(a: number, b: number, alpha: number): number {
  const d = ((((b - a) % 360) + 540) % 360) - 180
  return (a + d * alpha + 360) % 360
}

/**
 * Últimas muestras de una fuente. `sampleAt(t)` interpola entre las dos que rodean `t`; con `t`
 * posterior a la última devuelve la última (no extrapola) y con un hueco o un salto entre las dos
 * mantiene la anterior hasta que `t` alcanza la siguiente, y entonces salta sin animar.
 */
export class Track {
  private items: Stored[] = []
  private readonly options: TrackOptions

  constructor(options: TrackOptions) {
    this.options = options
  }

  clear(): void {
    this.items = []
  }

  get size(): number {
    return this.items.length
  }

  push(s: Sample): void {
    const prev = this.items[this.items.length - 1]
    if (prev && s.t < prev.t) this.items = [] // reinicio: el tiempo ha retrocedido
    const last = this.items[this.items.length - 1]
    if (last && s.t === last.t) return
    let broken = false
    if (last) {
      const dt = s.t - last.t
      broken = dt > this.options.maxGapS || (this.options.maxJumpM !== undefined && Math.hypot(s.x - last.x, s.y - last.y) > this.options.maxJumpM(dt))
    }
    this.items.push({ ...s, broken })
    if (this.items.length > MAX_STORED) this.items.shift()
  }

  last(): Sample | null {
    return this.items[this.items.length - 1] ?? null
  }

  sampleAt(t: number): Sample | null {
    const items = this.items
    if (items.length === 0) return null
    if (t <= items[0].t) return items[0]
    for (let i = 0; i < items.length - 1; i++) {
      const a = items[i]
      const b = items[i + 1]
      if (t >= b.t) continue
      if (b.broken) return a
      const alpha = (t - a.t) / (b.t - a.t)
      return { t, x: a.x + (b.x - a.x) * alpha, y: a.y + (b.y - a.y) * alpha, heading: lerpAngle(a.heading, b.heading, alpha) }
    }
    return items[items.length - 1]
  }
}

/** Lo que la web sabe en directo, sin pasar por el volcado a React: reloj y muestras de los dos iconos. */
export type Live = {
  clock: SimClock
  /** Posición conocida: las `PositionUpdated` del GPS (1 Hz de simulación). */
  gps: Track
  /** Posición real: los mensajes `truth` (cada 0,1 s de reloj). */
  truth: Track
  speed: number
}

export const GPS_PERIOD_S = 1

export function createLive(): Live {
  return {
    clock: new SimClock(),
    gps: new Track({ maxGapS: 1.5 * GPS_PERIOD_S, maxJumpM: (dt) => 40 + 40 * dt }),
    truth: new Track({ maxGapS: Infinity }),
    speed: 1,
  }
}

/** Instante de simulación con el que se pintan **los dos** iconos (el mismo, para que no se desfasen). */
export function renderTime(live: Live, wallMs: number): number {
  return live.clock.now(wallMs) - renderDelay(live.speed, GPS_PERIOD_S)
}
