// «Injected vs detected» (vista del instructor): lo que se inyectó en el ejercicio, sacado de la
// verdad (`/api/truth`) y de los fallos del instructor, frente al incidente que lo vio y cuándo.
// Puro y con pruebas. No hace falta contrato: la verdad ya llega a la web, y el módulo de IA no
// la ve nunca.
import type { Envelope, IncidentKind, TruthFile } from './contracts'
import type { IncidentView } from './derive'

/** Viento por encima del cual el dron no garantiza la ruta (m/s): el límite del dron. */
export const WIND_LIMIT_MPS = 12
/** Un incidente que abre hasta tantos segundos después de acabar lo inyectado aún lo vio. */
export const MATCH_SLACK_S = 30

export type InjectedKind = 'wind' | 'spoofing' | 'jamming' | 'hijack' | 'fault'
export type Injected = {
  key: string
  kind: InjectedKind
  label: string
  start: number
  /** `null` si sigue en curso en el último instante conocido. */
  end: number | null
}
export type InjectedRow = {
  injected: Injected
  /** El incidente que lo vio: el primero de su tipo que abrió durante lo inyectado o poco después. */
  incident: IncidentView | null
  /** Segundos desde que empezó lo inyectado hasta que se abrió el incidente. */
  delay: number | null
}

/** Qué incidentes cuentan como ver cada cosa inyectada (el secuestro abre como enlace perdido). */
const SEEN_AS: Record<InjectedKind, IncidentKind[]> = {
  wind: ['WIND'],
  spoofing: ['GPS_SPOOFING'],
  jamming: ['GPS_DEGRADED'],
  hijack: ['LINK_LOSS', 'HIJACK'],
  fault: [],
}

/** Tramos consecutivos de muestras que cumplen `on`; el último queda abierto (`end: null`) si sigue. */
function intervals<T extends { t: number }>(samples: T[], on: (s: T) => boolean): { start: number; end: number | null; peak: T }[] {
  const out: { start: number; end: number | null; peak: T }[] = []
  let open: { start: number; end: number | null; peak: T } | null = null
  let previous: T | null = null
  for (const s of samples) {
    if (on(s)) {
      open ??= { start: s.t, end: null, peak: s }
      previous = s
    } else if (open) {
      out.push({ ...open, end: previous?.t ?? s.t })
      open = null
    }
  }
  if (open) out.push(open)
  return out
}

const FAULT_LABEL: Record<string, string> = { gps: 'GPS', radar: 'Radar', meteo: 'Weather station', link: 'Command link', battery: 'Battery' }

export function injectedEpisodes(truth: TruthFile | null, events: Envelope[]): Injected[] {
  const out: Injected[] = []
  if (truth) {
    for (const w of intervals(truth.wind, (s) => s.speed_mps >= WIND_LIMIT_MPS)) {
      const peak = Math.max(...truth.wind.filter((s) => s.t >= w.start && (w.end === null || s.t <= w.end)).map((s) => s.speed_mps))
      out.push({ key: `wind-${w.start}`, kind: 'wind', label: `Wind above ${WIND_LIMIT_MPS} m/s (up to ${Math.round(peak)} m/s)`, start: w.start, end: w.end })
    }
    for (const e of intervals(truth.trajectory, (s) => (s.emitters_active ?? []).some((id) => id.startsWith('spoofer')))) {
      out.push({ key: `spoofing-${e.start}`, kind: 'spoofing', label: 'GPS spoofing', start: e.start, end: e.end })
    }
    for (const e of intervals(truth.trajectory, (s) => (s.emitters_active ?? []).some((id) => id.startsWith('jammer')))) {
      out.push({ key: `jamming-${e.start}`, kind: 'jamming', label: 'GPS jamming', start: e.start, end: e.end })
    }
    for (const e of intervals(truth.trajectory, (s) => s.mode === 'foreign_control')) {
      out.push({ key: `hijack-${e.start}`, kind: 'hijack', label: 'Hijack (another station controls the drone)', start: e.start, end: e.end })
    }
  }
  // fallos del instructor o del escenario (silenciar una fuente, pérdida de GPS)
  const started = new Map<string, Injected>()
  for (const e of events) {
    if (e.type !== 'FaultInjected' && e.type !== 'FaultCleared') continue
    const p = e.payload as { source: string; mode: string }
    const id = `${p.source}-${p.mode}`
    if (e.type === 'FaultInjected') {
      const item: Injected = { key: `fault-${id}-${e.sim_time}`, kind: 'fault', label: `${FAULT_LABEL[p.source] ?? p.source} ${p.mode === 'loss' ? 'loss' : 'muted'}`, start: e.sim_time, end: null }
      started.set(id, item)
      out.push(item)
    } else {
      const item = started.get(id)
      if (item) item.end = e.sim_time
      started.delete(id)
    }
  }
  return out.sort((a, b) => a.start - b.start)
}

/** Cada cosa inyectada con el incidente que la vio (o ninguno) y cuánto tardó. */
export function injectedVsDetected(injected: Injected[], incidents: IncidentView[]): InjectedRow[] {
  const taken = new Set<string>()
  return injected.map((item) => {
    const kinds = SEEN_AS[item.kind]
    const incident =
      incidents.find((i) => {
        if (taken.has(i.id)) return false
        const opened = i.opened.payload.opened_at
        const seen = i.revisions.some((r) => kinds.includes(r.payload.kind))
        return seen && opened >= item.start - 5 && opened <= (item.end ?? Infinity) + MATCH_SLACK_S
      }) ?? null
    if (incident) taken.add(incident.id)
    return { injected: item, incident, delay: incident ? Math.max(0, incident.opened.payload.opened_at - item.start) : null }
  })
}
