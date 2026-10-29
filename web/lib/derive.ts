import type {
  AgentToolCall,
  Anomaly,
  AlertClosed,
  Battery,
  Detection,
  DetectionAcknowledged,
  DetectionCleared,
  Envelope,
  Link,
  Position,
  Track,
  Wind,
} from './contracts'

export type Sample = { t: number; x: number; y: number }
export type GpsSample = Sample & { heading: number; speed: number; alt: number; fix: Position['fix']; sats: number; hdop: number }
export type RadarSample = Sample & { speed: number }

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
  /** Motivo de la última pausa si el reproductor sigue pausado por ella. */
  pauseReason: 'user' | 'waiting_agent' | null
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
  let lastWaypoint = 'BASE'
  let missionDone = false
  let report: Derived['report'] = null
  let pauseReason: Derived['pauseReason'] = null
  let t0Ms: number | null = null
  const order: string[] = []

  for (const e of events) {
    if (t0Ms === null) t0Ms = Date.parse(e.event_time) - e.sim_time * 1000
    switch (e.type) {
      case 'PositionUpdated': {
        const p = e.payload as unknown as Position
        gps.push({ t: e.sim_time, x: p.x, y: p.y, heading: p.heading_deg, speed: p.speed_mps, alt: p.alt_m, fix: p.fix, sats: p.sats, hdop: p.hdop })
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
      case 'SimulationPaused':
        pauseReason = (e.payload as { reason: 'user' | 'waiting_agent' }).reason
        break
      case 'SimulationResumed':
      case 'SimulationStarted':
        pauseReason = null
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
    pauseReason,
    t0Ms,
  }
}

export function isDetectionEvent(e: Envelope) {
  return DETECTION_EVENTS.has(e.type)
}

export type ToolCallEvent = Envelope<AgentToolCall>

export type ChatEntry =
  | { kind: 'operator'; key: string; id: string; t: number; text: string }
  | { kind: 'agent'; key: string; t: number; text: string; toolCalls: string[]; calls: ToolCallEvent[]; streaming: boolean }

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

/** Mensajes de una conversación: pregunta del operador, respuesta completa o, mientras llega,
 *  los trozos acumulados (`chunks` por `reply_to`) y las llamadas a tool que lleva hasta ahora. */
export function chatEntries(
  events: Envelope[],
  conversation: 'monitor' | 'report',
  chunks: Record<string, string>,
  toolCalls: ToolCallEvent[] = [],
): ChatEntry[] {
  const out: ChatEntry[] = []
  const replied = new Set<string>()
  const calls = callsByCause(toolCalls, [conversation === 'monitor' ? 'chat-monitor' : 'chat-report'])
  for (const e of events) {
    if (e.type === 'AgentReply') {
      const p = e.payload as { conversation_id: string; reply_to: string; text: string; tool_calls: string[] }
      if (p.conversation_id === conversation) {
        replied.add(p.reply_to)
        out.push({ kind: 'agent', key: e.event_id, t: e.sim_time, text: p.text, toolCalls: p.tool_calls, calls: calls.get(p.reply_to) ?? [], streaming: false })
      }
    } else if (e.type === 'OperatorMessage') {
      const p = e.payload as { conversation_id: string; text: string }
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
