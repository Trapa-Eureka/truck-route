// Frame-time measurement for the map: real mouse input over the Chrome DevTools Protocol, with CPU
// throttling. It opens the app, runs the form (Chicago to Denver, 10-mile checkpoints: the most
// checkpoints the form allows), waits for the routes and the heatmap, then records the time between
// animation frames while it
//   1. sweeps the forecast slider 0 -> 48 -> 0,
//   2. zooms in, pans around and zooms out (the Step 2 protocol), and
//   3. sweeps the slider while panning.
//
// Usage (the backend must be running, and the app served: `npm run build && npx vite preview`):
//   node scripts/measure-frames.mjs [url] [cpu slowdowns]      e.g.  http://localhost:4173/ 1,4,6
//   PROFILE=1 node scripts/measure-frames.mjs http://localhost:4173/ 6     # where a slider step spends its time
// Set CHROME_PATH if Chrome is not in the macOS default place. Needs Node 22+ (built-in WebSocket).

import { spawn } from 'node:child_process'
import { setTimeout as sleep } from 'node:timers/promises'

const URL_ = process.argv[2] ?? 'http://localhost:4173/'
const RATES = (process.argv[3] ?? '1,4,6').split(',').map(Number)
const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const PORT = 9333

const chrome = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${process.env.TMPDIR ?? '/tmp'}/spotter-perf-profile`, '--no-first-run',
  '--no-default-browser-check', '--window-size=1568,900', '--disable-background-timer-throttling',
  '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows', 'about:blank',
], { stdio: 'ignore' })

async function target() {
  for (let i = 0; i < 50; i++) {
    try {
      const tabs = await (await fetch(`http://localhost:${PORT}/json`)).json()
      const page = tabs.find((t) => t.type === 'page')
      if (page) return page.webSocketDebuggerUrl
    } catch {}
    await sleep(200)
  }
  throw new Error('Chrome did not start')
}

const ws = new WebSocket(await target())
await new Promise((r) => (ws.onopen = r))
let id = 0
const pending = new Map()
ws.onmessage = (m) => { const msg = JSON.parse(m.data); if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id) } }
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const mid = ++id
  pending.set(mid, (msg) => (msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)))
  ws.send(JSON.stringify({ id: mid, method, params }))
})
const evaluate = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? 'evaluate failed')
  return r.result.value
}

const stats = (frames) => {
  const s = [...frames].sort((a, b) => a - b), q = (p) => s[Math.min(s.length - 1, Math.floor(s.length * p))]
  return { frames: frames.length, avg: +(frames.reduce((a, b) => a + b, 0) / frames.length).toFixed(1), p95: +q(0.95).toFixed(1), p99: +q(0.99).toFixed(1), max: +s[s.length - 1].toFixed(1), over50: frames.filter((f) => f > 50).length, over100: frames.filter((f) => f > 100).length }
}

const RECORDER = `(() => { const rec = window.__rec = { frames: [], on: false, last: 0, long: 0 };
  new PerformanceObserver((l) => { if (rec.on) rec.long += l.getEntries().length }).observe({ entryTypes: ['longtask'] });
  const loop = (t) => { if (rec.on) { if (rec.last) rec.frames.push(t - rec.last); rec.last = t } requestAnimationFrame(loop) };
  requestAnimationFrame(loop); })()`
const start = () => evaluate(`window.__rec.frames = []; window.__rec.long = 0; window.__rec.last = 0; window.__rec.on = true`)
const stop = () => evaluate(`window.__rec.on = false; JSON.stringify({ frames: window.__rec.frames, long: window.__rec.long })`).then(JSON.parse)

const SWEEP = `(async () => { const s = document.getElementById('forecast-hour');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  for (let pass = 0; pass < 2; pass++) for (let h = 0; h <= 48; h++) { set.call(s, String(pass ? 48 - h : h)); s.dispatchEvent(new Event('input', { bubbles: true })); await new Promise((r) => requestAnimationFrame(r)) }
  return true })()`

const mouse = (type, x, y, extra = {}) => send('Input.dispatchMouseEvent', { type, x, y, button: 'left', buttons: type === 'mouseReleased' ? 0 : 1, clickCount: 1, ...extra })
async function wheel(x, y, deltaY, times, gap = 90) { for (let i = 0; i < times; i++) { await send('Input.dispatchMouseEvent', { type: 'mouseWheel', x, y, deltaX: 0, deltaY }); await sleep(gap) } }
async function drag(x1, y1, x2, y2, steps = 25) { await mouse('mouseMoved', x1, y1, { buttons: 0 }); await mouse('mousePressed', x1, y1); for (let i = 1; i <= steps; i++) { await mouse('mouseMoved', x1 + ((x2 - x1) * i) / steps, y1 + ((y2 - y1) * i) / steps); await sleep(16) } await mouse('mouseReleased', x2, y2) }

