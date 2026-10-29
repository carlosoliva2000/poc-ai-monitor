// Conduce la web como lo haría una persona y saca capturas en los momentos clave.
//   node scripts/capture.mjs demo  <carpeta>   demo a 4× con «esperar al agente» (sin fallos)
//   node scripts/capture.mjs radar <carpeta>   nominal a 4×: silenciar el radar unos 30 s (modo interactivo)
//   node scripts/capture.mjs gps   <carpeta>   nominal a 4×: pérdida de GPS manual (solo se anota lo que pasa)
//   node scripts/capture.mjs fase9 <carpeta>   demo a 4× con «esperar al agente»: cámara del mapa, dos iconos,
//                                              timeline con filtros, chats, pestaña Informe y tool calls
//   node scripts/capture.mjs icons <carpeta>   los dos iconos con el engaño del GPS (demo), con zoom y siguiendo al dron
//   node scripts/capture.mjs chatsize <carpeta> minimizar y redimensionar el chat del monitor (y que se recuerde)
//   node scripts/capture.mjs layout <carpeta>  mide y captura el final de la página a varios tamaños de ventana
//   node scripts/capture.mjs deadgps <carpeta> nominal a 4×, interactivo: GPS con pérdida y silencio a la vez, en los dos órdenes
//   node scripts/capture.mjs fase9_1 <carpeta> demo a 4× con «esperar al agente», a 1920×1080 y luego a 1440×900 y 1280×720:
//                                              leyenda, tamaños, rejilla, escala, Ctrl+rueda, secuestro con la misma vista,
//                                              timeline al fondo, filtros, columnas redimensionadas
//   node scripts/capture.mjs truthlag <carpeta> demo a 16× (y 4×): distancia en pantalla entre el icono conocido y el real
//   node scripts/capture.mjs compare <carpeta9_1> <carpeta9> <salida>  junta capturas de las dos fases lado a lado
//   node scripts/capture.mjs chattools <carpeta> chat del monitor con tools (módulo con el perfil qwen3-14b-t0-chat-tools)
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
  const truth = page.getByRole("checkbox", { name: /Truth trail/ })
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

const mapBox = async () => (await page.locator('[data-testid=drone-map]').boundingBox())
const mapAttr = (name) => page.locator('[data-testid=drone-map]').getAttribute(name)

