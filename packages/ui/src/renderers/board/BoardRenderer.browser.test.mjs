import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { harnessBundle } from '../harness/bundle.mjs';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import { fitPlotTransform, layoutPlot, pageToScreen } from '@cad/core/lib/plot2d/plot.js';
import { boardPalette } from '@cad/core/lib/plot2d/theme.js';

// A board's one load path, in a real browser: the COMMITTED payload (`__fixtures__/README.md`: the
// test board as the engine draws it from its file), served as `GET /api/v1/documents/kicad_pcb/<id>/plot` serves it, painted from
// its rasters on a real canvas, and a press on a pad's pixels picking it and lighting it. What the
// tab offers and what it hands over are the jsdom suite's (`BoardRenderer.test.tsx`).
const BOARD = JSON.parse(await readFile(new URL('./__fixtures__/board.plot.json', import.meta.url), 'utf8'));
// A part's 3D model, as the engine serves a STEP it read: core's bracket (`lib/xbf/__fixtures__/bracket`, a 40 x 20 x 4
// plate and two pegs), its structure and its two part buffers, under `/api/v1/documents/step/bracket`.
const BRACKET = new URL('../../../../core/src/lib/xbf/__fixtures__/bracket/', import.meta.url);
// The bracket's document id, as the models table names a STEP it resolved (a document id is a uuid).
const BRACKET_ID = 'b4ac0e70-0000-4000-8000-000000000001';
// What the board's routes answer now: its plot, and its models table (none: a 404, as a server without the route);
// `revision` names a revision of the file past the first.
let served = { plot: BOARD, models: null };
const HARNESS_SIZE = '<style>#root > div { width: var(--harness-width, 800px) !important; height: var(--harness-height, 500px) !important; }</style>';

