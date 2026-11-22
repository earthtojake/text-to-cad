import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { createServer } from 'node:http';
import { harnessBundle } from '../harness/bundle.mjs';
import { pressInPreview } from '../harness/preview.mjs';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';

// Fixtures, served from memory: cadgen's exports of two boxes with authored colours (core's
// `lib/render/fixtures`), static and with the clip that slides one of them from its rest pose,
// a GLB with no node, made here, and bytes that are not a GLB at all.
const CORE_FIXTURES = join(dirname(createRequire(import.meta.url).resolve('@cad/core/lib/render/glbMeshData.js')), 'fixtures');
// A GLB of its JSON chunk alone (12 bytes of header, then the chunk, padded to four bytes with spaces).
function glbOf(json) {
  const text = Buffer.from(JSON.stringify(json));
  const chunk = Buffer.concat([text, Buffer.alloc((4 - text.length % 4) % 4, 0x20)]);
  const head = Buffer.alloc(20);
  head.writeUInt32LE(0x46546c67, 0); head.writeUInt32LE(2, 4); head.writeUInt32LE(20 + chunk.length, 8);
  head.writeUInt32LE(chunk.length, 12); head.writeUInt32LE(0x4e4f534a, 16);
  return Buffer.concat([head, chunk]);
}
const FILES = {
  'static.glb': readFileSync(join(CORE_FIXTURES, 'pair.glb')),
  'animated.glb': readFileSync(join(CORE_FIXTURES, 'pair.slide.glb')),
  'bare.glb': glbOf({ asset: { version: '2.0' }, scene: 0, scenes: [{ nodes: [] }] }),
  'broken.glb': Buffer.from('glTF is not what this is'),
};
// A file's bytes held back until the test lets them go: the view as it is before the file arrives.
const holds = new Map();
function hold(name) {
  let release;
  holds.set(name, new Promise(resolve => { release = resolve; }));
  return () => { holds.delete(name); release(); };
}

// The harness renders its panes at a fixed CSS size; the spec draws them smaller, so a software
// GL (CI's SwiftShader) has fewer pixels to fill and a capture fewer to read.
const HARNESS_SIZE = '<style>#root > div { width: 800px !important; height: 500px !important; }</style>';

// One harness bundle, one server and one browser for the file; every test opens its own page.
// (A browser's first WebGL page pays for compiling the viewer's shaders; later pages reuse them.)
let server, browser;
before(async () => {
  const { bundle } = await harnessBundle();
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    const name = url.pathname.split('/').pop();
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/api/v1/documents') && request.method === 'GET') {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ documents: (Object.entries(FILES).map(([file, data]) => (
        { kind: 'glb', file: `/models/${file}`, url: `/${file}`, hash: `${root}-${file}`, bytes: data.length }))).map(entry => ({ entry, revision: entry.hash })) }));
    } else if (url.pathname.endsWith('/api/v1/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ backend: 'cadgen' }));
    } else if (FILES[name]) {
      response.setHeader('Content-Type', 'model/gltf-binary');
      Promise.resolve(holds.get(name)).then(() => response.end(FILES[name]));
    } else {
      const width = Number(url.searchParams.get('width')) || 800;
      response.setHeader('Content-Type', 'text/html');
      response.end(`<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE.replace('800px', `${width}px`)}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`);
    }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: (process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1')
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
});

