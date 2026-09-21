import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';

// Inline fixtures, served from memory. The models corpus is entirely cut layouts in
// millimetres with no text and no coloured layer, so a document, a unit override, a
// coloured layer and an unclosed contour exist nowhere but here.
const dxf = body => Buffer.from(`${['0', 'SECTION', '2', 'ENTITIES', ...body, '0', 'ENDSEC', '0', 'EOF'].join('\n')}\n`);
const header = pairs => ['0', 'SECTION', '2', 'HEADER', ...pairs, '0', 'ENDSEC'];
const rect = (layer, [x, y], [w, h]) => [
  '0', 'LWPOLYLINE', '8', layer, '90', '4', '70', '1',
  '10', `${x}`, '20', `${y}`, '10', `${x + w}`, '20', `${y}`,
  '10', `${x + w}`, '20', `${y + h}`, '10', `${x}`, '20', `${y + h}`,
];
const line = (layer, [x1, y1], [x2, y2]) => ['0', 'LINE', '8', layer, '10', `${x1}`, '20', `${y1}`, '11', `${x2}`, '21', `${y2}`];
// A layer table entry, so a layer can declare a colour of its own (ACI 1 is red).
const layerTable = rows => ['0', 'SECTION', '2', 'TABLES', '0', 'TABLE', '2', 'LAYER',
  ...rows.flatMap(([name, aci]) => ['0', 'LAYER', '2', name, '62', `${aci}`]), '0', 'ENDTAB', '0', 'ENDSEC'];

const FILES = {
  // One closed rectangle with a hole: one layer, so neither Bends nor Layers has anything to show.
  'plate.dxf': dxf([...rect('CUT', [0, 0], [40, 20]), '0', 'CIRCLE', '8', 'CUT', '10', '20', '20', '10', '40', '3']),
  // Four creases, a score line, a label, and a layer that names its own colour.
  'panel.dxf': Buffer.concat([
    Buffer.from(`${layerTable([['NOTES', 1]]).join('\n')}\n`),
    dxf([
      ...rect('CUT', [0, 0], [100, 20]),
      ...line('BEND', [20, 0], [20, 20]), ...line('BEND', [40, 0], [40, 20]),
      ...line('BEND', [60, 0], [60, 20]), ...line('BEND', [80, 0], [80, 20]),
      ...line('ENGRAVE', [4, 10], [16, 10]),
      '0', 'TEXT', '8', 'NOTES', '10', '4', '20', '4', '40', '4', '1', 'PART A',
    ]),
  ]),
  // A dimensioned drawing: line-work and a DIMENSION, so there is no flat pattern at all.
  'sheet.dxf': dxf([
    ...line('OUTLINE', [0, 0], [50, 0]), ...line('OUTLINE', [50, 0], [50, 30]),
    ...line('OUTLINE', [50, 30], [0, 30]), ...line('OUTLINE', [0, 30], [0, 0]),
    ...line('DIMS', [0, -6], [50, -6]),
    '0', 'DIMENSION', '8', 'DIMS', '10', '0', '20', '-6', '11', '25', '21', '-9',
  ]),
  // The same 40x20 rectangle, declared in INCHES ($INSUNITS 1).
  'inches.dxf': Buffer.concat([
    Buffer.from(`${header(['9', '$INSUNITS', '70', '1']).join('\n')}\n`),
    dxf([...rect('CUT', [0, 0], [40, 20])]),
  ]),
  'broken.dxf': Buffer.from('this is prose, and not a drawing\n'),
  // A cut layer that never closes: a layout by profile with nothing to extrude.
  'open.dxf': dxf([...line('CUT', [0, 0], [30, 0]), ...line('CUT', [30, 0], [30, 15])]),
};

async function serveHarness(t) {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-dxf-browser-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    const name = url.pathname.split('/').pop();
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: Object.entries(FILES).map(([file, data]) => (
        { kind: 'dxf', file, rootRelativeFile: file, url: `/${file}`, hash: `${root}-${file}`, bytes: data.length })) }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else if (FILES[name]) { response.setHeader('Content-Type', 'application/octet-stream'); response.end(FILES[name]); }
    else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: process.platform === 'darwin'
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const open = async (file) => {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
    page.setDefaultTimeout(20000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => { window.Worker = undefined; });
    await page.goto(`http://127.0.0.1:${server.address().port}/?file=${file}`);
    return { page, errors, pane: page.getByTestId('one') };
  };
  return { open };
}

