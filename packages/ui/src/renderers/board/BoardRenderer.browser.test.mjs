import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { harnessBundle } from '../harness/bundle.mjs';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import { fitPlotTransform, layoutPlot, pageToScreen } from '@cad/core/lib/plot2d/plot.js';

// A board's one load path, in a real browser: the COMMITTED payload (`__fixtures__/README.md`: the
// test board as the engine draws it from its file), served as `GET /api/v1/documents/kicad_pcb/<id>/plot` serves it, painted from
// its rasters on a real canvas, and a press on a pad's pixels picking it and lighting it. What the
// tab offers and what it hands over are the jsdom suite's (`BoardRenderer.test.tsx`).
const BOARD = JSON.parse(await readFile(new URL('./__fixtures__/board.plot.json', import.meta.url), 'utf8'));
const HARNESS_SIZE = '<style>#root > div { width: var(--harness-width, 800px) !important; height: var(--harness-height, 500px) !important; }</style>';

let server, browser;
before(async () => {
  const { bundle } = await harnessBundle();
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname.endsWith('/api/v1/documents') && request.method === 'POST') {
      // The board opened by its path: its document's reads are under its kind, by an id.
      request.resume();
      request.on('end', () => {
        response.statusCode = 201;
        response.setHeader('Content-Type', 'application/json');
        response.end(JSON.stringify({ id: 'blinky', kind: 'kicad_pcb', api: '/api/v1/documents/kicad_pcb/blinky' }));
      });
      return;
    }
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/plot')) { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(BOARD)); }
    else if (url.pathname.endsWith('/api/v1/documents') && request.method === 'GET') {
      response.setHeader('Content-Type', 'application/json');
      const entry = { kind: 'kicad_pcb', file: '/models/blinky.kicad_pcb', url: '/blinky.kicad_pcb', hash: `${root}-blinky`, bytes: 4096 };
      response.end(JSON.stringify({ documents: [{ entry, revision: entry.hash }] }));
    } else if (url.pathname.endsWith('/api/v1/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ backend: 'cadgen' }));
    } else { response.setHeader('Content-Type', 'text/html'); response.end(`<!doctype html><html><head><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
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
  // The board's fit: its margin, clear of the tool strip the frame measures over its top.
  const top = await pane.evaluate(element => Number.parseFloat(getComputedStyle(element.querySelector('[data-slot=cad-file-view]'))
    .getPropertyValue('--cad-tools-bottom')) || 0);
  const transform = fitPlotTransform(layoutPlot(BOARD), Math.round(canvas.width), Math.round(canvas.height), { top });
  const at = ([x, y]) => pageToScreen(transform, x, y);
  // The board on KiCad's canvas: its background off the page as on it, the board's area shadowed over it;
  // the VBUS track (y = 15) red.
  const background = hex(BOARD.sheets[0].background);
  assert.ok(near(pixel(fitted, 2, 2), background, 12), `KiCad's canvas round the board: ${pixel(fitted, 2, 2)}`);
  const [cornerX, cornerY] = at([1, 1]);
  assert.ok(near(pixel(fitted, cornerX, cornerY), [62, 62, 62], 12), `the board's area over it: ${pixel(fitted, cornerX, cornerY)}`);
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
