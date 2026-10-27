import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import { fitPlotTransform, layoutPlot, pageToScreen } from '@text-to-cad/core/lib/plot2d/plot.js';

// A board's one load path, in a real browser: the COMMITTED payload (`__fixtures__/README.md`: the
// test board as cadgen draws it from its file), served as `GET /__cad/plot` serves it, painted from
// its rasters on a real canvas, and a press on a pad's pixels picking it and lighting it. What the
// tab offers and what it hands over are the jsdom suite's (`BoardRenderer.test.tsx`).
const BOARD = JSON.parse(await readFile(new URL('./__fixtures__/board.plot.json', import.meta.url), 'utf8'));
const HARNESS_SIZE = '<style>#root > div { width: var(--harness-width, 800px) !important; height: var(--harness-height, 500px) !important; }</style>';

let temporary, server, browser;
before(async () => {
  temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-board-browser-'));
  await build({ entryPoints: [fileURLToPath(new URL('../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.avif': 'dataurl', '.woff2': 'dataurl', '.svg': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/__cad/plot')) { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(BOARD)); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ entries: [{ kind: 'kicad_pcb', file: '/models/blinky.kicad_pcb', url: '/blinky.kicad_pcb', hash: `${root}-blinky`, bytes: 4096 }] }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ backend: 'cadgen' }));
    } else { response.setHeader('Content-Type', 'text/html'); response.end(`<!doctype html><html><head><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
  if (temporary) await rm(temporary, { recursive: true, force: true });
});

const canvasOf = pane => pane.locator('[data-board-surface] canvas').first();
const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
/** The frame the pane painted once it is final and at rest (two reads alike); after `before`, once it changed. */
async function frame(pane, before = null) {
  await pane.locator('[data-board-surface] [aria-busy="false"][data-board-settled="true"]').first().waitFor();
  let last = null;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await settle(pane.page());
    const shot = Buffer.from((await canvasOf(pane).evaluate(canvas => canvas.toDataURL('image/png'))).split(',')[1], 'base64');
    if (last?.equals(shot) && !before?.shot.equals(shot)) return Object.assign(PNG.sync.read(shot), { shot });
    last = shot;
  }
  throw new Error(before ? 'the board never came to rest showing the change' : 'the board never came to rest');
}
const pixel = (image, x, y) => {
  const offset = (Math.round(y) * image.width + Math.round(x)) * 4;
  return [image.data[offset], image.data[offset + 1], image.data[offset + 2]];
};
const near = (left, right, tolerance = 40) => Math.abs(left[0] - right[0]) + Math.abs(left[1] - right[1]) + Math.abs(left[2] - right[2]) <= tolerance;
const hex = value => [1, 3, 5].map(index => Number.parseInt(value.slice(index, index + 2), 16));
const red = ([r, g, b]) => r > 150 && g < 90 && b < 90;

test('a board opens fitted on its own background, its track in KiCad’s red, and a press on a pad picks it and lights it', async (t) => {
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
  t.after(() => page.close());
  page.setDefaultTimeout(20000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; window.__cadPromptDestination = 'clipboard'; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=blinky.kicad_pcb`);
  const pane = page.getByTestId('one');
  const fitted = await frame(pane);
  const canvas = await canvasOf(pane).boundingBox();
  const transform = fitPlotTransform(layoutPlot(BOARD), Math.round(canvas.width), Math.round(canvas.height));
  const at = ([x, y]) => pageToScreen(transform, x, y);
  // The sheet on KiCad's board background, the surround the theme's; the VBUS track (y = 15) red.
  const [cornerX, cornerY] = at([1, 1]);
  assert.ok(near(pixel(fitted, cornerX, cornerY), hex(BOARD.sheets[0].background), 12), `board background: ${pixel(fitted, cornerX, cornerY)}`);
  const surround = await canvasOf(pane).evaluate(element => {
    const style = getComputedStyle(element.closest('[data-cad-flat-view]') || element);
    const probe = document.createElement('canvas');
    probe.width = probe.height = 1;
    const context = probe.getContext('2d');
    context.fillStyle = style.getPropertyValue('--background');
    context.fillRect(0, 0, 1, 1);
    const rgb = [...context.getImageData(0, 0, 1, 1).data].slice(0, 3);
    return rgb;
  });
  assert.ok(near(pixel(fitted, 2, 2), surround, 12), `theme surround: ${pixel(fitted, 2, 2)}`);
  const [trackX, trackY] = at([30, 15]);
  assert.ok(red(pixel(fitted, trackX, trackY)), `the track: ${pixel(fitted, trackX, trackY)}`);
  // R1 pad 2 (35.825, 15): drawn as the board draws it, until a press selects it and lights it.
  const highlight = [141, 197, 255];
  const [x, y] = at([35.825, 15]);
  assert.ok(!near(pixel(fitted, x, y), highlight), `the pad as drawn first: ${pixel(fitted, x, y)}`);
  await page.mouse.click(canvas.x + x, canvas.y + y);
  await page.mouse.move(canvas.x + 2, canvas.y + 2);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().selection[0]?.target.selectors[0] === '#R1.2');
  const lit = await frame(pane, fitted);
  assert.ok(near(pixel(lit, x, y), highlight), `the pad is lit where it is: ${pixel(lit, x, y)}`);
  assert.deepEqual(errors, []);
});
