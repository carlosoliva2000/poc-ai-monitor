import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Envelope, InstructorCommand } from './contracts.ts'
import { activeWind, compassDegrees, describeCommand, describeWind, EMPTY_FORM, exactPoint, formFromParams, nearestPoint, parseForm, remaining } from './instructor.ts'

const P = { from_deg: 0, speed_mps: 12, ramp_s: 10, duration_s: 60 }
const cmd = (t: number, c: Partial<InstructorCommand> & { command: InstructorCommand['command'] }): Envelope =>
  ({ event_id: `cmd-${t}`, type: 'InstructorCommand', sim_time: t, payload: { params: null, issued_by: 'panel', text: null, ...c } }) as unknown as Envelope

test('la rosa de 16 rumbos va cada 22,5 grados y el viento se nombra por de dónde viene', () => {
  assert.equal(compassDegrees('N'), 0)
  assert.equal(compassDegrees('NE'), 45)
  assert.equal(compassDegrees('SSW'), 202.5)
  assert.equal(compassDegrees('NNW'), 337.5)
  assert.equal(nearestPoint(359), 'N')
  assert.equal(nearestPoint(225), 'SW')
  assert.equal(nearestPoint(-45), 'NW')
  assert.equal(exactPoint(45), 'NE')
  assert.equal(exactPoint(47), null)
})

test('el texto de una propuesta es el de la tarjeta', () => {
  assert.equal(describeWind({ from_deg: 45, speed_mps: 8, ramp_s: 10, duration_s: 60 }), 'Wind from NE (45°), 8 m/s, 60 s, ramp 10 s')
  assert.equal(describeWind({ ...P, from_deg: 47, duration_s: null }), 'Wind from 47° (≈NE), 12 m/s, until cancelled, ramp 10 s')
})

test('el formulario se valida con los rangos del contrato', () => {
  assert.equal(parseForm(EMPTY_FORM).ok, true)
  const bad = (patch: object) => parseForm({ ...EMPTY_FORM, ...patch })
  for (const patch of [{ speed_mps: '41' }, { speed_mps: '-1' }, { from_deg: '361' }, { ramp_s: '0' }, { ramp_s: '121' }, { duration_s: '0' }, { duration_s: '1801' }, { speed_mps: '' }, { speed_mps: 'abc' }]) {
    assert.equal(bad(patch).ok, false, JSON.stringify(patch))
  }
  const sinFin = parseForm({ ...EMPTY_FORM, untilCancelled: true, duration_s: 'basura' })
  assert.ok(sinFin.ok && sinFin.params.duration_s === null) // sin fin: la duración no cuenta
  const norte = parseForm({ ...EMPTY_FORM, from_deg: '360' })
  assert.ok(norte.ok && norte.params.from_deg === 0) // 360 es el norte
})

test('formFromParams y parseForm se invierten', () => {
  for (const p of [P, { ...P, duration_s: null, from_deg: 22.5 }]) {
    const r = parseForm(formFromParams(p))
    assert.ok(r.ok)
    assert.deepEqual(r.params, p)
  }
})

test('el viento activo sale de los comandos: se sustituye, se cancela y acaba por duración', () => {
  assert.equal(activeWind([], 10), null)
  const set = cmd(95, { command: 'set_wind', params: P })
  const a = activeWind([set], 120)
  assert.ok(a && a.since === 95 && a.endsAt === 155 && a.params.speed_mps === 12)
  assert.equal(remaining(a, 120), 35)
  assert.equal(activeWind([set], 155), null) // acabó por duración
  const next = cmd(130, { command: 'set_wind', params: { ...P, speed_mps: 5, duration_s: null } })
  const b = activeWind([set, next], 500)
  assert.ok(b && b.params.speed_mps === 5 && b.endsAt === null && remaining(b, 500) === null)
  assert.equal(activeWind([set, next, cmd(200, { command: 'cancel_wind' })], 210), null)
})

test('el timeline resume el comando', () => {
  assert.equal(describeCommand({ command: 'set_wind', params: { ...P, from_deg: 45 }, issued_by: 'llm', text: 'x' }), 'set_wind: from NE (45°), 12 m/s, 60 s, ramp 10 s · llm')
  assert.equal(describeCommand({ command: 'cancel_wind', params: null, issued_by: 'panel', text: null }), 'cancel_wind · panel')
})
