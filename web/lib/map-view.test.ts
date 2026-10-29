import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  clampConsoleWidth,
  clampZoom,
  fixAge,
  frameCamera,
  gridStep,
  HOME,
  MAX_ZOOM,
  panBy,
  rectOf,
  scaleBar,
  scaledPx,
  segmentTrail,
  SIZES,
  visibleRect,
  zoomAt,
  type Rect,
} from './map-view.ts'

const base: Rect = { x: 0, y: -1000, w: 2000, h: 1000 }

test('la región visible tiene la proporción del contenedor y el zoom pedido', () => {
  const v = visibleRect(base, HOME, 1000, 1000)
  assert.equal(v.w, 2000)
  assert.equal(v.h, 2000) // cuadrado: sobra altura, no hay franjas
  assert.equal(v.x + v.w / 2, 1000)
  const z = visibleRect(base, { zoom: 4, center: { x: 500, y: -500 } }, 1000, 500)
  assert.equal(z.w, 500)
  assert.equal(z.h, 250)
  assert.equal(z.x, 250)
})

test('el zoom con ancla mantiene fijo el punto bajo el cursor', () => {
  const view = visibleRect(base, HOME, 1000, 500)
  const at = { x: 400, y: -300 }
  const cam = zoomAt(base, HOME, view, 2, at)
  const after = visibleRect(base, cam, 1000, 500)
  const before = { fx: (at.x - view.x) / view.w, fy: (at.y - view.y) / view.h }
  const now = { fx: (at.x - after.x) / after.w, fy: (at.y - after.y) / after.h }
  assert.ok(Math.abs(before.fx - now.fx) < 1e-9 && Math.abs(before.fy - now.fy) < 1e-9)
  assert.equal(cam.zoom, 2)
})

test('el zoom se limita y el paneo no saca el centro del mapa', () => {
  assert.equal(clampZoom(1000), MAX_ZOOM)
  assert.equal(clampZoom(0.01), 0.5)
  const view = visibleRect(base, HOME, 1000, 500)
  const cam = panBy(base, HOME, view, 99999, -99999)
  assert.deepEqual(cam.center, { x: 2000, y: -1000 })
})

test('un hueco parte la estela sin unir los dos lados', () => {
  const pts = [0, 1, 2, 5, 6, 7].map((t) => ({ t }))
  const segs = segmentTrail(pts, 1.5)
  assert.deepEqual(segs.map((s) => s.points.map((p) => p.t)), [[0, 1, 2], [5, 6, 7]])
})

test('un cambio de clave repite el último punto para no dejar un salto', () => {
  const pts = [0, 1, 2, 3].map((t) => ({ t, fix: t >= 2 ? 'none' : '3d' }))
  const segs = segmentTrail(pts, 1.5, (p) => p.fix)
  assert.deepEqual(segs.map((s) => [s.key, s.points.map((p) => p.t)]), [['3d', [0, 1]], ['none', [1, 2, 3]]])
})

test('sin huecos ni cambios hay un solo tramo y sin puntos, ninguno', () => {
  assert.equal(segmentTrail([{ t: 0 }, { t: 2 }, { t: 4 }], 3).length, 1)
  assert.equal(segmentTrail([], 3).length, 0)
})


test('el paso de la rejilla da 100/250/500/1000 m a zoom normal y baja al acercar', () => {
  assert.equal(gridStep(800), 100)
  assert.equal(gridStep(2000), 250)
  assert.equal(gridStep(4000), 500)
  assert.equal(gridStep(8000), 1000)
  assert.equal(gridStep(30), 10)
  assert.equal(gridStep(1e6), 5000)
})

test('los tamaños escalan con la raíz del zoom, con mínimo y máximo', () => {
  const u = SIZES.unit
  assert.equal(scaledPx(u, 1), 4.5)
  assert.equal(scaledPx(u, 0.5), 3.5) // 4,5·√0,5 = 3,18 → mínimo
  assert.equal(scaledPx(u, 4), 8) // 9 → máximo
  assert.equal(scaledPx(u, 40), 8)
  assert.ok(scaledPx(u, 2) > scaledPx(u, 1) && scaledPx(u, 2) < scaledPx(u, 4))
  assert.ok(scaledPx(SIZES.gpsTrail, 8) <= 3 && scaledPx(SIZES.gpsTrail, 0.5) >= 1.25)
})

test('la barra de escala elige 1, 2 o 5 × 10ⁿ m que quepa', () => {
  assert.equal(scaleBar(0.5)?.meters, 200)
  assert.equal(scaleBar(0.3)?.meters, 200)
  assert.equal(scaleBar(2)?.meters, 50)
  assert.equal(scaleBar(0), null)
  const bar = scaleBar(0.137)!
  assert.ok(bar.px <= 140 && bar.px > 40)
})

test('reset view encuadra un rectángulo respecto a la vista base', () => {
  const target = rectOf([{ x: 0, y: 0 }, { x: 1000, y: 500 }], 50)
  assert.deepEqual(target, { x: -50, y: -550, w: 1100, h: 600 })
  const cam = frameCamera({ x: 0, y: -1000, w: 2000, h: 1000 }, target, 1000, 500)
  assert.equal(cam.zoom, clampZoom(Math.min(1000 / 1100, 500 / 600) / Math.min(1000 / 2000, 500 / 1000)))
  assert.deepEqual(cam.center, { x: 500, y: -250 })
})

test('el ancho de la consola respeta los mínimos de las dos columnas', () => {
  assert.equal(clampConsoleWidth(100, 1920), 340)
  assert.equal(clampConsoleWidth(420, 1920), 420)
  assert.equal(clampConsoleWidth(5000, 1920), 1360)
  assert.equal(clampConsoleWidth(600, 1280), 600)
  assert.equal(clampConsoleWidth(900, 1280), 720)
})

test('antigüedad del último fix', () => {
  assert.equal(fixAge(100.4, 88), 12)
  assert.equal(fixAge(10, 12), 0)
})
