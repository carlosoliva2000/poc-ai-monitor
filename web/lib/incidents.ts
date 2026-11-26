// Etiquetas y formato de los incidentes del monitor de situación (contrato v1.1). Puro y con
// pruebas: la tarjeta pinta lo que sale de aquí.
import type { ConfidenceLevel, ContextItem, EvidenceCondition, EvidenceItem, EvidenceValue, IncidentKind, IncidentState } from './contracts'

export const KIND_LABEL: Record<IncidentKind, string> = {
  WIND: 'Wind beyond limit',
  GPS_SPOOFING: 'GPS spoofing',
  HIJACK: 'Hijack',
  LINK_LOSS: 'Command link lost',
  LINK_DEGRADED: 'Command link degraded',
  GPS_DEGRADED: 'GPS degraded',
  GPS_NO_FIX: 'GPS position lost',
  DEAD_RECKONING: 'Dead-reckoning drift',
  SOURCE_SILENT: 'Source silent',
  RADAR_OUT_OF_RANGE: 'Drone beyond radar range',
  BATTERY_LOW: 'Battery low',
  BATTERY_CRITICAL: 'Battery critical',
  CANNOT_REACH_HOME: 'Cannot reach home',
  FAILSAFE: 'Drone failsafe',
  UNDETERMINED: 'Undetermined deviation',
}

export const STATE_LABEL: Record<IncidentState, string> = { open: 'open', recovering: 'recovering', closed: 'closed' }

export const CONFIDENCE_LABEL: Record<ConfidenceLevel, string> = { confirmed: 'confirmed', probable: 'probable', possible: 'possible' }
export const CONFIDENCE_TITLE: Record<ConfidenceLevel, string> = {
  confirmed: 'Confirmed: the rule that decided it is very reliable',
  probable: 'Probable: the rule that decided it is reliable but not conclusive',
  possible: 'Possible: a weak match, to be checked',
}

const FACET_LABEL: Record<string, string> = {
  'gps.availability': 'GPS signal',
  'gps.quality': 'GPS quality',
  'gps.integrity': 'GPS integrity',
  'link.availability': 'Command link',
  'link.quality': 'Command link quality',
  'environment.wind': 'Wind',
  'radar.availability': 'Radar',
  'meteo.availability': 'Weather station',
  'battery.availability': 'Battery telemetry',
  'battery.level': 'Battery level',
  'battery.endurance': 'Battery endurance',
  'drone.mode': 'Autopilot mode',
  'drone.situation': 'Drone vs route',
  'drone.cause': 'Cause of the deviation',
}

/** Estados de las facetas (y de las entradas de la tabla) en palabras. */
const VALUE_LABEL: Record<string, string> = {
  spoofed: 'spoofed',
  reliable: 'reliable',
  lost: 'lost',
  connected: 'connected',
  calm: 'calm',
  notable: 'notable',
  beyond_limit: 'beyond limit',
  on_route: 'on route',
  deviated: 'deviated',
  returning: 'returning',
  normal: 'normal',
  good: 'good',
  degraded: 'degraded',
  no_fix: 'no fix',
  no_data: 'no data',
  out_of_range: 'out of range',
  low: 'low',
  critical: 'critical',
  sufficient: 'sufficient',
  cannot_reach_home: 'cannot reach home',
  mission: 'mission',
  failsafe_hold: 'failsafe: holding',
  failsafe_return: 'failsafe: returning home',
  failsafe_land: 'failsafe: landing',
  foreign_control: 'foreign control',
  spoofed_position: 'spoofed position',
  dead_reckoning: 'dead reckoning',
  wind: 'wind',
  unexplained: 'undetermined',
  confirmed: 'confirmed',
  probable: 'probable',
  possible: 'possible',
  'n/a': 'not applicable',
  '?': 'unknown',
  ...KIND_LABEL,
}

