import type {
  AgentToolCall,
  Anomaly,
  AlertClosed,
  AlertEnriched,
  AutopilotStatus,
  Battery,
  Detection,
  DetectionAcknowledged,
  DetectionCleared,
  Envelope,
  IncidentChange,
  IncidentEnriched,
  IncidentKind,
  IncidentState,
  IncidentUpdated,
  Link,
  Position,
  Proposal,
  Track,
  Wind,
} from './contracts'

export type Sample = { t: number; x: number; y: number }
export type GpsSample = Sample & { heading: number; speed: number; alt: number; fix: Position['fix']; sats: number; hdop: number }
export type RadarSample = Sample & { speed: number }

/** Estado del enlace según el último `LinkStatus` (nuestra estación): caído, degradado o bueno. */
export type LinkState = 'good' | 'degraded' | 'lost'
export const LINK_LOSS_BAD_PCT = 20
export const LINK_LATENCY_BAD_MS = 100

export function linkState(link: Link | null): LinkState | null {
  if (!link) return null
  if (link.rssi_dbm === null || link.latency_ms === null || (link.packet_loss_pct ?? 0) >= 100) return 'lost'
  if ((link.packet_loss_pct ?? 0) > LINK_LOSS_BAD_PCT || link.latency_ms > LINK_LATENCY_BAD_MS) return 'degraded'
  return 'good'
}

/** Telemetría del dron: llega por el enlace, así que con el enlace caído deja de llegar. */
const TELEMETRY_EVENTS = new Set(['PositionUpdated', 'GnssStatus', 'AutopilotStatus', 'BatteryStatus'])

export type DetectionView = {
  detection_id: string
  rule: Detection['rule']
  severity: Detection['severity']
  source: Detection['source']
  since: number
  message: string
  closedAt: number | null
}

/** Una alerta (un `AnomalyDetected`) con su lugar en la cadena de `supersedes`. */
export type AlertView = {
  event: Envelope<Anomaly>
  /** Etiqueta del episodio (A1, A2…): una cadena de `supersedes` es una sola alerta. */
  episode: string
  /** Si otra alerta la ha sustituido. */
  supersededBy: string | null
  closedAt: number | null
}

export type Episode = { label: string; head: AlertView; chain: AlertView[]; open: boolean }

export type Derived = {
  gps: GpsSample[]
  radar: RadarSample[]
  wind: Envelope<Wind> | null
  link: Envelope<Link> | null
  battery: Envelope<Battery> | null
  /** Último `PositionUpdated` (con o sin posición): el fix y los satélites. */
  gpsStatus: { t: number; fix: Position['fix']; sats: number } | null
  autopilot: Envelope<AutopilotStatus> | null
  linkState: LinkState | null
  /** `sim_time` del último mensaje de telemetría del dron (GPS, receptor, autopiloto, batería). */
  lastTelemetry: number | null
  lastWaypoint: string
  reached: Set<string>
  missionDone: boolean
  detections: DetectionView[]
  openDetections: DetectionView[]
  alerts: Map<string, AlertView>
  episodes: Episode[]
  /** Eventos de detección (Raised/Updated/Cleared) y quién les ha respondido (por `causation_id`). */
  responses: Map<string, Envelope[]>
  /** Eventos de detección a los que el monitor aún no ha respondido. */
  pending: Envelope[]
  report: Envelope<{ run_id: string; markdown: string; alerts_count: number }> | null
  /** v1.4: el debriefing del instructor (lleva la verdad: la vista del alumno no lo recibe). */
  debrief: Envelope<{ run_id: string; markdown: string; injects_count: number }> | null
  /** Motivo de la última pausa si el reproductor sigue pausado por ella. */
  t0Ms: number | null
}

const DETECTION_EVENTS = new Set(['DetectionRaised', 'DetectionUpdated', 'DetectionCleared'])
const RESPONSE_EVENTS = new Set(['AnomalyDetected', 'AlertClosed', 'DetectionAcknowledged'])