// `record` opens the page as a previous session left its tab (`window.__cadTabRecord`); `width`, the view's.
async function open(t, file, { record = null, width = 800, clock = false } = {}) {
  const page = await browser.newPage({ viewport: { width, height: 500 }, deviceScaleFactor: 1 });
  // `clock`: the page's timers Playwright's, to run forward (`page.clock`).
  if (clock) await page.clock.install();
  t.after(() => page.close());
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    window.Worker = undefined;
    for (const name of ['localStorage', 'sessionStorage']) {
      Object.defineProperty(window, name, { get() { throw new Error(`Renderer accessed ${name}`); } });
    }
  });
  if (record) await page.addInitScript(stored => { window.__cadTabRecord = stored; }, record);
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=${file}&width=${width}`);
  return { page, errors, pane: page.getByTestId('one') };
}

const ready = pane => pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
// What the view handed Export (the harness's ExportContext records it): the file it shows, named by
// its path, at the bytes on screen (their catalog hash), which Export converts to the other mesh kinds.
async function exported(page, file) {
  await page.waitForFunction(() => window.cadHarness.exportViews.at(-1));
  const shown = await page.evaluate(() => window.cadHarness.exportViews.at(-1));
  assert.deepEqual(Object.keys(shown).sort(), ['doc', 'file', 'name', 'revision']);
  assert.deepEqual([shown.doc, shown.file, shown.name], [`/models/${file}`, `/models/${file}`, file]);
  assert.ok(shown.revision.endsWith(`-${file}`), `the catalog hash of the bytes shown: ${shown.revision}`);
}

// A GLB of two nodes that draw has a GLB's every tool on its strip, Select in hand, then Explode and Clip, tools
// as Draw is; its view's controls end the strip, in their section: Projection, Display, then Preview.
const GLB_TOOLS = ['Select:true', 'Draw:false', 'Measure:false', 'Explode:false', 'Clip:false'];
const glbTools = async (pane) => {
  assert.deepEqual(await pane.getByRole('group', { name: 'Interaction tools' }).getByRole('button')
    .evaluateAll(buttons => buttons.filter(button => button.hasAttribute('aria-pressed') && !button.closest('[data-view-controls]')).map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
  GLB_TOOLS, 'Select, Draw, Measure, Explode and Clip');
  const strip = pane.getByRole('group', { name: 'Interaction tools' });
  // The strip is the tools alone, Clip last, no rule; the view's settings are the navbar's, Display left of Preview, and
  // the corner is the cube alone.
  assert.equal(await strip.locator('[data-view-controls]').count(), 0, 'nothing of the view on the strip');
  assert.equal(await strip.locator('[data-strip-rule]').count(), 0, 'no rule');
  assert.deepEqual(await pane.locator('[data-viewer-navbar] [data-navbar-view-controls] button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label').split(':')[0])),
    ['Display', 'Preview'], 'the navbar\'s: Display, then Preview');
  assert.equal(await pane.locator('[data-view-corner] *').count(), 0, 'nothing beside the cube in its corner');
  // Nothing else of the view on screen.
  for (const name of ['Orbit', 'Pencil', 'Shapes', 'Joints']) assert.equal(await pane.getByRole('button', { name, exact: true }).count(), 0, name);
};
/** World point -> page coordinates, from the camera the viewport publishes. */
function projector(camera, box) {
  const sub = (a, b) => a.map((value, index) => value - b[index]);
  const norm = vector => { const length = Math.hypot(...vector); return vector.map(value => value / length); };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const dot = (a, b) => a.reduce((sum, value, index) => sum + value * b[index], 0);
  const forward = norm(sub(camera.target, camera.position));
  const right = norm(cross(forward, camera.up));
  const up = cross(right, forward);
  const halfWidth = camera.halfHeight * (box.width / box.height);
  return point => {
    const offset = sub(point, camera.target);
    return [box.x + (dot(offset, right) / halfWidth * 0.5 + 0.5) * box.width, box.y + (0.5 - dot(offset, up) / camera.halfHeight * 0.5) * box.height];
  };
}
// The tools view's routines, for a file with routines (an animated GLB): the panel's Animation tab, no playbar under the
// model, nothing of it on the strip; the clips, the transport, and Speed, Loop and Autoplay.
const animationSection = pane => pane.locator('[data-animation-section]');
// The Animation tab opened: the panel shown where it is put away (a narrow view starts it so), then its tab.
async function openAnimation(pane) {
  const shut = pane.locator('[data-navbar-panel="left"][aria-expanded="false"]');
  if (await shut.count()) await shut.click();
  await pane.locator('aside[data-flat-panel]:not([hidden]) [data-flat-panel-tab="animation"]').click();
  await animationSection(pane).waitFor();
  return animationSection(pane);
}
// Preview's playbar, under the model, for a file with routines (Preview has no panel).
const playbar = pane => pane.getByRole('toolbar', { name: 'Animation playback', exact: true });
// Display: the navbar's (`kit/shell/DisplaySettings.jsx`), its card's Style the modes a file offers (an option each),
// then the Background and Show grid.
const displayButton = pane => pane.locator('[data-navbar-view-controls] [data-display-settings]');
// Display's card opened, its rows read (the modes by id; whether Grid is there; the Background's choices), and shut again.
async function displayMenu(pane) {
  const page = pane.page();
  await displayButton(pane).click();
  const card = page.locator('[data-display-settings-card]');
  await card.waitFor();
  // A choice is a dropdown of the card (Style, Background), its options in its list; Grid a switch of the card's.
  const choices = async (id, attribute) => {
    await card.locator(`[data-settings-select="${id}"]`).click();
    const options = page.getByRole('menu').locator(`[${attribute}]`);
    await options.first().waitFor();
    const values = await options.evaluateAll((items, name) => items.map(item => item.getAttribute(name)), attribute);
    await page.keyboard.press('Escape');
    await page.getByRole('menu').waitFor({ state: 'detached' });
    return values;
  };
  const rows = { modes: await choices('display', 'data-display-mode-option'), grid: await card.getByRole('switch', { name: 'Show grid', exact: true }).count() === 1,
    backgrounds: await choices('background', 'data-display-background') };
  await card.getByRole('button', { name: 'Close display settings', exact: true }).click();
  await card.waitFor({ state: 'detached' });
  return rows;
}
const displayModes = async pane => (await displayMenu(pane)).modes;
// The viewport's own pixels, without any chrome over them: what a host capture returns.
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
// Colours covering a real share of the picture: the faces of the model, never antialiased rims.
function dominantColors(image, { minShare = 0.004 } = {}) {
  const counts = new Map();
  for (let offset = 0; offset < image.data.length; offset += 4) {
    const key = (image.data[offset] << 16) | (image.data[offset + 1] << 8) | image.data[offset + 2];
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const total = image.width * image.height;
  // The corner pixel is the backdrop, whatever share of the picture the model takes. The
  // backdrop is a GRADIENT, so its neighbouring shades are backdrop too: matching only the
  // exact corner colour counts a few of them as "colours of the model" as soon as the model
  // leaves enough of the frame uncovered.
  const backdrop = [image.data[0], image.data[1], image.data[2]];
  const isBackdrop = key => Math.max(Math.abs((key >> 16) - backdrop[0]),
    Math.abs(((key >> 8) & 255) - backdrop[1]), Math.abs((key & 255) - backdrop[2])) <= 12;
  return [...counts].filter(([key, count]) => !isBackdrop(key) && count / total >= minShare)
    .sort((left, right) => right[1] - left[1]).map(([key]) => [key >> 16, (key >> 8) & 255, key & 255]);
}
const differingPixels = (left, right) => {
  assert.deepEqual([left.width, left.height], [right.width, right.height]);
  let count = 0;
  for (let offset = 0; offset < left.data.length; offset += 4) {
    if (left.data[offset] !== right.data[offset] || left.data[offset + 1] !== right.data[offset + 1] || left.data[offset + 2] !== right.data[offset + 2]) count += 1;
  }
  return count;
};
const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
// A press on a control Preview's bar may hide (`harness/preview.mjs`), or on any other.
const pressPreviewable = async (page, pane, control) => (await pane.locator('[data-preview-view]').count()
  ? pressInPreview(page, pane, control) : control.click());
// Render is Preview's: in by Preview at the strip's end and out by Exit preview in Preview's bar, each once the view has
// come together under its cover.
async function togglePreview(page, pane, enter) {
  await pressPreviewable(page, pane, pane.getByRole('button', { name: enter ? 'Preview' : 'Exit preview', exact: true }));
  await pane.getByRole('button', { name: enter ? 'Exit preview' : 'Preview', exact: true }).waitFor();
  await page.waitForFunction(() => !document.querySelector('[data-testid="one"] [data-preview-cover]')
    && document.querySelector('[data-testid="one"] [aria-busy="false"]'));
}
// The capture once the view has come to rest: the same picture twice running.
async function stillCapture(page) {
  let last = await capture(page);
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await settle(page);
    const next = await capture(page);
    if (differingPixels(last, next) === 0) return next;
    last = next;
  }
  assert.fail('the view never came to rest');
}
// A capture that shows `expected` exactly, once the change that leads to it has landed: a capture
// at another size is that change still landing (the navbar coming back after preview resizes the view).
async function captureMatching(page, expected, message) {
  let differing = -1;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const next = await capture(page);
    differing = next.width === expected.width && next.height === expected.height ? differingPixels(expected, next) : Infinity;
    if (differing === 0) return;
    await settle(page);
  }
  assert.equal(differing, 0, message);
}
const display = (page, patch) => page.evaluate(next => window.cadHarness.a.controller.setDisplaySettings(next), patch);

test('a static GLB opens on its native scene in Select: its tools, its display modes on its authored colours, its node picks refused to a command, its settings under its renderer (the shell around it is the mesh spec\'s)', async (t) => {
  const { page, pane, errors } = await open(t, 'static.glb');
  await ready(pane);
  assert.deepEqual(errors, []);
  await exported(page, 'static.glb');

  await glbTools(pane);
  assert.deepEqual([await pane.locator('[data-quick-edit-box]').count(), await pane.locator('[data-quick-edit-context]').count()], [1, 0], 'Quick Edit is there, one row: nothing attached until a pick or a mark');
  assert.equal(await pane.locator('[data-navbar-view-controls]').getByRole('button', { name: 'Preview', exact: true }).count(), 1,
    'a GLB is 3D: Preview is the navbar\'s, after Display');
  assert.equal(await pane.locator('[data-playbar], [data-animation-section]').count(), 0, 'a static GLB has no playbar and no Animation tab');
  // Its Model tab: the file's node tree in the view's panel, a press on a node's row picking it as a press on the model does.
  if (await pane.locator('[data-navbar-panel="left"][aria-expanded="false"]').count()) await pane.getByRole('button', { name: 'Show panel', exact: true }).click();
  const tree = pane.locator('aside[data-flat-panel]');
  // Its one tab is a title: no pill.
  await tree.locator('[data-flat-panel-heading]').filter({ hasText: 'Model' }).waitFor();
  const nodeRows = tree.locator('[data-scene-node] button[aria-pressed]');
  assert.ok(await nodeRows.count() >= 1, 'a row for each node that draws');
  await nodeRows.first().click();
  assert.equal(await nodeRows.first().getAttribute('aria-pressed'), 'true', 'the row lit as its node is picked');
  await page.waitForFunction(() => (window.cadHarness.a.controller?.readState().selectedNodes || []).length === 1);
  await nodeRows.first().click();
  await page.waitForFunction(() => (window.cadHarness.a.controller?.readState().selectedNodes || []).length === 0);
  // Put away again, so the model has the whole view for what follows.
  await pane.locator('[data-viewer-navbar]').getByRole('button', { name: 'Hide panel', exact: true }).click();
  await pane.locator('[data-navbar-panel="left"][aria-expanded="false"]').waitFor();

  // A GLB has no stack panel of its own: its only settings are Display's, the corner's menu, never over the model.
  assert.equal(await pane.locator('[data-cad-tool-stack] [data-tool-panel]').count(), 0, 'nothing in the tool stack');
  // Display: its modes (a GLB has no edges to draw: no mode made of them; its two parts, Parts to colour), then Grid and
  // the Background, every 3D view's, and no settings a mode would bring.
  assert.deepEqual(await displayMenu(pane), { modes: ['solid', 'parts'], grid: true, backgrounds: ['light', 'dark'] });
  // The panel put away leaves the scene the whole width; let that frame land before comparing pictures.
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy] > div > canvas').width >= 790);
  await settle(page);

  // Surfaces, on the native scene: Solid, each part its own authored colour, shaded.
  const red = ([r, g, b]) => r > 150 && g < 90 && b < 90;
  const blue = ([r, g, b]) => b > 150 && r < 90 && g < 130;
  const shaded = await capture(page);
  const original = dominantColors(shaded);
  assert.ok(original.length >= 4, 'shaded faces differ');
  assert.ok(original.some(red) && original.some(blue), `the authored red and blue: ${JSON.stringify(original)}`);
  // Parts deals a palette colour per part, in place of the authored ones.
  await display(page, { mode: 'parts' });
  const palette = dominantColors(await capture(page));
  assert.ok(!palette.some(red) && !palette.some(blue), `a palette colour per part: ${JSON.stringify(palette)}`);
  // The grid draws in any mode.
  const parts = await capture(page);
  await display(page, { grid: true });
  assert.ok(differingPixels(parts, await capture(page)) > 0, 'the grid draws under Parts');
  // Solid with the grid off restores the initial look.
  await display(page, { mode: 'solid', grid: false });
  assert.equal(differingPixels(shaded, await capture(page)), 0, 'the look is fully reversible');

  // A GLB's own answers to the host: its state, and a command's pick refused (a person picks its nodes).
  const state = await page.evaluate(() => window.cadHarness.a.controller.readState());
  assert.deepEqual([state.resource.path, state.revision, state.loading, state.selection], ['/models/static.glb', 'one-static.glb', false, []]);
  const declined = await page.evaluate(() => window.cadHarness.a.controller.select({ selectors: ['f:pair.make_box1.1'] }).then(() => '', error => error.message));
  assert.match(declined, /A GLB's nodes are picked by a person in the viewport under Select/);
  assert.equal(await page.evaluate(() => window.cadHarness.a.controller.clearSelection().then(() => '', error => error.message)), '', 'its node selection clears');

  // Display settings belong to this file under this renderer's id (a remount restoring them is the mesh spec's).
  await display(page, { mode: 'parts', grid: true });
  await page.waitForFunction(() => window.cadHarness.state.renderers?.[JSON.stringify(['/models/static.glb', 'glb'])]?.display?.mode === 'parts');
  const stored = await page.evaluate(() => window.cadHarness.state.renderers);
  assert.deepEqual(Object.keys(stored), [JSON.stringify(['/models/static.glb', 'glb'])], 'keyed by [absolute path, renderer id]');

  assert.deepEqual(errors, []);
});

test('an animated GLB opens at rest, its clips its Animation tab\'s, no playbar under the model; in Preview, from its playbar, they play in Render without moving the camera or the floor, Orbit turns the camera, and leaving restores the tools routine\'s held frame', async (t) => {
  const { page, pane, errors } = await open(t, 'animated.glb');
  await ready(pane);
  await glbTools(pane);
  // Its routines are the Animation tab's: no playbar under the model, nothing on the strip. Its controls are one set,
  // at rest, playing and paused: nothing comes or goes, and there is no Stop (the scrubber's start is the rest pose).
  assert.ok(await pane.locator('[data-flat-panel], [data-navbar-panel="left"]').count() >= 1, 'a GLB has the view\'s panel, its Model tab its nodes');
  assert.equal(await pane.locator('[data-playbar]').count(), 0, 'no playbar in the tools view');
  const panel = await openAnimation(pane);
  assert.deepEqual([await pane.locator('aside[data-flat-panel]:not([hidden]) [data-flat-panel-tab="animation"] [data-flat-panel-tab-name]').textContent(),
    await panel.locator('[data-panel-select-row]').first().locator('label, [data-field-label]').first().textContent()], ['Animation', 'Animation'], 'a GLB\'s tab and clip row use glTF\'s word');
  const controls = () => panel.locator('[data-animation-play], [role=slider], [data-animation-speed], [data-animation-loop]')
    .evaluateAll(elements => elements.map(element => (element.getAttribute('aria-label') || element.textContent).replace('Pause', 'Play').split(':')[0]));
  const CONTROLS = ['Play animation', 'Animation time', 'Animation speed', 'Loop'];
  assert.deepEqual(await controls(), CONTROLS, 'at rest');
  // No Reset in the transport and no Stop: Reset is the tab's, at its bottom right (the panel's actions row, as Params'
  // and Joints'), idle at rest.
  const tab = panel.locator('xpath=ancestor::*[@data-tool-panel][1]');
  const reset = tab.locator('[data-panel-foot] [data-animation-reset]');
  const [tabBox, resetBox] = [await tab.boundingBox(), await reset.boundingBox()];
  assert.deepEqual([await panel.locator('[data-animation-transport] button').count(), await reset.isDisabled(), await tab.getByRole('button', { name: /Stop/ }).count(),
    resetBox.y > (await panel.locator('[data-animation-loop]').boundingBox()).y, Math.abs(tabBox.x + tabBox.width - resetBox.x - resetBox.width) <= 24],
  [1, true, 0, true, true], `the transport is Play alone; Reset idle at the tab's bottom right, no Stop: ${JSON.stringify({ tabBox, resetBox })}`);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  const toolsRest = await stillCapture(page);
  const panelTime = () => page.evaluate(() => Number(document.querySelector(
    '[data-testid="one"] [data-animation-section] [role="slider"][aria-label="Animation time"]')?.getAttribute('aria-valuenow')));
  // Play plays the clip in the tools view, the controls the same; its start is the rest pose.
  await panel.getByRole('button', { name: 'Play animation', exact: true }).click();
  await panel.getByRole('button', { name: 'Pause animation', exact: true }).waitFor();
  assert.deepEqual(await controls(), CONTROLS, 'playing');
  await page.waitForFunction(() => Number(document.querySelector(
    '[data-testid="one"] [data-animation-section] [role="slider"][aria-label="Animation time"]')?.getAttribute('aria-valuenow')) > 0.25);
  await panel.getByRole('button', { name: 'Pause animation', exact: true }).click();
  assert.ok(differingPixels(toolsRest, await capture(page)) > 200, 'the panel moved the rider');
  await panel.getByRole('slider', { name: 'Animation time', exact: true }).focus();
  await page.keyboard.press('Home');
  assert.equal(await panelTime(), 0);
  await captureMatching(page, toolsRest, 'the clip at its start is the rest pose');
  // The panel's routine left at its end: preview has a routine of its own, at rest.
  await page.keyboard.press('End');
  await page.waitForFunction(() => Number(document.querySelector(
    '[data-testid="one"] [data-animation-section] [role="slider"][aria-label="Animation time"]')?.getAttribute('aria-valuenow')) > 0.25);
  const panelHeld = await panelTime();
  const heldCapture = await stillCapture(page);
  assert.ok(differingPixels(toolsRest, heldCapture) > 200, 'the panel holds the rider at the end of its clip');

  await togglePreview(page, pane, true);
  // Preview's routine is its own playbar's, under the model; the model in Render, on its floor.
  assert.equal(await animationSection(pane).isVisible(), false, 'the tools view\'s Animation tab goes with the panel');
  const section = playbar(pane);
  await section.getByRole('button', { name: 'Play animation', exact: true }).waitFor();
  await page.waitForFunction(() => window.__cadStage()?.studioGround);
  const rest = await stillCapture(page);
  // It opens paused, at the clip's start.
  assert.equal(await section.getByRole('button', { name: 'Pause animation', exact: true }).count(), 0, 'it opens paused');
  const time = section.getByRole('slider', { name: 'Animation time' });
  assert.equal(Number(await time.getAttribute('aria-valuenow')), 0);
  // Scrubbing away and back is the rest pose again.
  await time.focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowLeft');
  await captureMatching(page, rest, 'a clip scrubbed back to 0 is the rest pose');

  // Playing moves the model, never the floor; pausing leaves it where it stopped.
  const floor = await page.evaluate(() => window.__cadStage().studioGround);
  await pressPreviewable(page, pane, section.getByRole('button', { name: 'Play animation', exact: true }));
  await page.waitForFunction(() => Number(document.querySelector('[data-testid="one"] [data-preview-playbar] [role="slider"][aria-label="Animation time"]')?.getAttribute('aria-valuenow')) > 0.25);
  await pressPreviewable(page, pane, section.getByRole('button', { name: 'Pause animation', exact: true }));
  assert.ok(differingPixels(rest, await capture(page)) > 200, 'the rider moved');
  assert.deepEqual(await page.evaluate(() => window.__cadStage().studioGround), floor);

  // Orbit, in Preview's settings, turns the camera; turned off again, it stops.
  await pressPreviewable(page, pane, pane.getByRole('button', { name: 'Display', exact: true }));
  const orbit = pane.getByRole('region', { name: 'Display' }).getByRole('switch', { name: 'Orbit', exact: true });
  assert.equal(await orbit.getAttribute('aria-checked'), 'false', 'Preview opens still');
  const held = await page.evaluate(() => window.__cadCamera().position);
  await orbit.click();
  await page.waitForFunction(start => window.__cadCamera().position.some((value, axis) => Math.abs(value - start[axis]) > 1e-6), held);
  await orbit.click();

  // Leaving preserves the tools view's held routine frame, camera and mode.
  await togglePreview(page, pane, false);
  await page.waitForFunction(() => !window.__cadStage()?.studioGround);
  assert.equal(await panelTime(), panelHeld, 'the tools routine stays at its held time');
  await captureMatching(page, heldCapture, 'the tools routine keeps its held frame');
  // Scrubbed back to its start, paused, the model is at rest again, the controls as they were.
  await panel.getByRole('slider', { name: 'Animation time', exact: true }).focus();
  await page.keyboard.press('Home');
  assert.equal(await panelTime(), 0);
  assert.deepEqual(await controls(), CONTROLS, 'paused at its start');
  await captureMatching(page, toolsRest, 'at its start, the rest pose');
  assert.deepEqual(errors, []);
});