async function runFase9() {
  await setup('demo', { waitAgent: true, interactive: false, speed: 4, resetCheck: false })
  await shot('00_inicio')
  const initialMap = await mapBox()
  await page.getByRole('tab', { name: 'Report' }).click()
  await sleep(300)
  note(`informe antes de empezar: ${await page.locator('[data-testid=report-notice]').innerText()}`)
  await shot('01_informe_antes_de_empezar')
  await page.getByRole('tab', { name: 'Monitor' }).click()
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  note('play')
  while ((await simTime()) < 70) await sleep(500)

  // --- Informe durante la simulación
  await page.getByRole('tab', { name: 'Report' }).click()
  await sleep(300)
  note(`informe durante la simulación: ${await page.locator('[data-testid=report-notice]').innerText()}`)
  await shot('02_informe_durante_la_simulacion')
  await page.getByRole('tab', { name: 'Monitor' }).click()

  // --- Mapa: zoom con la rueda, botones, paneo, centrar, seguir, restablecer
  const box = await mapBox()
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5)
  await page.mouse.wheel(0, -500)
  await sleep(200)
  note(`zoom tras la rueda: ${await mapAttr('data-zoom')}`)
  await page.getByRole('button', { name: 'Zoom in' }).click()
  note(`zoom tras el botón +: ${await mapAttr('data-zoom')}`)
  await shot('03_mapa_zoom_y_estelas')
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.4, { steps: 6 })
  await page.mouse.up()
  note('paneo: arrastrado el mapa')
  await shot('04_mapa_paneo')
  await page.getByRole('button', { name: 'Center on the drone' }).click()
  await shot('05_mapa_centrado_en_el_dron')
  await page.getByRole('button', { name: 'Follow the drone' }).click()
  note(`seguir al dron: data-follow=${await mapAttr('data-follow')}`)
  await sleep(2500)
  await shot('06_mapa_siguiendo_al_dron')
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * 0.45, box.y + box.height * 0.5, { steps: 4 })
  await page.mouse.up()
  note(`tras arrastrar, data-follow=${await mapAttr('data-follow')} (debe ser false)`)
  await page.getByRole('button', { name: 'Reset view' }).click()
  note(`tras restablecer: zoom ${await mapAttr('data-zoom')}, follow ${await mapAttr('data-follow')}; el mapa no ha cambiado de tamaño: ${JSON.stringify(await mapBox()) === JSON.stringify(initialMap)}`)

  // --- Interruptores de capas: icono del dron y estelas
  const drone = page.getByRole('checkbox', { name: /Drone \(known position\)/ })
  await drone.uncheck()
  note(`icono conocido oculto: ${(await count('[data-testid=known-drone]')) === 0}`)
  await drone.check()
  await page.getByRole('checkbox', { name: 'GPS trail' }).uncheck()
  await page.getByRole('checkbox', { name: 'GPS trail' }).check()

  // --- Dos iconos con la verdad (se espera a que el viento los separe)
  const truth = page.getByRole("checkbox", { name: /Truth trail/ })
  note(`sin la capa de verdad, icono real presente: ${(await count('[data-testid=true-drone]')) > 0}`)
  await truth.check()
  while ((await simTime()) < 125) await sleep(500)
  await sleep(1200)
  note(`con la capa de verdad, icono real presente: ${(await count('[data-testid=true-drone]')) > 0}`)
  await page.getByRole('button', { name: 'Zoom in' }).click()
  await page.getByRole('button', { name: 'Zoom in' }).click()
  await page.getByRole('button', { name: 'Center on the drone' }).click()
  await shot('07_dos_iconos_con_la_verdad')
  await page.getByRole('button', { name: 'Reset view' }).click()
  await truth.uncheck()

  // --- Timeline: filtros, topic, buscador
  await page.getByRole('switch', { name: 'Show topic and source' }).check()
  await shot('08_timeline_topic_y_fuente')
  await page.locator('details > summary', { hasText: 'Type' }).first().click()
  await page.locator('details[open] label', { hasText: 'DetectionRaised' }).first().locator('input').uncheck()
  await shot('09_timeline_filtro_por_tipo')
  await page.locator('details > summary', { hasText: 'Type' }).first().click()
  await page.locator('details > summary', { hasText: 'Type' }).first().click()
  await page.locator('details[open] label', { hasText: 'DetectionRaised' }).first().locator('input').check()
  await page.locator('details > summary', { hasText: 'Type' }).first().click()
  await page.getByLabel('Search events').fill('det-')
  await sleep(400)
  note(`buscador «det-»: ${await page.locator('[data-testid=timeline-shown]').innerText().catch(() => 'sin recuento')}`)
  await shot('10_timeline_busqueda')
  await page.getByLabel('Search events').fill('')
  await page.getByRole('switch', { name: 'Show topic and source' }).uncheck()

  // --- Tool calls del monitor y chats
  while ((await count('[data-testid=monitor-invocation]')) < 1) await sleep(500)
  await page.locator('[data-testid=monitor-invocation] > details').first().evaluate((d) => (d.open = true))
  await page.locator('[data-testid=monitor-invocation] details details').first().evaluate((d) => (d.open = true)).catch(() => {})
  await sleep(300)
  await shot('11_toolcalls_del_monitor')
  const nCalls = await count('[data-testid=monitor-invocation] ol > li')
  note(`llamadas del monitor visibles: ${nCalls}`)
  await ask('monitor', 'Which alerts are open?', '12_chat_monitor_con_toolcalls')
  const chat = page.locator('[data-testid=chat-monitor]')
  await page.getByRole('button', { name: 'Minimize the monitor chat' }).click()
  await sleep(300)
  note(`chat minimizado: ${await chat.getAttribute('data-minimized')}`)
  await shot('13_chat_minimizado')
  await page.getByRole('button', { name: 'Expand the monitor chat' }).click()
  const handle = await page.locator('[data-testid=chat-monitor-resize]').boundingBox()
  const before = (await chat.boundingBox()).height
  await page.mouse.move(handle.x + handle.width / 2, handle.y + 2)
  await page.mouse.down()
  await page.mouse.move(handle.x + handle.width / 2, handle.y - 200, { steps: 8 })
  await page.mouse.up()
  const after = (await chat.boundingBox()).height
  note(`chat redimensionado: ${before.toFixed(0)} px → ${after.toFixed(0)} px`)
  await shot('14_chat_redimensionado')
  await page.reload()
  await page.waitForFunction(() => document.querySelector('[data-testid=chat-monitor]') !== null)
  await sleep(800)
  note(`tras recargar, alto del chat: ${(await page.locator('[data-testid=chat-monitor]').boundingBox()).height.toFixed(0)} px`)

  // --- Fin de la simulación y del informe
  while (!(await headerText()).includes('Finished')) await sleep(500)
  note('simulación terminada')
  await page.getByRole('tab', { name: 'Report' }).click()
  let writing = false
  const lim = Date.now() + 180000
  while (Date.now() < lim) {
    if (!writing && (await count('[data-testid=report-writing], [data-testid=report-notice]')) > 0) {
      const txt = await page.locator('[data-testid=report-writing], [data-testid=report-notice]').first().innerText()
      if (txt.includes('writing')) {
        writing = true
        note(`informe: ${txt}`)
        await shot('15_informe_generandose')
      } else if (!writing) note(`informe (aún): ${txt}`)
    }
    if ((await count('[data-testid=report-done]')) > 0) break
    await sleep(400)
  }
  note(`el chat del informe aparece solo con el informe: ${(await count('[data-testid=chat-report]')) > 0}`)
  await sleep(500)
  await shot('16_informe_final')
  await ask('report', 'What do you recommend?', '17_chat_informe')
  await page.getByRole('tab', { name: 'Monitor' }).click()
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, wall_total_s: (Date.now() - t0) / 1000 }, null, 2))
}

