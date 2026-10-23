import assert from 'node:assert/strict'
import { test } from 'node:test'
import { stripFieldValues } from './clean-text.ts'

test('quita campo=valor con y sin punto', () => {
  assert.equal(stripFieldValues('empuja en la dirección de la deriva (with_drift=true).'), 'empuja en la dirección de la deriva.')
  assert.equal(stripFieldValues('discrepan poco (disagreed=false) y siguen juntos'), 'discrepan poco y siguen juntos')
  assert.equal(stripFieldValues('viento notable (wind.notable=true) a favor'), 'viento notable a favor')
})

test('quita campo: valor con cifras y unidades', () => {
  assert.equal(stripFieldValues('El viento es fuerte (wind.mean_speed_mps: 1.9 m/s) hoy'), 'El viento es fuerte hoy')
  assert.equal(stripFieldValues('El viento es fuerte (wind.mean_speed_mps: 1,9 m/s).'), 'El viento es fuerte.')
})

test('quita varias expresiones en el mismo paréntesis', () => {
  assert.equal(stripFieldValues('GPS y radar coinciden (gps_radar.disagreed=false, wind.notable=true) y sigue'), 'GPS y radar coinciden y sigue')
  assert.equal(stripFieldValues('ok (wind.mean_speed_mps: 1,9 m/s; wind.with_drift: true).'), 'ok.')
})

test('quita varios paréntesis y respeta el resto del texto', () => {
  const text = 'Viento notable (wind.notable=true) y a favor (wind.with_drift=true), 4,9° de diferencia (T+01:46).'
  assert.equal(stripFieldValues(text), 'Viento notable y a favor, 4,9° de diferencia (T+01:46).')
})

test('deja los paréntesis con prosa, horas, cifras o contenido mezclado', () => {
  for (const text of [
    'Dron desviado (T+01:46) del plan',
    'Diferencia de 4,9° (nota: se mantiene) hoy',
    'Entre GPS y radar (6,8 m de diferencia)',
    'Coinciden (gps_radar.disagreed=false y además estable)',
    'Pasa de GCS-1 a UNK-4F2A (controller_id: cambia a mitad de vuelo y sigue siendo raro)',
    'Sin cambios (p.ej. otra vez)',
  ]) {
    assert.equal(stripFieldValues(text), text)
  }
})

test('texto sin paréntesis, vacío y paréntesis al principio', () => {
  assert.equal(stripFieldValues(''), '')
  assert.equal(stripFieldValues('sin nada raro'), 'sin nada raro')
  assert.equal(stripFieldValues('(with_drift=true) a favor'), 'a favor')
})

test('funciona con textos en inglés y cifras con punto decimal', () => {
  assert.equal(
    stripFieldValues('The wind is notable (notable=true) and pushes with the drift (wind.mean_speed_mps: 3.9 m/s).'),
    'The wind is notable and pushes with the drift.',
  )
})
