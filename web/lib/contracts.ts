// Tipos de `contracts/eventos.md` (§2 sobre, §4 payloads, §5 WebSocket, §6 API). Escritos a mano:
// si cambia el contrato, cambian aquí.

export type Severity = 'low' | 'medium' | 'high'
export type SensorSource = 'gps' | 'radar' | 'meteo' | 'link' | 'battery'
export type FaultMode = 'mute' | 'loss'
export type Cause = 'WIND' | 'HIJACK' | 'GPS_SPOOFING' | 'SENSOR_FAULT' | 'GPS_JAMMING' | 'UNKNOWN'
export type Conversation = 'monitor' | 'report'
export type PlayerStatus = 'idle' | 'running' | 'paused' | 'finished'

export type Envelope<P = Record<string, unknown>> = {
  event_id: string
  topic: string
  type: string
  source: string
  asset: string | null
  seq: number
  sim_time: number
  event_time: string
  ingestion_time: string
  causation_id: string | null
  ephemeral: boolean
  payload: P
}

export type EventDraft = Omit<Envelope, 'seq' | 'ingestion_time'>

export type Position = {
  x: number
  y: number
  alt_m: number
  speed_mps: number
  heading_deg: number
  fix: 'none' | '2d' | '3d'
  sats: number
  hdop: number
}
export type Track = { radar_id: string; x: number; y: number; speed_mps: number; course_deg: number; quality: number }
export type Wind = { station_id: string; speed_mps: number; gust_mps: number; from_deg: number }
export type Link = { controller_id: string; rssi_dbm: number; latency_ms: number }
export type Battery = { battery_pct: number; voltage_v: number }
export type Waypoint = { id: string; x: number; y: number; eta_s: number }

export type Detection = {
  detection_id: string
  rule: 'ROUTE_DEVIATION' | 'SOURCE_DISCREPANCY' | 'SOURCE_SILENT' | 'GPS_DEGRADED'
  severity: Severity
  value: number
  threshold: number
  unit: string
  source: SensorSource | null
  window: { since: number; until: number }
  trigger_event_ids: string[]
  message: string
}
export type DetectionCleared = { detection_id: string; rule: Detection['rule']; duration_s: number; max_value: number }

export type Checks = {
  gps_alert_recent: boolean
  gps_radar_disagreed: boolean
  wind_notable: boolean
  wind_with_drift: boolean
  link_checked: boolean
  link_anomalous: boolean | null
}
export type Anomaly = {
  alert_id: string
  detection_ids: string[]
  cause: Cause
  severity: Severity
  confidence: number
  summary: string
  explanation: string
  recommendation: string
  evidence_event_ids: string[]
  supersedes: string | null
  as_of_sim_time: number
  fallback: boolean
  checks: Checks | null
}
export type AlertClosed = { alert_id: string; reason: string; as_of_sim_time: number }
export type DetectionAcknowledged = {
  detection_id: string
  alert_id: string | null
  reason: string
  as_of_sim_time: number
  fallback: boolean
}
export type ReportGenerated = { run_id: string; markdown: string; alerts_count: number }
export type OperatorMessage = { conversation_id: Conversation; text: string }
export type AgentReply = { conversation_id: Conversation; reply_to: string; text: string; tool_calls: string[] }
export type AgentReplyChunk = { conversation_id: Conversation; reply_to: string; delta: string }
export type AgentActivity = {
  agent: 'monitor' | 'report' | 'chat-monitor' | 'chat-report'
  state: 'started' | 'finished'
  invocation_id: string
  causation_id: string | null
}
export type SimulationStarted = { scenario: string; run_id: string; duration_s: number; total_events: number }
export type SimulationPaused = { reason: 'user' | 'waiting_agent' }
export type FaultEvent = { source: SensorSource; mode: FaultMode; origin: 'manual' | 'scenario' }

export type ActiveFault = FaultEvent
export type PlayerState = {
  op: 'state'
  status: PlayerStatus
  scenario: string | null
  run_id: string | null
  sim_time: number
  speed: number
  wait_agent: boolean
  interactive: boolean
  active_faults: ActiveFault[]
  cursor: number
  total_events: number
}

export type ServerMessage =
  | { op: 'event'; event: Envelope }
  | PlayerState
  | { op: 'error'; message: string }

export type ControlMessage =
  | { action: 'load'; value: string }
  | { action: 'play' | 'pause' | 'step' | 'reset'; value?: null }
  | { action: 'speed'; value: number }
  | { action: 'wait_agent' | 'interactive'; value: boolean }
  | { action: 'fault'; value: { source: SensorSource; mode: FaultMode; active: boolean } }

export type ScenarioInfo = { name: string; description: string; generated: boolean; duration_s: number | null }
export type PlanFile = {
  mission_id: string
  cruise_speed_mps: number
  altitude_m: number
  acceptance_radius_m: number
  duration_s: number
  waypoints: Waypoint[]
  trajectory: { t: number; x: number; y: number; speed_mps: number; heading_deg: number }[]
}
export type TruthFile = {
  duration_s: number
  trajectory: { t: number; x: number; y: number; speed_mps: number; heading_deg: number; course_deg: number }[]
  wind: { t: number; speed_mps: number; gust_mps: number; from_deg: number }[]
}

export const PLATFORM_HTTP = 'http://127.0.0.1:8100/api'
export const PLATFORM_WS = 'ws://127.0.0.1:8100/ws'
export const SPEEDS = [0.5, 1, 2, 4, 8, 16] as const
export const SOURCES: SensorSource[] = ['gps', 'radar', 'meteo', 'link', 'battery']
