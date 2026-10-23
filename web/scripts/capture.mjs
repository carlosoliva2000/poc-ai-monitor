// Conduce la web como lo haría una persona y saca capturas en los momentos clave.
//   node scripts/capture.mjs demo  <carpeta>   demo a 4× con «esperar al agente» (sin fallos)
//   node scripts/capture.mjs radar <carpeta>   nominal a 4×: silenciar el radar unos 30 s (modo interactivo)
//   node scripts/capture.mjs gps   <carpeta>   nominal a 4×: pérdida de GPS manual (solo se anota lo que pasa)
// Requiere plataforma (8100), módulo de IA y web (3000) en marcha. Una sola pestaña: los ids
// `ops-` los calcula la web y con dos pestañas podrían repetirse.
import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'

const [mode = 'demo', out = 'captures'] = process.argv.slice(2)
mkdirSync(out, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1680, height: 1250 } })
page.on('pageerror', (e) => console.log('page error:', e.message))
page.on('console', (m) => m.type() === 'error' && console.log('console error:', m.text()))

const t0 = Date.now()
const log = []
const note = (what) => {
  const s = ((Date.now() - t0) / 1000).toFixed(1)
  log.push({ wall_s: Number(s), what })
  console.log(`[${s}s] ${what}`)
}
const shot = async (name) => {
  await page.screenshot({ path: `${out}/${name}.png` })
  note(`captura ${name}.png`)
}
const sleep = (ms) => page.waitForTimeout(ms)
const count = (sel) => page.locator(sel).count()
const headerText = () => page.locator('header').first().innerText()
const simTime = async () => {
  const text = await page.locator('[role=progressbar]').first().getAttribute('aria-valuenow')
  return Number(text ?? 0)
}

async function setup(scenario, { waitAgent, interactive, speed, resetCheck = false }) {
  await page.goto('http://127.0.0.1:3000')
  await page.waitForFunction(() => document.querySelectorAll('select[aria-label=Scenario] option').length > 1, null, { timeout: 15000 })
  if (resetCheck) {
    // el modo interactivo se enciende antes de cargar: la carga tiene que apagarlo
    const sw = page.getByRole('switch', { name: 'Interactive mode' })
    await sw.click()
    await page.waitForFunction(() => document.querySelector('[role=switch][aria-label="Interactive mode"]')?.getAttribute('aria-checked') === 'true')
    note('modo interactivo encendido antes de cargar')
  }
  await page.selectOption('select[aria-label=Scenario]', scenario)
  await page.waitForFunction((s) => document.querySelector('select[aria-label=Scenario]')?.value === s, scenario)
  await sleep(800)
  if (resetCheck) note(`tras cargar, modo interactivo = ${await page.getByRole('switch', { name: 'Interactive mode' }).getAttribute('aria-checked')}`)
  await page.getByRole('button', { name: `${speed}×`, exact: true }).click()
  const wa = page.getByRole('switch', { name: 'Wait for the agent' })
  if (waitAgent && (await wa.getAttribute('aria-checked')) !== 'true') await wa.click()
  const it = page.getByRole('switch', { name: 'Interactive mode' })
  // el modo interactivo se conserva entre cargas: se fija al valor pedido, encendido o apagado
  if ((await it.getAttribute('aria-checked')) !== String(interactive)) await it.click()
  await sleep(500)
  note(`escenario ${scenario} cargado, ${speed}×, esperar al agente=${waitAgent}, interactivo=${interactive}`)
}

async function ask(tab, question, shotName) {
  await page.getByRole('tab', { name: tab === 'monitor' ? 'Monitor' : 'Report' }).click()
  const box = page.locator(`#input-${tab === 'monitor' ? 'monitor' : 'report'}`)
  await box.fill(question)
  await box.press('Enter')
  note(`pregunta a ${tab}: ${question}`)
  const chat = page.locator(`[data-testid="chat-${tab === 'monitor' ? 'monitor' : 'report'}"]`)
  // Hay respuesta cuando aparece un artículo del agente sin cursor de streaming.
  const started = Date.now()
  let streamShot = false
  while (Date.now() - started < 90000) {
    const streaming = await chat.locator('span.animate-pulse').count()
    const replies = await chat.locator('article:not(.items-end)').count()
    if (streaming > 0 && shotName && !streamShot) {
      await shot(`${shotName}_streaming`)
      streamShot = true
    }
    if (replies > 0 && streaming === 0) break
    await sleep(300)
  }
  note(`respuesta de ${tab} en ${((Date.now() - started) / 1000).toFixed(1)} s`)
  if (shotName) await shot(shotName)
}