let server, browser;
before(async () => {
  const { bundle } = await harnessBundle();
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname.endsWith('/api/v1/documents') && request.method === 'POST') {
      // The board opened by its path, or a model by the id its models table gave: its reads are under its kind, by an id.
      let body = '';
      request.on('data', chunk => { body += chunk; });
      request.on('end', () => {
        const model = JSON.parse(body || '{}').id === BRACKET_ID;
        response.statusCode = 201;
        response.setHeader('Content-Type', 'application/json');
        response.end(JSON.stringify(model ? { id: 'bracket', kind: 'step', api: '/api/v1/documents/step/bracket' }
          : { id: 'blinky', kind: 'kicad_pcb', api: '/api/v1/documents/kicad_pcb/blinky' }));
      });
      return;
    }
    if (url.pathname.endsWith('/api/v1/documents/step/bracket/structure')) {
      readFile(new URL('structure.json', BRACKET)).then(bytes => { response.setHeader('Content-Type', 'application/json'); response.end(bytes); });
      return;
    }
    const part = /\/api\/v1\/documents\/step\/bracket\/parts\/([0-9a-f]+)$/.exec(url.pathname);
    if (part) {
      readFile(new URL(`${part[1]}.xbm`, BRACKET)).then(bytes => { response.setHeader('Content-Type', 'application/octet-stream'); response.end(bytes); });
      return;
    }
    if (url.pathname.endsWith('/models')) {
      response.statusCode = served.models ? 200 : 404;
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify(served.models ? { models: served.models } : { error: 'no route' }));
      return;
    }
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/plot')) { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(served.plot)); }
    else if (url.pathname.endsWith('/api/v1/documents') && request.method === 'GET') {
      response.setHeader('Content-Type', 'application/json');
      const entry = { kind: 'kicad_pcb', file: '/models/blinky.kicad_pcb', url: '/blinky.kicad_pcb', hash: `${root}-blinky${served.revision ? `-${served.revision}` : ''}`, bytes: 4096 };
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
  // The board on the app's canvas: the theme's background off the page as on it, the board's area shadowed
  // over it (its 35% grey); the VBUS track (y = 15) red.
  const background = hex(boardPalette('dark').background);
  assert.ok(near(pixel(fitted, 2, 2), background, 12), `the canvas round the board: ${pixel(fitted, 2, 2)}`);
  const [cornerX, cornerY] = at([1, 1]);
  const area = background.map(channel => Math.round(channel + 0.35 * (100 - channel)));
  assert.ok(near(pixel(fitted, cornerX, cornerY), area, 12), `the board's area over it: ${pixel(fitted, cornerX, cornerY)}`);
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

/** A world point's pixel on the 3D view's canvas, through its live orthographic camera (`window.__cadCamera`). */
const project3d = (camera, point, width, height) => {
  const sub = (a, b) => a.map((v, i) => v - b[i]), dot = (a, b) => a.reduce((s, v, i) => s + v * b[i], 0);
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const unit = a => { const l = Math.hypot(...a); return a.map(v => v / l); };
  const forward = unit(sub(camera.target, camera.position)), right = unit(cross(forward, camera.up)), up = cross(right, forward);
  const d = sub(point, camera.target);
  return [(dot(d, right) / (camera.halfHeight * camera.aspect) + 1) / 2 * width, (1 - dot(d, up) / camera.halfHeight) / 2 * height];
};

test('in 3D the board is its two faces in the 2D colours, a press on a pad’s pixels picks what the 2D press picks, and the corner stays: its column over the pill, whose zoom is the camera’s', async (t) => {
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
  t.after(() => page.close());
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; window.__cadPromptDestination = 'clipboard'; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=blinky.kicad_pcb`);
  const pane = page.getByTestId('one');
  await frame(pane);
  // The corner's boxes, from the top down: Display, 2D/3D and Flip in the column, each one 24px button,
  // then the pill, a 24px row 96px wide, 8px off the pane's right and bottom edges.
  const corner = () => pane.evaluate(element => [...element.querySelectorAll('[data-view-pill-column] > *, [data-zoom-pill]')]
    .map(control => { const { x, y, width, height } = control.getBoundingClientRect(); return { x, y, width, height }; }));
  const flat = await corner();
  const pill = flat.at(-1);
  const stage = await pane.locator('[data-cad-canvas]').first().boundingBox();
  assert.equal(flat.length, 4);
  assert.deepEqual([pill.width, pill.height, stage.x + stage.width - pill.x - pill.width, stage.y + stage.height - pill.y - pill.height],
    [96, 24, 8, 8], 'the pill: 96 x 24, 8px in from the corner');
  for (const [index, box] of flat.entries()) {
    assert.equal(box.x + box.width, pill.x + pill.width, `corner control ${index} flush with the pill's right edge`);
    if (index) assert.equal(box.y - flat[index - 1].y - flat[index - 1].height, 4, `corner control ${index} 4px under the one over it`);
    if (index < 3) assert.deepEqual([box.width, box.height], [24, 24], `corner control ${index} a 24px button`);
  }
  await pane.locator('[data-board-dimension]').click();
  await page.waitForFunction(() => document.querySelector('[data-board-surface] canvas[role=img]')?.classList.contains('invisible'));
  assert.deepEqual(await corner(), flat, 'every corner control stands where it stood');
  // The pill is the 3D camera's zoom: a step in (half again), and it reads the camera's new percentage.
  const settled = () => page.waitForFunction(() => { const camera = window.__cadCamera?.(); return camera && !camera.settling; });
  await settled();
  const before = (await page.evaluate(() => window.__cadCamera())).zoomPercent;
  await pane.locator('[data-zoom-pill]').getByRole('button', { name: 'Zoom in' }).click();
  await page.waitForFunction(before => {
    const { zoomPercent } = window.__cadCamera();
    return Math.abs(zoomPercent / before - 1.5) < 0.01
      && document.querySelector('[data-zoom-pill] [data-zoom-control]').textContent === `${Math.round(zoomPercent).toLocaleString()}%`;
  }, before);
  // Head on from the top, as the 2D view sees it, through the 3D camera.
  await page.evaluate(() => window.cadHarness.a.controller.setCamera({ position: [20, -15, 200], target: [20, -15, 0], up: [0, 1, 0] }));
  await settled();
  const canvas = pane.locator('[data-board-3d] canvas').first();
  const shot = async () => PNG.sync.read(Buffer.from((await canvas.evaluate(element => element.toDataURL('image/png'))).split(',')[1], 'base64'));
  const box = await canvas.boundingBox();
  let camera = await page.evaluate(() => window.__cadCamera());
  const top = await shot();
  const [trackX, trackY] = project3d(camera, [30, -15, 0], box.width, box.height);
  assert.ok(red(pixel(top, trackX, trackY)), `the VBUS track on the front face: ${pixel(top, trackX, trackY)}`);
  // Turned, a press on R1 pad 2's pixels picks it, as the 2D view's press does.
  await page.evaluate(() => window.cadHarness.a.controller.setCamera({ position: [10, -55, 40], target: [35.825, -15, 0], up: [0, 0, 1] }));
  await settled();
  camera = await page.evaluate(() => window.__cadCamera());
  const [padX, padY] = project3d(camera, [35.825, -15, 0], box.width, box.height);
  await page.mouse.click(box.x + padX, box.y + padY);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().selection[0]?.target.selectors[0] === '#R1.2');
  assert.equal(await pane.locator('[data-board-side]').getAttribute('data-board-side'), 'top');
  assert.deepEqual(errors, []);
});