const ready = pane => pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
const loaded = page => page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
const toolNames = pane => pane.getByRole('group', { name: 'Interaction tools' }).getByRole('button')
  .evaluateAll(buttons => buttons.map(button => [button.getAttribute('aria-label'), button.getAttribute('aria-pressed')]));
const tabNames = pane => pane.getByRole('tab').evaluateAll(tabs => tabs.map(tab => [tab.textContent, tab.getAttribute('aria-selected')]));
const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
const state = page => page.evaluate(() => window.cadHarness.a.controller.readState());
const display = (page, patch) => page.evaluate(next => window.cadHarness.a.controller.setDisplaySettings(next), patch);
const GUIDES_OFF = { grid: { enabled: false }, axes: { enabled: false }, floor: { enabled: false } };

/**
 * The FRAME ON SCREEN: the last thing the viewport actually drew.
 *
 * Not `capture()` — a capture renders before it reads pixels, so it shows the scene as it
 * IS rather than as it was drawn, and a setting that re-poses the scene without asking for a
 * frame passes every capture-based assertion while the viewport sits on a stale picture.
 * (That is exactly what shipped once: bends folded the geometry and nothing repainted.)
 * Anything asserting "this setting reached the screen" must read the frame, not a capture.
 */
async function frame(pane) {
  await settle(pane.page());
  return PNG.sync.read(await pane.locator('[aria-busy] > div > canvas').first().screenshot());
}

async function capture(page) {
  const encoded = await page.evaluate(async () => {
    const blob = await window.cadHarness.a.controller.capture();
    const data = new Uint8Array(await blob.arrayBuffer());
    let binary = ''; for (const byte of data) binary += String.fromCharCode(byte);
    return { type: blob.type, base64: btoa(binary) };
  });
  assert.equal(encoded.type, 'image/png');
  return PNG.sync.read(Buffer.from(encoded.base64, 'base64'));
}
/** How much of the picture is not the backdrop: the model's share of it. */
function coverage(image) {
  const backdrop = [image.data[0], image.data[1], image.data[2]];
  let painted = 0;
  for (let offset = 0; offset < image.data.length; offset += 4) {
    if (Math.abs(image.data[offset] - backdrop[0]) + Math.abs(image.data[offset + 1] - backdrop[1])
      + Math.abs(image.data[offset + 2] - backdrop[2]) > 12) painted += 1;
  }
  return painted / (image.width * image.height);
}
/** The mean colour of the pixels that are not the backdrop. */
function meanColor(image) {
  const backdrop = [image.data[0], image.data[1], image.data[2]];
  const total = [0, 0, 0];
  let painted = 0;
  for (let offset = 0; offset < image.data.length; offset += 4) {
    if (Math.abs(image.data[offset] - backdrop[0]) + Math.abs(image.data[offset + 1] - backdrop[1])
      + Math.abs(image.data[offset + 2] - backdrop[2]) <= 12) continue;
    painted += 1;
    for (let channel = 0; channel < 3; channel += 1) total[channel] += image.data[offset + channel];
  }
  return painted ? total.map(sum => Math.round(sum / painted)) : [0, 0, 0];
}
const differingPixels = (left, right) => {
  assert.deepEqual([left.width, left.height], [right.width, right.height]);
  let count = 0;
  for (let offset = 0; offset < left.data.length; offset += 4) {
    if (left.data[offset] !== right.data[offset] || left.data[offset + 1] !== right.data[offset + 1]
      || left.data[offset + 2] !== right.data[offset + 2]) count += 1;
  }
  return count;
};
/** The unit direction the camera looks along, for asserting "straight down". */
const viewDirection = (camera) => {
  const offset = camera.position.map((value, axis) => value - camera.target[axis]);
  const length = Math.hypot(...offset);
  return offset.map(value => value / length);
};
const commit = async (pane, label, value) => {
  const input = pane.getByLabel(label, { exact: true });
  await input.click();
  await input.fill(String(value));
  await input.press('Enter');
};
const tab = (pane, name) => pane.getByRole('tab', { name, exact: true }).click();
// The harness opens every file with `panel: ''` — nothing open — so a test that wants the
// Inspector asks for it. That it OPENS by default for a DXF is the registration's business
// (`registrations.test.ts`), not this harness's.
const openInspector = async (pane) => {
  // One panel is open at a time and the harness keeps that choice across a remount, so this
  // asks for the Inspector rather than toggling it.
  if (!await pane.locator('[data-file-sheet="DXF"]').count()) await pane.getByRole('button', { name: 'Inspector', exact: true }).click();
  await pane.locator('[data-file-sheet="DXF"]').waitFor();
};
// An eased camera transition coasts. A comparison of two cameras waits for both to be still.
const rest = page => page.waitForFunction(() => {
  const camera = JSON.stringify(window.cadHarness.a.controller.readState().camera);
  const still = window.__restCamera === camera;
  window.__restCamera = camera;
  return still;
}, null, { polling: 200 });