const SIZES = [
  [1920, 1080],
  [1680, 1050],
  [1440, 900],
  [1280, 720],
  [1024, 768],
  [800, 900],
]

async function runIcons() {
  // El engaño del GPS (demo, T+168–222) separa la posición conocida de la real.
  await setup('demo', { waitAgent: false, interactive: false, speed: 8 })
  await page.getByRole("checkbox", { name: /Truth trail/ }).check()
  await page.getByRole("checkbox", { name: /True position/ }).check()
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  while ((await simTime()) < 215) await sleep(300)
  await page.getByRole('button', { name: 'Pause' }).click()
  await sleep(800)
  await page.getByRole('button', { name: 'Center on the drone' }).click()
  for (let i = 0; i < 3; i++) await page.getByRole('button', { name: 'Zoom in' }).click()
  await sleep(500)
  note(`iconos: conocido ${await count('[data-testid=known-drone]')}, real ${await count('[data-testid=true-drone]')}`)
  await shot('50_dos_iconos_engano_del_gps')
  await page.getByRole('button', { name: 'Follow the drone' }).click()
  await page.getByRole('button', { name: 'Resume' }).click()
  await sleep(4000)
  await shot('51_siguiendo_al_icono_conocido')
  await page.getByRole('button', { name: 'Pause' }).click()
  await page.getByRole('button', { name: 'Reset view' }).click()
  await page.getByRole('button', { name: 'Zoom in' }).click()
  await sleep(400)
  await shot('52_dos_iconos_zoom_moderado')
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, wall_total_s: (Date.now() - t0) / 1000 }, null, 2))
}

async function runChatSize() {
  await setup('demo', { waitAgent: false, interactive: false, speed: 8 })
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  while ((await simTime()) < 110) await sleep(500)
  await ask('monitor', 'Which alerts are open?', null)
  const chat = page.locator('[data-testid=chat-monitor]')
  await page.getByRole('button', { name: 'Minimize the monitor chat' }).click()
  await sleep(400)
  note(`chat minimizado: ${await chat.getAttribute('data-minimized')}`)
  await shot('13_chat_minimizado')
  await page.getByRole('button', { name: 'Expand the monitor chat' }).click()
  await sleep(400)
  const handle = await page.locator('[data-testid=chat-monitor-resize]').boundingBox()
  const before = (await chat.boundingBox()).height
  const x = handle.x + handle.width / 2
  const y = handle.y + handle.height / 2
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x, y - 250, { steps: 10 })
  await page.mouse.up()
  await sleep(300)
  note(`chat redimensionado: ${before.toFixed(0)} px → ${(await chat.boundingBox()).height.toFixed(0)} px`)
  await shot('14_chat_redimensionado')
  await page.reload()
  await page.waitForSelector('[data-testid=chat-monitor]')
  await sleep(800)
  note(`tras recargar, alto del chat: ${(await page.locator('[data-testid=chat-monitor]').boundingBox()).height.toFixed(0)} px`)
  await page.getByRole('button', { name: 'Minimize the monitor chat' }).click()
  await sleep(300)
  await page.reload()
  await page.waitForSelector('[data-testid=chat-monitor]')
  await sleep(800)
  note(`tras recargar, minimizado: ${await page.locator('[data-testid=chat-monitor]').getAttribute('data-minimized')}`)
  await page.getByRole('button', { name: 'Expand the monitor chat' }).click()
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, wall_total_s: (Date.now() - t0) / 1000 }, null, 2))
}

