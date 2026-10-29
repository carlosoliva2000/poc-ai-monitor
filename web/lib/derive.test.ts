import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { AgentToolCall, Envelope } from './contracts.ts'
import { callsByCause, chatEntries, type ToolCallEvent } from './derive.ts'

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
