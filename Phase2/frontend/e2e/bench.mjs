// Manual benchmark: `node e2e/bench.mjs` against `npm run preview`. Reports
// frame timing while the layout runs, on the machine's GPU where available
// (it prints which renderer it got). Headless Chromium may cap at 30 fps, so
// compare cases against each other rather than reading absolute numbers.
import { chromium } from '@playwright/test';
import { syntheticGraph, useFakePipeline } from './helpers.js';

const launch = () => chromium.launch({ channel: 'chromium', args: ['--use-angle=metal', '--ignore-gpu-blocklist'] });
const probeBrowser = await launch();
const probe = await probeBrowser.newPage();
console.log('GPU:', await probe.evaluate(() => {
  const gl = document.createElement('canvas').getContext('webgl2');
  return gl?.getParameter(gl.getExtension('WEBGL_debug_renderer_info')?.UNMASKED_RENDERER_WEBGL ?? gl.RENDERER);
}));
await probeBrowser.close();
const sizes = process.argv.slice(2).map(Number);
if (!sizes.length) sizes.push(75, 1000, 5000, 20000);
const RUN_TIMEOUT_MS = 60_000;

const measure = (page) => page.evaluate(() => new Promise(resolve => {
  const frames = [];
  let last = performance.now();
  const start = last;
  const tick = (now) => {
    frames.push(now - last);
    last = now;
    if (now - start < 5000) requestAnimationFrame(tick);
    else {
      frames.sort((a, b) => a - b);
      resolve({ fps: Math.round(frames.length / 5), p95ms: Math.round(frames[Math.floor(frames.length * 0.95)]), heapMB: Math.round((performance.memory?.usedJSHeapSize || 0) / 1e6) });
    }
  };
  requestAnimationFrame(tick);
}));

for (const size of sizes) {
  for (const [view, all] of [['2D', false], ['2D', true], ['3D', false], ['3D', true]]) {
    if (view === '3D' && all && size > 980) continue; // over MAX_3D_NODES
    // A fresh browser per case: a heavy earlier page otherwise slows the next one.
    const browser = await launch();
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const label = { messages: size, view, mode: all ? 'all' : 'overview' };
    const run = async () => {
      await useFakePipeline(page, syntheticGraph(size, Math.max(10, Math.round(size / 200))));
      await page.goto('http://localhost:4173/');
      await page.locator('input[type="file"]').setInputFiles({ name: 'c.txt', mimeType: 'text/plain', buffer: Buffer.from('x') });
      await page.locator('canvas').first().waitFor();
      if (all) await page.getByRole('checkbox', { name: 'Show every message' }).check();
      if (view === '3D') await page.getByRole('button', { name: '3D', exact: true }).click();
      await page.waitForTimeout(1500);
      return measure(page);
    };
    const timeout = new Promise(resolve => setTimeout(() => resolve({ result: `no result in ${RUN_TIMEOUT_MS / 1000}s` }), RUN_TIMEOUT_MS));
    console.log(JSON.stringify({ ...label, ...(await Promise.race([run().catch(e => ({ error: e.message.split('\n')[0] })), timeout])) }));
    // Closing can hang on a page that's still saturated.
    await Promise.race([browser.close().catch(() => {}), new Promise(resolve => setTimeout(resolve, 5000))]);
  }
}
process.exit(0);
