import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { harnessBundle } from '../harness/bundle.mjs';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import { APP_THEME_COLORS } from '@cad/core/lib/appTheme.js';
import { SCHEMATIC_COLORS, SCHEMATIC_DARK_COLORS, fitBoardBounds, layoutPlot, pageToScreen, schematicFitBounds } from '@cad/core/lib/plot2d/index.js';

// A schematic's one load path, in a real browser: the COMMITTED payload (`__fixtures__/schematic.plot.json`,
// the Python suite's divider), served a sheet at a time as `GET /api/v1/documents/kicad_sch/<id>/plot?sheet=`
// serves it, painted on a real canvas in the host's theme — the sheet's paper on the app's canvas — and a
// press on a wire's pixels picking it and lighting it. What the tab offers is the jsdom suite's.
const SCHEMATIC = JSON.parse(await readFile(new URL('./__fixtures__/schematic.plot.json', import.meta.url), 'utf8'));
const HARNESS_SIZE = '<style>#root > div { width: var(--harness-width, 800px) !important; height: var(--harness-height, 500px) !important; }</style>';
const json = (response, body, status = 200) => { response.statusCode = status; response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(body)); };

let server, browser;
before(async () => {
  const { bundle } = await harnessBundle();
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname.endsWith('/api/v1/documents') && request.method === 'POST') {
      request.resume();
      request.on('end', () => json(response, { id: 'divider', kind: 'kicad_sch', api: '/api/v1/documents/kicad_sch/divider' }, 201));
      return;
    }
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/plot')) {
      const sheet = SCHEMATIC.sheets.find(one => one.path === (url.searchParams.get('sheet') || '/'));
      const { schematic, ...rest } = SCHEMATIC;
      json(response, { ...rest, sheets: [sheet], ...(url.searchParams.get('index') === '0' ? {} : { schematic }) });
    } else if (url.pathname.endsWith('/api/v1/documents') && request.method === 'GET') {
      const entry = { kind: 'kicad_sch', file: '/models/divider.kicad_sch', url: '/divider.kicad_sch', hash: `${root}-divider`, bytes: 4096 };
      json(response, { documents: [{ entry, revision: entry.hash }] });
    } else if (url.pathname.endsWith('/api/v1/server')) json(response, { backend: 'cadgen' });
    else { response.setHeader('Content-Type', 'text/html'); response.end(`<!doctype html><html><head><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
});

const canvasOf = pane => pane.locator('[data-schematic-surface] canvas').first();
const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
async function frame(pane, before = null) {
  await pane.locator('[data-schematic-surface] [aria-busy="false"][data-board-settled="true"]').first().waitFor();
  let last = null;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await settle(pane.page());
    const shot = Buffer.from((await canvasOf(pane).evaluate(canvas => canvas.toDataURL('image/png'))).split(',')[1], 'base64');
    if (last?.equals(shot) && !before?.shot.equals(shot)) return Object.assign(PNG.sync.read(shot), { shot });
    last = shot;
  }
  throw new Error(before ? 'the sheet never came to rest showing the change' : 'the sheet never came to rest');
}
const pixel = (image, x, y) => {
  const offset = (Math.round(y) * image.width + Math.round(x)) * 4;
  return [image.data[offset], image.data[offset + 1], image.data[offset + 2]];
};
const near = (left, right, tolerance = 40) => Math.abs(left[0] - right[0]) + Math.abs(left[1] - right[1]) + Math.abs(left[2] - right[2]) <= tolerance;
const hex = value => [1, 3, 5].map(index => Number.parseInt(value.slice(index, index + 2), 16));

for (const [scheme, paper, surround, lit] of [
  ['dark', SCHEMATIC_DARK_COLORS.background, APP_THEME_COLORS.dark.canvas, [141, 197, 255]],
  ['light', SCHEMATIC_COLORS.background, APP_THEME_COLORS.light.canvas, [31, 111, 235]]
]) {
  test(`in the ${scheme} theme the sheet is its paper on the canvas, and a press on a wire lights it`, async (t) => {
    const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
    t.after(() => page.close());
    page.setDefaultTimeout(20000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => { window.Worker = undefined; window.__cadPromptDestination = 'clipboard'; });
    await page.goto(`http://127.0.0.1:${server.address().port}/?file=divider.kicad_sch&scheme=${scheme}`);
    const pane = page.getByTestId('one');
    const fitted = await frame(pane);
    const canvas = await canvasOf(pane).boundingBox();
    const top = await pane.evaluate(element => Number.parseFloat(getComputedStyle(element.querySelector('[data-slot=cad-file-view]'))
      .getPropertyValue('--cad-tools-bottom')) || 0);
    const layout = layoutPlot({ ...SCHEMATIC, sheets: [SCHEMATIC.sheets[0]] });
    // The fit: the divider is a corner of its A4 page, so what the sheet draws with 10 mm round it (`schematicFitBounds`),
    // the paper past the pane's edges; the page whole, on the canvas round it, is a zoom out away (below).
    const [left, bottom, right, upper] = schematicFitBounds(layout);
    assert.notDeepEqual([left, bottom, right, upper], [...layout.modelBounds]);
    const transform = fitBoardBounds([left, bottom, right, upper], Math.round(canvas.width), Math.round(canvas.height), { top });
    const at = ([x, y]) => pageToScreen(transform, x, y);
    assert.ok(near(pixel(fitted, 2, canvas.height - 2), hex(paper), 12), `the paper, past the pane's corner: ${pixel(fitted, 2, canvas.height - 2)}`);
    // Inside the margin round the content, where the sheet draws nothing: the paper.
    const [inX, inY] = at([left + 3, -upper + 3]);
    assert.ok(near(pixel(fitted, inX, inY), hex(paper), 12), `the paper: ${pixel(fitted, inX, inY)}`);
    // The MID wire to the sheet Load (y = 64.77, x 101.6..127): drawn as the sheet draws it, until a press lights it.
    const [x, y] = at([120, 64.77]);
    assert.ok(!near(pixel(fitted, x, y), lit), `the wire as drawn first: ${pixel(fitted, x, y)}`);
    await page.mouse.click(canvas.x + x, canvas.y + y);
    await page.mouse.move(canvas.x + 2, canvas.y + 2);
    await page.waitForFunction(() => window.cadHarness.a.controller?.readState().selection[0]?.target.selectors[0]?.startsWith('#wire:'));
    const shown = await frame(pane, fitted);
    // The wire is a pixel or so wide at this fit and lies across two rows of pixels, each covered in part: the
    // highlight blended with the sheet under it (the wire as drawn first is its green, 280 away).
    const across = [-1, 0, 1].map(row => pixel(shown, x, y + row));
    assert.ok(across.some(found => near(found, lit, 80)), `the wire is lit where it is: ${across.join(' | ')}`);
    // Zoomed out, the page whole: the app's canvas round the sheet.
    await page.mouse.move(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2);
    await page.mouse.wheel(0, 1200);
    const whole = await frame(pane, shown);
    assert.ok(near(pixel(whole, 2, canvas.height - 2), hex(surround), 12), `the canvas round the sheet: ${pixel(whole, 2, canvas.height - 2)}`);
    assert.deepEqual(errors, []);
  });
}
