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
import { writeGlb } from '@hardcore/core/glb/writeGlb.js';

// Inline fixtures, served from memory: two boxes with authored colours, the same
// pair with one box driven by a clip whose first key IS the rest pose, and bytes
// that are not a GLB at all.
function box([x, y, z], size) {
  const [a, b, c] = [x + size, y + size, z + size];
  const corners = [[x, y, z], [a, y, z], [a, b, z], [x, b, z], [x, y, c], [a, y, c], [a, b, c], [x, b, c]];
  const faces = [[0, 2, 1, 0, 3, 2], [4, 5, 6, 4, 6, 7], [0, 1, 5, 0, 5, 4], [2, 3, 7, 2, 7, 6], [1, 2, 6, 1, 6, 5], [3, 0, 4, 3, 4, 7]];
  return new Float32Array(faces.flat().flatMap(index => corners[index]));
}
const primitives = [
  { name: 'base', node: 'base', positions: box([0, 0, 0], 0.02), color: '#d02020' },
  { name: 'rider', node: 'rider', positions: box([0.03, 0, 0], 0.01), color: '#2040d0' },
];
const bytes = glb => Buffer.from(glb.buffer, glb.byteOffset, glb.byteLength);
const FILES = {
  'static.glb': bytes(writeGlb({ primitives }, { preset: 'export' })),
  'animated.glb': bytes(writeGlb({ primitives }, { preset: 'export', animations: [{
    name: 'slide', times: new Float32Array([0, 1]),
    channels: [{ node: 'rider', translation: new Float32Array([0, 0, 0, 0, 0.03, 0]) }],
  }] })),
  'broken.glb': Buffer.from('glTF is not what this is'),
};

async function serveHarness(t) {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-glb-browser-'));
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
        { kind: 'glb', file, rootRelativeFile: file, url: `/${file}`, hash: `${root}-${file}`, bytes: data.length })) }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else if (FILES[name]) { response.setHeader('Content-Type', 'model/gltf-binary'); response.end(FILES[name]); }
    else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: process.platform === 'darwin'
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  // `record` opens the page as a previous session left its tab (`window.__cadTabRecord`).
  const open = async (file, { record = null } = {}) => {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
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
  };
  return { open };
}

const ready = pane => pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();

