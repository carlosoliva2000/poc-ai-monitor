// Tipos de `contracts/eventos.md` (§2 sobre, §4 payloads, §5 WebSocket, §6 API). Escritos a mano:
// si cambia el contrato, cambian aquí.

export type Severity = 'low' | 'medium' | 'high'
/** Fase de una alerta (v0.14): `recovering` cuando el problema ha terminado y la situación vuelve a la normalidad. */
export type Phase = 'active' | 'recovering'
export type SensorSource = 'gps' | 'radar' | 'meteo' | 'link' | 'battery'
export type FaultMode = 'mute' | 'loss'
export type Cause = 'WIND' | 'HIJACK' | 'GPS_SPOOFING' | 'SENSOR_FAULT' | 'GPS_JAMMING' | 'UNKNOWN'
/** Quién decidió una alerta (v0.19, E6): la tabla de decisión del módulo o el LLM del monitor. */
export type DecidedBy = 'table' | 'llm'
export type Conversation = 'monitor' | 'report' | 'instructor'
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
  /** Sin fix (`fix: none`) el receptor no da posición, altitud, velocidad ni rumbo: `null` (v1.0). */
  x: number | null
  y: number | null
  alt_m: number | null
  speed_mps: number | null
  /** Rumbo sobre el suelo (v1.0; antes `heading_deg`). */
  course_deg: number | null
  fix: 'none' | '2d' | '3d'
  sats: number
  hdop: number
}
export type Track = { x: number; y: number; speed_mps: number; course_deg: number }
export type Wind = { speed_mps: number; from_deg: number }
/** Enlace medido por nuestra estación (v1.0): con el enlace caído, `rssi_dbm` y `latency_ms` son `null`. */
export type Link = { rssi_dbm: number | null; latency_ms: number | null; packet_loss_pct?: number | null }
export type Battery = { battery_pct: number; power_w?: number | null; time_remaining_s?: number | null }
export type GnssStatus = { h_acc_m: number; cn0_dbhz: number; agc_db: number }
export type AutopilotStatus = {
  mode: 'mission' | 'failsafe_return' | 'failsafe_hold' | 'failsafe_land'
  heading_deg: number
  airspeed_mps: number
  wind_est_speed_mps: number
  wind_est_from_deg: number
  innovation_m: number | null
  est_x: number
  est_y: number
  ground_speed_mps: number
  course_deg: number
}
export type Waypoint = { id: string; x: number; y: number; eta_s: number }

export type Detection = {
  detection_id: string
  rule: 'ROUTE_DEVIATION' | 'SOURCE_DISCREPANCY' | 'SOURCE_SILENT' | 'GPS_DEGRADED' | 'LINK_ANOMALY'
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
  /** Ausente en las ejecuciones anteriores a la v0.14: se lee como `active`. */
  phase?: Phase
  /** v0.19 (E6): quién la decidió; ausente = el LLM (las alertas anteriores a la v0.19). */
  decided_by?: DecidedBy | null
  /** v0.19 (E6): la fila de la tabla de decisión que dio la causa (`C05`…), solo con `table`. */
  rule_id?: string | null
}
export type AlertClosed = { alert_id: string; reason: string; as_of_sim_time: number }
/** v0.19 (E6, híbrido): hipótesis del LLM en una alerta UNKNOWN. No es un diagnóstico. */
export type EnrichHypothesis = { cause: Cause; confidence: number; evidence_event_ids: string[] }
/** v0.19 (E6, híbrido): interpretación del LLM de una alerta de la tabla (fuente `ai-enricher`,
 *  `causation_id` = la alerta). No cambia la alerta. */
export type AlertEnriched = {
  alert_id: string
  text: string
  hypothesis: EnrichHypothesis | null
  decided_by: 'llm'
  as_of_sim_time: number
  alert_status: 'open' | 'superseded' | 'closed'
}
/** v1.1: tipo de incidente del monitor de situación. `UNDETERMINED` es una salida del sistema
 *  con confianza baja, no una etiqueta de la verdad. */