test('a cut layout opens in Orbit with its own settings tabs, and 2D is a locked plan view', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('plate.dxf');
  await ready(pane);
  await loaded(page);

  // Orbit and Draw, and nothing that would promise a selection.
  assert.deepEqual(await toolNames(pane), [['Orbit', 'true'], ['Draw', 'false']]);
  for (const name of ['Select', 'Measure', 'Pose', 'Animate']) {
    assert.equal(await pane.getByRole('button', { name, exact: true }).count(), 0, name);
  }
  // A drawing's settings live in the Inspector: Material first.
  await openInspector(pane);
  assert.deepEqual(await tabNames(pane), [['Material', 'true'], ['Display', 'false']],
    'one layer and no bend lines: neither Bends nor Layers has anything to show');
  for (const section of ['Edges', 'Clip', 'Explode']) {
    assert.equal(await pane.getByRole('heading', { name: section, exact: true }).count(), 0, section);
  }

  // 3D is the default, and the view cube is offered.
  const solid = await state(page);
  assert.equal(solid.camera.projection, 'orthographic');
  assert.ok(Math.abs(viewDirection(solid.camera)[2]) < 0.9, 'a three-quarter view');
  assert.equal(await pane.getByLabel('Jump to top view', { exact: true }).count(), 1);

  // 2D: the navbar action, the label flipping, and the lock.
  await display(page, { camera: { projection: 'perspective' } });
  await pane.getByRole('button', { name: 'Switch to 2D view', exact: true }).click();
  await pane.getByRole('button', { name: 'Switch to 3D view', exact: true }).waitFor();
  await page.waitForFunction(() => {
    const camera = window.cadHarness.a.controller.readState().camera;
    const offset = camera.position.map((value, axis) => value - camera.target[axis]);
    return offset[2] / Math.hypot(...offset) > 0.99;
  });
  await rest(page);
  const plan = await state(page);
  assert.equal(plan.camera.projection, 'orthographic', 'a plan is a measurable projection, whatever Display asks for');
  assert.equal(plan.display.camera.projection, 'perspective', 'and Display keeps what it was set to');
  assert.equal(await pane.getByLabel('Jump to top view', { exact: true }).count(), 0, 'a locked view stops advertising axes it cannot turn to');

  // Left-drag pans a locked view instead of turning it; the keyboard cannot turn it either.
  const canvas = await pane.locator('[aria-busy] > div > canvas').first().boundingBox();
  await page.mouse.move(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2);
  await page.mouse.down();
  await page.mouse.move(canvas.x + canvas.width / 2 + 160, canvas.y + canvas.height / 2 + 60, { steps: 6 });
  await page.mouse.up();
  await page.waitForFunction(target => JSON.stringify(window.cadHarness.a.controller.readState().camera.target) !== target,
    JSON.stringify(plan.camera.target));
  await rest(page);
  const panned = await state(page);
  assert.deepEqual(viewDirection(panned.camera).map(value => Math.round(value * 100)), viewDirection(plan.camera).map(value => Math.round(value * 100)),
    'dragging slides the sheet; it never turns it');

  await page.locator('canvas').first().click({ position: { x: 40, y: 40 } });
  for (const key of ['ArrowLeft', 'ArrowUp', 'ArrowRight', 'ArrowDown']) await page.keyboard.press(key);
  await settle(page);
  assert.deepEqual(viewDirection((await state(page)).camera).map(value => Math.round(value * 100)),
    viewDirection(panned.camera).map(value => Math.round(value * 100)), 'and neither do the arrow keys');

  // A host that asks for a tilted camera is told why it cannot have one, not quietly straightened.
  const declined = await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    const camera = controller.readState().camera;
    return controller.setCamera({ ...camera, position: [90, -70, 60], target: [10, 5, 5] }).then(() => '', error => error.message);
  });
  assert.match(declined, /locked looking straight down/);
  assert.equal(Math.round(viewDirection((await state(page)).camera)[2] * 100), 100);
  // One it CAN have is applied.
  await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    const { projection, ...camera } = controller.readState().camera;
    await controller.setCamera({ ...camera, position: [5, 5, 120], target: [5, 5, 0] });
  });
  assert.deepEqual((await state(page)).camera.target.map(Math.round), [5, 5, 0]);

  // Reset camera in 2D lands back on top-down, not on the default three-quarter view.
  await page.evaluate(() => window.cadHarness.a.controller.resetCamera());
  await page.waitForFunction(() => {
    const camera = window.cadHarness.a.controller.readState().camera;
    const offset = camera.position.map((value, axis) => value - camera.target[axis]);
    // Framed on the plate's centre again, and still looking straight down at it.
    return offset[2] / Math.hypot(...offset) > 0.99 && Math.abs(camera.target[0] - 20) < 1;
  });

  // And back to 3D: the three-quarter view and the cube return.
  await pane.getByRole('button', { name: 'Switch to 3D view', exact: true }).click();
  await page.waitForFunction(() => {
    const camera = window.cadHarness.a.controller.readState().camera;
    const offset = camera.position.map((value, axis) => value - camera.target[axis]);
    return Math.abs(offset[2] / Math.hypot(...offset)) < 0.9;
  });
  await pane.getByLabel('Jump to top view', { exact: true }).waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().camera.projection === 'perspective',
    null, { message: 'Display gets its projection back' });
  assert.deepEqual(errors, []);
});