type Feature = { label: string; unit?: string; signed?: boolean }
const FEATURES: Record<string, Feature> = {
  // tablas a mano del vídeo
  cn0_rise_db: { label: 'C/N0 over reference', unit: ' dB', signed: true },
  agc_drop_db: { label: 'AGC vs reference', unit: ' dB', signed: true },
  tele_gap_s: { label: 'No telemetry for', unit: ' s' },
  link_loss_pct: { label: 'Packet loss', unit: ' %' },
  wind_est_mps: { label: 'Estimated wind', unit: ' m/s' },
  wind_high_s: { label: 'Wind beyond limit for', unit: ' s' },
  route_dev_m: { label: 'Distance to the route', unit: ' m' },
  radar_route_dev_m: { label: 'Radar distance to the route', unit: ' m' },
  previous: { label: 'Before' },
  link: { label: 'Command link' },
  gps_integrity: { label: 'GPS' },
  situation: { label: 'Drone' },
  wind: { label: 'Wind' },
  telemetry: { label: 'Telemetry' },
  deviation_source: { label: 'Deviation measured by' },
  // tablas aprendidas: las ratios son relativas a los activos (límite del dron, σ del sensor, periodo)
  agc_vs_nominal_db: { label: 'AGC vs nominal', unit: ' dB', signed: true },
  cn0_vs_nominal_db: { label: 'C/N0 vs nominal', unit: ' dB', signed: true },
  age_gps_p: { label: 'Time since the last GPS message', unit: ' periods' },
  age_gnss_p: { label: 'Time since the last receiver status', unit: ' periods' },
  age_autopilot_p: { label: 'Time since the last autopilot status', unit: ' periods' },
  age_radar_p: { label: 'Time since the last radar track', unit: ' periods' },
  age_meteo_p: { label: 'Time since the last weather report', unit: ' periods' },
  age_battery_p: { label: 'Time since the last battery report', unit: ' periods' },
  tele_gap_p: { label: 'No drone telemetry for', unit: ' periods' },
  battery_pct: { label: 'Battery', unit: ' %' },
  cause_active: { label: 'A cause was already active' },
  dev_hi_m: { label: 'Deviation to start (hysteresis)', unit: ' m' },
  dev_lo_m: { label: 'Deviation to finish (hysteresis)', unit: ' m' },
  gps_fix_3d: { label: '3D fix' },
  gps_hacc_m: { label: 'GPS accuracy', unit: ' m' },
  gps_hdop: { label: 'GPS HDOP' },
  gps_radar_avg_sigma: { label: 'GPS–radar disagreement (mean, in sigmas)' },
  radar_dev_sigma: { label: 'Radar distance to the route (sigmas)' },
  radar_dev_sigma_max30: { label: 'Radar distance to the route, last 30 s (sigmas)' },
  radar_dev_slope_cruise: { label: 'Radar approach to the route (cruise speeds)', signed: true },
  radar_range_ratio: { label: 'Radar range used' },
  ground_speed_over_cruise: { label: 'Ground speed over cruise' },
  home_time_ratio: { label: 'Time to get home over time left' },
  link_latency_ms: { label: 'Link latency', unit: ' ms' },
  link_latency_vs_base: { label: 'Link latency over its normal' },
  link_rssi_dbm: { label: 'Link signal', unit: ' dBm' },
  mode_hold: { label: 'Holding position' },
  mode_return: { label: 'Returning home' },
  mode_land: { label: 'Landing' },
  station_wind_over_limit: { label: 'Station wind over the drone limit' },
  wind_est_mean5_over_limit: { label: 'Estimated wind (5 s mean) over the drone limit' },
  wind_est_over_airspeed: { label: 'Estimated wind over the drone top speed' },
  wind_est_over_limit: { label: 'Estimated wind over the drone limit' },
  // contexto
  suspected_cause: { label: 'Suspected cause' },
  possible_cause: { label: 'Possible cause' },
  telemetry_gap_s: { label: 'No telemetry for', unit: ' s' },
}

/** Entradas 0/1 (las aprendidas las cortan en 0,5): se leen como sí o no, no como una comparación. */
const FLAGS = new Set(['mode_hold', 'mode_return', 'mode_land', 'gps_fix_3d'])
const isFlagCut = (feature: string, op: string, threshold: unknown) => FLAGS.has(feature) && threshold === 0.5 && (op === '<=' || op === '>')

export const facetLabel = (facet: string) => FACET_LABEL[facet] ?? facet
export const valueLabel = (value: string) => VALUE_LABEL[value] ?? value
export const featureLabel = (feature: string) => FEATURES[feature]?.label ?? feature

const MINUS = '−'
const SYMBOL: Record<string, string> = { '>=': '≥', '<=': '≤' }

/** Un valor para personas: enteros tal cual y un decimal (el resto, redondeado). */
function number(v: number, signed = false): string {
  const text = Number.isInteger(v) ? String(Math.abs(v)) : Math.abs(v).toFixed(1)
  if (v < 0) return `${MINUS}${text}`
  return signed && v > 0 ? `+${text}` : text
}

/** Un umbral para personas: los aprendidos vienen con 15 decimales; se enseñan a lo sumo con 2, sin ceros de más. */
function cut(v: number): string {
  const text = String(Number(Math.abs(v).toFixed(2)))
  return v < 0 && Number(text) !== 0 ? `${MINUS}${text}` : text
}