async function runDemo() {
  await setup('demo', { waitAgent: true, interactive: false, speed: 4, resetCheck: true })
  await shot('00_inicio')
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  note('play')
  const done = new Set()
  const once = async (key, cond, action) => {
    if (done.has(key)) return
    if (await cond()) {
      done.add(key)
      await action()
    }
  }
  let waitStart = null
  const waits = []
  let asked = false
  const deadline = Date.now() + 15 * 60 * 1000
  while (Date.now() < deadline) {
    const waiting = (await count('[data-testid=waiting-agent]')) > 0
    if (waiting && waitStart === null) waitStart = Date.now()
    if (!waiting && waitStart !== null) {
      waits.push((Date.now() - waitStart) / 1000)
      waitStart = null
    }
    await once('espera', async () => waiting, async () => shot('01_aviso_de_espera'))
    await once('alerta1', async () => (await count('[data-testid=alert-card]')) >= 1, async () => {
      await shot('02_alert_wind')
      await page.locator('[data-testid=alert-card] details').first().evaluate((d) => (d.open = true))
      await sleep(300)
      await shot('03_alerta_desplegada_checks')
    })
    await once('chat_monitor', async () => (await count('[data-testid=alert-card]')) >= 1 && (await simTime()) > 120, async () => {
      asked = true
      await ask('monitor', 'Why do you think it is wind?', '04_chat_monitor')
    })
    await once('supersedes', async () => (await count('[data-testid=supersedes]')) >= 1, async () => shot('05_supersedes_spoofing'))
    await once('hijack', async () => (await page.locator('[data-testid=alert-card]', { hasText: 'Hijacking' }).count()) >= 1, async () => shot('06_alert_hijack'))
    const status = await headerText()
    if (status.includes('Finished')) break
    await sleep(500)
  }
  if (waitStart !== null) waits.push((Date.now() - waitStart) / 1000)
  note(`fin de la simulación; esperas al agente (visibles): ${waits.length}, suma ${waits.reduce((a, b) => a + b, 0).toFixed(1)} s`)
  // el informe llega unos segundos después de SimulationFinished
  await page.getByRole('tab', { name: 'Report' }).click()
  await page.waitForFunction(() => document.querySelector('[data-testid=report-view] h1') !== null, null, { timeout: 120000 })
  note('informe recibido')
  await sleep(500)
  await shot('07_informe')
  await ask('report', 'Which was the most serious anomaly and why?', '08_chat_informe')
  await page.getByRole('tab', { name: 'Monitor' }).click()
  await sleep(300)
  await shot('09_final_monitor')
  // la capa «verdad» (solo simulador): se enciende un momento para la captura y se vuelve a apagar
  const truth = page.getByRole('checkbox', { name: /Show truth/ })
  await truth.check()
  await sleep(1500)
  await shot('10_verdad')
  await truth.uncheck()
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, waits, wall_total_s: (Date.now() - t0) / 1000, asked }, null, 2))
}

async function runRadar() {
  await setup('nominal', { waitAgent: true, interactive: true, speed: 4 })
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  note('play')
  while ((await simTime()) < 40) await sleep(500)
  await page.getByRole('switch', { name: 'Mute Radar' }).click()
  const muteAt = await simTime()
  note(`radar silenciado a T+${muteAt}`)
  await shot('10_radar_silenciado')
  let alert = false
  const limit = Date.now() + 120000
  while (Date.now() < limit && !alert) {
    alert = (await count('[data-testid=alert-card]')) >= 1
    if (!alert && (await simTime()) > muteAt + 20 && (await count('[data-testid=waiting-agent]')) > 0) await sleep(300)
    await sleep(500)
  }
  note(`alerta del monitor visible: ${alert}`)
  await sleep(1500)
  await page.locator('[data-testid=alert-card] details').first().evaluate((d) => (d.open = true)).catch(() => {})
  await shot('11_sensor_fault')
  while ((await simTime()) < muteAt + 30) await sleep(500)
  await page.getByRole('switch', { name: 'Mute Radar' }).click()
  note(`radar reactivado a T+${await simTime()}`)
  // cierre de la alerta
  const lim2 = Date.now() + 120000
  while (Date.now() < lim2) {
    const txt = await page.locator('[data-testid=monitor-feed]').innerText()
    if (txt.includes('Closes alert')) break
    await sleep(700)
  }
  await shot('12_radar_cierre')
  while (!(await headerText()).includes('Finished')) await sleep(1000)
  await page.getByRole('tab', { name: 'Report' }).click()
  await page.waitForFunction(() => document.querySelector('[data-testid=report-view] h1') !== null, null, { timeout: 120000 })
  await shot('13_radar_informe')
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, wall_total_s: (Date.now() - t0) / 1000 }, null, 2))
}

async function runGps() {
  await setup('nominal', { waitAgent: true, interactive: true, speed: 4 })
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  while ((await simTime()) < 40) await sleep(500)
  await page.getByRole('switch', { name: 'GPS loss', exact: true }).click()
  const at = await simTime()
  note(`pérdida de GPS a T+${at}`)
  await shot('20_gps_perdido')
  while ((await simTime()) < at + 40) await sleep(500)
  await page.getByRole('switch', { name: 'GPS loss' }).click().catch(() => {})
  note(`GPS recuperado a T+${await simTime()}`)
  while (!(await headerText()).includes('Finished')) await sleep(1000)
  await sleep(4000)
  await shot('21_gps_final')
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, wall_total_s: (Date.now() - t0) / 1000 }, null, 2))
}

try {
  if (mode === 'demo') await runDemo()
  else if (mode === 'radar') await runRadar()
  else if (mode === 'gps') await runGps()
  else throw new Error(`modo desconocido: ${mode}`)
} catch (e) {
  note(`ERROR: ${e.message}`)
  await shot('error').catch(() => {})
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, error: String(e) }, null, 2))
  process.exitCode = 1
} finally {
  await browser.close()
}