async function runLayout() {
  await setup('demo', { waitAgent: false, interactive: false, speed: 16 })
  const report = []
  for (const [w, h] of SIZES) {
    await page.setViewportSize({ width: w, height: h })
    await sleep(400)
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
    await page.evaluate(() => document.querySelectorAll('main > div').forEach((el) => (el.scrollTop = el.scrollHeight)))
    await sleep(300)
    const m = await page.evaluate(() => {
      const r = (el) => (el ? el.getBoundingClientRect() : null)
      const main = document.querySelector('main')
      const [left, right] = [...main.children]
      const doc = document.documentElement
      return {
        inner: [window.innerWidth, window.innerHeight],
        docScroll: [doc.scrollHeight, doc.clientHeight],
        mainBottom: r(main).bottom,
        leftBottom: r(left).bottom,
        rightBottom: r(right).bottom,
        leftScroll: [left.scrollHeight, left.clientHeight],
        scrollY: window.scrollY,
      }
    })
    const stripe = Math.max(m.inner[1] - m.mainBottom, 0)
    const flush = Math.abs(m.leftBottom - m.rightBottom) < 1.5
    report.push({ size: `${w}x${h}`, ...m, stripe_px: Math.round(stripe), columns_end_together: flush })
    note(`${w}x${h}: main termina en ${m.mainBottom.toFixed(0)}, izquierda ${m.leftBottom.toFixed(0)}, derecha ${m.rightBottom.toFixed(0)}, ventana ${m.inner[1]}, scroll del documento ${m.docScroll.join('/')}, franja ${stripe.toFixed(0)} px, columnas alineadas: ${flush}`)
    await shot(`layout_${w}x${h}_final_de_pagina`)
  }
  writeFileSync(`${out}/layout.json`, JSON.stringify(report, null, 2))
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, wall_total_s: (Date.now() - t0) / 1000 }, null, 2))
}

const faultsText = () => page.locator('[data-testid=active-faults]').innerText()

async function runDeadGps() {
  await setup('nominal', { waitAgent: false, interactive: true, speed: 4 })
  await page.getByRole("checkbox", { name: /Truth trail/ }).check()
  await page.getByRole("checkbox", { name: /True position/ }).check()
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  const loss = page.getByRole('switch', { name: 'GPS loss', exact: true })
  const mute = page.getByRole('switch', { name: 'Mute GPS' })
  const at = async (t) => { while ((await simTime()) < t) await sleep(300) }
  // Orden A: silencio y luego pérdida; se quita primero el silencio y luego la pérdida.
  await at(40)
  await mute.click(); await at(46); await loss.click()
  note(`A: mute y loss activos: ${await faultsText()}`)
  await at(60)
  await shot('30_receptor_muerto_A')
  await mute.click()
  note(`A: se quita el mute (sigue loss): ${await faultsText()}`)
  await at(75)
  await shot('31_A_quitado_el_mute_sigue_la_perdida')
  await loss.click()
  note(`A: se quita la pérdida: ${await faultsText()}`)
  await at(95)
  // Orden B: pérdida y luego silencio; se quita primero la pérdida (el GPS sigue callado) y luego el silencio.
  await at(130)
  await loss.click(); await at(136); await mute.click()
  note(`B: loss y mute activos: ${await faultsText()}`)
  await at(150)
  await shot('32_receptor_muerto_B')
  await loss.click()
  note(`B: se quita la pérdida (sigue mute): ${await faultsText()}`)
  await at(170)
  await shot('33_B_quitada_la_perdida_sigue_callado')
  await mute.click()
  note(`B: se quita el mute: ${await faultsText()}`)
  while (!(await headerText()).includes('Finished')) await sleep(1000)
  await sleep(3000)
  await shot('34_receptor_muerto_final')
  const timeline = await (await fetch('http://127.0.0.1:8100/api/timeline')).json()
  const interesting = timeline.events.filter((e) => e.event_id.startsWith('sim-') || e.type.startsWith('Detection') || e.type === 'AnomalyDetected' || e.type === 'AlertClosed')
  const rows = interesting.map((e) => `${e.sim_time.toFixed(0)}s ${e.type} ${JSON.stringify(e.payload.rule ?? e.payload.cause ?? e.payload.mode ?? '')} ${JSON.stringify(e.payload.source ?? '')}`)
  note(`eventos clave:\n${rows.join('\n')}`)
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, events: rows, wall_total_s: (Date.now() - t0) / 1000 }, null, 2))
}

