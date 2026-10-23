import { stripFieldValues } from './clean-text'
import type { Cause, Envelope, Severity, SensorSource } from './contracts'

export function formatT(seconds: number) {
  const s = Math.max(0, Math.floor(seconds))
  const mm = String(Math.floor(s / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return `T+${mm}:${ss}`
}

export const CAUSE_LABEL: Record<Cause, string> = {
  WIND: 'Wind',
  HIJACK: 'Hijacking',
  GPS_SPOOFING: 'GPS spoofing',
  SENSOR_FAULT: 'Sensor fault',
  GPS_JAMMING: 'GPS loss/interference',
  UNKNOWN: 'No diagnosis',
}
export const SEVERITY_LABEL: Record<Severity, string> = { low: 'low', medium: 'medium', high: 'high' }
export const SOURCE_LABEL: Record<SensorSource, string> = {
  gps: 'GPS',
  radar: 'Radar',
  meteo: 'Meteo',
  link: 'Link',
  battery: 'Battery',
}

export const CHECK_LABEL: Record<string, string> = {
  gps_alert_recent: 'There is a recent GPS alert',
  gps_radar_disagreed: 'GPS and radar disagree',
  wind_notable: 'The wind is notable',
  wind_with_drift: 'The drift goes with the wind',
  link_checked: 'The command link was checked',
  link_anomalous: 'The command link is anomalous',
}

/** Grupo de filtro del timeline: de dónde viene el evento. */
export type Group = 'gps' | 'radar' | 'meteo' | 'link' | 'battery' | 'mission' | 'detector' | 'monitor' | 'report' | 'chat' | 'sim'
export const GROUPS: { id: Group; label: string }[] = [
  { id: 'gps', label: 'GPS' },
  { id: 'radar', label: 'Radar' },
  { id: 'meteo', label: 'Meteo' },
  { id: 'link', label: 'Link' },
  { id: 'battery', label: 'Battery' },
  { id: 'mission', label: 'Mission' },
  { id: 'detector', label: 'Detector' },
  { id: 'monitor', label: 'Monitor' },
  { id: 'report', label: 'Report' },
  { id: 'chat', label: 'Chat' },
  { id: 'sim', label: 'Simulator' },
]

export function groupOf(e: Envelope): Group {
  switch (e.source) {
    case 'd1-gps':
      return 'gps'
    case 'radar-1':
      return 'radar'
    case 'meteo-1':
      return 'meteo'
    case 'd1-link':
      return 'link'
    case 'd1-bat':
      return 'battery'
    case 'd1-mission':
      return 'mission'
    case 'ai-detector':
      return 'detector'
    case 'ai-monitor':
      return 'monitor'
    case 'ai-report':
      return 'report'
    case 'platform-player':
      return 'sim'
    default:
      return e.source.startsWith('ai-chat') || e.source === 'web-operator' || e.source === 'ai-module' ? 'chat' : 'sim'
  }
}

export type Tone = 'neutral' | 'primary' | 'warning' | 'danger'
export const toneClasses: Record<Tone, string> = {
  neutral: 'bg-muted text-muted-foreground',
  primary: 'bg-primary/10 text-primary',
  warning: 'bg-warning/15 text-foreground',
  danger: 'bg-destructive text-destructive-foreground',
}

export function eventTone(e: Envelope): Tone {
  switch (e.type) {
    case 'DetectionRaised':
    case 'DetectionUpdated':
    case 'FaultInjected':
      return 'warning'
    case 'AnomalyDetected':
      return 'danger'
    case 'PositionUpdated':
    case 'TrackUpdated':
    case 'WindReported':
    case 'LinkStatus':
    case 'BatteryStatus':
      return 'neutral'
    default:
      return 'primary'
  }
}

const n = (v: unknown, d = 1) => (typeof v === 'number' ? v.toFixed(d) : String(v))

/** Resumen corto del payload de un evento para el timeline. */
export function payloadSummary(e: Envelope): string {
  const p = e.payload as Record<string, unknown>
  switch (e.type) {
    case 'PositionUpdated':
      return `x=${n(p.x, 0)} y=${n(p.y, 0)} v=${n(p.speed_mps)} heading=${n(p.heading_deg, 0)}° fix=${p.fix} sats=${p.sats} hdop=${n(p.hdop)}`
    case 'TrackUpdated':
      return `x=${n(p.x, 0)} y=${n(p.y, 0)} v=${n(p.speed_mps)} quality=${n(p.quality, 2)}`
    case 'WindReported':
      return `${n(p.speed_mps)} m/s (gust ${n(p.gust_mps)}) from ${n(p.from_deg, 0)}°`
    case 'LinkStatus':
      return `${p.controller_id} rssi=${n(p.rssi_dbm, 0)} dBm lat=${n(p.latency_ms, 0)} ms`
    case 'BatteryStatus':
      return `${n(p.battery_pct, 0)} % · ${n(p.voltage_v)} V`
    case 'WaypointReached':
      return `${p.waypoint_id}`
    case 'DetectionRaised':
    case 'DetectionUpdated':
      return `${p.detection_id} ${p.rule} (${p.severity}) ${p.message}`
    case 'DetectionCleared':
      return `${p.detection_id} ${p.rule} · lasted ${n(p.duration_s, 0)} s`
    case 'AnomalyDetected':
      return `${p.alert_id} ${p.cause} (${p.severity}) ${p.summary}`
    case 'AlertClosed':
      return `${p.alert_id} ${stripFieldValues(String(p.reason))}`
    case 'DetectionAcknowledged':
      return `${p.detection_id} → ${p.alert_id ?? 'no alert'}`
    case 'FaultInjected':
    case 'FaultCleared':
      return `${p.source} ${p.mode} (${p.origin})`
    case 'InteractiveModeChanged':
      return p.interactive ? 'interactive mode ON' : 'interactive mode OFF'
    case 'SimulationPaused':
      return `reason: ${p.reason}`
    case 'OperatorMessage':
      return `[${p.conversation_id}] ${p.text}`
    case 'AgentReply':
      return `[${p.conversation_id}] ${String(p.text).slice(0, 120)}`
    case 'ReportGenerated':
      return `${p.alerts_count} alerts`
    default:
      return Object.entries(p)
        .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`)
        .join(' ')
        .slice(0, 160)
  }
}

export function distance(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.hypot(b.x - a.x, b.y - a.y)
}

function distToSegment(p: { x: number; y: number }, a: { x: number; y: number }, b: { x: number; y: number }) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const l2 = dx * dx + dy * dy
  if (l2 === 0) return distance(p, a)
  const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2))
  return distance(p, { x: a.x + t * dx, y: a.y + t * dy })
}

/** Distancia de un punto a la polilínea de la ruta planificada. */
export function crossTrack(p: { x: number; y: number }, route: { x: number; y: number }[]) {
  let min = Infinity
  for (let i = 0; i < route.length - 1; i++) min = Math.min(min, distToSegment(p, route[i], route[i + 1]))
  return min
}
