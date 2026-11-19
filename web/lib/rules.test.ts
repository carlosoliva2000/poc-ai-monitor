import assert from 'node:assert/strict'
import { test } from 'node:test'
import { describeCell, describeOutput } from './incidents.ts'
import { rulesView, type RulesFile } from './rules.ts'

const file: RulesFile = {
  facets: {
    'gps.integrity': {
      table: 'gps_integrity', description: 'd', hit_policy: 'FIRST', inputs: [], outputs: ['state'],
      rules: [
        { id: 'GI-01', note: '', when: { telemetry: 'false' }, then: { state: '?' } },
        { id: 'GI-02', note: 'n', when: { cn0_rise_db: '>= 4', agc_drop_db: '<= -2' }, then: { state: 'spoofed' } },
        { id: 'GI-04', note: '', when: {}, then: { state: 'reliable' } },
      ],
    },
  },
}

test('las celdas de las reglas se leen con palabras y unidades', () => {
  assert.equal(describeCell('cn0_rise_db', '>= 4'), 'C/N0 over reference ≥ 4 dB')
  assert.equal(describeCell('agc_drop_db', '<= -2'), 'AGC vs reference ≤ −2 dB')
  assert.equal(describeCell('route_dev_m', '> 25'), 'Distance to the route > 25 m')
  assert.equal(describeCell('telemetry', 'false'), 'Telemetry: no')
  assert.equal(describeCell('link', '"lost"'), 'Command link: lost')
  assert.equal(describeCell('previous', '"deviated","returning"'), 'Before: deviated or returning')
  assert.equal(describeCell('wind_est_mps', 'null'), 'Estimated wind: no data')
})

test('las salidas de las reglas', () => {
  assert.equal(describeOutput({ state: 'beyond_limit' }), 'beyond limit')
  assert.equal(describeOutput({ state: '?' }), 'unknown')
  assert.equal(describeOutput({ kind: 'HIJACK', confidence: 'probable' }), 'Hijack · probable')
  assert.equal(describeOutput({ kind: 'none', confidence: 'none' }), 'no incident')
})

test('la tabla completa en orden, con la fila que encajó marcada', () => {
  const view = rulesView(file, 'gps.integrity', 'GI-02')
  assert.ok(view)
  assert.equal(view.policy, 'FIRST')
  assert.deepEqual(view.lines.map((l) => [l.id, l.matched]), [['GI-01', false], ['GI-02', true], ['GI-04', false]])
  assert.deepEqual(view.lines[2].conditions, []) // la fila por defecto no tiene condiciones
  assert.equal(rulesView(file, 'otra', null), null)
})