async function runChatTools() {
  await setup('demo', { waitAgent: false, interactive: false, speed: 8 })
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  while ((await simTime()) < 110) await sleep(500)
  // el chat se agranda para que quepa la respuesta con sus llamadas a tool
  const handle = await page.locator('[data-testid=chat-monitor-resize]').boundingBox()
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2)
  await page.mouse.down()
  await page.mouse.move(handle.x + handle.width / 2, handle.y - 420, { steps: 10 })
  await page.mouse.up()
  await ask('monitor', 'Check the latest GPS and radar data and tell me how far the drone is from the route.', '40_chat_con_tools')
  const names = await page.locator('[data-testid=chat-monitor] [data-testid=tool-calls] summary').allInnerTexts()
  note(`desplegables de tool calls en el chat: ${JSON.stringify(names)}`)
  await page.locator('[data-testid=chat-monitor] [data-testid=tool-calls]').first().evaluate((d) => (d.open = true)).catch(() => {})
  await page.locator('[data-testid=chat-monitor] [data-testid=tool-calls] details').first().evaluate((d) => (d.open = true)).catch(() => {})
  await sleep(300)
  await page.locator('[data-testid=chat-monitor] [role=log]').evaluate((el) => (el.scrollTop = el.scrollHeight))
  await sleep(200)
  await shot('41_chat_toolcalls_desplegado')
  const reply = await page.locator('[data-testid=chat-monitor] article:not(.items-end)').last().innerText()
  note(`respuesta del chat: ${reply.slice(0, 600)}`)
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, wall_total_s: (Date.now() - t0) / 1000 }, null, 2))
}

const zoomOf = async () => Number(await page.locator('[data-testid=drone-map]').getAttribute('data-zoom'))
const viewOf = () => page.locator('[data-testid=drone-map]').getAttribute('data-view')
const mapBtn = (name) => page.getByRole('button', { name, exact: true })
const waitSim = async (t) => {
  while ((await simTime()) < t) await sleep(400)
}
const pauseRun = async () => {
  await mapBtn('Pause').click()
  await sleep(500)
}
const resumeRun = async () => {
  await mapBtn('Resume').click()
  await sleep(300)
}
async function zoomClicks(name, n) {
  for (let i = 0; i < n; i++) await mapBtn(name).click()
  await sleep(300)
}

