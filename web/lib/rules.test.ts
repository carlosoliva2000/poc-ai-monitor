import assert from 'node:assert/strict'
import { test } from 'node:test'
import { describeCell, describeOutput, describeSupport } from './incidents.ts'
import { HANDWRITTEN_TABLE, pickRules, rulesView, type RulesFile } from './rules.ts'

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

test('las filas aprendidas se leen con su confianza y su respaldo', () => {
  const then = { state: 'spoofed', probability: '0.9986', confidence: 'confirmed', instants: '1242582', variants: '380', episodes: '90' }
  assert.equal(describeOutput(then), 'spoofed · confirmed (p 1.00)')
  assert.equal(describeOutput({ state: 'on_route' }), 'on route') // la regla de la situación no lleva confianza
  assert.equal(describeSupport(then), 'Training support: 1,242,582 instants in 380 variants')
  assert.equal(describeSupport({ state: 'spoofed' }), null)
  assert.equal(describeOutput({ state: 'no_fix', confidence: 'probable', probability: '0.7315' }), 'no fix · probable (p 0.73)')
})

test('el fichero de reglas es el del juego de tablas que ejecutó el monitor', () => {
  const frozen: RulesFile = { facets: { 'gps.integrity': { ...file.facets['gps.integrity'], description: 'frozen' } } }
  const hand: RulesFile = { facets: { 'gps.integrity': { ...file.facets['gps.integrity'], description: 'hand' } } }
  assert.equal(pickRules('learned-e7b-v3', frozen, hand), frozen)
  assert.equal(pickRules(undefined, frozen, hand), frozen)
  assert.equal(pickRules(HANDWRITTEN_TABLE, frozen, hand), hand)
})

test('las celdas de las tablas aprendidas: «o sin dato», rangos, «tiene dato» y banderas', () => {
  assert.equal(describeCell('cn0_vs_nominal_db', '> -3.649999976158142, null'), 'C/N0 vs nominal > −3.65 dB or no data')
  assert.equal(describeCell('battery_pct', '(18.449999809265137..25.65000057220459]'), 'Battery between 18.45 and 25.65 %')
  assert.equal(describeCell('wind_est_over_limit', '(0.92..0.93], null'), 'Estimated wind over the drone limit between 0.92 and 0.93 or no data')
  assert.equal(describeCell('mode_return', 'not(null)'), 'Returning home: has data')
  assert.equal(describeCell('mode_hold', '<= 0.5'), 'Holding position: no')
  assert.equal(describeCell('mode_land', '> 0.5'), 'Landing: yes')
  assert.equal(describeCell('home_time_ratio', '<= 0.3142392486333847, null'), 'Time to get home over time left ≤ 0.31 or no data')
})
