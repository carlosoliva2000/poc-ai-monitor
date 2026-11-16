// Comandos del instructor (contrato v0.18): rosa de rumbos, validación del formulario (los mismos
// rangos que `poc_contracts.commands`), texto de una propuesta y viento activo según los eventos.
import type { Envelope, InstructorCommand, WindParams } from './contracts'

export const LIMITS = { speed: 40, gust: 60, ramp: 120, duration: 1800 } as const
export const DEFAULTS = { ramp_s: 10, duration_s: 60, gust_factor: 1.3 } as const

/** Los 16 rumbos de la rosa, cada 22,5°. El viento se nombra por **de dónde viene**. */
export const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'] as const
export type Point = (typeof COMPASS)[number]

export const compassDegrees = (point: Point): number => COMPASS.indexOf(point) * 22.5

/** Rumbo más cercano a unos grados. */
export function nearestPoint(deg: number): Point {
  const d = ((deg % 360) + 360) % 360
  return COMPASS[Math.round(d / 22.5) % 16]
}

/** Si los grados son justo un rumbo de la rosa, ese rumbo; si no, `null`. */
export function exactPoint(deg: number): Point | null {
  const p = nearestPoint(deg)
  return Math.abs((((deg - compassDegrees(p) + 540) % 360) - 180)) < 1e-6 ? p : null
}

const num = (v: number) => String(Number(v.toFixed(1)))

/** «NE (45°)» o «47° (≈NE)». */
export function describeFrom(deg: number): string {
  const exact = exactPoint(deg)
  return exact ? `${exact} (${num(deg)}°)` : `${num(deg)}° (≈${nearestPoint(deg)})`
}

export function describeDuration(duration_s: number | null): string {
  return duration_s === null ? 'until cancelled' : `${num(duration_s)} s`
}

/** «Wind from NE (45°), 8 m/s, gusts 10.4 m/s, 60 s, ramp 10 s». */
export function describeWind(p: WindParams): string {
  return `Wind from ${describeFrom(p.from_deg)}, ${num(p.speed_mps)} m/s, gusts ${num(p.gust_mps)} m/s, ${describeDuration(p.duration_s)}, ramp ${num(p.ramp_s)} s`
}

/** Campos del formulario (texto, para poder escribir con comodidad). */
export type WindForm = { from_deg: string; speed_mps: string; gust_mps: string; ramp_s: string; duration_s: string; untilCancelled: boolean }

export const EMPTY_FORM: WindForm = { from_deg: '0', speed_mps: '8', gust_mps: '10.4', ramp_s: String(DEFAULTS.ramp_s), duration_s: String(DEFAULTS.duration_s), untilCancelled: false }

export function formFromParams(p: WindParams): WindForm {
  return {
    from_deg: num(p.from_deg),
    speed_mps: num(p.speed_mps),
    gust_mps: num(p.gust_mps),
    ramp_s: num(p.ramp_s),
    duration_s: p.duration_s === null ? EMPTY_FORM.duration_s : num(p.duration_s),
    untilCancelled: p.duration_s === null,
  }
}

export type ParsedForm = { ok: true; params: WindParams } | { ok: false; errors: string[] }

function field(label: string, raw: string, min: number, max: number, errors: string[], exclusiveMin = false): number {
  const v = raw.trim() === '' ? NaN : Number(raw)
  if (!Number.isFinite(v)) errors.push(`${label}: enter a number`)
  else if (exclusiveMin ? v <= min : v < min) errors.push(`${label}: must be ${exclusiveMin ? 'greater than' : 'at least'} ${min}`)
  else if (v > max) errors.push(`${label}: at most ${max}`)
  return v
}

/** Valida el formulario con los rangos del contrato (el servidor los vuelve a comprobar). */
export function parseForm(f: WindForm): ParsedForm {
  const errors: string[] = []
  const from = field('Direction', f.from_deg, 0, 360, errors)
  const speed = field('Speed', f.speed_mps, 0, LIMITS.speed, errors)
  const gust = field('Gust', f.gust_mps, 0, LIMITS.gust, errors)
  const ramp = field('Ramp', f.ramp_s, 0, LIMITS.ramp, errors, true)
  const duration = f.untilCancelled ? null : field('Duration', f.duration_s, 0, LIMITS.duration, errors, true)
  if (errors.length === 0 && gust < speed) errors.push('Gust: must be at least the speed')
  if (errors.length > 0) return { ok: false, errors }
  return { ok: true, params: { from_deg: from % 360, speed_mps: speed, gust_mps: gust, ramp_s: ramp, duration_s: duration } }
}

export type ActiveWind = { params: WindParams; since: number; endsAt: number | null; issuedBy: InstructorCommand['issued_by'] }

/** Viento del instructor en curso en `simTime`, a partir de los `InstructorCommand` (por orden). */
export function activeWind(events: Envelope[], simTime: number): ActiveWind | null {
  let active: ActiveWind | null = null
  for (const e of events) {
    if (e.type !== 'InstructorCommand') continue
    const c = e.payload as unknown as InstructorCommand
    if (c.command === 'cancel_wind' || !c.params) {
      active = null
    } else {
      const end = c.params.duration_s === null ? null : e.sim_time + c.params.duration_s
      active = { params: c.params, since: e.sim_time, endsAt: end, issuedBy: c.issued_by }
    }
  }
  if (active && active.endsAt !== null && simTime >= active.endsAt) return null
  return active
}

/** Segundos que le quedan (`null` = sin fin). */
export const remaining = (a: ActiveWind, simTime: number): number | null => (a.endsAt === null ? null : Math.max(0, a.endsAt - simTime))

/** Texto corto de un comando para el timeline. */
export function describeCommand(c: InstructorCommand): string {
  if (c.command === 'cancel_wind' || !c.params) return `cancel_wind · ${c.issued_by}`
  return `set_wind: ${describeWind(c.params).replace(/^Wind /, '')} · ${c.issued_by}`
}