async function runFase9_1() {
  await page.setViewportSize({ width: 1920, height: 1080 })
  await setup('demo', { waitAgent: true, interactive: false, speed: 4 })
  await shot('00_inicio_mapa_alto')
  await page.getByRole('group', { name: 'Map layers' }).screenshot({ path: `${out}/01_leyenda_por_grupos.png` })
  note('captura 01_leyenda_por_grupos.png')
  const legend = await page.getByRole('group', { name: 'Map layers' }).evaluate((el) => ({
    groups: [...el.querySelectorAll('legend')].map((l) => l.textContent),
    rows: new Set([...el.querySelectorAll('fieldset')].map((f) => Math.round(f.getBoundingClientRect().top))).size,
  }))
  note(`leyenda: grupos ${legend.groups.join(' · ')}; filas ${legend.rows}`)
  const mapBox = await page.locator('[data-testid=drone-map]').boundingBox()
  note(`mapa: ${Math.round(mapBox.width)}×${Math.round(mapBox.height)} px (${Math.round((mapBox.height / 1080) * 100)} % del alto de la ventana)`)

  await page.getByRole('checkbox', { name: /Truth trail/ }).check()
  await page.getByRole('checkbox', { name: /True position/ }).check()
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  note('play')

  // --- Viento: los dos iconos y los tamaños
  await waitSim(125)
  await pauseRun()
  const home = await viewOf()
  note(`vista inicial (ruta planificada): ${home}, zoom ${await zoomOf()}`)
  const titles = await page.evaluate(() => [...document.querySelectorAll('[data-testid=known-drone] title, [data-testid=true-drone] title')].map((t) => t.textContent))
  note(`tooltips de los iconos: ${titles.join(' | ')}`)
  const legendTitles = await page.evaluate(() => [...document.querySelectorAll('[aria-label="Map layers"] label[title]')].map((l) => l.title))
  note(`tooltips de la leyenda: ${legendTitles.join(' | ')}`)
  await shot('10_viento_dos_iconos_vista_inicial')
  const sizeShot = async (name) => {
    note(`${name}: zoom ${await zoomOf()}, unidad ${await page.locator('[data-testid=drone-map]').getAttribute('data-unit-px')} px`)
    await shot(name)
  }
  await zoomClicks('Zoom out', 3)
  await sizeShot('20_tamanos_zoom_minimo')
  await mapBtn('Center on the drone').click()
  await zoomClicks('Zoom in', 2)
  await sizeShot('21_tamanos_zoom_1')
  await zoomClicks('Zoom in', 1)
  await sizeShot('22_tamanos_zoom_2_3')
  await zoomClicks('Zoom in', 1)
  await mapBtn('Center on the drone').click()
  await sizeShot('23_tamanos_zoom_3_4')
  await zoomClicks('Zoom in', 3)
  await mapBtn('Center on the drone').click()
  await sleep(300)
  await sizeShot('24_tamanos_zoom_alto')
  await zoomClicks('Zoom in', 4)
  await sizeShot('25_tamanos_zoom_maximo_cerca')

  // --- Rejilla sin recuadro, con y sin coordenadas, y la barra de escala
  await mapBtn('Reset view').click()
  await sleep(300)
  note(`reset view: zoom ${await zoomOf()}, vista ${await viewOf()}`)
  await shot('30_rejilla_sin_coordenadas')
  await page.getByRole('checkbox', { name: /Coordinates/ }).check()
  await sleep(300)
  await shot('31_rejilla_con_coordenadas')
  await page.getByRole('checkbox', { name: /Coordinates/ }).uncheck()
  note(`barra de escala: ${await page.locator('[data-testid=scale-bar]').innerText()}`)

  // --- Rueda sin Ctrl: avisa; con Ctrl: zoom
  const box = await page.locator('[data-testid=drone-map]').boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  const z0 = await zoomOf()
  await page.mouse.wheel(0, 120)
  await sleep(250)
  note(`rueda sin Ctrl: zoom ${z0} → ${await zoomOf()}, aviso visible ${(await count('[data-testid=wheel-hint]')) > 0}`)
  await shot('32_aviso_rueda_sin_ctrl')
  await sleep(1800)
  note(`aviso tras 2 s: ${(await count('[data-testid=wheel-hint]')) > 0}`)
  await page.mouse.wheel(0, 120)
  await sleep(250)
  note(`segunda vez, aviso visible ${(await count('[data-testid=wheel-hint]')) > 0} (solo la primera)`)
  await page.keyboard.down('Control')
  await page.mouse.wheel(0, -300)
  await page.keyboard.up('Control')
  await sleep(300)
  note(`Ctrl + rueda: zoom ${z0} → ${await zoomOf()}`)
  await mapBtn('Reset view').click()

  // --- Secuestro: la vista no se recoloca sola. Se fija una vista y se compara a mitad y al final.
  await resumeRun()
  await waitSim(300)
  await pauseRun()
  await mapBtn('Reset view').click()
  await sleep(300)
  const fixed = await viewOf()
  note(`vista fijada antes del secuestro: ${fixed}`)
  await resumeRun()
  await waitSim(400)
  await pauseRun()
  const mid = await viewOf()
  await shot('40_secuestro_a_mitad')
  await resumeRun()
  const end = Date.now() + 8 * 60 * 1000
  while (Date.now() < end && !(await headerText()).includes('Finished')) await sleep(1000)
  await sleep(1500)
  const fin = await viewOf()
  await shot('41_secuestro_al_final')
  note(`vista: antes ${fixed} · a mitad ${mid} · al final ${fin} · sin recolocarse: ${fixed === mid && mid === fin}`)

  // --- Timeline al bajar del todo
  await page.evaluate(() => document.querySelectorAll('main > div')[0].scrollTo(0, 1e6))
  await sleep(400)
  const tl = await page.locator('#timeline-title').evaluate((h) => {
    const sec = h.closest('section')
    const r = sec.getBoundingClientRect()
    const col = document.querySelectorAll('main > div')[0].getBoundingClientRect()
    return { sectionHeight: Math.round(r.height), columnHeight: Math.round(col.height), rows: sec.querySelectorAll('ol > li').length, visibleRows: [...sec.querySelectorAll('ol > li')].filter((li) => li.getBoundingClientRect().bottom <= window.innerHeight).length }
  })
  note(`timeline al fondo: alto ${tl.sectionHeight} px de ${tl.columnHeight} de la columna, ${tl.visibleRows} filas visibles`)
  await shot('50_timeline_al_bajar')

  // --- Filtros con All / None / Default
  const sources = page.getByRole('group', { name: 'Source presets' })
  await sources.getByRole('button', { name: 'None' }).click()
  await sleep(300)
  await shot('51_fuentes_none')
  await sources.getByRole('button', { name: 'All' }).click()
  await sleep(300)
  await shot('52_fuentes_all')
  await sources.getByRole('button', { name: 'Default' }).click()
  await sleep(300)
  note(`Default: ${await page.locator('[aria-label="Filter by source"] input:not(:checked)').evaluateAll((els) => els.map((e) => e.closest('label').textContent.trim()))} sin marcar`)
  await shot('53_fuentes_default')
  const typeMenu = page.locator('details', { has: page.locator('summary', { hasText: 'Type' }) })
  await typeMenu.locator('summary').click()
  await typeMenu.getByRole('button', { name: 'None' }).click()
  note(`Type None: ${(await count('[data-testid=timeline-shown]')) ? await page.locator('[data-testid=timeline-shown]').innerText() : 'sin contador'}`)
  await typeMenu.locator('label', { hasText: 'AnomalyDetected' }).locator('input').check()
  await sleep(300)
  await shot('54_tipo_none_y_una_marcada')
  await typeMenu.getByRole('button', { name: 'All' }).click()
  await typeMenu.locator('summary').click()

  // --- Columnas redimensionables (se recuerda tras recargar)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.evaluate(() => document.querySelectorAll('main > div')[0].scrollTo(0, 0))
  const widthOf = () => page.evaluate(() => Math.round(document.querySelectorAll('main > div')[1].getBoundingClientRect().width))
  const dragHandle = async (dx) => {
    const h = await page.locator('[data-testid=console-handle]').boundingBox()
    await page.mouse.move(h.x + h.width / 2, h.y + h.height / 2)
    await page.mouse.down()
    await page.mouse.move(h.x + h.width / 2 + dx, h.y + h.height / 2, { steps: 8 })
    await page.mouse.up()
    await sleep(300)
  }
  note(`consola: ${await widthOf()} px`)
  await dragHandle(-260)
  note(`consola ancha: ${await widthOf()} px`)
  await shot('60_consola_ancha')
  await dragHandle(900)
  note(`consola al mínimo: ${await widthOf()} px`)
  await shot('61_consola_estrecha')
  await dragHandle(-150)
  const w = await widthOf()
  await page.reload()
  await page.waitForFunction(() => document.querySelectorAll('main > div').length === 2)
  await sleep(1500)
  note(`tras recargar: ${await widthOf()} px (antes ${w})`)
  await page.locator('[data-testid=console-handle]').dblclick()
  await sleep(300)
  note(`doble clic: ${await widthOf()} px`)

  // --- Otros tamaños de ventana
  for (const [vw, vh] of [[1440, 900], [1280, 720]]) {
    await page.setViewportSize({ width: vw, height: vh })
    await sleep(700)
    await page.evaluate(() => document.querySelectorAll('main > div')[0].scrollTo(0, 0))
    await shot(`70_${vw}x${vh}_arriba`)
    await page.evaluate(() => document.querySelectorAll('main > div')[0].scrollTo(0, 1e6))
    await sleep(300)
    await shot(`71_${vw}x${vh}_timeline_al_fondo`)
    const g = await page.getByRole('group', { name: 'Map layers' }).evaluate((el) => ({ rows: new Set([...el.querySelectorAll('fieldset')].map((f) => Math.round(f.getBoundingClientRect().top))).size, overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth }))
    note(`${vw}x${vh}: leyenda en ${g.rows} fila(s), scroll horizontal ${g.overflowX}`)
  }
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, wall_total_s: (Date.now() - t0) / 1000 }, null, 2))
}

