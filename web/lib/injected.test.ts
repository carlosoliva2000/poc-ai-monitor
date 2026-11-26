import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Envelope, TruthFile } from './contracts.ts'
import type { IncidentView } from './derive.ts'
import { injectedEpisodes, injectedVsDetected } from './injected.ts'

const sample = (t: number, extra: Record<string, unknown> = {}) => ({ t, x: 0, y: 0, speed_mps: 15, heading_deg: 0, course_deg: 0, ...extra })
const truth: TruthFile = {
  duration_s: 10,
  wind: [0, 1, 2, 3, 4, 5, 6].map((t) => ({ t, speed_mps: t >= 2 && t <= 4 ? 18 : 2, from_deg: 0 })),
  trajectory: [
    sample(0), sample(1), sample(2, { emitters_active: ['spoofer-1'] }), sample(3, { emitters_active: ['spoofer-1'] }), sample(4),
    sample(5, { mode: 'foreign_control' }), sample(6, { mode: 'foreign_control' }),
  ],
}
const fault = (type: string, t: number): Envelope => ({ event_id: `${type}${t}`, type, sim_time: t, payload: { source: 'radar', mode: 'mute', origin: 'manual' } }) as unknown as Envelope
const incident = (id: string, kinds: string[], opened: number, subject: string | null = null): IncidentView =>
  ({ id, opened: { payload: { opened_at: opened } }, revisions: kinds.map((kind) => ({ payload: { kind, subject } })) }) as unknown as IncidentView

test('lo inyectado sale de la verdad y de los fallos', () => {
  const list = injectedEpisodes(truth, [fault('FaultInjected', 1), fault('FaultCleared', 3)])
  assert.deepEqual(list.map((i) => [i.kind, i.start, i.end]), [['fault', 1, 3], ['wind', 2, 4], ['spoofing', 2, 3], ['hijack', 5, null]])
  assert.match(list.find((i) => i.kind === 'wind')?.label ?? '', /18 m\/s/)
  assert.deepEqual(injectedEpisodes(null, []), [])
})

test('cada cosa inyectada con el incidente que la vio y el retraso; sin incidente, no vista', () => {
  const list = injectedEpisodes(truth, [])
  const rows = injectedVsDetected(list, [incident('inc-1', ['WIND'], 3), incident('inc-2', ['LINK_LOSS', 'HIJACK'], 7)])
  const byKind = Object.fromEntries(rows.map((r) => [r.injected.kind, r]))
  assert.equal(byKind.wind.incident?.id, 'inc-1')
  assert.equal(byKind.wind.delay, 1)
  assert.equal(byKind.hijack.incident?.id, 'inc-2') // abre como enlace perdido y se renombra
  assert.equal(byKind.hijack.delay, 2)
  assert.equal(byKind.spoofing.incident, null) // nadie lo vio
  assert.equal(byKind.spoofing.delay, null)
})

test('un fallo lo ve el incidente de su fuente: silenciar es «fuente sin datos» con su sujeto, no cualquiera', () => {
  const events = [fault('FaultInjected', 1), fault('FaultCleared', 3)] // radar mute
  const list = injectedEpisodes(null, events)
  const wrong = injectedVsDetected(list, [incident('inc-1', ['SOURCE_SILENT'], 2, 'meteo')])
  assert.equal(wrong[0].incident, null)
  const right = injectedVsDetected(list, [incident('inc-1', ['SOURCE_SILENT'], 2, 'meteo'), incident('inc-2', ['SOURCE_SILENT'], 4, 'radar')])
  assert.equal(right[0].incident?.id, 'inc-2')
  assert.equal(right[0].delay, 3)
})

test('una interferencia puede salir como GPS degradado, sin fix o a estima', () => {
  const jam: TruthFile = { ...truth, wind: [], trajectory: [sample(0), sample(1, { emitters_active: ['jammer-1'] }), sample(2, { emitters_active: ['jammer-1'] }), sample(3)] }
  const rows = injectedVsDetected(injectedEpisodes(jam, []), [incident('inc-1', ['GPS_DEGRADED', 'GPS_NO_FIX'], 2)])
  assert.equal(rows[0].injected.kind, 'jamming')
  assert.equal(rows[0].incident?.id, 'inc-1')
})
