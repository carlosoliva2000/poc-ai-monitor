// Etiquetas y formato de los incidentes del monitor de situación (contrato v1.1). Puro y con
// pruebas: la tarjeta pinta lo que sale de aquí.
import type { ConfidenceLevel, ContextItem, EvidenceCondition, EvidenceItem, EvidenceValue, IncidentKind, IncidentState } from './contracts'

export const KIND_LABEL: Record<IncidentKind, string> = {
  WIND: 'Wind beyond limit',
  GPS_SPOOFING: 'GPS spoofing',
  HIJACK: 'Hijack',
  LINK_LOSS: 'Command link lost',
  GPS_DEGRADED: 'GPS degraded',
  DEAD_RECKONING: 'Dead reckoning',
  BATTERY: 'Battery',
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
  'gps.integrity': 'GPS integrity',
  'link.availability': 'Command link',
  'environment.wind': 'Wind',
  'drone.situation': 'Drone vs route',
  'drone.cause': 'Decisive rule',
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
  '?': 'unknown',
  ...KIND_LABEL,
}

type Feature = { label: string; unit?: string; signed?: boolean }
const FEATURES: Record<string, Feature> = {
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
}

export const facetLabel = (facet: string) => FACET_LABEL[facet] ?? facet
export const valueLabel = (value: string) => VALUE_LABEL[value] ?? value
export const featureLabel = (feature: string) => FEATURES[feature]?.label ?? feature

const MINUS = '−'
const SYMBOL: Record<string, string> = { '>=': '≥', '<=': '≤' }

function number(v: number, signed = false): string {
  const text = Number.isInteger(v) ? String(Math.abs(v)) : Math.abs(v).toFixed(1)
  if (v < 0) return `${MINUS}${text}`
  return signed && v > 0 ? `+${text}` : text
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
  const threshold = typeof c.threshold === 'number' ? number(c.threshold) : String(c.threshold)
  return `${label} ${value(c.value, c.feature, signed)} ${SYMBOL[c.op] ?? c.op} ${threshold}`
}

/** Lo que no decide pero ayuda: «Estimated wind 2.6 m/s». */
export function describeContext(c: ContextItem): string {
  return `${featureLabel(c.feature)} ${c.feature === 'deviation_source' ? `the ${c.value === 'gps' ? 'GPS' : String(c.value)}` : value(c.value, c.feature)}`
}

/** Una celda de una fila de las reglas como condición: `>= 4` → «C/N0 over reference ≥ 4 dB». */
export function describeCell(feature: string, cell: string): string {
  const label = featureLabel(feature)
  const text = cell.trim()
  const comparison = /^(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)$/.exec(text)
  if (comparison) return `${label} ${SYMBOL[comparison[1]] ?? comparison[1]} ${number(Number(comparison[2]))}${FEATURES[feature]?.unit ?? ''}`
  if (text === 'true') return `${label}: yes`
  if (text === 'false') return `${label}: no`
  if (text === 'null') return `${label}: no data`
  const words = text.split(',').map((w) => valueLabel(w.trim().replace(/^"|"$/g, '')))
  return `${label}: ${words.join(' or ')}`
}

/** Lo que dice una fila al encajar: `{state: spoofed}` → «spoofed»; `{kind: HIJACK, confidence: probable}` → «Hijack · probable». */
export function describeOutput(then: Record<string, string>): string {
  if ('kind' in then) return then.kind === 'none' ? 'no incident' : `${valueLabel(then.kind)} · ${then.confidence}`
  return Object.values(then).map(valueLabel).join(' · ')
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
