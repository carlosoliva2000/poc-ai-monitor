import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createLive, lerpAngle, renderDelay, renderTime, SimClock, Track } from './motion.ts'

const s = (t: number, x: number, y = 0, heading = 0) => ({ t, x, y, heading })
const gps = () => new Track({ maxGapS: 1.5, maxJumpM: (dt) => 40 + 40 * dt })

test('interpola entre las dos muestras que rodean el instante', () => {
  const tr = gps()
  tr.push(s(10, 0))
  tr.push(s(11, 20, 10))
  const p = tr.sampleAt(10.25)!
  assert.equal(p.x, 5)
  assert.equal(p.y, 2.5)
})

test('no extrapola: tras la última muestra se queda en ella', () => {
  const tr = gps()
  tr.push(s(10, 0))
  tr.push(s(11, 20))
  assert.equal(tr.sampleAt(11)!.x, 20)
  assert.equal(tr.sampleAt(15)!.x, 20)
  assert.equal(tr.sampleAt(1e9)!.x, 20)
})

test('antes de la primera muestra devuelve la primera; sin muestras, nada', () => {
  const tr = gps()
  assert.equal(tr.sampleAt(5), null)
  tr.push(s(10, 3))
  assert.equal(tr.sampleAt(5)!.x, 3)
})

test('un hueco (fuente callada) se salta sin animar: mantiene la anterior y luego salta', () => {
  const tr = gps()
  tr.push(s(10, 0))
  tr.push(s(11, 10))
  tr.push(s(41, 12)) // 30 s sin GPS, y vuelve cerca
  assert.equal(tr.sampleAt(20)!.x, 10) // callado: quieto en la última
  assert.equal(tr.sampleAt(40.9)!.x, 10) // sin animar el hueco
  assert.equal(tr.sampleAt(41)!.x, 12)
})

test('un salto grande de posición (recuperación, engaño) no se anima', () => {
  const tr = gps()
  tr.push(s(10, 0))
  tr.push(s(11, 500)) // 500 m en 1 s
  assert.equal(tr.sampleAt(10.5)!.x, 0)
  assert.equal(tr.sampleAt(11)!.x, 500)
  tr.push(s(12, 515)) // el movimiento normal vuelve a interpolarse
  assert.equal(tr.sampleAt(11.5)!.x, 507.5)
})

test('si el tiempo retrocede (reinicio) se vacía el buffer', () => {
  const tr = gps()
  tr.push(s(100, 0))
  tr.push(s(101, 10))
  tr.push(s(1, 999))
  assert.equal(tr.size, 1)
  assert.equal(tr.sampleAt(100)!.x, 999)
})

test('una muestra repetida se ignora', () => {
  const tr = gps()
  tr.push(s(10, 0))
  tr.push(s(10, 5))
  assert.equal(tr.size, 1)
})

test('el rumbo se interpola por el camino corto', () => {
  assert.equal(lerpAngle(350, 10, 0.5), 0)
  assert.equal(lerpAngle(10, 350, 0.5), 0)
  assert.equal(lerpAngle(90, 100, 0.5), 95)
  const tr = gps()
  tr.push(s(0, 0, 0, 350))
  tr.push(s(1, 0, 0, 10))
  assert.equal(tr.sampleAt(0.25)!.heading, 355)
})

test('el reloj reparte el tiempo según la velocidad y no avanza en pausa', () => {
  for (const speed of [0.5, 1, 4, 16]) {
    const c = new SimClock()
    c.sync(100, speed, true, 0)
    assert.ok(Math.abs(c.now(1000) - (100 + speed)) < 1e-9, `a ${speed}×`)
  }
  const c = new SimClock()
  c.sync(100, 4, false, 0)
  assert.equal(c.now(5000), 100)
})

test('el reloj no retrocede por una corrección pequeña, pero sí con un reinicio', () => {
  const c = new SimClock()
  c.sync(100, 1, true, 0)
  assert.equal(c.now(1000), 101)
  c.sync(100.6, 1, true, 1000) // el estado llega «antes» de lo estimado
  assert.equal(c.now(1000), 101) // se mantiene
  assert.ok(c.now(1500) > 101)
  c.sync(0, 1, false, 2000) // reinicio
  assert.equal(c.now(2000), 0)
})

test('el reloj salta hacia delante (paso a paso, recuperación tras una pausa larga)', () => {
  const c = new SimClock()
  c.sync(10, 1, false, 0)
  assert.equal(c.now(100), 10)
  c.sync(11, 1, false, 100)
  assert.equal(c.now(100), 11)
})

test('el retraso es una muestra y, a velocidad alta, lo que dura una ráfaga', () => {
  assert.equal(renderDelay(1, 1), 1)
  assert.equal(renderDelay(4, 1), 1)
  assert.ok(Math.abs(renderDelay(16, 1) - 2.4) < 1e-9)
})

test('los dos iconos se pintan con el mismo instante', () => {
  const live = createLive()
  live.speed = 4
  live.clock.sync(50, 4, true, 0)
  const t = renderTime(live, 500)
  assert.equal(t, 50 + 2 - 1)
})

test('con el reloj en marcha, el icono avanza fotograma a fotograma sin saltos', () => {
  const live = createLive()
  live.speed = 1
  live.clock.sync(10, 1, true, 0)
  for (let k = 0; k <= 12; k++) live.gps.push(s(k, k * 10))
  let prev = live.gps.sampleAt(renderTime(live, 0))!.x
  const steps: number[] = []
  for (let f = 1; f <= 120; f++) {
    const x = live.gps.sampleAt(renderTime(live, f * 16.67))!.x
    steps.push(x - prev)
    prev = x
  }
  // ≈ 10 m/s · 16,67 ms = 0,167 m por fotograma, siempre
  assert.ok(steps.every((d) => Math.abs(d - 0.1667) < 1e-3), steps.slice(0, 5).join())
})

test('la latencia variable de los `state` no frena ni adelanta el reloj de golpe', () => {
  const c = new SimClock()
  c.sync(100, 4, true, 0)
  let prev = c.now(0)
  let maxStep = 0
  // un `state` cada 500 ms de pared, con entre 0 y 60 ms de retraso en la llegada (la simulación avanza 4×)
  const delays = [0, 40, 10, 60, 0, 30, 55, 5, 25, 0, 50, 15]
  for (let k = 1; k <= 12; k++) {
    const trueWall = k * 500
    c.sync(100 + (trueWall / 1000) * 4, 4, true, trueWall + delays[k - 1])
    for (let w = trueWall; w < trueWall + 500; w += 16.67) {
      const t = c.now(w)
      if (k > 1 || w > trueWall) maxStep = Math.max(maxStep, t - prev) // el primer fotograma tras el arranque no cuenta
      prev = t
    }
  }
  const ideal = (16.67 / 1000) * 4 // 0,0667 s de simulación por fotograma
  assert.ok(maxStep < ideal * 2, `paso máximo ${maxStep} frente a ${ideal}`)
})
