import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFileSync } from 'node:fs';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';

// Fixtures, served from memory: cadgen's exports of two boxes with authored colours (core's
// `lib/render/fixtures`), static and with the clip that slides one of them from its rest pose,
// and bytes that are not a GLB at all.
const CORE_FIXTURES = join(dirname(createRequire(import.meta.url).resolve('@text-to-cad/core/lib/render/glbMeshData.js')), 'fixtures');
const FILES = {
  'static.glb': readFileSync(join(CORE_FIXTURES, 'pair.glb')),
  'animated.glb': readFileSync(join(CORE_FIXTURES, 'pair.slide.glb')),
  'broken.glb': Buffer.from('glTF is not what this is'),
};

// The harness renders its panes at a fixed CSS size; the spec draws them smaller, so a software
// GL (CI's SwiftShader) has fewer pixels to fill and a capture fewer to read.
const HARNESS_SIZE = '<style>#root > div { width: 800px !important; height: 500px !important; }</style>';

// One harness bundle, one server and one browser for the file; every test opens its own page.
// (A browser's first WebGL page pays for compiling the viewer's shaders; later pages reuse them.)
let temporary, server, browser;
before(async () => {
  temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-glb-browser-'));
  await build({ entryPoints: [fileURLToPath(new URL('../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.avif': 'dataurl', '.svg': 'dataurl' } });
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
      response.end(JSON.stringify({ entries: Object.entries(FILES).map(([file, data]) => (
        { kind: 'glb', file: `/models/${file}`, url: `/${file}`, hash: `${root}-${file}`, bytes: data.length })) }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ backend: 'cadgen' }));
    } else if (FILES[name]) { response.setHeader('Content-Type', 'model/gltf-binary'); response.end(FILES[name]); }
    else { response.setHeader('Content-Type', 'text/html'); response.end(`<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: (process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1')
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
  if (temporary) await rm(temporary, { recursive: true, force: true });
});

// `record` opens the page as a previous session left its tab (`window.__cadTabRecord`).
async function open(t, file, { record = null } = {}) {
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
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
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=${file}`);
  return { page, errors, pane: page.getByTestId('one') };
}

const ready = pane => pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
// What the view handed Export (the harness's ExportContext records it): the file it shows, named by
// its path, at the bytes on screen (their catalog hash), which Export converts to the other mesh kinds.
async function exported(page, file) {
  await page.waitForFunction(() => window.cadHarness.exportViews.at(-1));
  const shown = await page.evaluate(() => window.cadHarness.exportViews.at(-1));
  assert.deepEqual(Object.keys(shown).sort(), ['doc', 'file', 'name', 'preview', 'revision']);
  assert.deepEqual([shown.doc, shown.file, shown.name, shown.preview], [`/models/${file}`, `/models/${file}`, file, false]);
  assert.ok(shown.revision.endsWith(`-${file}`), `the catalog hash of the bytes shown: ${shown.revision}`);
}

// A GLB of two nodes that draw has a GLB's every tool on its strip, Select in hand; its view's
// controls end the strip, in the section of Explode and Clip: Projection, Display, then Preview.
const GLB_TOOLS = ['Select:true', 'Pencil:false', 'Shapes:false', 'Measure:false', 'Explode:false', 'Clip:false'];
const glbTools = async (pane) => {
  assert.deepEqual(await pane.getByRole('group', { name: 'Interaction tools' }).getByRole('button')
    .evaluateAll(buttons => buttons.filter(button => button.hasAttribute('aria-pressed') && !button.closest('[data-view-controls]')).map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
  GLB_TOOLS, 'Select, Pencil, Shapes, Measure, Explode and Clip');
  const strip = pane.getByRole('group', { name: 'Interaction tools' });
  assert.deepEqual(await strip.locator('[data-view-controls]').getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    ['Projection: Orthographic', 'Display mode: Solid', 'Preview'], 'its view\'s controls end the strip');
  assert.equal(await strip.locator('[data-strip-rule]').count(), 1, 'one rule, after the tools that pick');
  assert.equal(await strip.locator('[data-view-controls]').evaluate(element => element.previousElementSibling?.getAttribute('aria-label')), 'Clip', 'the view\'s controls follow Clip, no rule between');
  assert.equal(await pane.locator('[data-viewer-navbar] [data-view-controls] button').count(), 0, 'nothing of the view in the navbar');
  for (const name of ['Orbit', 'Draw', 'Position']) assert.equal(await pane.getByRole('button', { name, exact: true }).count(), 0, name);
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
// The file sidebar's tiles (an animated GLB's Animation), and a section opened by its tile.
const tileNames = pane => pane.locator('[data-file-sidebar-tools] button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label')));
async function openSection(pane, name) {
  const tile = pane.getByRole('group', { name: 'File sidebar' }).getByRole('button', { name, exact: true });
  if (await tile.getAttribute('aria-pressed') !== 'true') await tile.click();
  await pane.locator(`[data-tool-panel][aria-label="${name}"]`).waitFor();
}
const animationSection = pane => pane.locator('[data-tool-panel][aria-label="Animation"]');
const displayButton = pane => pane.locator('[data-cad-toolbar] [data-view-controls]').getByRole('button', { name: /^Display mode: / });
// Preview's playbar, under the model, for a file with routines (Preview has no file sidebar).
const playbar = pane => pane.getByRole('toolbar', { name: 'Animation playback', exact: true });
// Display's menu: the modes, then the Grid switch.
async function openDisplay(pane) {
  await displayButton(pane).click();
  await displayPanel(pane).waitFor();
}
// The display modes Display's menu offers, by id.
async function displayModes(pane) {
  await displayButton(pane).click();
  const menu = displayPanel(pane);
  const modes = await menu.locator('[data-display-mode-option]').evaluateAll(items => items.map(item => item.getAttribute('data-display-mode-option')));
  await pane.page().keyboard.press('Escape');
  await menu.waitFor({ state: 'detached' });
  return modes;
}
// Display's menu: a dropdown, portaled out of the viewer.
// Its accessible name is its tile's ("Display mode: Solid"); its own label is Display.
const displayPanel = pane => pane.page().locator('[role=menu][aria-label="Display"]');
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
// Render is Preview's: in by Preview at the strip's end and out by Exit preview in the navbar, each once the view has
// come together under its cover.
async function togglePreview(page, pane, enter) {
  await pane.getByRole('button', { name: enter ? 'Preview' : 'Exit preview', exact: true }).click();
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

test('a static GLB opens on its native scene in Select: display settings, orbit, host commands and state all work', async (t) => {
  const { page, pane, errors } = await open(t, 'static.glb');
  await ready(pane);
  assert.deepEqual(errors, []);
  await exported(page, 'static.glb');

  await glbTools(pane);
  assert.equal(await pane.locator('[data-quick-edit-box]').count(), 0, 'Quick Edit opens on a pick or a mark, never by itself');
  assert.equal(await pane.locator('[data-view-controls]').getByRole('button', { name: 'Preview', exact: true }).count(), 1,
    'a GLB is 3D: Preview ends the strip after Display');
  assert.equal(await pane.locator('[data-file-sidebar-tools]').count(), 0, 'a static GLB has nothing for the file sidebar');

  // A GLB has no panel of its own: its only settings are Display's, and Display is never
  // where a file opens, so the model has the room.
  assert.equal(await pane.locator('[data-tool-panel]').count(), 0, 'nothing in the tool stack');
  assert.deepEqual(await displayModes(pane), ['solid', 'parts'], 'a GLB has no edges to draw: no mode made of them; its two parts, Parts to colour');
  await openDisplay(pane);
  const displayMenu = displayPanel(pane);
  assert.equal(await displayMenu.getByRole('menuitemcheckbox', { name: 'Grid', exact: true }).count(), 1);
  assert.equal(await displayMenu.getByRole('menuitem').count(), 0, 'and no settings: a mode has nothing to set');
  await page.keyboard.press('Escape');
  await displayPanel(pane).waitFor({ state: 'detached' });
  // The column closing reaches the scene as a resize; let that frame land before comparing pictures.
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy] > div > canvas').width >= 790);
  await settle(page);

  // Preview draws the model in Render, on the studio's floor; leaving it takes the studio down.
  await togglePreview(page, pane, true);
  await page.waitForFunction(() => window.__cadStage()?.studioGround);
  await togglePreview(page, pane, false);
  await page.waitForFunction(() => !window.__cadStage()?.studioGround);

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

  // Dragging orbits.
  const before = await page.evaluate(() => window.cadHarness.a.controller.readState().camera);
  const canvas = await pane.locator('[aria-busy] > div > canvas').first().boundingBox();
  await page.mouse.move(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2);
  await page.mouse.down();
  await page.mouse.move(canvas.x + canvas.width / 2 + 140, canvas.y + canvas.height / 2 + 40, { steps: 6 });
  await page.mouse.up();
  await page.waitForFunction(position => JSON.stringify(window.cadHarness.a.controller.readState().camera.position) !== position, JSON.stringify(before.position));

  // The drag's damping coasts for a moment; a host camera lands on a view at rest.
  // At rest: the live camera the same over several frames running.
  await page.waitForFunction(() => new Promise(resolve => {
    let still = 0, last = null;
    const step = () => {
      const position = JSON.stringify(window.__cadCamera().position);
      still = position === last ? still + 1 : 0;
      last = position;
      if (still >= 5) resolve(true); else requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }));

  // Host commands drive the mounted view, and one that makes no sense here fails loudly.
  const camera = await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    const current = controller.readState().camera;
    return (await controller.setCamera({ ...current, position: [90, -70, 60], target: [10, 5, 5], zoom: 1.3 })).camera;
  });
  assert.deepEqual(camera.position.map(Math.round), [90, -70, 60]);
  const state = await page.evaluate(() => window.cadHarness.a.controller.readState());
  assert.deepEqual([state.resource.path, state.revision, state.loading, state.selection], ['/models/static.glb', 'one-static.glb', false, []]);
  const declined = await page.evaluate(() => window.cadHarness.a.controller.select({ selectors: ['o1.f1'] }).then(() => '', error => error.message));
  assert.match(declined, /A GLB's nodes are picked by a person in the viewport under Select/);
  assert.equal(await page.evaluate(() => window.cadHarness.a.controller.clearSelection().then(() => '', error => error.message)), '', 'its node selection clears');

  // A secondary press is the camera's: no menu of the viewer's, and the browser's own stays off the canvas.
  await page.evaluate(() => {
    window.nativeMenu = [];
    document.addEventListener('contextmenu', event => window.nativeMenu.push(event.defaultPrevented));
  });
  await page.mouse.click(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2, { button: 'right' });
  // The press has reached the page, and a menu it opened would be up two frames on.
  await page.waitForFunction(() => window.nativeMenu.length > 0);
  await settle(page);
  assert.equal(await page.getByRole('menu').count(), 0);
  assert.deepEqual(await page.evaluate(() => window.nativeMenu), [true]);

  // A host's capture request goes through the prompt port: the view, of the whole file.
  await page.evaluate(() => window.cadHarness.capture());
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  const captured = await page.evaluate(() => window.cadHarness.captures[0]);
  assert.deepEqual([captured.file, captured.type, captured.references.length], ['/models/static.glb', 'image/png', 1]);
  assert.deepEqual(captured.references[0].target, { kind: 'whole-resource' });

  // Camera and Display settings belong to this file under this renderer's id, and survive a remount.
  await display(page, { mode: 'parts', grid: true });
  await page.waitForFunction(() => window.cadHarness.state.renderers?.[JSON.stringify(['/models/static.glb', 'glb'])]?.display?.mode === 'parts');
  const stored = await page.evaluate(() => window.cadHarness.state.renderers);
  assert.deepEqual(Object.keys(stored), [JSON.stringify(['/models/static.glb', 'glb'])], 'keyed by [absolute path, renderer id]');
  const left = await page.evaluate(() => window.cadHarness.a.controller.readState());
  await page.evaluate(() => window.cadHarness.mounted(false));
  await pane.locator('canvas').first().waitFor({ state: 'detached' });
  await page.evaluate(() => window.cadHarness.mounted(true));
  await ready(pane);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  const reopened = await page.evaluate(() => window.cadHarness.a.controller.readState());
  // Within a thousandth: the camera read when leaving can still be coasting its last hundredth.
  assert.ok(reopened.camera.position.every((value, axis) => Math.abs(value - left.camera.position[axis]) <= 1e-3 * Math.max(1, Math.abs(left.camera.position[axis]))),
    `reopening restores the camera the file was left at: ${JSON.stringify([reopened.camera.position, left.camera.position])}`);
  assert.ok(Math.abs(reopened.camera.zoom - left.camera.zoom) < 1e-6);
  assert.deepEqual([reopened.display.mode, reopened.display.grid], ['parts', true]);

  assert.deepEqual(errors, []);
});

test('an animated GLB opens at rest, its clips the file sidebar\'s Animation section; in Preview, from its playbar, they play in Render without moving the camera or the floor, Orbit turns the camera, and leaving restores the tools routine\'s held frame', async (t) => {
  const { page, pane, errors } = await open(t, 'animated.glb');
  await ready(pane);
  await glbTools(pane);
  // Its routines are the sidebar's: one tile, its section closed as the file opens.
  assert.deepEqual(await tileNames(pane), ['Animation']);
  assert.equal(await animationSection(pane).isVisible(), false, 'no section open as the file opens');
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  const toolsRest = await stillCapture(page);
  const panelTime = () => page.evaluate(() => Number(document.querySelector(
    '[data-testid="one"] [data-tool-panel][aria-label="Animation"] [role="slider"][aria-label="Animation time"]')?.getAttribute('aria-valuenow')));
  // The panel plays the clip in the tools view, and its start is the rest pose.
  await openSection(pane, 'Animation');
  const panel = animationSection(pane);
  await panel.getByRole('button', { name: 'Play animation', exact: true }).click();
  await page.waitForFunction(() => Number(document.querySelector(
    '[data-testid="one"] [data-tool-panel][aria-label="Animation"] [role="slider"][aria-label="Animation time"]')?.getAttribute('aria-valuenow')) > 0.25);
  await panel.getByRole('button', { name: 'Pause animation', exact: true }).click();
  assert.ok(differingPixels(toolsRest, await capture(page)) > 200, 'the panel moved the rider');
  await panel.getByRole('slider', { name: 'Animation time', exact: true }).focus();
  await page.keyboard.press('Home');
  assert.equal(await panelTime(), 0);
  await captureMatching(page, toolsRest, 'the clip at its start is the rest pose');
  // The panel's routine left at its end: preview has a routine of its own, at rest.
  await page.keyboard.press('End');
  await page.waitForFunction(() => Number(document.querySelector(
    '[data-testid="one"] [data-tool-panel][aria-label="Animation"] [role="slider"][aria-label="Animation time"]')?.getAttribute('aria-valuenow')) > 0.25);
  const panelHeld = await panelTime();
  const heldCapture = await stillCapture(page);
  assert.ok(differingPixels(toolsRest, heldCapture) > 200, 'the panel holds the rider at the end of its clip');

  await togglePreview(page, pane, true);
  // Preview has no sidebar: its routine is the playbar's, under the model; the model in Render, on its floor.
  assert.equal(await pane.locator('[data-file-sidebar-room]').isHidden(), true, 'no file sidebar in Preview');
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
  await section.getByRole('button', { name: 'Play animation', exact: true }).click();
  await page.waitForFunction(() => Number(document.querySelector('[data-testid="one"] [data-preview-playbar] [role="slider"][aria-label="Animation time"]')?.getAttribute('aria-valuenow')) > 0.25);
  await section.getByRole('button', { name: 'Pause animation', exact: true }).click();
  assert.ok(differingPixels(rest, await capture(page)) > 200, 'the rider moved');
  assert.deepEqual(await page.evaluate(() => window.__cadStage().studioGround), floor);

  // Orbit, in Preview's settings, turns the camera; turned off again, it stops.
  await pane.getByRole('button', { name: 'Preview settings', exact: true }).click();
  const orbit = pane.getByRole('region', { name: 'Preview settings' }).getByRole('checkbox', { name: 'Orbit', exact: true });
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
  assert.deepEqual(errors, []);
});

test("an animated GLB's Speed and Loop are the file's: chosen in its Animation section, Preview's routine plays with them, and every visit to Preview opens still", async (t) => {
  const { page, pane, errors } = await open(t, 'animated.glb');
  await ready(pane);
  // Playback settings: the Animation section's in the tools view, Preview's playbar's in Preview.
  let settingsButton = animationSection(pane).getByRole('button', { name: 'Playback settings' });
  const menu = page.getByRole('menu', { name: 'Playback settings', exact: true });
  const settings = async () => {
    await settingsButton.click();
    const read = [await menu.getByRole('menuitem', { name: /^Animation speed: / }).getAttribute('aria-label'),
      await menu.getByRole('menuitemcheckbox', { name: 'Loop', exact: true }).getAttribute('aria-checked')];
    await page.keyboard.press('Escape');
    await menu.waitFor({ state: 'detached' });
    return read;
  };
  // A Speed chosen and Loop turned over, by keyboard (an item easing in never reads as stable under the pointer).
  const choose = async speed => {
    await settingsButton.click();
    await menu.getByRole('menuitem', { name: /^Animation speed: / }).click();
    await page.getByRole('menuitemradio', { name: `${speed}×`, exact: true }).press('Enter');
    await menu.waitFor({ state: 'detached' });
    await settingsButton.click();
    await menu.getByRole('menuitemcheckbox', { name: 'Loop', exact: true }).press('Enter');
    await page.keyboard.press('Escape');
    await menu.waitFor({ state: 'detached' });
  };
  const orbit = pane.getByRole('region', { name: 'Preview settings' }).getByRole('checkbox', { name: 'Orbit', exact: true });
  await openSection(pane, 'Animation');
  assert.deepEqual(await settings(), ['Animation speed: 1×', 'true'], 'the clip\'s own');
  await choose(0.5);
  assert.deepEqual(await settings(), ['Animation speed: 0.5×', 'false']);
  await togglePreview(page, pane, true);
  settingsButton = playbar(pane).getByRole('button', { name: 'Playback settings' });
  assert.deepEqual(await settings(), ['Animation speed: 0.5×', 'false'], 'the file\'s, in Preview too');
  await pane.getByRole('button', { name: 'Preview settings', exact: true }).click();
  await orbit.click();
  assert.equal(await orbit.getAttribute('aria-checked'), 'true');
  await togglePreview(page, pane, false);
  await togglePreview(page, pane, true);
  await pane.getByRole('button', { name: 'Preview settings', exact: true }).click();
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
  // The base is n1: its 20 mm cube is x 0..20, y -20..0, z 0..20 in CAD millimetres.
  await page.mouse.click(...at([10, -10, 20]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedNodes?.join() === 'n1');
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
  // Clip set, by its own slider: the model is cut, and Explode goes off (one motion at a time).
  await pane.getByRole('button', { name: 'Clip', exact: true }).click();
  await pane.getByRole('slider', { name: 'Clip amount' }).press('End');
  await page.waitForFunction(() => window.__cadStage().cut === 1 && window.cadHarness.a.controller.readState().display.exploded?.enabled !== true);
  assert.deepEqual(errors, []);
});

test('a corrupt GLB raises the viewer\'s load alert, with reload and details', async (t) => {
  const { page, pane } = await open(t, 'broken.glb');
  const alert = pane.getByRole('alert');
  await alert.waitFor();
  assert.match(await alert.innerText(), /Couldn’t load the model/);
  assert.match(await alert.innerText(), /broken\.glb/);
  // Nothing on screen is the file's to work on: the card alone, with no tools or view actions.
  for (const name of [/^Display mode: /, 'Preview']) {
    assert.equal(await pane.getByRole('button', { name, exact: true }).count(), 0, `no ${name} over a failed load`);
  }
  void page;
});