/** Where the highlight lights the canvas (its pixels' centroid and count): a picked pad, as the 2D view draws it. */
const litAt = image => {
  let [x, y, count] = [0, 0, 0];
  for (let row = 0; row < image.height; row += 1) {
    for (let column = 0; column < image.width; column += 1) {
      if (near(pixel(image, column, row), [141, 197, 255], 30)) { x += column; y += row; count += 1; }
    }
  }
  return count ? [x / count, y / count, count] : null;
};

test('2D to 3D and back with the camera left alone: every frame shows the board, and the 2D view comes back as it was, a pad where it stood', async (t) => {
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
  t.after(() => page.close());
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; window.__cadPromptDestination = 'clipboard'; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=blinky.kicad_pcb`);
  const pane = page.getByTestId('one');
  const fitted = await frame(pane);
  // R1 pad 2 picked, so it is lit where it is drawn, in a view zoomed a step and panned off the fit.
  await page.evaluate(() => window.cadHarness.a.controller.select('#R1.2'));
  await pane.locator('[data-zoom-pill]').getByRole('button', { name: 'Zoom in' }).click();
  const canvas = await canvasOf(pane).boundingBox();
  await page.mouse.move(canvas.x + 400, canvas.y + 250);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(canvas.x + 300, canvas.y + 280, { steps: 4 });
  await page.mouse.up({ button: 'right' });
  await page.mouse.move(canvas.x + 2, canvas.y + 2);
  const pad = litAt(await frame(pane, fitted));
  assert.ok(pad, 'R1 pad 2 lit in 2D');
  // Every animation frame, either way: the flat canvas, or the board in 3D with its face drawn; never the
  // 3D view's cover over the board, its bare slab, or neither.
  await page.evaluate(() => {
    window.__missed = [];
    const look = () => {
      if (!window.__missed) return;
      const flat = document.querySelector('[data-board-surface] canvas[role=img]');
      const solid = document.querySelector('[data-board-3d]');
      const seen = Boolean(solid) && getComputedStyle(solid).opacity !== '0';
      const drawn = seen && solid.querySelector('canvas')?.style.visibility !== 'hidden';
      const cover = seen && Boolean(solid.querySelector('[data-viewer-transition]'));
      const bare = drawn && !solid.dataset.boardFaces;
      const flatShown = Boolean(flat) && !flat.classList.contains('invisible');
      if (cover || bare || (!flatShown && !drawn)) window.__missed.push({ cover, bare, flatShown, drawn });
      requestAnimationFrame(look);
    };
    requestAnimationFrame(look);
  });
  await pane.locator('[data-board-dimension]').click();
  // Up in place of the flat canvas, then eased from head on to where 3D opens (Home, the world's z up);
  // nothing moves the camera.
  await page.waitForFunction(() => {
    const camera = window.__cadCamera?.();
    return document.querySelector('[data-board-surface] canvas[role=img]')?.classList.contains('invisible') && camera && !camera.settling && camera.up[2] > 0.9;
  });
  await pane.locator('[data-board-dimension="3d"]').click();
  await pane.locator('[data-board-3d]').waitFor({ state: 'detached' });
  const back = litAt(await frame(pane));
  assert.deepEqual(await page.evaluate(() => { const missed = window.__missed; window.__missed = null; return missed; }), [],
    'a frame showed the board on neither canvas, or the 3D view unready over it');
  assert.ok(back && Math.hypot(back[0] - pad[0], back[1] - pad[1]) <= 1, `R1 pad 2 back where it stood: ${back} vs ${pad}`);
  assert.deepEqual(errors, []);
});

test('a board reopened in 3D leaves for 2D centred on what its camera centred on, nobody having moved it', async (t) => {
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
  t.after(() => page.close());
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; window.__cadPromptDestination = 'clipboard'; });
  // The tab's record in the page's sessionStorage (`?store=session`): a reload of the page is a reload of the tab.
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=blinky.kicad_pcb&store=session`);
  const pane = page.getByTestId('one');
  await frame(pane);
  // In 3D, the camera turned onto R1 pad 2 from the front, right and above, and kept with the file's view.
  await pane.locator('[data-board-dimension]').click();
  const settled = () => page.waitForFunction(() => { const camera = window.__cadCamera?.(); return camera && !camera.settling; });
  await settled();
  await page.evaluate(() => window.cadHarness.a.controller.setCamera({ position: [55, -45, 40], target: [35.825, -15, 0], up: [0, 0, 1] }));
  await page.waitForFunction(() => {
    const board3d = value => (value && typeof value === 'object' ? value.board3d?.value ?? Object.values(value).map(board3d).find(Boolean) : null);
    const kept = board3d(JSON.parse(sessionStorage.getItem('text-to-cad:tab:harness') || 'null'));
    return kept?.mode === '3d' && Math.abs((kept.camera?.target?.[0] ?? 0) - 35.825) < 1e-6;
  });
  // Reopened, it is in 3D on that camera; the pad picked, then 2D with the camera untouched.
  await page.reload();
  await page.waitForFunction(() => { const camera = window.__cadCamera?.(); return camera && !camera.settling && Math.abs(camera.target[0] - 35.825) < 1e-6; });
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await page.evaluate(() => window.cadHarness.a.controller.select('#R1.2'));
  await pane.locator('[data-board-dimension="3d"]').click();
  await pane.locator('[data-board-3d]').waitFor({ state: 'detached' });
  const flat = await frame(pane);
  const pad = litAt(flat);
  assert.ok(pad && Math.hypot(pad[0] - flat.width / 2, pad[1] - flat.height / 2) <= 1, `R1 pad 2 at the centre: ${pad} in ${flat.width} x ${flat.height}`);
  assert.equal(await pane.locator('[data-board-side]').getAttribute('data-board-side'), 'top');
  assert.deepEqual(errors, []);
});

