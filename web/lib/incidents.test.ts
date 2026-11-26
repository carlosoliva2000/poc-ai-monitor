import assert from 'node:assert/strict'
import { test } from 'node:test'
import { describeCell, describeCondition, describeContext, evidenceRows, facetLabel, formatDuration, valueLabel } from './incidents.ts'

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
    ['Cause of the deviation', 'Hijack', 'IK-01'],
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

test('las facetas y los estados nuevos del catálogo salen con palabras', () => {
  assert.equal(facetLabel('battery.endurance'), 'Battery endurance')
  assert.equal(facetLabel('drone.cause'), 'Cause of the deviation')
  assert.equal(valueLabel('cannot_reach_home'), 'cannot reach home')
  assert.equal(valueLabel('failsafe_return'), 'failsafe: returning home')
  assert.equal(describeCell('wind_est_over_limit', '> 1'), 'Estimated wind over the drone limit > 1')
  assert.equal(describeCondition({ feature: 'tele_gap_p', op: '>=', threshold: 3, value: 7.5 }), 'No drone telemetry for 7.5 periods ≥ 3')
  assert.equal(describeContext({ feature: 'possible_cause', value: 'HIJACK (possible)' }), 'Possible cause HIJACK (possible)')
  assert.equal(describeContext({ feature: 'telemetry_gap_s', value: 31 }), 'No telemetry for 31 s')
  assert.equal(describeContext({ feature: 'battery_pct', value: 14.2 }), 'Battery 14.2 %')
})

test('las banderas del modo y los datos que faltan en una condición', () => {
  assert.equal(describeCondition({ feature: 'mode_hold', op: '<=', threshold: 0.5, value: null }), 'Holding position: no data')
  assert.equal(describeCondition({ feature: 'mode_land', op: '>', threshold: 0.5, value: 1 }), 'Landing: yes')
  assert.equal(describeCondition({ feature: 'mode_return', op: '!=', threshold: null, value: 1 }), 'Returning home: has data')
  assert.equal(describeCondition({ feature: 'cn0_vs_nominal_db', op: '>', threshold: -3.649999976158142, value: 7.23 }), 'C/N0 vs nominal +7.2 dB > −3.65')
})