test("an animated GLB's Speed and Loop are the file's: chosen in the Animation tab, Preview's routine plays with them, and every visit to Preview opens still", async (t) => {
  const { page, pane, errors } = await open(t, 'animated.glb');
  await ready(pane);
  // The tools view's: the Animation tab's Speed and Loop rows.
  const tab = await openAnimation(pane);
  const tabSettings = async () => [await tab.locator('[data-animation-speed]').getAttribute('aria-label'),
    await tab.getByRole('switch', { name: 'Loop', exact: true }).getAttribute('aria-checked')];
  // Preview's: its playbar's cog.
  let settingsButton = null;
  const menu = page.getByRole('menu', { name: 'Playback settings', exact: true });
  const settings = async () => {
    if (!settingsButton) return tabSettings();
    await pressPreviewable(page, pane, settingsButton);
    const read = [await menu.getByRole('menuitem', { name: /^Animation speed: / }).getAttribute('aria-label'),
      await menu.getByRole('menuitemcheckbox', { name: 'Loop', exact: true }).getAttribute('aria-checked')];
    await page.keyboard.press('Escape');
    await menu.waitFor({ state: 'detached' });
    return read;
  };
  // A Speed chosen and Loop turned over, in the Animation tab's rows.
  const choose = async speed => {
    await tab.locator('[data-animation-speed]').click();
    await page.getByRole('menuitemradio', { name: `${speed}×`, exact: true }).click();
    await tab.getByRole('switch', { name: 'Loop', exact: true }).click();
  };
  const orbit = pane.getByRole('region', { name: 'Display' }).getByRole('switch', { name: 'Orbit', exact: true });
  assert.deepEqual(await settings(), ['Animation speed: 1×', 'true'], 'the clip\'s own');
  await choose(0.5);
  assert.deepEqual(await settings(), ['Animation speed: 0.5×', 'false']);
  await togglePreview(page, pane, true);
  settingsButton = playbar(pane).getByRole('button', { name: 'Playback settings' });
  assert.deepEqual(await settings(), ['Animation speed: 0.5×', 'false'], 'the file\'s, in Preview too');
  await pressPreviewable(page, pane, pane.getByRole('button', { name: 'Display', exact: true }));
  await orbit.click();
  assert.equal(await orbit.getAttribute('aria-checked'), 'true');
  await togglePreview(page, pane, false);
  await togglePreview(page, pane, true);
  await pressPreviewable(page, pane, pane.getByRole('button', { name: 'Display', exact: true }));
  assert.equal(await orbit.getAttribute('aria-checked'), 'false', 'still again');
  assert.deepEqual(await settings(), ['Animation speed: 0.5×', 'false'], 'the file\'s, kept');
  await togglePreview(page, pane, false);
  assert.deepEqual(errors, []);
});