export type IncidentKind =
  | 'WIND' | 'GPS_SPOOFING' | 'HIJACK' | 'LINK_LOSS' | 'LINK_DEGRADED' | 'GPS_DEGRADED' | 'GPS_NO_FIX'
  | 'DEAD_RECKONING' | 'SOURCE_SILENT' | 'RADAR_OUT_OF_RANGE' | 'BATTERY_LOW' | 'BATTERY_CRITICAL'
  | 'CANNOT_REACH_HOME' | 'FAILSAFE' | 'UNDETERMINED'
export type IncidentState = 'open' | 'recovering' | 'closed'
export type IncidentChange = 'opened' | 'state' | 'renamed' | 'severity' | 'evidence' | 'closed'
export type ConfidenceLevel = 'confirmed' | 'probable' | 'possible'
export type EvidenceValue = number | string | boolean | null
export type EvidenceCondition = { feature: string; op: '>=' | '<=' | '>' | '<' | '==' | '!='; threshold: EvidenceValue; value: EvidenceValue }
/** Un paso del camino de la tabla: faceta → estado → fila → condiciones con su valor. */
export type EvidenceItem = { facet: string; state: string; rule_id: string; conditions: EvidenceCondition[] }
export type ContextItem = { feature: string; value: EvidenceValue }
/** v1.1: estado de un incidente, un evento por transición (fuente `ai-monitor`). La web se
 *  queda con el último por `incident_id`. */
export type IncidentUpdated = {
  incident_id: string
  revision: number
  kind: IncidentKind
  /** v1.3: la fuente (SOURCE_SILENT) o el modo (FAILSAFE); null en el resto. */
  subject?: string | null
  name: string
  state: IncidentState
  severity: Severity
  confidence: ConfidenceLevel
  opened_at: number
  as_of_sim_time: number
  change: IncidentChange
  evidence: EvidenceItem[]
  context: ContextItem[]
  checks: string[]
  evidence_event_ids: string[]
  decided_by: 'table'
  table: string
}
/** v1.4: qué fuente comprobar (lista cerrada, para poder medirla). */
export type HypothesisTarget = 'gps' | 'receiver' | 'radar' | 'meteo' | 'link' | 'battery' | 'autopilot'
export type RankedCause = { kind: IncidentKind; supports: string[]; missing: string[] }
export type HypothesisCheck = { target: HypothesisTarget; text: string }
/** Hipótesis del asistente sobre un `UNDETERMINED` (no es un diagnóstico). v1.4: `ranked` (la
 *  primera es `kind`) y `checks` pueden ir vacíos (hipótesis de la v1.1). */
export type IncidentHypothesis = { kind: IncidentKind; confidence: 'possible'; evidence_event_ids: string[]; ranked?: RankedCause[]; checks?: HypothesisCheck[] }
/** v1.1: texto del asistente sobre una revisión de un incidente (fuente `ai-enricher`,
 *  `causation_id` = el `IncidentUpdated`). No cambia el incidente. */