test('thickness, bends, layers and the stock material each reshape what is drawn', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('panel.dxf');
  await ready(pane);
  await loaded(page);
  await openInspector(pane);
  assert.deepEqual(await tabNames(pane), [['Material', 'true'], ['Bends', 'false'], ['Layers', 'false'], ['Display', 'false']]);
  await display(page, GUIDES_OFF);
  await settle(page);

  // Thickness: the flat sheet is nearly edge-on from the default view, so giving it 6 mm of
  // stock puts visibly more of it on screen — ON SCREEN, without anything else prompting a frame.
  const flat = await frame(pane);
  await commit(pane, 'Thickness value', 6);
  const thick = await frame(pane);
  assert.ok(coverage(thick) > coverage(flat) * 1.15, `6 mm of stock is more picture: ${coverage(flat)} -> ${coverage(thick)}`);
  assert.ok(differingPixels(flat, thick) > 20000, 'and the viewport drew it');

  // Bends. One crease first, so "up" and "down" are unmistakably different pictures.
  await commit(pane, 'Thickness value', 2);
  const unfolded = await frame(pane);
  await tab(pane, 'Bends');
  await commit(pane, 'Bend 1 angle value', 90);
  const foldedUp = await frame(pane);
  // A fold stands a whole strip of the sheet up. "Not blank" would pass on a sheet that never
  // moved, so this asks for a large CHANGE against the flat frame.
  assert.ok(differingPixels(unfolded, foldedUp) > 20000,
    `a 90° fold visibly reshapes the sheet: ${differingPixels(unfolded, foldedUp)} pixels`);
  assert.ok(coverage(foldedUp) > 0.01, `and it is not blank: ${coverage(foldedUp)}`);
  await pane.locator('[aria-label="Bend 1 direction"]').getByLabel('Down', { exact: true }).click();
  assert.ok(differingPixels(foldedUp, await frame(pane)) > 20000, 'folding down is not folding up');

  // Four creases is the count that used to blank the sheet outright, because the re-meshed
  // geometry kept the first build's normal buffer and the draw was rejected silently.
  await pane.locator('[aria-label="Bend 1 direction"]').getByLabel('Up', { exact: true }).click();
  for (const index of [2, 3, 4]) await commit(pane, `Bend ${index} angle value`, 90);
  const fourBends = await frame(pane);
  assert.ok(coverage(fourBends) > 0.01, 'a four-bend fold still draws');
  assert.ok(differingPixels(unfolded, fourBends) > 20000, 'and all four creases reached the screen');
  // And the schematic fold draws, differently from the curved one.
  await pane.getByRole('combobox', { name: 'Corners', exact: true }).click();
  await page.getByRole('option', { name: 'Boxed', exact: true }).click();
  const boxed = await frame(pane);
  assert.ok(coverage(boxed) > 0.01, 'and so does a boxed one');
  assert.ok(differingPixels(unfolded, boxed) > 20000, 'which is also a fold');

  // Layers: the dashed creases belong to BEND, the score line and the label to their layers.
  await tab(pane, 'Layers');
  await pane.getByRole('button', { name: 'Reset bend angles', exact: true }).count();
  await tab(pane, 'Bends');
  await pane.getByRole('button', { name: 'Reset bend angles', exact: true }).click();
  await settle(page);
  await tab(pane, 'Layers');
  const withGuides = await frame(pane);
  await pane.getByRole('button', { name: 'Hide layer BEND', exact: true }).click({ force: true });
  const withoutGuides = await frame(pane);
  assert.ok(differingPixels(withGuides, withoutGuides) > 200, 'the crease marks ARE that layer');
  await pane.getByRole('button', { name: 'Show layer BEND', exact: true }).click({ force: true });
  assert.ok(differingPixels(withGuides, await frame(pane)) < 200, 'and showing it brings them back');
  await pane.getByRole('button', { name: 'Hide layer ENGRAVE', exact: true }).click({ force: true });
  assert.ok(differingPixels(withGuides, await frame(pane)) > 100, 'the score line goes with ENGRAVE');
  await pane.getByRole('button', { name: 'Show layer ENGRAVE', exact: true }).click({ force: true });
  await settle(page);

  // Material: a preset is a tint, and it beats every colour mode.
  await tab(pane, 'Material');
  const neutral = meanColor(await frame(pane));
  await pane.getByRole('button', { name: 'Material', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Metals', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Brass', exact: true }).click();
  const brass = meanColor(await frame(pane));
  assert.ok(brass[0] - brass[2] > neutral[0] - neutral[2] + 20, `brass is warmer than the viewer's surface: ${neutral} -> ${brass}`);
  await display(page, { surfaces: { colorMode: 'single', color: '#0040ff' } });
  const stillBrass = meanColor(await frame(pane));
  assert.ok(stillBrass[0] > stillBrass[2], `a chosen stock beats Single colour: ${stillBrass}`);
  assert.deepEqual(errors, []);
});