test('in 3D Flip turns the camera over and its icon is the side the camera is on, turned by Flip, ⇧F or a drag; 2D comes back on that side', async (t) => {
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
  t.after(() => page.close());
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; window.__cadPromptDestination = 'clipboard'; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=blinky.kicad_pcb`);
  const pane = page.getByTestId('one');
  await frame(pane);
  const corner = () => pane.evaluate(element => [...element.querySelectorAll('[data-view-pill-column] > *, [data-zoom-pill]')]
    .map(control => { const { x, y, width, height } = control.getBoundingClientRect(); return { x, y, width, height }; }));
  const boxes = await corner();
  await pane.locator('[data-board-dimension]').click();
  await page.waitForFunction(() => document.querySelector('[data-board-surface] canvas[role=img]')?.classList.contains('invisible'));
  // At rest, the side the camera looks at (`boardFrame.js`'s `sideSeenAlong`) and what Flip says: its side, its name, its fill.
  const rest = () => page.waitForFunction(() => { const camera = window.__cadCamera?.(); return camera && !camera.settling; })
    .then(() => page.evaluate(() => {
      const { position, target } = window.__cadCamera();
      const button = document.querySelector('[data-board-side]');
      return { camera: target[2] - position[2] > 0 ? 'bottom' : 'top',
        flip: [button.dataset.boardSide, button.getAttribute('aria-label'), button.dataset.variant] };
    }));
  // Like Projection, Flip's icon says its side, and neither side is drawn in a pressed fill.
  const top = { camera: 'top', flip: ['top', 'Side: Top', 'ghost'] }, bottom = { camera: 'bottom', flip: ['bottom', 'Side: Bottom', 'ghost'] };
  assert.deepEqual(await rest(), top, 'Home, over the board');
  // Flip: the camera turned over the board, and the button follows it under; not one corner box moves.
  await pane.locator('[data-board-side]').click();
  await page.waitForFunction(() => window.__cadCamera?.().position[2] < 0);
  assert.deepEqual(await rest(), bottom, 'Flip turned the camera under the board');
  assert.deepEqual(await corner(), boxes, 'every corner control stands where it stood');
  // By hand: a drag down turns the camera up, back over the board's plane, and the button follows.
  const box = await pane.locator('[data-board-3d] canvas').first().boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 100, { steps: 8 });
  await page.mouse.up();
  assert.deepEqual(await rest(), top, 'a drag turned the camera back over the board');
  // ⇧F, Flip's key: under again.
  await page.keyboard.press('Shift+F');
  await page.waitForFunction(() => window.__cadCamera?.().position[2] < 0);
  assert.deepEqual(await rest(), bottom, '⇧F turned the camera under the board');
  // A Flip is a move of the camera: leaving 3D frames the 2D view from the side the camera was on, the bottom.
  await pane.locator('[data-board-dimension]').click();
  await pane.locator('[data-board-3d]').waitFor({ state: 'detached' });
  assert.deepEqual(await page.evaluate(() => [window.cadHarness.a.controller.readState().boardDisplay.side,
    document.querySelector('[data-board-side]').getAttribute('aria-label'), document.querySelector('[data-board-dimension]').getAttribute('aria-label')]),
  ['bottom', 'Side: Bottom', 'View: 2D']);
  assert.deepEqual(errors, []);
});

test('in 3D a part stands its model, a press on its body picks the part rather than the pad under it, and with 3D models hidden the pad', async (t) => {
  // R1's model is the bracket, a tenth its size: a 4 x 2 mm plate over both its pads, 0.4 mm thick, standing on the front face.
  const name = '${KIPRJMOD}/bracket.step';
  const plot = structuredClone(BOARD);
  plot.board.parts.find(part => part.ref === 'R1').models = [{ name, offset: [0, 0, 0.2], scale: [0.1, 0.1, 0.1] }];
  served = { plot, models: { [name]: { file: 'bracket.step', document: BRACKET_ID, api: '/api/v1/documents/step/bracket', stamp: '1-1' } } };
  t.after(() => { served = { plot: BOARD, models: null }; });
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
  t.after(() => page.close());
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; window.__cadPromptDestination = 'clipboard'; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=blinky.kicad_pcb`);
  const pane = page.getByTestId('one');
  await frame(pane);
  await pane.locator('[data-board-dimension]').click();
  // The model read, baked once and placed: one body, one model; D1, whose model the table does not find, a block.
  await pane.locator('[data-board-3d][data-board-bodies="1"][data-board-models="1"][data-board-blocks="1"]').waitFor();
  const settled = () => page.waitForFunction(() => { const camera = window.__cadCamera?.(); return camera && !camera.settling; });
  await page.evaluate(() => window.cadHarness.a.controller.setCamera({ position: [10, -55, 40], target: [35.825, -15, 0], up: [0, 0, 1] }));
  await settled();
  const box = await pane.locator('[data-board-3d] canvas').first().boundingBox();
  const camera = await page.evaluate(() => window.__cadCamera());
  // R1 pad 2's place on the plate's top, where the ray meets the body first.
  const [x, y] = project3d(camera, [35.825, -15, 0.4], box.width, box.height);
  const picked = () => page.evaluate(() => window.cadHarness.a.controller?.readState().selection.map(reference => reference.target.selectors[0]));
  await page.mouse.click(box.x + x, box.y + y);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().selection[0]?.target.selectors[0] === '#R1');
  // The Layers' 3D models eye hides the bodies, and the same press takes the pad under where the body stood.
  await pane.locator('[data-layer-row="models-3d"] button[aria-label="Hide 3D models"]').dispatchEvent('click');
  await pane.locator('[data-layer-row="models-3d"] button[aria-label="Show 3D models"]').waitFor({ state: 'attached' });
  await page.mouse.click(box.x + x, box.y + y);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().selection[0]?.target.selectors[0] === '#R1.2');
  assert.deepEqual(await picked(), ['#R1.2']);
  assert.deepEqual(errors, []);
});

