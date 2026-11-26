import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { AgentToolCall, Anomaly, Envelope } from './contracts.ts'
import { callsByCause, chatEntries, derive, enrichmentViews, groupByWarning, incidents, linkState, TEXT_PENDING_MS, type ToolCallEvent } from './derive.ts'

const base = { asset: null, event_time: '2026-10-20T10:00:01Z', ingestion_time: '2026-10-20T10:00:01.000Z', ephemeral: false }
const call = (id: string, cause: string, agent: AgentToolCall['agent'], index: number): ToolCallEvent => ({
  ...base, event_id: id, topic: 'citadel.pub.evt.ai.agent.AgentToolCall.v1', type: 'AgentToolCall', source: 'ai-module', seq: index, sim_time: 5,
  ephemeral: true, causation_id: cause,
  payload: { agent, invocation_id: 'inv-0001', index, iteration: 1, tool: 'get_events', arguments: '{}', status: 'ok', result: '{}', error: null, truncated: false },
})
const op = (id: string): Envelope => ({ ...base, event_id: id, topic: 'citadel.pub.evt.ops.monitor.OperatorMessage.v1', type: 'OperatorMessage', source: 'web-operator', seq: 1, sim_time: 5, causation_id: null, payload: { conversation_id: 'monitor', text: 'hola' } })
const reply = (id: string, to: string): Envelope => ({ ...base, event_id: id, topic: 'citadel.pub.evt.ai.monitor.AgentReply.v1', type: 'AgentReply', source: 'ai-chat-monitor', seq: 2, sim_time: 6, causation_id: to, payload: { conversation_id: 'monitor', reply_to: to, text: 'ok', tool_calls: ['get_events'] } })

test('las llamadas se agrupan por el evento que las provocó y se ordenan', () => {
  const calls = [call('tcl-2', 'det-1', 'monitor', 2), call('tcl-1', 'det-1', 'monitor', 1), call('tcl-3', 'ops-0001', 'chat-monitor', 1)]
  const map = callsByCause(calls, ['monitor'])
  assert.deepEqual(map.get('det-1')?.map((c) => c.event_id), ['tcl-1', 'tcl-2'])
  assert.equal(map.has('ops-0001'), false)
})

test('cada respuesta del chat lleva sus llamadas; sin respuesta, una entrada en curso', () => {
  const calls = [call('tcl-1', 'ops-0001', 'chat-monitor', 1), call('tcl-2', 'ops-0002', 'chat-monitor', 1)]
  const done = chatEntries([op('ops-0001'), reply('ai-0001', 'ops-0001'), op('ops-0002')], 'monitor', {}, calls)
  const agent = done.filter((e) => e.kind === 'agent')
  assert.equal(agent.length, 2)
  assert.deepEqual(agent.map((e) => (e.kind === 'agent' ? [e.streaming, e.calls.length, e.toolCalls.length] : [])), [[false, 1, 1], [true, 1, 0]])
})

test('sin llamadas ni trozos no se inventa ninguna respuesta', () => {
  const entries = chatEntries([op('ops-0001')], 'monitor', {}, [])
  assert.deepEqual(entries.map((e) => e.kind), ['operator'])
})

test('la cadena de una alerta se cuenta como estados: causa → recovering → closed', async () => {
  const { episodePath, phaseOf } = await import('./format.ts')
  const spoof = { cause: 'GPS_SPOOFING' as const }
  assert.deepEqual(episodePath([spoof, { ...spoof, phase: 'recovering' }], true), ['GPS spoofing', 'recovering', 'closed'])
  assert.deepEqual(episodePath([spoof, { ...spoof, phase: 'recovering' }], false), ['GPS spoofing', 'recovering'])
  assert.deepEqual(episodePath([{ cause: 'SENSOR_FAULT' }, { cause: 'GPS_JAMMING' }], true), ['Sensor fault', 'GPS loss/interference', 'closed'])
  assert.deepEqual(episodePath([{ cause: 'WIND' }], false), ['Wind'])
  assert.equal(phaseOf({}), 'active') // ejecución anterior a la v0.14
  assert.equal(phaseOf({ phase: 'recovering' }), 'recovering')
})

test('E6: las respuestas del monitor van bajo su aviso y lo demás queda arriba', () => {
  const ev = (id: string, source: string, type: string, cause: string | null, seq: number): Envelope => ({
    ...base, event_id: id, topic: 't', type, source, seq, sim_time: seq, causation_id: cause, payload: {},
  }) as unknown as Envelope
  const feed = [
    ev('det-0001', 'ai-detector', 'DetectionRaised', null, 1),
    ev('det-0002', 'ai-detector', 'DetectionRaised', null, 2),
    ev('ai-0001', 'ai-monitor', 'AnomalyDetected', 'det-0001', 3),
    ev('ai-0002', 'ai-monitor', 'DetectionAcknowledged', 'det-0002', 4),
    ev('ai-0003', 'ai-monitor', 'AlertClosed', 'det-9999', 5),
  ]
  const { top, responses } = groupByWarning(feed)
  assert.deepEqual(top.map((e) => e.event_id), ['det-0001', 'det-0002', 'ai-0003'])
  assert.deepEqual(responses.get('det-0001')?.map((e) => e.event_id), ['ai-0001'])
  assert.deepEqual(responses.get('det-0002')?.map((e) => e.event_id), ['ai-0002'])
})