export type IncidentEnriched = {
  incident_id: string
  revision: number
  state: IncidentState
  text: string
  hypothesis: IncidentHypothesis | null
  role: 'explain' | 'hypothesis'
  decided_by: 'llm'
  as_of_sim_time: number
  /** v1.4: modelo y huella de los prompts con que se escribió. */
  model?: string | null
  prompt_sha?: string | null
}
/** v1.4: lo programado en el ejercicio (la verdad: solo el proceso del instructor lo recibe). */
export type Inject = { id: string; type: string; source: string | null; start_s: number; end_s: number }
export type ExerciseInjects = { injects: Inject[] }
/** v1.4: debriefing del instructor (`ai.instructor`), con la verdad. */
export type DebriefGenerated = { run_id: string; markdown: string; injects_count: number }
export type DetectionAcknowledged = {
  detection_id: string
  alert_id: string | null
  reason: string
  as_of_sim_time: number
  fallback: boolean
}
export type ReportGenerated = { run_id: string; markdown: string; alerts_count: number }
/** Viento del instructor en curso que la web manda con la pregunta al agente del instructor (v0.18). */
export type ActiveWindContext = { from_deg: number; speed_mps: number; remaining_s: number | null }
export type OperatorMessage = { conversation_id: Conversation; text: string; context?: { active_wind: ActiveWindContext | null } }
/** Propuesta del agente del instructor (v0.18): no se aplica hasta que el instructor confirma. */
export type Proposal = { command: InstructorCommandName; params: WindParams | null; defaults_used: string[] }
export type AgentReply = { conversation_id: Conversation; reply_to: string; text: string; tool_calls: string[]; proposal?: Proposal | null }
export type AgentReplyChunk = { conversation_id: Conversation; reply_to: string; delta: string }
export type AgentActivity = {
  agent: 'monitor' | 'report' | 'chat-monitor' | 'chat-report' | 'chat-instructor' | 'assistant' | 'translator' | 'debrief'
  state: 'started' | 'finished'
  invocation_id: string
  causation_id: string | null
}
export type ToolCallStatus = 'ok' | 'error' | 'rejected' | 'aborted'
/** Una llamada a tool de un agente (efímero, solo para depurar; `arguments` y `result` van recortados). */
export type AgentToolCall = {
  agent: AgentActivity['agent']
  invocation_id: string
  index: number
  iteration: number
  tool: string
  arguments: string
  status: ToolCallStatus
  result: string | null
  error: string | null
  truncated: boolean
}
/** Viento de un comando del instructor (v0.18): m/s y grados; `from_deg` es la procedencia. */
export type WindParams = { from_deg: number; speed_mps: number; ramp_s: number; duration_s: number | null }
export type InstructorCommandName = 'set_wind' | 'cancel_wind'
/** Payload de `InstructorCommand` y valor de `control` → `instructor`. */
export type InstructorCommand = {
  command: InstructorCommandName
  params: WindParams | null
  issued_by: 'panel' | 'llm' | 'scenario'
  text: string | null
}
export type SimulationStarted = { scenario: string; run_id: string; duration_s: number; total_events: number }
export type SimulationPaused = { reason: 'user' }
export type FaultEvent = { source: SensorSource; mode: FaultMode; origin: 'manual' | 'scenario' }

export type ActiveFault = FaultEvent
export type PlayerState = {
  op: 'state'
  status: PlayerStatus
  scenario: string | null
  run_id: string | null
  sim_time: number
  speed: number
  interactive: boolean
  active_faults: ActiveFault[]
  cursor: number
  total_events: number
}

/** Última posición real (fuera del bus; solo llega si se pide con `truth_feed`). `heading_deg` es el
 *  rumbo del morro; `course_deg`, el rumbo sobre el suelo. */
export type TruthMessage = {
  op: 'truth'
  run_id: string | null
  t: number
  x: number
  y: number
  heading_deg: number
  course_deg: number
  speed_mps: number
}

export type ServerMessage =
  | { op: 'event'; event: Envelope }
  | PlayerState
  | TruthMessage
  | { op: 'error'; message: string }

export type ControlMessage =
  | { action: 'load'; value: string }
  | { action: 'play' | 'pause' | 'step' | 'reset'; value?: null }
  | { action: 'speed'; value: number }
  | { action: 'interactive'; value: boolean }
  | { action: 'fault'; value: { source: SensorSource; mode: FaultMode; active: boolean } }
  | { action: 'instructor'; value: InstructorCommand }

export type ScenarioInfo = { name: string; description: string; generated: boolean; duration_s: number | null }
export type PlanFile = {
  mission_id: string
  cruise_speed_mps: number
  altitude_m: number
  acceptance_radius_m: number
  duration_s: number
  waypoints: Waypoint[]
  trajectory: { t: number; x: number; y: number; speed_mps: number; heading_deg: number }[]
  /** Posición y alcance del radar. */
  radar?: { x: number; y: number; max_range_m: number }
}
/** Emisor o estación ajena con posición (solo en la verdad y en la vista del instructor). */
export type TruthEmitter = { id: string; kind: 'spoofer' | 'jammer' | 'hijacker'; x: number; y: number }
export type TruthFile = {
  duration_s: number
  trajectory: { t: number; x: number; y: number; speed_mps: number; heading_deg: number; course_deg: number; mode?: string; link_up?: boolean; emitters_active?: string[] }[]
  emitters?: TruthEmitter[]
  wind: { t: number; speed_mps: number; from_deg: number }[]
}

export const PLATFORM_HTTP = 'http://127.0.0.1:8100/api'
export const PLATFORM_WS = 'ws://127.0.0.1:8100/ws'
export const SPEEDS = [0.5, 1, 2, 4, 8, 16] as const
export const SOURCES: SensorSource[] = ['gps', 'radar', 'meteo', 'link', 'battery']