test('preview orbits every GLB, and an animated one plays its routines there alone', async (t) => {
  const { open } = await serveHarness(t);
  const staticView = await open('static.glb');
  await ready(staticView.pane);
  await noTools(staticView.pane);
  await staticView.pane.getByRole('button', { name: 'Preview', exact: true }).click();
  await staticView.pane.getByRole('button', { name: 'Pause orbit', exact: true }).waitFor();
  assert.equal(await staticView.pane.getByRole('button', { name: 'Display settings', exact: true }).count(), 1, 'Display settings stay in preview');
  await staticView.pane.getByRole('button', { name: 'Playback settings', exact: true }).click();
  const menu = staticView.page.getByRole('menu', { name: 'Playback settings', exact: true });
  // A static file's playback is its orbit alone: no Animation group.
  assert.equal(await menu.getByText('Animation', { exact: true }).count(), 0);
  const orbit = staticView.page.getByRole('menuitemcheckbox', { name: 'Orbit', exact: true });
  assert.equal(await orbit.getAttribute('aria-checked'), 'true');
  await orbit.click();
  assert.equal(await orbit.getAttribute('aria-checked'), 'false');
  await staticView.pane.getByRole('button', { name: 'Play orbit', exact: true }).waitFor();
  await staticView.page.getByRole('menuitem', { name: /Orbit speed/ }).hover();
  await staticView.page.getByRole('menuitemradio', { name: '2×', exact: true }).click();
  await menu.waitFor({ state: 'hidden' });
  assert.equal(await staticView.pane.getByLabel('View cube', { exact: true }).count(), 0, 'preview draws no cube');
  await staticView.pane.getByRole('button', { name: 'Exit preview', exact: true }).click();
  assert.equal(await staticView.pane.getByLabel('View cube', { exact: true }).isVisible(), true);

  const { page, pane, errors } = await open('animated.glb');
  await ready(pane);
  const playing = () => pane.getByRole('button', { name: 'Pause animation', exact: true }).count().then(count => count > 0);
  // No Animate tool and no Animate panel: the tools view has nothing of the routine's.
  await noTools(pane);
  assert.equal(await pane.locator('[data-tool-panel]').count(), 0, 'no panel at all');
  assert.equal(await pane.locator('[data-animation-transport]').count(), 0, 'no transport outside preview');
  // Preview: the playbar under the model and the routine's settings with the orbit's in Playback settings.
  await pane.getByRole('button', { name: 'Preview', exact: true }).click();
  await pane.getByRole('toolbar', { name: 'Animation playback' }).waitFor();
  assert.equal(await playing(), false, 'Autoplay is off: the routine waits for its play button');
  await pane.getByRole('toolbar', { name: 'Animation playback' }).getByRole('button', { name: 'Playback settings', exact: true }).click();
  const settings = page.getByRole('menu', { name: 'Playback settings', exact: true });
  await settings.waitFor();
  assert.deepEqual(await settings.getByRole('menuitem').evaluateAll(items => items.map(item => item.getAttribute('aria-label'))),
    ['Animation speed: 1×', 'Orbit speed: 1×'], 'one clip: no Routine');
  assert.deepEqual(await settings.getByRole('menuitemcheckbox').evaluateAll(items => items.map(item => `${item.textContent}:${item.getAttribute('aria-checked')}`)),
    ['Loop:true', 'Autoplay:false', 'Orbit:true']);
  // Autoplay is the person's: ticked, the next preview starts the routine.
  await settings.getByRole('menuitemcheckbox', { name: 'Autoplay', exact: true }).click();
  await page.keyboard.press('Escape');
  await settings.waitFor({ state: 'detached' });
  // The playbar plays and pauses.
  await pane.getByRole('button', { name: 'Play animation', exact: true }).click();
  await pane.getByRole('button', { name: 'Pause animation', exact: true }).waitFor();
  await pane.getByRole('button', { name: 'Pause animation', exact: true }).click();
  await pane.getByRole('button', { name: 'Play animation', exact: true }).waitFor();
  // Display settings open over preview and hold its controls; the routine plays on under them.
  await pane.getByRole('button', { name: 'Play animation', exact: true }).click();
  await pane.getByRole('button', { name: 'Display settings', exact: true }).click();
  await page.locator('[data-display-popover]').waitFor();
  await page.waitForTimeout(1300);
  assert.equal(await pane.locator('[data-preview-controls]').getAttribute('data-visible'), 'true', 'an open popover holds preview\'s controls');
  assert.equal(await playing(), true);
  await page.keyboard.press('Escape');
  await page.locator('[data-display-popover]').waitFor({ state: 'detached' });
  // Leaving preview stops the routine; there is nothing of it in the tools view.
  await pane.getByRole('button', { name: 'Exit preview', exact: true }).click();
  await pane.getByRole('button', { name: 'Preview', exact: true }).waitFor();
  assert.equal(await pane.locator('[data-animation-transport]').count(), 0);
  // With Autoplay on, entering preview starts it.
  await pane.getByRole('button', { name: 'Preview', exact: true }).click();
  await pane.getByRole('button', { name: 'Pause animation', exact: true }).waitFor();
  await pane.getByRole('button', { name: 'Exit preview', exact: true }).click();
  assert.deepEqual([...staticView.errors, ...errors], []);
});
// A GLB has no tools; its Display settings are the button beside Preview.
const noTools = async (pane) => {
  assert.equal(await pane.getByRole('group', { name: 'Interaction tools' }).count(), 0, 'a static GLB has no tools, so no strip');
  assert.equal(await pane.getByRole('button', { name: 'Display settings', exact: true }).count(), 1, 'its Display settings are the button beside Preview');
  for (const name of ['Orbit', 'Draw', 'Select', 'Measure', 'Position', 'Animate']) {
    assert.equal(await pane.getByRole('button', { name, exact: true }).count(), 0, name);
  }
};
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
// The nav row's panel toggles, in order, each with whether its panel is the open one.
const panels = pane => pane.locator('[data-file-panel]')
  .evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`));
const display = (page, patch) => page.evaluate(next => window.cadHarness.a.controller.setDisplaySettings(next), patch);

test('a static GLB opens on its native scene with no tools: display settings, orbit, host commands and state all work', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('static.glb');
  await ready(pane);
  assert.deepEqual(errors, []);

  // Nothing of a GLB picks, measures, poses or is drawn on: the viewport simply
  // orbits, pans and zooms, with no strip over it.
  await noTools(pane);
  assert.equal(await pane.getByRole('button', { name: /Copy|Add to prompt/i }).count(), 0, 'no copy-references action');

  // A GLB has no panel of its own: its only settings are Display's, and Display is never
  // where a file opens. So it opens with the column shut and the model given the room.
  assert.deepEqual(await panels(pane), ['Show files:false']);
  assert.equal(await pane.locator('[data-tool-panel]').count(), 0, 'nothing in the tool stack');
  await pane.getByRole('button', { name: 'Display settings', exact: true }).click();
  await pane.page().locator('[data-display-popover]').waitFor();
  assert.deepEqual(await panels(pane), ['Show files:false']);
  const displayMenu = page.locator('[data-display-popover]');
  assert.equal(await displayMenu.getByRole('tab').count(), 0, 'the popover has no tabs inside it');
  assert.deepEqual(await displayMenu.getByRole('combobox', { name: 'Mode', exact: true }).innerText(), 'Solid');
  await displayMenu.getByRole('combobox', { name: 'Mode', exact: true }).click();
  assert.deepEqual(await page.getByRole('option').allInnerTexts(), ['Solid', 'Render', 'Grid'], 'a GLB has no edges to draw: Solid and Render only');
  await page.keyboard.press('Escape');
  assert.equal(await displayMenu.getByRole('heading', { name: 'Surfaces', exact: true }).count(), 1);
  for (const section of ['Edges', 'Cross-section', 'Explode']) assert.equal(await displayMenu.getByRole('heading', { name: section, exact: true }).count(), 0, section);
  await pane.getByRole('button', { name: 'Display settings', exact: true }).click();
  await pane.page().locator('[data-display-popover]').waitFor({ state: 'detached' });
  // The column closing reaches the scene as a resize; let that frame land before comparing pictures.
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy] > div > canvas').width >= 1190);
  await settle(page);

  // Solid <-> Render through the host's live surface.
  const solid = await capture(page);
  assert.equal((await page.evaluate(() => window.cadHarness.a.controller.setRenderMode(true))).renderMode, 'render');
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy="false"]'));
  assert.ok(differingPixels(solid, await capture(page)) > 5000, 'Render re-lights the model');
  assert.equal((await page.evaluate(() => window.cadHarness.a.controller.setRenderMode(false))).renderMode, 'inspect');
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy="false"]'));

  // Surfaces, on the native scene. Flat is unlit: each part is one colour, its own.
  const shaded = await capture(page);
  assert.ok(dominantColors(shaded).length >= 4, 'shaded faces differ');
  await display(page, { surfaces: { style: 'flat' } });
  const original = dominantColors(await capture(page));
  assert.equal(original.length, 2, `two parts, two flat colours: ${JSON.stringify(original)}`);
  assert.ok(original.some(([r, g, b]) => r > 150 && g < 90 && b < 90), `the authored red: ${JSON.stringify(original)}`);
  assert.ok(original.some(([r, g, b]) => b > 150 && r < 90 && g < 130), `the authored blue: ${JSON.stringify(original)}`);
  await display(page, { surfaces: { style: 'flat', colorMode: 'single', color: '#00c040' } });
  const single = dominantColors(await capture(page));
  assert.equal(single.length, 1, `one colour for every part: ${JSON.stringify(single)}`);
  assert.ok(single[0][1] > single[0][0] + 60 && single[0][1] > single[0][2] + 60, 'and it is the chosen green');
  await display(page, { surfaces: { style: 'flat', colorMode: 'by-part' } });
  const palette = dominantColors(await capture(page));
  assert.equal(palette.length, 2, `a palette colour per part: ${JSON.stringify(palette)}`);
  assert.notDeepEqual(palette.sort(), original.sort());
  await display(page, { surfaces: { style: 'flat', colorMode: 'single', color: '#00c040', opacity: 0.3 } });
  const faded = dominantColors(await capture(page));
  assert.ok(faded.length >= 1 && faded.every(color => JSON.stringify(color) !== JSON.stringify(single[0])), 'opacity lets the backdrop through');
  // Saved settings are edits, never rewritten: Original, Shaded and 100% bring the authored look back exactly.
  await display(page, { surfaces: { style: 'shaded', colorMode: 'original', opacity: 1 } });
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
  await page.waitForFunction(() => {
    const position = JSON.stringify(window.cadHarness.a.controller.readState().camera.position);
    const still = window.lastCameraPosition === position;
    window.lastCameraPosition = position;
    return still;
  }, null, { polling: 250 });

  // Host commands drive the mounted view, and one that makes no sense here fails loudly.
  const camera = await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    const current = controller.readState().camera;
    return (await controller.setCamera({ ...current, position: [90, -70, 60], target: [10, 5, 5], zoom: 1.3 })).camera;
  });
  assert.deepEqual(camera.position.map(Math.round), [90, -70, 60]);
  const state = await page.evaluate(() => window.cadHarness.a.controller.readState());
  assert.deepEqual([state.resource.path, state.revision, state.loading, state.selection], ['static.glb', 'one-static.glb', false, []]);
  const declined = await page.evaluate(() => window.cadHarness.a.controller.select({ selectors: ['o1.f1'] }).then(() => '', error => error.message));
  assert.match(declined, /A GLB has nothing to select/);
  assert.match(await page.evaluate(() => window.cadHarness.a.controller.clearSelection().then(() => '', error => error.message)), /no selection to clear/);

  // A secondary press is the camera's: no menu of the viewer's, and the browser's own stays off the canvas.
  await page.evaluate(() => {
    window.nativeMenu = [];
    document.addEventListener('contextmenu', event => window.nativeMenu.push(event.defaultPrevented));
  });
  await page.mouse.click(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2, { button: 'right' });
  await page.waitForTimeout(200);
  assert.equal(await page.getByRole('menu').count(), 0);
  assert.deepEqual(await page.evaluate(() => window.nativeMenu), [true]);

  // The navbar snapshot goes through the prompt port.
  await pane.getByRole('button', { name: 'Take snapshot', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  const captured = await page.evaluate(() => window.cadHarness.captures[0]);
  assert.deepEqual([captured.file, captured.type, captured.references.length], ['static.glb', 'image/png', 1]);
  assert.deepEqual(captured.references[0].target, { kind: 'whole-resource' });

  // Camera and Display settings belong to this file under this renderer's id, and survive a remount.
  await display(page, { surfaces: { colorMode: 'single', color: '#00c040' }, grid: { enabled: false } });
  await page.waitForFunction(() => window.cadHarness.state.renderers?.[JSON.stringify(['static.glb', 'glb'])]?.display?.surfaces?.colorMode === 'single');
  const stored = await page.evaluate(() => window.cadHarness.state.renderers);
  assert.deepEqual(Object.keys(stored), [JSON.stringify(['static.glb', 'glb'])], 'keyed by [path, renderer id]');
  const left = await page.evaluate(() => window.cadHarness.a.controller.readState());
  await page.evaluate(() => window.cadHarness.mounted(false));
  await pane.locator('canvas').first().waitFor({ state: 'detached' });
  await page.evaluate(() => window.cadHarness.mounted(true));
  await ready(pane);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  const reopened = await page.evaluate(() => window.cadHarness.a.controller.readState());
  assert.deepEqual(reopened.camera.position.map(value => Math.round(value * 100)), left.camera.position.map(value => Math.round(value * 100)), "reopening restores the camera the file was left at");
  assert.ok(Math.abs(reopened.camera.zoom - left.camera.zoom) < 1e-6);
  assert.deepEqual([reopened.display.surfaces.colorMode, reopened.display.surfaces.color, reopened.display.grid.enabled], ['single', '#00c040', false]);

  assert.deepEqual(errors, []);
});

test('an animated GLB opens at rest, plays in preview, and leaving preview puts it back at rest', async (t) => {
  const { open } = await serveHarness(t);
  // The file's Playback settings as a previous session left them: Orbit off, so the preview
  // camera holds still and what moves in a capture is the model alone.
  const { page, pane, errors } = await open('animated.glb', { record: { version: 1, settings: {},
    files: { [JSON.stringify(['one', 'animated.glb', 'glb'])]: { version: 2, playback: { orbit: false } } } } });
  await ready(pane);
  assert.equal(await pane.getByRole('toolbar', { name: 'Animation playback' }).count(), 0);
  assert.equal(await pane.getByRole('button', { name: 'Animate', exact: true }).count(), 0, 'no Animate tool');
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await settle(page);
  const toolsRest = await capture(page);

  await pane.getByRole('button', { name: 'Preview', exact: true }).click();
  await pane.getByRole('button', { name: 'Play animation', exact: true }).waitFor();
  await settle(page);
  const rest = await capture(page);
  // The playbar is simply there, and the file is at rest under it.
  assert.equal(await pane.getByRole('button', { name: 'Pause animation', exact: true }).count(), 0, 'it opens paused');
  assert.equal(Number(await pane.getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuenow')), 0);

  // Scrubbing away and back is the rest pose again.
  const time = pane.getByRole('slider', { name: 'Animation time' });
  await time.focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowLeft');
  assert.equal(differingPixels(rest, await capture(page)), 0, 'a clip scrubbed back to 0 is the rest pose');

  // Playing moves the model; pausing leaves it where it stopped.
  await pane.getByRole('button', { name: 'Play animation', exact: true }).click();
  await page.waitForFunction(() => Number(document.querySelector('[data-testid="one"] [role="slider"][aria-label="Animation time"]')?.getAttribute('aria-valuenow')) > 0.25);
  await pane.getByRole('button', { name: 'Pause animation', exact: true }).click();
  const moved = await capture(page);
  assert.ok(differingPixels(rest, moved) > 200, 'the rider moved');

  // Leaving preview puts the model back at rest, in the tools view's own camera.
  await pane.getByRole('button', { name: 'Exit preview', exact: true }).click();
  await pane.getByRole('button', { name: 'Preview', exact: true }).waitFor();
  await settle(page);
  assert.equal(differingPixels(toolsRest, await capture(page)), 0, 'the tools view is at rest again');

  // In Render the studio's floor is sized from the rest placement: a playing clip never resizes it.
  await page.evaluate(() => window.cadHarness.a.controller.setRenderMode(true));
  await page.waitForFunction(() => window.__cadStage()?.studioGround);
  await pane.getByRole('button', { name: 'Preview', exact: true }).click();
  await pane.getByRole('button', { name: 'Play animation', exact: true }).waitFor();
  await page.waitForFunction(() => window.__cadStage()?.studioGround);
  const floor = await page.evaluate(() => window.__cadStage().studioGround);
  await pane.getByRole('button', { name: 'Play animation', exact: true }).click();
  await page.waitForFunction(() => Number(document.querySelector('[data-testid="one"] [role="slider"][aria-label="Animation time"]')?.getAttribute('aria-valuenow')) > 0.25);
  await pane.getByRole('button', { name: 'Pause animation', exact: true }).click();
  assert.deepEqual(await page.evaluate(() => window.__cadStage().studioGround), floor);
  assert.deepEqual(errors, []);
});

test('a corrupt GLB raises the viewer\'s load alert, with reload and details', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane } = await open('broken.glb');
  const alert = pane.getByRole('alert');
  await alert.waitFor();
  assert.match(await alert.innerText(), /Couldn’t load the model/);
  assert.match(await alert.innerText(), /broken\.glb/);
  await noTools(pane);
  void page;
});
