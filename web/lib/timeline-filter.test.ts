import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Envelope } from './contracts.ts'
import {
  ALL_KEYS,
  countBy,
  DEFAULT_HIDDEN_GROUPS,
  filterEvents,
  hideAllGroups,
  hideNoGroups,
  NO_KEYS,
  toggleKey,
  topicOf,
  visibleKeyCount,
  type TimelineFilter,
} from './timeline-filter.ts'

const ev = (id: string, type: string, topic: string, source: string, payload: Record<string, unknown> = {}): Envelope => ({
  event_id: id, topic: `citadel.pub.evt.${topic}.${type}.v1`, type, source, asset: null, seq: 1, sim_time: 1,
  event_time: '2026-10-20T10:00:01Z', ingestion_time: '2026-10-20T10:00:01.000Z', causation_id: null, ephemeral: false, payload,
})
const events = [
  ev('gps-000001', 'PositionUpdated', 'air.d1', 'd1-gps', { x: 10, fix: '3d' }),
  ev('rad-000001', 'TrackUpdated', 'air.d1', 'radar-1', { x: 12 }),
  ev('det-0001', 'DetectionRaised', 'ai.d1', 'ai-detector', { rule: 'ROUTE_DEVIATION' }),
  ev('plr-0001', 'InteractiveModeChanged', 'sim.player', 'platform-player', { interactive: true }),
]
const none = (): TimelineFilter => ({ hiddenGroups: new Set(), types: ALL_KEYS, topics: ALL_KEYS, query: '' })
const ids = (f: TimelineFilter) => filterEvents(events, f).map((e) => e.event_id)

test('sin filtros pasa todo; el topic es dominio.ruta', () => {
  assert.equal(ids(none()).length, 4)
  assert.equal(topicOf(events[2]), 'ai.d1')
})

test('filtra por fuente, por tipo y por topic', () => {
  assert.deepEqual(ids({ ...none(), hiddenGroups: new Set(['gps' as const]) }), ['rad-000001', 'det-0001', 'plr-0001'])
  assert.deepEqual(ids({ ...none(), types: { only: false, keys: new Set(['TrackUpdated']) } }), ['gps-000001', 'det-0001', 'plr-0001'])
  assert.deepEqual(ids({ ...none(), topics: { only: false, keys: new Set(['air.d1', 'sim.player']) } }), ['det-0001'])
})

test('el buscador mira tipo, id, topic, fuente y contenido, sin mayúsculas y con todos los términos', () => {
  assert.deepEqual(ids({ ...none(), query: 'positionupdated' }), ['gps-000001'])
  assert.deepEqual(ids({ ...none(), query: 'DET-0001' }), ['det-0001'])
  assert.deepEqual(ids({ ...none(), query: 'sim.player' }), ['plr-0001'])
  assert.deepEqual(ids({ ...none(), query: 'radar-1' }), ['rad-000001'])
  assert.deepEqual(ids({ ...none(), query: 'route_deviation' }), ['det-0001'])
  assert.deepEqual(ids({ ...none(), query: 'air x' }), ['gps-000001', 'rad-000001'])
  assert.deepEqual(ids({ ...none(), query: 'air 3d' }), ['gps-000001'])
  assert.deepEqual(ids({ ...none(), query: 'nada' }), [])
})

test('la búsqueda se combina con los filtros', () => {
  assert.deepEqual(ids({ ...none(), query: 'air', types: { only: false, keys: new Set(['TrackUpdated']) } }), ['gps-000001'])
})

test('recuento por tipo', () => {
  assert.deepEqual(countBy(events, (e) => e.type).map(([k, n]) => `${k}:${n}`), [
    'DetectionRaised:1', 'InteractiveModeChanged:1', 'PositionUpdated:1', 'TrackUpdated:1',
  ])
})

test('«None» deja ver solo lo marcado, también lo que aparezca después', () => {
  assert.deepEqual(ids({ ...none(), types: NO_KEYS }), [])
  const marked = toggleKey({ only: true, keys: [] }, 'DetectionRaised')
  const f = { ...none(), types: { only: marked.only, keys: new Set(marked.keys) } }
  assert.deepEqual(ids(f), ['det-0001'])
  // un tipo nuevo, que no estaba entre los conocidos, queda oculto
  const later = [...events, ev('ai-0001', 'AnomalyDetected', 'ai.monitor', 'ai-monitor')]
  assert.deepEqual(filterEvents(later, f).map((e) => e.event_id), ['det-0001'])
  // y «All» lo devuelve todo
  assert.equal(filterEvents(later, { ...none(), types: ALL_KEYS }).length, 5)
})

test('marcar y desmarcar funciona en los dos modos y el contador cuenta lo que se ve', () => {
  assert.deepEqual(toggleKey({ only: false, keys: ['a'] }, 'b'), { only: false, keys: ['a', 'b'] })
  assert.deepEqual(toggleKey({ only: false, keys: ['a', 'b'] }, 'a'), { only: false, keys: ['b'] })
  assert.deepEqual(toggleKey({ only: true, keys: ['a'] }, 'a'), { only: true, keys: [] })
  const known = ['a', 'b', 'c']
  assert.equal(visibleKeyCount(ALL_KEYS, known), 3)
  assert.equal(visibleKeyCount(NO_KEYS, known), 0)
  assert.equal(visibleKeyCount({ only: false, keys: new Set(['a']) }, known), 2)
})

test('botones de fuentes: All, None y Default', () => {
  assert.deepEqual(hideNoGroups(), []) // All: se ven todas
  assert.equal(hideAllGroups().length, 11) // None: se ocultan todas
  assert.deepEqual(DEFAULT_HIDDEN_GROUPS, ['gps', 'radar']) // Default: todo menos GPS y radar
})