async function runTruthLag() {
  await page.setViewportSize({ width: 1920, height: 1080 })
  const report = {}
  for (const speed of [16, 4]) {
    await setup('demo', { waitAgent: false, interactive: false, speed })
    await page.getByRole('checkbox', { name: /True position/ }).check()
    await page.getByRole('button', { name: 'Start', exact: true }).click()
    await waitSim(60)
    const samples = []
    const until = Date.now() + 40000
    // solo hasta T+160, antes del engaño del GPS (que separa los dos iconos a propósito)
    while (Date.now() < until && (await simTime()) < 160) {
      const d = await page.evaluate(() => {
        const c = (id) => {
          const el = document.querySelector(`[data-testid=${id}] polygon`)
          if (!el) return null
          const r = el.getBoundingClientRect()
          return [r.x + r.width / 2, r.y + r.height / 2]
        }
        const a = c('known-drone')
        const b = c('true-drone')
        return a && b ? Math.hypot(a[0] - b[0], a[1] - b[1]) : null
      })
      if (d !== null) samples.push(d)
      await sleep(150)
    }
    samples.sort((a, b) => a - b)
    const q = (p) => samples[Math.min(samples.length - 1, Math.floor(samples.length * p))]
    report[speed] = { n: samples.length, median_px: q(0.5), p90_px: q(0.9), max_px: samples[samples.length - 1], zoom: await zoomOf() }
    note(`${speed}×: distancia en pantalla entre el icono conocido y el real: ${JSON.stringify(report[speed])}`)
    await shot(`80_icono_real_${speed}x`)
    await mapBtn('Pause').click().catch(() => {})
  }
  writeFileSync(`${out}/truthlag.json`, JSON.stringify(report, null, 2))
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, wall_total_s: (Date.now() - t0) / 1000 }, null, 2))
}

