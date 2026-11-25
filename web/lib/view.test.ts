import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Envelope } from './contracts.ts'
import { eventsForView, isInstructorOnly, reviveView } from './view.ts'

const ev = (type: string, payload: object = {}): Envelope =>
  ({ event_id: type, topic: 't', type, source: 's', asset: null, seq: 1, sim_time: 1, event_time: '', ingestion_time: '', causation_id: null, ephemeral: false, payload }) as Envelope

test('la vista del alumno no enseña fallos, comandos ni el chat del instructor', () => {
  const events = [
    ev('FaultInjected'), ev('FaultCleared'), ev('InstructorCommand'), ev('InteractiveModeChanged'),
    ev('OperatorMessage', { conversation_id: 'instructor' }), ev('AgentReply', { conversation_id: 'instructor' }),
    ev('AgentReplyChunk', { conversation_id: 'instructor' }), ev('AgentActivity', { agent: 'chat-instructor' }),
    ev('IncidentUpdated'), ev('IncidentEnriched'), ev('SimulationStarted'), ev('WindReported'),
    ev('OperatorMessage', { conversation_id: 'monitor' }), ev('AgentActivity', { agent: 'chat-monitor' }),
  ]
  assert.equal(events.filter(isInstructorOnly).length, 8)
  assert.deepEqual(eventsForView(events, 'student').map((e) => e.type), ['IncidentUpdated', 'IncidentEnriched', 'SimulationStarted', 'WindReported', 'OperatorMessage', 'AgentActivity'])
  assert.equal(eventsForView(events, 'instructor').length, events.length)
})

test('la vista recordada se lee con cuidado', () => {
  assert.equal(reviveView('student'), 'student')
  assert.equal(reviveView('instructor'), 'instructor')
  assert.equal(reviveView('otra'), 'instructor')
  assert.equal(reviveView(null), 'instructor')
})