test('a dimensioned drawing draws its line-work, opens locked, and has every tool that works on a scene', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('sheet.dxf');
  await ready(pane);
  await loaded(page);

  // It IS a plan: no third dimension to look at, so there is no 2D/3D action to offer.
  assert.equal(await pane.getByRole('button', { name: /Switch to (2D|3D) view/ }).count(), 0);
  const camera = (await state(page)).camera;
  assert.equal(Math.round(viewDirection(camera)[2] * 100), 100, 'opened looking straight down');
  assert.equal(camera.projection, 'orthographic');

  // Tools, the snapshot and a capture all work on it: they are about a scene, not about a mesh.
  assert.deepEqual(await toolNames(pane), [['Orbit', 'true'], ['Draw', 'false']]);
  assert.equal(await pane.getByRole('group', { name: 'Interaction tools' }).getByRole('button', { name: 'Orbit' }).isDisabled(), false);
  await display(page, GUIDES_OFF);
  await settle(page);
  const drawn = await capture(page);
  assert.ok(coverage(drawn) > 0.0005, `the drawing is on screen: ${coverage(drawn)}`);
  await pane.getByRole('button', { name: 'Take snapshot', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  assert.deepEqual(await page.evaluate(() => [window.cadHarness.captures[0].file, window.cadHarness.captures[0].type]), ['sheet.dxf', 'image/png']);

  // Draw works over it, and never moves the camera.
  await pane.getByRole('button', { name: 'Draw', exact: true }).click();
  await pane.locator('[data-drawing-ready]').waitFor();
  const locked = (await state(page)).camera;
  const overlay = await pane.locator('[data-cad-drawing-overlay]').boundingBox();
  await page.mouse.move(overlay.x + 140, overlay.y + 140);
  await page.mouse.down();
  await page.mouse.move(overlay.x + 280, overlay.y + 180, { steps: 8 });
  await page.mouse.up();
  assert.deepEqual((await state(page)).camera, locked, 'drawing never moves the camera');
  await pane.getByRole('button', { name: 'Add to Prompt', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.captures.length === 2);
  await pane.getByRole('button', { name: 'Draw', exact: true }).click();
  await pane.locator('[data-drawing-ready]').waitFor({ state: 'detached' });
  // Leaving Draw leaves the plan lock exactly as it was.
  await settle(page);
  assert.equal(Math.round(viewDirection((await state(page)).camera)[2] * 100), 100);

  // Layers: a document's are its line objects.
  await openInspector(pane);
  assert.deepEqual(await tabNames(pane), [['Material', 'true'], ['Layers', 'false'], ['Display', 'false']]);
  await tab(pane, 'Layers');
  await pane.getByRole('button', { name: 'Hide layer OUTLINE', exact: true }).click({ force: true });
  await settle(page);
  assert.ok(coverage(await capture(page)) < coverage(drawn), 'hiding a layer takes its lines away');
  assert.deepEqual(errors, []);
});

test('a source unit other than millimetres scales the drawing; the Units select only relabels it', async (t) => {
  const { open } = await serveHarness(t);
  const millimetres = await open('plate.dxf');
  await ready(millimetres.pane);
  await loaded(millimetres.page);
  const inches = await open('inches.dxf');
  await ready(inches.pane);
  await loaded(inches.page);
  // The same 40 x 20 rectangle, declared in inches: the scene is millimetres, so it is 25.4x bigger.
  const framed = page => page.evaluate(() => {
    const bounds = window.__cadCamera().originalBounds;
    return bounds.max[0] - bounds.min[0];
  });
  assert.ok(Math.abs((await framed(inches.page)) / (await framed(millimetres.page)) - 25.4) < 0.1,
    `${await framed(inches.page)} / ${await framed(millimetres.page)}`);

  // The Units select converts what the inputs show and accept, and nothing else.
  await openInspector(inches.pane);
  await commit(inches.pane, 'Thickness value', 6);
  await settle(inches.page);
  const box = await inches.page.evaluate(() => window.__cadCamera().originalBounds);
  await inches.pane.getByRole('combobox', { name: 'Units', exact: true }).click();
  await inches.page.getByRole('option', { name: 'Inches', exact: true }).click();
  await settle(inches.page);
  assert.match(await inches.pane.getByLabel('Thickness value', { exact: true }).inputValue(), /^0\.24/);
  // The part itself is untouched: the same box, still 6 mm of stock. (A pixel comparison here
  // would be a claim about the renderer's idle resolution, not about units.)
  assert.deepEqual(await inches.page.evaluate(() => window.__cadCamera().originalBounds), box, 'the part is unchanged');
  assert.equal(await inches.pane.getByRole('combobox', { name: 'Units', exact: true }).innerText(), 'Inches');
  assert.deepEqual(inches.errors, []);
});

test('a DXF that will not parse says so; one with no closed contour shows its lines and warns', async (t) => {
  const { open } = await serveHarness(t);
  const broken = await open('broken.dxf');
  const alert = broken.pane.getByRole('alert');
  await alert.waitFor();
  assert.match(await alert.innerText(), /Couldn’t load the model/);
  assert.match(await alert.innerText(), /broken\.dxf/);
  // The point of the fix: the parser's own sentence, instead of a loading overlay forever.
  assert.match(await alert.innerText(), /malformed/i);
  assert.equal(await broken.pane.locator('[data-viewer-loading]').count(), 0);

  const unclosed = await open('open.dxf');
  await ready(unclosed.pane);
  await loaded(unclosed.page);
  // A non-blocking warning rides the file badge; pressing it opens the diagnostic.
  await unclosed.pane.locator('[data-file-status="Model warning"]').click();
  await unclosed.page.getByText('No closed cut contour').first().waitFor();
  await unclosed.page.keyboard.press('Escape');
  await display(unclosed.page, GUIDES_OFF);
  await settle(unclosed.page);
  assert.ok(coverage(await capture(unclosed.page)) > 0.0005, 'its line-work is drawn rather than nothing');
  assert.deepEqual(unclosed.errors, []);
});

test('thickness, bends, hidden layers, the 2D view and the camera all come back on reopening', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('panel.dxf');
  await ready(pane);
  await loaded(page);
  await openInspector(pane);

  await commit(pane, 'Thickness value', 4);
  await tab(pane, 'Bends');
  await commit(pane, 'Bend 1 angle value', 75);
  await tab(pane, 'Layers');
  await pane.getByRole('button', { name: 'Hide layer ENGRAVE', exact: true }).click({ force: true });
  await pane.getByRole('button', { name: 'Switch to 2D view', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.state.renderers?.[JSON.stringify(['panel.dxf', 'dxf'])]?.renderer?.view === '2d');
  const stored = await page.evaluate(() => window.cadHarness.state.renderers);
  assert.deepEqual(Object.keys(stored), [JSON.stringify(['panel.dxf', 'dxf'])], 'keyed by [path, renderer id]');
  const record = stored[JSON.stringify(['panel.dxf', 'dxf'])].renderer;
  assert.deepEqual([record.thicknessMm, record.bends[0], record.hiddenLayers, record.view],
    [4, { angleDeg: 75, direction: 'up' }, ['ENGRAVE'], '2d']);
  const left = await state(page);
  await page.waitForFunction(position => JSON.stringify(window.cadHarness.state.renderers[JSON.stringify(['panel.dxf', 'dxf'])].camera?.position.map(Math.round)) === position,
    JSON.stringify(left.camera.position.map(Math.round)));

  await page.evaluate(() => window.cadHarness.mounted(false));
  await pane.locator('canvas').first().waitFor({ state: 'detached' });
  await page.evaluate(() => window.cadHarness.mounted(true));
  await ready(pane);
  await loaded(page);
  await openInspector(pane);
  const reopened = await state(page);
  // The Inspector comes back on the tab it was left on, so ask for the one being read.
  await tab(pane, 'Material');
  assert.deepEqual(reopened.camera.position.map(value => Math.round(value * 100)), left.camera.position.map(value => Math.round(value * 100)));
  assert.equal(Math.round(viewDirection(reopened.camera)[2] * 100), 100, 'reopened into the locked plan view');
  await pane.getByRole('button', { name: 'Switch to 3D view', exact: true }).waitFor();
  assert.equal(await pane.getByLabel('Thickness value', { exact: true }).inputValue(), '4.0 mm');
  await tab(pane, 'Bends');
  assert.equal(await pane.getByLabel('Bend 1 angle value', { exact: true }).inputValue(), '75°');
  await tab(pane, 'Layers');
  await pane.getByRole('button', { name: 'Show layer ENGRAVE', exact: true }).waitFor();
  assert.deepEqual(errors, []);
});

test('a host command that needs a selection is declined in words, and fullscreen keeps the plan view', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('plate.dxf');
  await ready(pane);
  await loaded(page);

  const declined = await page.evaluate(() => window.cadHarness.a.controller.select({ selectors: ['o1.f1'] }).then(() => '', error => error.message));
  assert.match(declined, /A DXF has nothing to select/);
  assert.match(await page.evaluate(() => window.cadHarness.a.controller.clearSelection().then(() => '', error => error.message)), /no selection to clear/);
  await page.evaluate(() => window.cadHarness.selectReference('o1.f1'));
  await pane.getByText(/A DXF has nothing to select/).waitFor();
  assert.equal(await page.evaluate(() => window.cadHarness.a.commands.getSnapshot().selectReference ?? null), null, 'the declined request is acknowledged');

  await pane.getByRole('button', { name: 'Switch to 2D view', exact: true }).click();
  await page.waitForFunction(() => {
    const camera = window.cadHarness.a.controller.readState().camera;
    const offset = camera.position.map((value, axis) => value - camera.target[axis]);
    return offset[2] / Math.hypot(...offset) > 0.99;
  });
  await page.evaluate(() => window.cadHarness.fullscreen(true));
  await pane.getByRole('group', { name: 'Interaction tools' }).waitFor({ state: 'detached' });
  await pane.getByRole('group', { name: 'Fullscreen controls' }).waitFor();
  assert.equal(await pane.locator('[data-animation-transport]').count(), 0, 'a drawing has no routines to play');
  await page.evaluate(() => window.cadHarness.fullscreen(false));
  await pane.getByRole('group', { name: 'Interaction tools' }).waitFor();
  await settle(page);
  // Fullscreen's slow auto-orbit still turns a locked view a little — a hole in the lock
  // this phase carries rather than widens; what matters is that leaving it is a plan view again.
  assert.ok(viewDirection((await state(page)).camera)[2] > 0.95, 'leaving fullscreen is still the plan view');
  assert.deepEqual(errors, []);
});