/** Junta pares de capturas (izquierda: fase anterior, derecha: ésta) en una sola imagen.
 *  Uso: node scripts/capture.mjs compare <salida> "<img izq>|<img der>|<nombre>" ... */
async function runCompare() {
  const { readFileSync } = await import('node:fs')
  const pairs = process.argv.slice(4).map((a) => a.split('|'))
  await page.setViewportSize({ width: 3840, height: 1100 })
  for (const [left, right, name] of pairs) {
    const img = (f) => `data:image/png;base64,${readFileSync(f).toString('base64')}`
    await page.setContent(`<body style="margin:0;background:#fff;display:flex;gap:8px"><figure style="margin:0"><figcaption style="font:14px monospace;padding:4px">${left.split('/').slice(-2).join('/')}</figcaption><img src="${img(left)}" style="width:1900px"></figure><figure style="margin:0"><figcaption style="font:14px monospace;padding:4px">${right.split('/').slice(-2).join('/')}</figcaption><img src="${img(right)}" style="width:1900px"></figure></body>`)
    await page.screenshot({ path: `${out}/${name}.png`, fullPage: true })
    note(`captura ${name}.png`)
  }
}

try {
  if (mode === 'demo') await runDemo()
  else if (mode === 'radar') await runRadar()
  else if (mode === 'gps') await runGps()
  else if (mode === 'fase9') await runFase9()
  else if (mode === 'fase9_1') await runFase9_1()
  else if (mode === 'truthlag') await runTruthLag()
  else if (mode === 'compare') await runCompare()
  else if (mode === 'layout') await runLayout()
  else if (mode === 'icons') await runIcons()
  else if (mode === 'chatsize') await runChatSize()
  else if (mode === 'deadgps') await runDeadGps()
  else if (mode === 'chattools') await runChatTools()
  else throw new Error(`modo desconocido: ${mode}`)
} catch (e) {
  note(`ERROR: ${e.message}`)
  await shot('error').catch(() => {})
  writeFileSync(`${out}/capture_log.json`, JSON.stringify({ log, error: String(e) }, null, 2))
  process.exitCode = 1
} finally {
  await browser.close()
}