export function derive(events: Envelope[]): Derived {
  const gps: GpsSample[] = []
  const radar: RadarSample[] = []
  const detections = new Map<string, DetectionView>()
  const alerts = new Map<string, AlertView>()
  const responses = new Map<string, Envelope[]>()
  const detectionEvents: Envelope[] = []
  const reached = new Set<string>()
  let wind: Envelope<Wind> | null = null
  let link: Envelope<Link> | null = null
  let battery: Envelope<Battery> | null = null
  let gpsStatus: Derived['gpsStatus'] = null
  let autopilot: Envelope<AutopilotStatus> | null = null
  let lastTelemetry: number | null = null
  let lastWaypoint = 'BASE'
  let missionDone = false
  let report: Derived['report'] = null
  let debrief: Derived['debrief'] = null
  let t0Ms: number | null = null
  const order: string[] = []

  for (const e of events) {
    if (t0Ms === null) t0Ms = Date.parse(e.event_time) - e.sim_time * 1000
    if (TELEMETRY_EVENTS.has(e.type)) lastTelemetry = e.sim_time
    switch (e.type) {
      case 'PositionUpdated': {
        const p = e.payload as unknown as Position
        gpsStatus = { t: e.sim_time, fix: p.fix, sats: p.sats }
        if (p.x === null || p.y === null) break // sin fix no hay posición que pintar
        gps.push({ t: e.sim_time, x: p.x, y: p.y, heading: p.course_deg ?? 0, speed: p.speed_mps ?? 0, alt: p.alt_m ?? 0, fix: p.fix, sats: p.sats, hdop: p.hdop })
        break
      }
      case 'TrackUpdated': {
        const p = e.payload as unknown as Track
        radar.push({ t: e.sim_time, x: p.x, y: p.y, speed: p.speed_mps })
        break
      }
      case 'WindReported':
        wind = e as Envelope<Wind>
        break
      case 'LinkStatus':
        link = e as Envelope<Link>
        break
      case 'BatteryStatus':
        battery = e as Envelope<Battery>
        break
      case 'AutopilotStatus':
        autopilot = e as Envelope<AutopilotStatus>
        break
      case 'WaypointReached': {
        const id = String((e.payload as { waypoint_id: string }).waypoint_id)
        reached.add(id)
        lastWaypoint = id
        break
      }
      case 'MissionCompleted':
        missionDone = true
        break
      case 'DetectionRaised':
      case 'DetectionUpdated': {
        const p = e.payload as unknown as Detection
        const prev = detections.get(p.detection_id)
        detections.set(p.detection_id, {
          detection_id: p.detection_id,
          rule: p.rule,
          severity: p.severity,
          source: p.source,
          since: prev?.since ?? p.window.since,
          message: prev?.message ?? p.message,
          closedAt: null,
        })
        detectionEvents.push(e)
        break
      }
      case 'DetectionCleared': {
        const p = e.payload as unknown as DetectionCleared
        const d = detections.get(p.detection_id)
        if (d) d.closedAt = e.sim_time
        detectionEvents.push(e)
        break
      }
      case 'AnomalyDetected': {
        const a = e.payload as unknown as Anomaly
        const root = a.supersedes ? alerts.get(a.supersedes)?.episode : undefined
        let episode = root
        if (!episode) {
          order.push(a.alert_id)
          episode = `A${order.length}`
        }
        if (a.supersedes) {
          const old = alerts.get(a.supersedes)
          if (old) old.supersededBy = a.alert_id
        }
        alerts.set(a.alert_id, { event: e as Envelope<Anomaly>, episode, supersededBy: null, closedAt: null })
        break
      }
      case 'AlertClosed': {
        const p = e.payload as unknown as AlertClosed
        const a = alerts.get(p.alert_id)
        if (a) a.closedAt = e.sim_time
        break
      }
      case 'ReportGenerated':
        report = e as Derived['report']
        break
      case 'DebriefGenerated':
        debrief = e as Derived['debrief']
        break
    }
    if (RESPONSE_EVENTS.has(e.type) && e.source === 'ai-monitor' && e.causation_id) {
      const list = responses.get(e.causation_id) ?? []
      list.push(e)
      responses.set(e.causation_id, list)
    }
  }

  const byEpisode = new Map<string, AlertView[]>()
  for (const a of alerts.values()) byEpisode.set(a.episode, [...(byEpisode.get(a.episode) ?? []), a])
  const episodes: Episode[] = [...byEpisode.entries()].map(([label, chain]) => {
    const head = chain.find((a) => a.supersededBy === null) ?? chain[chain.length - 1]
    return { label, head, chain, open: head.closedAt === null }
  })

  const all = [...detections.values()]
  return {
    gps,
    radar,
    wind,
    link,
    battery,
    gpsStatus,
    autopilot,
    linkState: linkState(link?.payload ?? null),
    lastTelemetry,
    lastWaypoint,
    reached,
    missionDone,
    detections: all,
    openDetections: all.filter((d) => d.closedAt === null),
    alerts,
    episodes,
    responses,
    pending: detectionEvents.filter((e) => !responses.has(e.event_id)),
    report,
    debrief,
    t0Ms,
  }
}

export function isDetectionEvent(e: Envelope) {
  return DETECTION_EVENTS.has(e.type)
}

export type ToolCallEvent = Envelope<AgentToolCall>

export type ChatEntry =
  | { kind: 'operator'; key: string; id: string; t: number; text: string }
  | { kind: 'agent'; key: string; t: number; text: string; toolCalls: string[]; calls: ToolCallEvent[]; streaming: boolean; replyTo?: string; question?: string; proposal?: Proposal | null }

