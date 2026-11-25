import assert from 'node:assert/strict'
import { test } from 'node:test'
import { describeCondition, describeContext, evidenceRows, formatDuration } from './incidents.ts'

test('las condiciones se leen con su valor y su umbral', () => {
  assert.equal(describeCondition({ feature: 'cn0_rise_db', op: '>=', threshold: 4, value: 8.14 }), 'C/N0 over reference +8.1 dB ≥ 4')
  assert.equal(describeCondition({ feature: 'agc_drop_db', op: '<=', threshold: -2, value: -4 }), 'AGC vs reference −4 dB ≤ −2')
  assert.equal(describeCondition({ feature: 'route_dev_m', op: '>', threshold: 25, value: 79.74 }), 'Distance to the route 79.7 m > 25')
  assert.equal(describeCondition({ feature: 'wind_high_s', op: '>=', threshold: 5, value: 7 }), 'Wind beyond limit for 7 s ≥ 5')
  // las condiciones de igualdad (tabla del tipo de incidente) se leen como «etiqueta: valor»
  assert.equal(describeCondition({ feature: 'link', op: '==', threshold: 'lost', value: 'lost' }), 'Command link: lost')
  assert.equal(describeCondition({ feature: 'previous', op: '==', threshold: 'deviated, returning', value: 'returning' }), 'Before: returning')
  assert.equal(describeCondition({ feature: 'cn0_rise_db', op: '>=', threshold: 4, value: null }), 'C/N0 over reference — ≥ 4')
})

test('las evidencias y el contexto se pintan con palabras, sin nombres internos', () => {
  const rows = evidenceRows([
    { facet: 'drone.situation', state: 'on_route', rule_id: 'DS-05', conditions: [{ feature: 'route_dev_m', op: '<', threshold: 15, value: 14.1 }] },
    { facet: 'environment.wind', state: 'beyond_limit', rule_id: 'EW-02', conditions: [] },
    { facet: 'drone.cause', state: 'HIJACK', rule_id: 'IK-01', conditions: [] },
  ])
  assert.deepEqual(rows.map((r) => [r.facet, r.state, r.rule]), [
    ['Drone vs route', 'on route', 'DS-05'],
    ['Wind', 'beyond limit', 'EW-02'],
    ['Decisive rule', 'Hijack', 'IK-01'],
  ])
  assert.equal(describeContext({ feature: 'wind_est_mps', value: 2.64 }), 'Estimated wind 2.6 m/s')
  assert.equal(describeContext({ feature: 'deviation_source', value: 'radar' }), 'Deviation measured by the radar')
  assert.equal(describeContext({ feature: 'deviation_source', value: 'gps' }), 'Deviation measured by the GPS')
})

test('duraciones', () => {
  assert.equal(formatDuration(45.4), '45 s')
  assert.equal(formatDuration(72), '1 min 12 s')
  assert.equal(formatDuration(125), '2 min 05 s')
})