test('E6: la interpretación del LLM de cada alerta de la tabla (híbrido)', () => {
  const ev = (id: string, type: string, payload: object): Envelope =>
    ({ ...base, event_id: id, topic: 't', type, source: 'ai-enricher', seq: 1, sim_time: 1, causation_id: null, payload }) as unknown as Envelope
  const alert = (id: string, extra: Partial<Anomaly> = {}) => ({ alert_id: id, decided_by: 'table', fallback: false, ...extra }) as Anomaly
  const enriched = ev('ai-0009', 'AlertEnriched', { alert_id: 'ai-0001', text: 'Wind drift.', hypothesis: null })
  // sin ningún AlertEnriched no es el híbrido: nada que mostrar
  assert.deepEqual(enrichmentViews([])(alert('ai-0001')), { state: 'none' })
  const view = enrichmentViews([enriched])
  assert.equal(view(alert('ai-0001')).state, 'published')
  assert.equal(view(alert('ai-0002')).state, 'pending')
  assert.equal(view(alert('ai-0003', { decided_by: 'llm' })).state, 'none')
  assert.equal(view(alert('ai-0004', { fallback: true })).state, 'none')
  const done = enrichmentViews([enriched, ev('ai-0010', 'ReportGenerated', {})])
  assert.equal(done(alert('ai-0002')).state, 'missing')
})

const tele = (type: string, t: number, payload: Record<string, unknown>): Envelope => ({
  ...base, event_id: `${type}-${t}`, topic: `citadel.pub.evt.air.d1.${type}.v1`, type, source: 'd1', seq: t, sim_time: t, causation_id: null, payload,
})

test('sin fix no hay posición que pintar, pero se sabe el fix; y el enlace caído se ve como tal', () => {
  const d = derive([
    tele('PositionUpdated', 1, { x: 10, y: 20, alt_m: 60, speed_mps: 15, course_deg: 90, fix: '3d', sats: 14, hdop: 0.8 }),
    tele('PositionUpdated', 2, { x: null, y: null, alt_m: null, speed_mps: null, course_deg: null, fix: 'none', sats: 0, hdop: 99.9 }),
    tele('LinkStatus', 5, { rssi_dbm: null, latency_ms: null, packet_loss_pct: 100 }),
  ])
  assert.equal(d.gps.length, 1) // la posición nula no entra en la estela
  assert.deepEqual(d.gpsStatus, { t: 2, fix: 'none', sats: 0 })
  assert.equal(d.linkState, 'lost')
  assert.equal(d.lastTelemetry, 2) // el último mensaje de telemetría del dron
})

test('el estado del enlace: bueno, degradado por pérdida o latencia, caído sin señal', () => {
  assert.equal(linkState({ rssi_dbm: -70, latency_ms: 45, packet_loss_pct: 0 }), 'good')
  assert.equal(linkState({ rssi_dbm: -70, latency_ms: 45, packet_loss_pct: 35 }), 'degraded')
  assert.equal(linkState({ rssi_dbm: -70, latency_ms: 150, packet_loss_pct: 0 }), 'degraded')
  assert.equal(linkState({ rssi_dbm: null, latency_ms: null, packet_loss_pct: 100 }), 'lost')
  assert.equal(linkState(null), null)
})

// --- Incidentes (contrato v1.1) ---
const inc = (id: string, revision: number, over: Record<string, unknown>, ingestion = '2026-10-20T10:00:00.000Z'): Envelope =>
  ({
    ...base, event_id: `ai-${id}-${revision}`, topic: 'citadel.pub.evt.ai.d1.IncidentUpdated.v1', type: 'IncidentUpdated', source: 'ai-monitor', seq: revision, sim_time: 100 + revision, ingestion_time: ingestion, causation_id: null,
    payload: { incident_id: id, revision, kind: 'WIND', name: 'Wind beyond limit', state: 'open', severity: 'low', confidence: 'probable', opened_at: 100, as_of_sim_time: 100 + revision, change: 'state', evidence: [], context: [], checks: [], evidence_event_ids: [], decided_by: 'table', table: 't', ...over },
  }) as unknown as Envelope
const text = (id: string, revision: number, state: string, t: string): Envelope =>
  ({ ...base, event_id: `txt-${id}-${revision}`, topic: 'citadel.pub.evt.ai.d1.IncidentEnriched.v1', type: 'IncidentEnriched', source: 'ai-enricher', seq: 9, sim_time: 120, causation_id: null,
    payload: { incident_id: id, revision, state, text: t, hypothesis: null, role: 'explain', decided_by: 'llm', as_of_sim_time: 100 + revision } }) as unknown as Envelope