/** Llamadas a tool de un agente, por el evento que las provocó (`causation_id`), en orden. */
export function callsByCause(toolCalls: ToolCallEvent[], agents: AgentToolCall['agent'][]): Map<string, ToolCallEvent[]> {
  const out = new Map<string, ToolCallEvent[]>()
  for (const c of toolCalls) {
    if (!c.causation_id || !agents.includes(c.payload.agent)) continue
    const list = out.get(c.causation_id) ?? []
    list.push(c)
    out.set(c.causation_id, list)
  }
  for (const list of out.values()) list.sort((a, b) => a.payload.index - b.payload.index || a.seq - b.seq)
  return out
}

/** E6: la consola del monitor agrupa por aviso. Separa las entradas del feed en las de primer
 *  nivel (avisos del detector y respuestas que no responden a un aviso visible) y, por cada aviso,
 *  sus respuestas del monitor (`causation_id` = el aviso), en el orden en que llegaron. */
export function groupByWarning(feed: Envelope[]): { top: Envelope[]; responses: Map<string, Envelope[]> } {
  const detectors = new Set(feed.filter((e) => e.source === 'ai-detector').map((e) => e.event_id))
  const responses = new Map<string, Envelope[]>()
  const top: Envelope[] = []
  for (const e of feed) {
    if (e.source === 'ai-monitor' && e.causation_id && detectors.has(e.causation_id)) {
      const list = responses.get(e.causation_id) ?? []
      list.push(e)
      responses.set(e.causation_id, list)
    } else {
      top.push(e)
    }
  }
  return { top, responses }
}

/** Mensajes de una conversación: pregunta del operador, respuesta completa o, mientras llega,
 *  los trozos acumulados (`chunks` por `reply_to`) y las llamadas a tool que lleva hasta ahora. */
export function chatEntries(
  events: Envelope[],
  conversation: 'monitor' | 'report' | 'instructor',
  chunks: Record<string, string>,
  toolCalls: ToolCallEvent[] = [],
): ChatEntry[] {
  const out: ChatEntry[] = []
  const replied = new Set<string>()
  const questions = new Map<string, string>()
  const calls = callsByCause(toolCalls, [`chat-${conversation}` as AgentToolCall['agent']])
  for (const e of events) {
    if (e.type === 'AgentReply') {
      const p = e.payload as { conversation_id: string; reply_to: string; text: string; tool_calls: string[]; proposal?: Proposal | null }
      if (p.conversation_id === conversation) {
        replied.add(p.reply_to)
        out.push({ kind: 'agent', key: e.event_id, t: e.sim_time, text: p.text, toolCalls: p.tool_calls, calls: calls.get(p.reply_to) ?? [], streaming: false, replyTo: p.reply_to, question: questions.get(p.reply_to), proposal: p.proposal })
      }
    } else if (e.type === 'OperatorMessage') {
      const p = e.payload as { conversation_id: string; text: string }
      if (p.conversation_id === conversation) questions.set(e.event_id, p.text)
      if (p.conversation_id === conversation) out.push({ kind: 'operator', key: e.event_id, id: e.event_id, t: e.sim_time, text: p.text })
    }
  }
  for (const replyTo of new Set([...Object.keys(chunks), ...calls.keys()])) {
    const q = out.find((m) => m.kind === 'operator' && m.id === replyTo)
    if (q && !replied.has(replyTo)) {
      const i = out.indexOf(q)
      out.splice(i + 1, 0, { kind: 'agent', key: `chunk-${replyTo}`, t: q.t, text: chunks[replyTo] ?? '', toolCalls: [], calls: calls.get(replyTo) ?? [], streaming: true })
    }
  }
  return out
}

/** v0.19 (E6, híbrido): estado de la interpretación del LLM de una alerta de la tabla. `none`:
 *  no hay híbrido en la ejecución (o la alerta no es de la tabla); `pending`: aún puede llegar;
 *  `missing`: el informe ya está y no llegó (no pasó las comprobaciones o no se pidió). El
 *  híbrido se reconoce por el primer `AlertEnriched` de la ejecución. */
export type EnrichmentView =
  | { state: 'none' }
  | { state: 'pending' }
  | { state: 'missing' }
  | { state: 'published'; enrichment: AlertEnriched }