// zoom in, pan around, zoom out: the Step 2 protocol, now with 3 routes, the heatmap and checkpoint dots
async function panAndZoom() {
  const cx = 900, cy = 450
  await wheel(cx, cy, -120, 8)
  for (const [dx, dy] of [[300, 0], [-300, 120], [0, -220], [-250, 0], [250, 100], [-100, 200]]) { await drag(cx, cy, cx + dx, cy + dy); await sleep(150) }
  await wheel(cx, cy, 120, 8)
  await sleep(500)
}

const results = []
try {
  await send('Page.enable'); await send('Runtime.enable')
  for (const rate of RATES) {
    await send('Emulation.setCPUThrottlingRate', { rate: 1 })
    const t0 = Date.now()
    await send('Page.navigate', { url: URL_ })
    await sleep(500)
    await send('Emulation.setCPUThrottlingRate', { rate })
    // wait for the form, measure first-load numbers
    for (let i = 0; i < 100 && !(await evaluate(`!!document.querySelector('button.primary')`)); i++) await sleep(100)
    const formReadyMs = Date.now() - t0
    const load = await evaluate(`JSON.stringify({ fcp: Math.round(performance.getEntriesByType('paint').find((p) => p.name === 'first-contentful-paint')?.startTime ?? -1), transferKB: Math.round(performance.getEntriesByType('resource').reduce((a, e) => a + (e.transferSize || 0), 0) / 1024), jsKB: Math.round(performance.getEntriesByType('resource').filter((e) => e.name.endsWith('.js') || e.name.endsWith('.mjs')).reduce((a, e) => a + (e.encodedBodySize || 0), 0) / 1024) })`).then(JSON.parse)
    await evaluate(RECORDER)
    // 10-mile interval: the most checkpoints (and timeline items) the form allows
    await evaluate(`[...document.querySelectorAll('.segmented label')].find((l) => l.textContent.includes('10 mi')).click()`)
    await evaluate(`document.querySelector('button.primary').click()`)
    const a0 = Date.now()
    for (let i = 0; i < 600 && !(await evaluate(`!!document.getElementById('forecast-hour')`)); i++) await sleep(150)
    const resultsMs = Date.now() - a0
    await sleep(2500) // let the map finish fitting the routes
    const dots = await evaluate(`document.querySelectorAll('.timeline li').length`)

    if (process.env.PROFILE) {
      await send('Profiler.enable'); await send('Profiler.setSamplingInterval', { interval: 200 }); await send('Profiler.start')
      await evaluate(SWEEP)
      const { profile } = await send('Profiler.stop')
      const self = new Map(), byId = new Map(profile.nodes.map((n) => [n.id, n]))
      profile.samples.forEach((nodeId, i) => { const n = byId.get(nodeId), f = n.callFrame, key = `${f.functionName || '(anonymous)'} ${f.url.split('/').pop()}:${f.lineNumber}`; self.set(key, (self.get(key) || 0) + (profile.timeDeltas[i] || 0)) })
      const total = [...self.values()].reduce((a, b) => a + b, 0)
      console.log(`total sampled ${(total / 1000).toFixed(0)} ms over the sweep (97 steps = ${(total / 97000).toFixed(1)} ms of main-thread work per step at ${rate}x slowdown)`)
      for (const [k, v] of [...self].sort((a, b) => b[1] - a[1]).slice(0, 14)) console.log(`  ${(v / 1000).toFixed(0).padStart(5)} ms  ${k}`)
      continue
    }
    const phases = {}
    await start(); await evaluate(SWEEP); phases.slider = stats((await stop()).frames)
    await start(); await panAndZoom(); const pz = await stop(); phases.panZoom = { ...stats(pz.frames), longTasks: pz.long }
    await start(); const sweep = evaluate(SWEEP); await sleep(300); await drag(900, 450, 700, 380, 60); await sweep; const both = await stop(); phases.sliderWhilePanning = { ...stats(both.frames), longTasks: both.long }
    results.push({ cpuSlowdown: rate, formReadyMs, load, resultsMs, timelineItems: dots, phases })
    console.log(JSON.stringify(results.at(-1)))
  }
} finally {
  try { await send('Emulation.setCPUThrottlingRate', { rate: 1 }) } catch {}
  ws.close(); chrome.kill()
}
