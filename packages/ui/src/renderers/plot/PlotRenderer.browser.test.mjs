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

// The plots under test are COMMITTED, hand-made payloads in KiCad's shape (see
// `__fixtures__/README.md`), served as `GET /__cad/plot` serves them: no KiCad, no board.
const BOARD = JSON.parse(await readFile(new URL('./__fixtures__/board.plot.json', import.meta.url), 'utf8'));
const SCHEMATIC = JSON.parse(await readFile(new URL('./__fixtures__/schematic.plot.json', import.meta.url), 'utf8'));
const HARNESS = JSON.parse(await readFile(new URL('./__fixtures__/harness.plot.json', import.meta.url), 'utf8'));
const PLOTS = { 'blinky.kicad_pcb': BOARD, 'blinky.kicad_sch': SCHEMATIC, 'cable.harness.yml': HARNESS };
const NO_KICAD = "KiCad's command line, kicad-cli, was not found: install KiCad 10 from https://www.kicad.org/download/.";

// The harness renders its pane at a fixed CSS size; the spec draws it smaller.
const HARNESS_SIZE = '<style>#root > div { width: var(--harness-width, 800px) !important; height: var(--harness-height, 500px) !important; }</style>';

let temporary, server, browser;
before(async () => {
  temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-plot-browser-'));
  await build({ entryPoints: [fileURLToPath(new URL('../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.avif': 'dataurl', '.woff2': 'dataurl', '.svg': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  const files = ['blinky.kicad_pcb', 'blinky.kicad_sch', 'cable.harness.yml', 'broken.kicad_pcb'];
  const kindOf = file => (file.endsWith('.harness.yml') ? 'harness' : file.split('.').pop());
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/__cad/plot')) {
      const plot = PLOTS[url.searchParams.get('file')];
      response.setHeader('Content-Type', 'application/json');
      if (!plot) { response.statusCode = 400; response.end(JSON.stringify({ error: NO_KICAD })); return; }
      response.end(JSON.stringify(plot));
    } else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: files.map(file => (
        { kind: kindOf(file), file, rootRelativeFile: file, url: `/${file}`, hash: `${root}-${file}`, bytes: 4096 })) }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
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

async function open(t, file) {
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
  t.after(() => page.close());
  page.setDefaultTimeout(20000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  // A clipboard host, like web: a capture is handed over, never queued.
  await page.addInitScript(() => { window.Worker = undefined; window.__cadPromptDestination = 'clipboard'; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=${file}`);
  return { page, errors, pane: page.getByTestId('one') };
}

const canvasOf = pane => pane.locator('[data-plot-surface] canvas').first();
const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
/**
 * The frame ON SCREEN once the pane says it is final — drawn at the scale it is shown at, not a
 * patch scaled while the view rests — and has come to rest (two screenshots alike); given the
 * frame from before a change, once it shows that change.
 */
async function frame(pane, before = null) {
  await canvasOf(pane).waitFor();
  await pane.locator('[data-plot-surface] [aria-busy="false"][data-plot-settled="true"]').first().waitFor();
  let last = null;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await settle(pane.page());
    await pane.locator('[data-plot-surface] [data-plot-settled="true"]').first().waitFor();
    const shot = await canvasOf(pane).screenshot();
    if (last?.equals(shot) && !before?.shot.equals(shot)) return Object.assign(PNG.sync.read(shot), { shot });
    last = shot;
  }
  throw new Error(before ? 'the plot never came to rest showing the change' : 'the plot never came to rest');
}
const pixel = (image, x, y) => {
  const offset = (Math.round(y) * image.width + Math.round(x)) * 4;
  return [image.data[offset], image.data[offset + 1], image.data[offset + 2]];
};
const near = (left, right, tolerance = 12) =>
  Math.abs(left[0] - right[0]) + Math.abs(left[1] - right[1]) + Math.abs(left[2] - right[2]) <= tolerance;
const hex = value => [1, 3, 5].map(index => Number.parseInt(value.slice(index, index + 2), 16));
/** The box of everything that is not the surround (the pane's corner colour). */
function sheetBox(image) {
  const surround = pixel(image, 0, 0);
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (let y = 0; y < image.height; y += 1) {
    for (let x = 0; x < image.width; x += 1) {
      if (near(pixel(image, x, y), surround)) continue;
      minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }
  }
  return { minX, minY, maxX, maxY, width: maxX - minX + 1, height: maxY - minY + 1, surround };
}
/** Runs down one column: [colour test, length] for each stretch of pixels the test accepts. */
function run(image, x, from, to, accept) {
  let length = 0, best = 0;
  for (let y = from; y <= to; y += 1) {
    length = accept(pixel(image, x, y)) ? length + 1 : 0;
    best = Math.max(best, length);
  }
  return best;
}
const red = ([r, g, b]) => r > 150 && g < 90 && b < 90;
const wheelAt = (page, box, point, deltaY) => page.mouse.move(box.x + point.x, box.y + point.y).then(() => page.mouse.wheel(0, deltaY));
/** The wheel delta the pane reads as `factor`: it zooms by exp(-deltaY * 0.0015). */
const deltaForFactor = factor => -Math.log(factor) / 0.0015;

test('a board opens fitted on its own background, its tracks drawn, and stays sharp when zoomed', async (t) => {
  const { page, pane, errors } = await open(t, 'blinky.kicad_pcb');
  const fitted = await frame(pane);
  const box = sheetBox(fitted);
  // Fitted: the board's 4:3, centred, filling the pane but for the 16 px gutter on the tight axis.
  assert.ok(Math.abs(box.width / box.height - 40 / 30) < 0.02, `the board's own aspect: ${box.width}x${box.height}`);
  assert.ok(Math.abs((box.minX + box.maxX) / 2 - fitted.width / 2) <= 1.5 && Math.abs((box.minY + box.maxY) / 2 - fitted.height / 2) <= 1.5,
    `centred: ${JSON.stringify(box)}`);
  assert.ok(Math.abs(box.height - (fitted.height - 32)) <= 2, `fitted to the gutter: ${box.height} in ${fitted.height}`);
  // The sheet is on KiCad's board background, the surround is the theme's.
  assert.ok(near(pixel(fitted, box.minX + 4, box.minY + 4), hex(BOARD.sheets[0].background)), `board background: ${pixel(fitted, box.minX + 4, box.minY + 4)}`);
  assert.ok(near(box.surround, [255, 255, 255]), `light surround: ${box.surround}`);
  // The 1 mm track across the middle (y = 15 of 30) is KiCad's red, as thick as 1 mm is here.
  const scale = box.width / 40;
  const column = Math.round(box.minX + 20 * scale);
  const middle = box.minY + 15 * scale;
  assert.ok(red(pixel(fitted, column, middle)), `the track: ${pixel(fitted, column, middle)}`);
  const atFit = run(fitted, column, box.minY, box.maxY, red);
  assert.ok(Math.abs(atFit - scale) <= 2, `1 mm of track is ${atFit} px at ${scale} px/mm`);

  // Zoomed in about the track, the view is drawn again at its own scale: four times as thick,
  // and its edges as sharp as at the fit — not the fitted picture blown up.
  const canvas = await canvasOf(pane).boundingBox();
  await wheelAt(page, canvas, { x: column, y: middle }, deltaForFactor(4));
  const zoomed = await frame(pane, fitted);
  const atZoom = run(zoomed, column, 0, zoomed.height - 1, red);
  assert.ok(Math.abs(atZoom - 4 * scale) <= 3, `four times as thick: ${atZoom} px for ${4 * scale}`);
  const background = hex(BOARD.sheets[0].background);
  let edge = 0;
  for (let y = 0; y < zoomed.height; y += 1) {
    const value = pixel(zoomed, column, y);
    if (!red(value) && !near(value, background, 40)) edge += 1;
  }
  assert.ok(edge <= 4, `a sharp edge, not a blur: ${edge} px between the track and the board`);
  assert.deepEqual(errors, []);
});

test('a schematic’s sheets stand one under another, root first, each on KiCad’s paper', async (t) => {
  const { pane, errors } = await open(t, 'blinky.kicad_sch');
  const image = await frame(pane);
  const box = sheetBox(image);
  const paper = hex(SCHEMATIC.sheets[0].background);
  const [first, second] = SCHEMATIC.sheets;
  const gap = first.width * 0.04;
  const scale = box.height / (first.height + gap + second.height);
  assert.ok(Math.abs(box.width - first.width * scale) <= 2, 'the widest sheet sets the width');
  const centreX = (box.minX + box.maxX) / 2;
  // Root sheet, then the gap (the surround), then the second, smaller sheet centred under it.
  assert.ok(near(pixel(image, centreX, box.minY + 20 * scale), paper), 'the root sheet is on paper');
  assert.ok(near(pixel(image, centreX, box.minY + (first.height + gap / 2) * scale), box.surround), 'the gap is the surround');
  const secondTop = box.minY + (first.height + gap) * scale;
  assert.ok(near(pixel(image, centreX, secondTop + 20 * scale), paper), 'the second sheet is on paper');
  const secondLeft = centreX - (second.width / 2) * scale;
  assert.ok(near(pixel(image, secondLeft - 4, secondTop + 20 * scale), box.surround), 'and narrower, centred under the first');
  assert.deepEqual(errors, []);
});

test('the theme is the surround only: the board keeps its own background', async (t) => {
  const { page, pane, errors } = await open(t, 'blinky.kicad_pcb');
  const light = await frame(pane);
  const lightBox = sheetBox(light);
  await page.evaluate(() => document.documentElement.classList.add('dark'));
  const dark = await frame(pane, light);
  const darkBox = sheetBox(dark);
  assert.ok(darkBox.surround[0] < 110, `a dark surround: ${darkBox.surround}`);
  assert.ok(near(pixel(dark, darkBox.minX + 4, darkBox.minY + 4), hex(BOARD.sheets[0].background)), 'the board background is KiCad’s');
  assert.deepEqual([darkBox.minX, darkBox.minY, darkBox.maxX], [lightBox.minX, lightBox.minY, lightBox.maxX], 'the theme is not a camera move');
  assert.deepEqual(errors, []);
});

test('a wiring harness is WireViz’s diagram, sized in points, on its white page', async (t) => {
  const { page, pane, errors } = await open(t, 'cable.harness.yml');
  const light = await frame(pane);
  // On a dark surround the white page shows whole: fitted to Graphviz's 216 x 108 pt, centred.
  await page.evaluate(() => document.documentElement.classList.add('dark'));
  const image = await frame(pane, light);
  const box = sheetBox(image);
  assert.ok(Math.abs(box.width / box.height - 2) < 0.03, `the diagram's own aspect: ${box.width}x${box.height}`);
  assert.ok(Math.abs(box.width - (image.width - 32)) <= 2, `fitted to the gutter: ${box.width} in ${image.width}`);
  assert.ok(near(pixel(image, box.minX + box.width / 2, box.minY + box.height * 0.15), hex(HARNESS.sheets[0].background)), 'on WireViz’s page colour');
  // The wire runs across the middle (y = 54 of 108 pt, x = 24..192 of 216): Graphviz's y-up
  // transform lands it where WireViz drew it.
  const wire = pixel(image, box.minX + box.width / 2, box.minY + box.height / 2);
  assert.ok(red(wire), `the wire: ${wire}`);
  assert.ok(!red(pixel(image, box.minX + box.width * 0.05, box.minY + box.height / 2)), 'and starts where the diagram starts it');
  assert.equal(await canvasOf(pane).getAttribute('aria-label'), 'Harness: cable.harness.yml');
  assert.deepEqual(errors, []);
});

test('a capture is the view as a PNG: the SVG drawn on the canvas does not taint it', async (t) => {
  const { page, pane, errors } = await open(t, 'blinky.kicad_pcb');
  await frame(pane);
  await page.evaluate(() => window.cadHarness.capture());
  await page.waitForFunction(() => window.cadHarness.captures.length > 0);
  const [capture] = await page.evaluate(() => window.cadHarness.captures);
  assert.equal(capture.type, 'image/png');
  assert.ok(capture.size > 1000, `a real picture: ${capture.size} bytes`);
  assert.deepEqual(errors, []);
});

test('a library card’s picture is the whole board, fitted, whatever the view on screen', async (t) => {
  const { page, pane, errors } = await open(t, 'blinky.kicad_pcb');
  const fitted = await frame(pane);
  const canvas = await canvasOf(pane).boundingBox();
  await wheelAt(page, canvas, { x: 200, y: 200 }, deltaForFactor(5));
  await frame(pane, fitted);
  const encoded = await page.evaluate(async () => {
    const blob = await window.cadHarness.a.controller.thumbnail({ width: 200, height: 150 });
    return { type: blob.type, data: await new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsDataURL(blob); }) };
  });
  assert.equal(encoded.type, 'image/png');
  const picture = PNG.sync.read(Buffer.from(encoded.data.split(',')[1], 'base64'));
  assert.deepEqual([picture.width, picture.height], [200, 150]);
  const box = sheetBox(picture);
  // Fitted as the pane fits it: height is the tight axis of a 200 x 150 card, inside the 16 px gutter.
  assert.ok(Math.abs(box.height - 118) <= 2 && Math.abs(box.width - 118 * 40 / 30) <= 2, `fitted: ${JSON.stringify(box)}`);
  assert.ok(Math.abs((box.minX + box.maxX) / 2 - 100) <= 1.5 && Math.abs((box.minY + box.maxY) / 2 - 75) <= 1.5, `centred: ${JSON.stringify(box)}`);
  assert.ok(near(pixel(picture, box.minX + 2, box.minY + 2), hex(BOARD.sheets[0].background)), 'on the board background');
  assert.deepEqual(errors, []);
});

test('the view a person chose is the file view’s camera, and comes back when the tab is reopened', async (t) => {
  const { page, pane, errors } = await open(t, 'blinky.kicad_pcb');
  const fitted = await frame(pane);
  const canvas = await canvasOf(pane).boundingBox();
  await wheelAt(page, canvas, { x: canvas.width * 0.3, y: canvas.height * 0.6 }, deltaForFactor(3));
  const chosen = sheetBox(await frame(pane, fitted));
  const key = JSON.stringify(['blinky.kicad_pcb', 'plot']);
  await page.waitForFunction(stateKey => window.cadHarness.state.renderers?.[stateKey]?.camera?.scale > 0, key);
  const record = await page.evaluate(stateKey => window.cadHarness.state.renderers[stateKey], key);
  assert.deepEqual(Object.keys(record.camera).sort(), ['offsetX', 'offsetY', 'scale']);
  await page.evaluate(() => window.cadHarness.mounted(false));
  await canvasOf(pane).waitFor({ state: 'detached' });
  await page.evaluate(() => window.cadHarness.mounted(true));
  const reopened = sheetBox(await frame(pane));
  assert.ok(Math.abs(reopened.minX - chosen.minX) <= 2 && Math.abs(reopened.height - chosen.height) <= 2,
    `reopened where it was left: ${JSON.stringify(reopened)} vs ${JSON.stringify(chosen)}`);
  assert.deepEqual(errors, []);
});

test('a machine without KiCad shows the server’s own sentence, and not a spinner forever', async (t) => {
  const { pane, errors } = await open(t, 'broken.kicad_pcb');
  const alert = pane.getByRole('alert');
  await alert.waitFor();
  const text = await alert.innerText();
  assert.match(text, /The viewer couldn’t complete the request/);
  assert.match(text, /HTTP 400/);
  assert.match(text, /install KiCad 10/);
  assert.equal(await pane.locator('[data-viewer-loading]').count(), 0);
  assert.deepEqual(errors, []);
});