function value(v: EvidenceValue, feature: string, signed = false): string {
  if (v === null) return '—'
  if (typeof v === 'number') return `${number(v, signed)}${FEATURES[feature]?.unit ?? ''}`
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  return valueLabel(v)
}

/** Una condición con su valor en ese instante: «C/N0 over reference +9.3 dB ≥ 4». */
export function describeCondition(c: EvidenceCondition): string {
  const label = featureLabel(c.feature)
  const signed = FEATURES[c.feature]?.signed ?? false
  if (c.op === '==') return `${label}: ${value(c.value, c.feature)}`
  if (c.op === '!=') return `${label}: ${c.threshold === null ? 'has data' : `not ${value(c.threshold as EvidenceValue, c.feature)}`}`
  if (isFlagCut(c.feature, c.op, c.threshold)) return `${label}: ${c.value === null ? 'no data' : c.op === '>' ? 'yes' : 'no'}`
  const threshold = typeof c.threshold === 'number' ? cut(c.threshold) : String(c.threshold)
  return `${label} ${value(c.value, c.feature, signed)} ${SYMBOL[c.op] ?? c.op} ${threshold}`
}

/** Lo que no decide pero ayuda: «Estimated wind 2.6 m/s». */
export function describeContext(c: ContextItem): string {
  return `${featureLabel(c.feature)} ${c.feature === 'deviation_source' ? `the ${c.value === 'gps' ? 'GPS' : String(c.value)}` : value(c.value, c.feature)}`
}

/** Una celda de una fila de las reglas como condición: `>= 4` → «C/N0 over reference ≥ 4 dB». Entiende también las
 *  celdas de las tablas aprendidas: `> 3, null` («o sin dato»), el rango `(a..b]` y `not(null)`. */
export function describeCell(feature: string, cell: string): string {
  const label = featureLabel(feature)
  const unit = FEATURES[feature]?.unit ?? ''
  const text = cell.trim()
  const noData = /^(.*),\s*null$/.exec(text)
  if (noData && !text.startsWith('"')) return `${describeCell(feature, noData[1])} or no data`
  const comparison = /^(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)$/.exec(text)
  if (comparison) {
    if (isFlagCut(feature, comparison[1], Number(comparison[2]))) return `${label}: ${comparison[1] === '>' ? 'yes' : 'no'}`
    return `${label} ${SYMBOL[comparison[1]] ?? comparison[1]} ${cut(Number(comparison[2]))}${unit}`
  }
  const range = /^\(\s*(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)\s*\]$/.exec(text)
  if (range) return `${label} between ${cut(Number(range[1]))} and ${cut(Number(range[2]))}${unit}`
  if (text === 'not(null)') return `${label}: has data`
  if (text === 'true') return `${label}: yes`
  if (text === 'false') return `${label}: no`
  if (text === 'null') return `${label}: no data`
  const words = text.split(',').map((w) => valueLabel(w.trim().replace(/^"|"$/g, '')))
  return `${label}: ${words.join(' or ')}`
}

/** Lo que dice una fila al encajar: `{state: spoofed}` → «spoofed»; una fila aprendida añade el nivel de confianza
 *  y su probabilidad: `{state: spoofed, confidence: confirmed, probability: 0.9986}` → «spoofed · confirmed (p 0.9986)»;
 *  `{kind: HIJACK, confidence: probable}` → «Hijack · probable». */
export function describeOutput(then: Record<string, string>): string {
  if ('kind' in then) return then.kind === 'none' ? 'no incident' : `${valueLabel(then.kind)} · ${then.confidence}`
  if ('state' in then) {
    const level = then.confidence ? ` · ${valueLabel(then.confidence)}` : ''
    const p = then.probability !== undefined && then.probability !== '' ? ` (p ${Number(then.probability).toFixed(2)})` : ''
    return `${valueLabel(then.state)}${level}${p}`
  }
  return Object.values(then).map(valueLabel).join(' · ')
}

/** El respaldo de una fila aprendida (instantes y variantes del entrenamiento), para el título; `null` si no lo tiene. */
export function describeSupport(then: Record<string, string>): string | null {
  if (!then.instants) return null
  return `Training support: ${Number(then.instants).toLocaleString('en-US')} instants in ${then.variants ?? '?'} variants`
}

export type EvidenceRow = { facetId: string; facet: string; state: string; rule: string; conditions: string[] }

export function evidenceRows(evidence: EvidenceItem[]): EvidenceRow[] {
  return evidence.map((item) => ({
    facetId: item.facet,
    facet: facetLabel(item.facet),
    state: valueLabel(item.state),
    rule: item.rule_id,
    conditions: item.conditions.map(describeCondition),
  }))
}

/** «45 s», «1 min 12 s». */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s`
}