test('3D entered from the 2D bottom eases to Home’s tilt under the board, Flip the bottom all the way, and a revision read while the camera looks at the back draws the back face', async (t) => {
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
  t.after(async () => { await page.close(); served = { plot: BOARD, models: null }; });
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; window.__cadPromptDestination = 'clipboard'; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=blinky.kicad_pcb`);
  const pane = page.getByTestId('one');
  await frame(pane);
  // Seen from the bottom in 2D, then in 3D, Flip's side read on every frame: head on from below, then eased to
  // Home's tilt from below (the world's z up), the camera never over the board's plane.
  await pane.locator('[data-board-side]').click();
  await pane.locator('[data-board-side="bottom"]').waitFor();
  await page.evaluate(() => {
    window.__sides = new Set();
    const look = () => { if (!window.__sides) return; window.__sides.add(document.querySelector('[data-board-side]')?.dataset.boardSide); requestAnimationFrame(look); };
    requestAnimationFrame(look);
  });
  await pane.locator('[data-board-dimension]').click();
  await page.waitForFunction(() => {
    const camera = window.__cadCamera?.();
    return document.querySelector('[data-board-surface] canvas[role=img]')?.classList.contains('invisible') && camera && !camera.settling && camera.up[2] > 0.9;
  });
  const camera = () => page.evaluate(() => window.__cadCamera());
  const eased = await camera();
  assert.ok(eased.position[2] < -1.6 && eased.target[2] > eased.position[2], `the eye under the board, looking up at it: ${eased.position} to ${eased.target}`);
  assert.deepEqual(await page.evaluate(() => { const sides = [...window.__sides]; window.__sides = null; return sides; }), ['bottom'], 'Flip said the bottom on every frame');
  await pane.locator('[data-board-3d][data-board-faces~="bottom"]').waitFor();
  const before = await camera();
  // The file saved again, a little thinner: a new plot, so a new stage, under the camera where it was.
  const plot = structuredClone(BOARD);
  plot.board.thickness = 1.2;
  served = { plot, models: null, revision: 'r2' };
  await page.evaluate(() => window.cadHarness.a.client.refresh());
  await page.waitForFunction(() => window.__cadCamera?.()?.originalBounds?.min?.[2] === -1.2);
  const after = await camera();
  assert.ok(after.position.every((value, axis) => Math.abs(value - before.position[axis]) < 1e-6), 'the camera did not move');
  await pane.locator('[data-board-3d][data-board-faces~="bottom"]').waitFor();
  assert.deepEqual(errors, []);
});