test('a GLB\'s tools: Select picks a node into Quick Edit, Measure reads metres approximately, Explode moves the nodes apart and Clip, set, takes it off', async (t) => {
  const { page, pane, errors } = await open(t, 'static.glb');
  await ready(pane);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await display(page, { grid: false });
  await settle(page);
  const box = await pane.locator('[data-cad-surface] canvas').first().boundingBox();
  const at = projector(await page.evaluate(() => window.__cadCamera()), box);
  const chips = () => pane.locator('[data-quick-edit-refs] [data-quick-edit-ref] > button:first-child')
    .evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label')));
  // The native static export groups the rider first and the base second, both named pair.
  // The base is n1: its 20 mm cube is x 0..20, y -20..0, z 0..20 in CAD millimetres. Picked with Clip in hand: a model
  // effect's tool picks as Select does, and stays in hand.
  await pane.getByRole('button', { name: 'Clip', exact: true }).click();
  await page.mouse.click(...at([10, -10, 20]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedNodes?.join() === 'n1');
  assert.equal(await pane.getByRole('button', { name: 'Clip', exact: true }).getAttribute('aria-pressed'), 'true');
  assert.deepEqual(await chips(), ['pair (n1)'], 'the shared authored name, disambiguated by its node: static.glb#n1');

  // Measure: two points on the base's top, 16 mm apart, each where it is pressed: a mesh's triangles are not snapped to.
  await pane.getByRole('button', { name: 'Measure', exact: true }).click();
  assert.equal(await pane.locator('[data-measurements]').count(), 0, 'no row under the strip until something is measured');
  for (const corner of [[2, -10, 20], [18, -10, 20]]) { await page.mouse.click(...at(corner)); await settle(page); }
  // Its chip is Measure's row's, under the strip; Quick Edit carries the pick alone.
  const measured = pane.locator('[data-measurements] [data-quick-edit-ref]');
  await measured.waitFor();
  assert.deepEqual(await measured.locator('> button:first-child').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    ['Measurement 1: ≈ 0.0160 m (approximate)']);
  assert.deepEqual(await pane.locator('[data-quick-edit-box] [data-quick-edit-ref]').count(), 1);

  // Explode: the two nodes move apart, and the stage follows the box they make.
  const width = (await page.evaluate(() => window.__cadStage().bounds)).max[0];
  await display(page, { exploded: { enabled: true, amount: 1 } });
  await page.waitForFunction(rest => window.__cadStage().bounds.max[0] > rest + 1, width);
  // Clip taken up, pressed, its row under the strip as wide as Draw's: its slider cuts the model, and Explode goes off
  // (one motion at a time). A press on the model still picks, as Select's does.
  const drawWidth = await (async () => {
    await pane.getByRole('button', { name: 'Draw', exact: true }).click();
    return pane.locator('[data-annotation-controls]').evaluate(element => element.getBoundingClientRect().width);
  })();
  await pane.getByRole('button', { name: 'Clip', exact: true }).click();
  assert.equal(await pane.getByRole('button', { name: 'Clip', exact: true }).getAttribute('aria-pressed'), 'true');
  const clipRow = pane.getByRole('toolbar', { name: 'Clip controls' });
  assert.equal(await clipRow.evaluate(element => element.getBoundingClientRect().width), drawWidth, 'Clip\'s row is as wide as Draw\'s');
  await page.getByRole('slider', { name: 'Clip amount' }).press('End');
  await page.waitForFunction(() => window.__cadStage().cut === 1 && window.cadHarness.a.controller.readState().display.exploded?.enabled !== true);
  // Put down: the cut stays, Clip's dot says so.
  await pane.getByRole('button', { name: 'Select', exact: true }).click();
  assert.equal(await pane.getByRole('button', { name: 'Clip', exact: true }).getAttribute('data-changed'), '');
  assert.equal(await page.evaluate(() => window.__cadStage().cut), 1);
  assert.deepEqual(errors, []);
});

// While the file loads, a structure tab with no row shows the panel's placeholder rows, its tabpanel busy.
const loadingRows = scope => scope.locator('aside[data-flat-panel] [role="tabpanel"][aria-busy="true"] [data-tree-row-placeholder]');

test('a GLB has its Model tab from the first frame, open as it stays once the file is in; one with no node lists the file', async (t) => {
  // Wide enough that the panel starts open beside the model (it keeps 640px).
  const release = hold('bare.glb');
  const { page, pane, errors } = await open(t, 'bare.glb', { width: 1000, clock: true });
  const panel = pane.locator('aside[data-flat-panel]');
  await panel.locator('[data-flat-panel-heading]').filter({ hasText: 'Model' }).waitFor();
  const toggle = pane.locator('[data-viewer-navbar] [data-navbar-panel]');
  const first = await toggle.getAttribute('aria-expanded');
  // Past the update status's delay: a first load is the loading cover's to say, never "Updating view…".
  await page.clock.runFor(1000);
  assert.deepEqual([first, await pane.locator('[aria-busy="true"]').count() > 0, await panel.locator('[data-scene-node]').count(), await loadingRows(pane).count(),
    await pane.locator('[data-view-update-status]').count()], ['true', true, 0, 6, 0], 'open, the file still loading, its placeholder rows, no update status');
  release();
  await ready(pane);
  const row = panel.locator('[data-scene-node="file"]');
  await row.waitFor();
  assert.deepEqual([await row.innerText(), await row.locator('button[aria-pressed]').count(), await loadingRows(pane).count()], ['bare.glb', 0, 0],
    'the file\'s one row, which picks nothing, in the placeholders\' place');
  assert.equal(await toggle.getAttribute('aria-expanded'), first, 'the panel as it was at the first frame');
  assert.deepEqual(errors, []);
});

test('a corrupt GLB raises the viewer\'s load alert, with reload and details', async (t) => {
  const { page, pane } = await open(t, 'broken.glb');
  const alert = pane.getByRole('alert');
  await alert.waitFor();
  assert.match(await alert.innerText(), /Couldn’t load the model/);
  assert.match(await alert.innerText(), /broken\.glb/);
  // Nothing on screen is the file's to work on: the card alone, with no tools or view actions.
  for (const name of ['Display', 'Preview']) {
    assert.equal(await pane.getByRole('button', { name, exact: true }).count(), 0, `no ${name} over a failed load`);
  }
  void page;
});