export function enrichmentViews(events: Envelope[]): (alert: Anomaly) => EnrichmentView {
  const byAlert = new Map<string, AlertEnriched>()
  let reportDone = false
  for (const e of events) {
    if (e.type === 'AlertEnriched') {
      const p = e.payload as unknown as AlertEnriched
      byAlert.set(p.alert_id, p)
    } else if (e.type === 'ReportGenerated') {
      reportDone = true
    }
  }
  const hybrid = byAlert.size > 0
  return (alert) => {
    const found = byAlert.get(alert.alert_id)
    if (found) return { state: 'published', enrichment: found }
    if (!hybrid || alert.decided_by !== 'table' || alert.fallback) return { state: 'none' }
    return reportDone ? { state: 'missing' } : { state: 'pending' }
  }
}

/** v1.1: cambios de un incidente que el asistente interpreta (un `evidence` o un `severity` no). */
export const INTERPRETED_CHANGES: ReadonlySet<IncidentChange> = new Set<IncidentChange>(['opened', 'state', 'renamed', 'closed'])
/** Plazo (10 s = max(10 s, 2 × p90): en el ensayo con el LLM, interpretaciones ≤ 1,7 s y hipótesis ≈ 5 s; reloj de pared desde que el bus publicó la revisión) para el texto del asistente, el
 *  mismo para todos los tipos de incidente: la tarjeta dice «pending…» hasta entonces y, si no ha
 *  llegado, «No interpretation». Un texto que llega tarde se enseña igualmente. */
export const TEXT_DEADLINE_MS = 10000

/** Estado del texto del asistente sobre un incidente: de su última revisión interpretable. */
export type IncidentText =
  | { state: 'none' } // sin texto y sin reloj con que juzgarlo
  | { state: 'pending' }
  | { state: 'missed' } // pasó el plazo sin texto (o el asistente está apagado)
  | { state: 'published'; enrichment: IncidentEnriched }

export type IncidentView = {
  id: string
  kind: IncidentKind
  /** Última revisión: lo que la tarjeta enseña (estado, severidad, evidencias). */
  latest: Envelope<IncidentUpdated>
  /** Primera revisión (la apertura). */
  opened: Envelope<IncidentUpdated>
  revisions: Envelope<IncidentUpdated>[]
  /** Nombre y estados por los que ha pasado: «Command link lost → Hijack → recovering → closed». */
  path: string[]
  open: boolean
  text: IncidentText
}

/**
 * Los incidentes de la ejecución (v1.1): el último `IncidentUpdated` por `incident_id` con su
 * historia, y el texto del asistente (`IncidentEnriched`) de su última revisión interpretable.
 * `nowMs` (reloj de pared) sirve para decir «pending…» durante `TEXT_DEADLINE_MS` desde que se
 * publicó la revisión y «missed» después, igual para todos los tipos. En orden de apertura.
 */
export function incidents(events: Envelope[], nowMs?: number): IncidentView[] {
  const byId = new Map<string, Envelope<IncidentUpdated>[]>()
  const texts = new Map<string, IncidentEnriched>()
  let reportDone = false
  for (const e of events) {
    if (e.type === 'IncidentUpdated') {
      const p = e.payload as unknown as IncidentUpdated
      const list = byId.get(p.incident_id) ?? []
      list.push(e as unknown as Envelope<IncidentUpdated>)
      byId.set(p.incident_id, list)
    } else if (e.type === 'IncidentEnriched') {
      const p = e.payload as unknown as IncidentEnriched
      texts.set(`${p.incident_id}#${p.revision}`, p)
    } else if (e.type === 'ReportGenerated') {
      reportDone = true
    }
  }
  const out: IncidentView[] = []
  for (const [id, list] of byId) {
    const revisions = [...list].sort((a, b) => a.payload.revision - b.payload.revision)
    const latest = revisions[revisions.length - 1]
    const path: string[] = []
    for (const r of revisions) {
      const p = r.payload
      if (p.change === 'opened' || p.change === 'renamed') path.push(p.name)
      if (p.change === 'state' || p.change === 'closed') path.push(p.state)
    }
    const target = [...revisions].reverse().find((r) => INTERPRETED_CHANGES.has(r.payload.change)) ?? latest
    const candidate = texts.get(`${id}#${target.payload.revision}`)
    // solo vale el texto escrito para esta revisión (mismo instante): uno rezagado de otra ejecución no
    const found = candidate && candidate.as_of_sim_time === target.payload.as_of_sim_time ? candidate : undefined
    let text: IncidentText = { state: 'none' }
    if (found) text = { state: 'published', enrichment: found }
    else if (nowMs !== undefined) {
      const waiting = nowMs - Date.parse(target.ingestion_time) < TEXT_DEADLINE_MS
      text = waiting && !reportDone ? { state: 'pending' } : { state: 'missed' }
    }
    out.push({ id, kind: latest.payload.kind, latest, opened: revisions[0], revisions, path, open: latest.payload.state !== ('closed' satisfies IncidentState), text })
  }
  return out.sort((a, b) => a.opened.payload.opened_at - b.opened.payload.opened_at)
}