test('v1.1: un incidente es el último IncidentUpdated por id, con su historia', () => {
  const events = [
    inc('inc-0001', 1, { change: 'opened', kind: 'LINK_LOSS', name: 'Command link lost' }),
    inc('inc-0002', 1, { change: 'opened', kind: 'GPS_SPOOFING', name: 'GPS spoofing', opened_at: 90 }),
    inc('inc-0001', 3, { change: 'state', kind: 'HIJACK', name: 'Hijack', state: 'recovering' }),
    inc('inc-0001', 2, { change: 'renamed', kind: 'HIJACK', name: 'Hijack' }),
    inc('inc-0001', 4, { change: 'evidence', kind: 'HIJACK', name: 'Hijack', state: 'recovering' }),
    inc('inc-0001', 5, { change: 'closed', kind: 'HIJACK', name: 'Hijack', state: 'closed' }),
  ]
  const list = incidents(events)
  assert.deepEqual(list.map((i) => i.id), ['inc-0002', 'inc-0001']) // por apertura
  const hijack = list[1]
  assert.equal(hijack.latest.payload.revision, 5)
  assert.equal(hijack.open, false)
  assert.deepEqual(hijack.path, ['Command link lost', 'Hijack', 'recovering', 'closed']) // el evidence no añade paso
  assert.equal(list[0].open, true)
  assert.equal(hijack.opened.payload.revision, 1)
})

test('v1.1: el texto del asistente es el de la última revisión interpretable', () => {
  const open = inc('inc-0001', 1, { change: 'opened' }, '2026-10-20T10:00:00.000Z')
  const events = [open, inc('inc-0001', 2, { change: 'evidence' })]
  const t0 = Date.parse('2026-10-20T10:00:00.000Z')
  // recién publicado y sin texto: pendiente; pasado el plazo y sin que el asistente haya contestado nunca: nada
  assert.deepEqual(incidents(events, t0 + 1000)[0].text, { state: 'pending' })
  assert.deepEqual(incidents(events, t0 + TEXT_PENDING_MS + 1000)[0].text, { state: 'none' })
  assert.deepEqual(incidents(events)[0].text, { state: 'none' }) // sin reloj no se inventa un pendiente
  // el texto de la revisión 1 vale aunque la 2 sea solo de evidencias
  const done = incidents([...events, text('inc-0001', 1, 'open', 'Wind.')], t0 + 60000)[0].text
  assert.equal(done.state, 'published')
  assert.equal(done.state === 'published' && done.enrichment.text, 'Wind.')
  // un texto de otra ejecución (mismo id y revisión, otro instante) no se pega a este incidente
  const stale = { ...text('inc-0001', 1, 'open', 'Old.'), payload: { ...text('inc-0001', 1, 'open', 'Old.').payload, as_of_sim_time: 297 } }
  assert.deepEqual(incidents([...events, stale], t0 + 1000)[0].text, { state: 'pending' })
  // una revisión nueva interpretable sin texto: pendiente (el asistente ya ha contestado antes)
  const next = [...events, text('inc-0001', 1, 'open', 'Wind.'), inc('inc-0001', 3, { change: 'state', state: 'recovering' })]
  assert.deepEqual(incidents(next, t0 + 60000)[0].text, { state: 'pending' })
  // con el informe ya publicado no llegará nada más
  const report = { ...base, event_id: 'ai-r', topic: 't', type: 'ReportGenerated', source: 'ai-report', seq: 99, sim_time: 500, causation_id: null, payload: {} } as unknown as Envelope
  assert.deepEqual(incidents([...next, report], t0 + 60000)[0].text, { state: 'none' })
})

test('E7c: «pending…» sin plazo solo para los tipos de los que el asistente ya ha escrito', () => {
  const t0 = Date.parse('2026-10-20T10:00:00.000Z')
  const events = [
    inc('inc-0001', 1, { change: 'opened', kind: 'WIND' }, '2026-10-20T10:00:00.000Z'),
    text('inc-0001', 1, 'open', 'Wind.'),
    inc('inc-0002', 1, { change: 'opened', kind: 'BATTERY_LOW', name: 'Battery low' }, '2026-10-20T10:00:00.000Z'),
    inc('inc-0003', 1, { change: 'opened', kind: 'WIND' }, '2026-10-20T10:00:00.000Z'),
  ]
  const late = incidents(events, t0 + 60000)
  assert.equal(late.find((i) => i.id === 'inc-0003')?.text.state, 'pending') // sí escribe del viento: llegará
  assert.equal(late.find((i) => i.id === 'inc-0002')?.text.state, 'none') // el asistente no escribe de la batería
  assert.equal(incidents(events, t0 + 1000).find((i) => i.id === 'inc-0002')?.text.state, 'pending') // dentro del plazo
})
