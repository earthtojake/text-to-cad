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
import { strToU8, zipSync } from 'three/examples/jsm/libs/fflate.module.js';

// Inline fixtures, served from memory: an ASCII STL box, a 3MF package with two
// boxes of two base-material colours, a 3MF whose objects carry no colour, a well
// formed STL with no triangles, and bytes that are no STL at all.
const CORNERS = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]];
const TRIANGLES = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]];
const boxCorners = ([x, y, z], size) => CORNERS.map(corner => [x + corner[0] * size, y + corner[1] * size, z + corner[2] * size]);
function stlBox(origin, size) {
  const corners = boxCorners(origin, size);
  const facets = TRIANGLES.map(triangle => `facet normal 0 0 0\nouter loop\n${triangle.map(index => `vertex ${corners[index].join(' ')}`).join('\n')}\nendloop\nendfacet`);
  return `solid box\n${facets.join('\n')}\nendsolid box\n`;
}
function threeMf(objects) {
  const colored = objects.some(object => object.color);
  const model = `<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
 <resources>
  ${colored ? `<basematerials id="1">${objects.map((object, index) => `<base name="material-${index}" displaycolor="${object.color}FF"/>`).join('')}</basematerials>` : ''}
  ${objects.map((object, index) => `<object id="${index + 2}" name="${object.name}" type="model"${colored ? ` pid="1" pindex="${index}"` : ''}><mesh>
   <vertices>${boxCorners(object.origin, object.size).map(([x, y, z]) => `<vertex x="${x}" y="${y}" z="${z}"/>`).join('')}</vertices>
   <triangles>${TRIANGLES.map(([a, b, c]) => `<triangle v1="${a}" v2="${b}" v3="${c}"/>`).join('')}</triangles>
  </mesh></object>`).join('\n')}
 </resources>
 <build>${objects.map((_, index) => `<item objectid="${index + 2}"/>`).join('')}</build>
</model>`;
  return Buffer.from(zipSync({
    '[Content_Types].xml': strToU8('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'),
    '_rels/.rels': strToU8('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'),
    '3D/3dmodel.model': strToU8(model),
  }));
}
const FILES = {
  'part.stl': Buffer.from(stlBox([0, 0, 0], 20)),
  'pair.3mf': threeMf([{ name: 'base', origin: [0, 0, 0], size: 20, color: '#D02020' }, { name: 'rider', origin: [30, 0, 0], size: 10, color: '#2040D0' }]),
  'plain.3mf': threeMf([{ name: 'base', origin: [0, 0, 0], size: 20 }, { name: 'rider', origin: [30, 0, 0], size: 10 }]),
  // A binary STL that is well formed and holds no triangles: an 80 byte header and a zero count.
  'empty.stl': Buffer.alloc(84),
  'broken.stl': Buffer.from('solid this is prose and not a mesh\nfacet normal but never a vertex\n'),
};

async function serveHarness(t) {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-mesh-browser-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  const requests = [];
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    requests.push(url.pathname);
    const root = url.pathname.split('/')[1];
    const name = url.pathname.split('/').pop();
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: Object.entries(FILES).map(([file, data]) => (
        { kind: file.split('.').pop(), file, rootRelativeFile: file, url: `/${file}`, hash: `${root}-${file}`, bytes: data.length })) }));
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
    page.setDefaultTimeout(15000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      window.Worker = undefined;
      for (const name of ['localStorage', 'sessionStorage']) {
        Object.defineProperty(window, name, { get() { throw new Error(`Renderer accessed ${name}`); } });
      }
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/?file=${file}`);
    return { page, errors, pane: page.getByTestId('one') };
  };
  return { open, requests };
}

const ready = pane => pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
// A mesh has no tools at all, so this must stay empty wherever it is asked.
const noTools = async (pane) => {
  assert.equal(await pane.getByRole('group', { name: 'Interaction tools' }).count(), 0, 'a mesh viewport has no tool strip');
  for (const name of ['Orbit', 'Draw', 'Select', 'Measure', 'Pose', 'Animate']) {
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
const display = (page, patch) => page.evaluate(next => window.cadHarness.a.controller.setDisplaySettings(next), patch);
// Grid lines, axes and the stage floor are a share of the picture too; with them off,
// only the model's own colours are counted.
const GUIDES_OFF = { grid: { enabled: false }, axes: { enabled: false }, floor: { enabled: false } };
const isRed = ([r, g, b]) => r > 150 && g < 90 && b < 90;
const isBlue = ([r, g, b]) => b > 150 && r < 90 && g < 130;

test('an STL opens as one mesh with no tools: display settings, orbit, host commands and state all work', async (t) => {
  const { open, requests } = await serveHarness(t);
  const { page, pane, errors } = await open('part.stl');
  await ready(pane);
  assert.deepEqual(errors, []);

  // Nothing of a mesh picks, measures, poses, plays or is drawn on: the viewport
  // simply orbits, pans and zooms, with no strip over it.
  await noTools(pane);
  assert.equal(await pane.getByRole('button', { name: /Copy|Add to prompt/i }).count(), 0, 'no copy-references action');

  // The Inspector starts shut and holds the single Display tab, titled by the format.
  assert.equal(await pane.locator('[data-file-sheet-header]').count(), 0);
  await pane.getByRole('button', { name: 'Inspector', exact: true }).click();
  await pane.locator('[data-file-sheet="STL"]').waitFor();
  assert.deepEqual(await pane.getByRole('tab').evaluateAll(tabs => tabs.map(tab => [tab.textContent, tab.getAttribute('aria-selected')])), [['Display', 'true']]);
  assert.deepEqual(await pane.getByRole('combobox', { name: 'Mode', exact: true }).innerText(), 'Solid');
  // While a menu is open the rest of the page is hidden from the accessibility tree; wait for it to close.
  const options = async (label) => {
    await pane.getByRole('combobox', { name: label, exact: true }).click();
    const texts = await page.getByRole('option').allInnerTexts();
    await page.keyboard.press('Escape');
    await page.getByRole('listbox').waitFor({ state: 'detached' });
    return texts;
  };
  assert.deepEqual(await options('Mode'), ['Solid', 'Render'], 'a mesh has no edges to draw: Solid and Render only');
  assert.deepEqual(await options('Surface style'), ['Shaded', 'Flat']);
  assert.deepEqual(await options('Parts'), ['Original', 'Single color', 'Color by part']);
  for (const section of ['Edges', 'Clip', 'Explode']) assert.equal(await pane.getByRole('heading', { name: section, exact: true }).count(), 0, section);
  for (const section of ['Lighting', 'Background', 'Floor', 'Grid', 'Axes']) assert.equal(await pane.getByRole('heading', { name: section, exact: true }).count(), 1, section);
  assert.equal(await pane.getByRole('combobox', { name: 'Projection', exact: true }).count(), 1);
  assert.equal(await pane.getByRole('button', { name: 'Reset', exact: true }).count(), 1);
  await pane.getByRole('button', { name: 'Inspector', exact: true }).click();
  await pane.locator('[data-file-sheet="STL"]').waitFor({ state: 'detached' });
  // The column closing reaches the scene as a resize; let that frame land before comparing pictures.
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy] > div > canvas').width >= 1190);
  await settle(page);

  await display(page, GUIDES_OFF);
  // Solid <-> Render through the host's live surface.
  const solid = await capture(page);
  assert.equal((await page.evaluate(() => window.cadHarness.a.controller.setRenderMode(true))).renderMode, 'render');
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy="false"]'));
  assert.ok(differingPixels(solid, await capture(page)) > 5000, 'Render re-lights the model');
  assert.equal((await page.evaluate(() => window.cadHarness.a.controller.setRenderMode(false))).renderMode, 'inspect');
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy="false"]'));

  // Surfaces. An STL authors no colour, so Original is the viewer's surface colour; Flat is unlit, one colour.
  const shaded = await capture(page);
  assert.ok(dominantColors(shaded).length >= 3, 'shaded faces differ');
  await display(page, { surfaces: { style: 'flat' } });
  const original = dominantColors(await capture(page));
  assert.equal(original.length, 1, `one object, one flat colour: ${JSON.stringify(original)}`);
  assert.ok(Math.max(...original[0]) - Math.min(...original[0]) < 60, `the viewer's neutral surface colour: ${JSON.stringify(original)}`);
  await display(page, { surfaces: { style: 'flat', colorMode: 'single', color: '#00c040' } });
  const single = dominantColors(await capture(page));
  assert.equal(single.length, 1, `one colour: ${JSON.stringify(single)}`);
  assert.ok(single[0][1] > single[0][0] + 60 && single[0][1] > single[0][2] + 60, 'and it is the chosen green');
  await display(page, { surfaces: { style: 'flat', colorMode: 'by-part', colors: ['#c02080', '#00c040'] } });
  const palette = dominantColors(await capture(page));
  assert.equal(palette.length, 1, `one object takes the first palette colour: ${JSON.stringify(palette)}`);
  assert.ok(palette[0][0] > palette[0][1] + 60 && palette[0][2] > palette[0][1] + 40, `the first palette colour: ${JSON.stringify(palette)}`);
  await display(page, { surfaces: { style: 'flat', colorMode: 'original', opacity: 0.3 } });
  const faded = dominantColors(await capture(page));
  assert.ok(faded.length >= 1 && faded.every(color => JSON.stringify(color) !== JSON.stringify(original[0])), 'opacity lets the backdrop through');
  // Saved settings are edits, never rewritten: Original, Shaded and 100% bring the first look back exactly.
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

  // A secondary press on the canvas is the camera's: the viewer opens no menu of
  // its own, and the browser's own stays off the canvas.
  await page.evaluate(() => {
    window.nativeMenu = [];
    document.addEventListener('contextmenu', event => window.nativeMenu.push(event.defaultPrevented));
  });
  await page.mouse.click(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2, { button: 'right' });
  await page.waitForTimeout(200);
  assert.equal(await page.getByRole('menu').count(), 0);
  assert.deepEqual(await page.evaluate(() => window.nativeMenu), [true], 'the native menu is still prevented');

  // Host commands drive the mounted view, and one that makes no sense here fails loudly.
  const camera = await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    const current = controller.readState().camera;
    return (await controller.setCamera({ ...current, position: [90, -70, 60], target: [10, 5, 5], zoom: 1.3 })).camera;
  });
  assert.deepEqual(camera.position.map(Math.round), [90, -70, 60]);
  const state = await page.evaluate(() => window.cadHarness.a.controller.readState());
  assert.deepEqual([state.resource.path, state.revision, state.loading, state.selection], ['part.stl', 'one-part.stl', false, []]);
  const declined = await page.evaluate(() => window.cadHarness.a.controller.select({ selectors: ['o1.f1'] }).then(() => '', error => error.message));
  assert.match(declined, /A mesh file has nothing to select/);
  assert.match(await page.evaluate(() => window.cadHarness.a.controller.clearSelection().then(() => '', error => error.message)), /no selection to clear/);
  // A host's request to select a reference is consumed and answered in words.
  await page.evaluate(() => window.cadHarness.selectReference('o1.f1'));
  await pane.getByText(/A mesh file has nothing to select/).waitFor();
  assert.equal(await page.evaluate(() => window.cadHarness.a.commands.getSnapshot().selectReference ?? null), null, 'the declined request is acknowledged');

  // The navbar snapshot and a host's capture request go through the same prompt port.
  await pane.getByRole('button', { name: 'Take snapshot', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  const captured = await page.evaluate(() => window.cadHarness.captures[0]);
  assert.deepEqual([captured.file, captured.type, captured.references.length], ['part.stl', 'image/png', 1]);
  assert.deepEqual(captured.references[0].target, { kind: 'whole-resource' });
  await page.evaluate(() => window.cadHarness.capture());
  await page.waitForFunction(() => window.cadHarness.captures.length === 2);

  // Camera and Display settings belong to this file under this renderer's id, and survive a remount.
  await display(page, { surfaces: { colorMode: 'single', color: '#00c040' }, grid: { enabled: true }, floor: { enabled: true } });
  await page.waitForFunction(() => window.cadHarness.state.renderers?.[JSON.stringify(['part.stl', 'mesh'])]?.display?.surfaces?.colorMode === 'single');
  const stored = await page.evaluate(() => window.cadHarness.state.renderers);
  assert.deepEqual(Object.keys(stored), [JSON.stringify(['part.stl', 'mesh'])], 'keyed by [path, renderer id]');
  const left = await page.evaluate(() => window.cadHarness.a.controller.readState());
  await page.waitForFunction(position => JSON.stringify(window.cadHarness.state.renderers[JSON.stringify(['part.stl', 'mesh'])].camera?.position.map(Math.round)) === position, JSON.stringify(left.camera.position.map(Math.round)));
  await page.evaluate(() => window.cadHarness.mounted(false));
  await pane.locator('canvas').first().waitFor({ state: 'detached' });
  await page.evaluate(() => window.cadHarness.mounted(true));
  await ready(pane);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  const reopened = await page.evaluate(() => window.cadHarness.a.controller.readState());
  assert.deepEqual(reopened.camera.position.map(value => Math.round(value * 100)), left.camera.position.map(value => Math.round(value * 100)));
  assert.equal(reopened.camera.zoom, left.camera.zoom);
  assert.deepEqual([reopened.display.surfaces.colorMode, reopened.display.surfaces.color, reopened.display.grid.enabled, reopened.display.floor.enabled], ['single', '#00c040', true, true]);
  assert.equal(requests.filter(path => path === '/one/part.stl').length, 1, 'reopening a file reuses its decoded mesh without another asset request');

  // Fullscreen: no Inspector toggle, orbit settings only (a mesh has nothing to play).
  await page.evaluate(() => window.cadHarness.fullscreen(true));
  await pane.getByRole('group', { name: 'Fullscreen controls' }).waitFor();
  assert.equal(await pane.getByRole('button', { name: 'Orbit settings', exact: true }).count(), 1);
  assert.equal(await pane.locator('[data-animation-transport]').count(), 0);
  await page.evaluate(() => window.cadHarness.fullscreen(false));
  await pane.getByRole('button', { name: 'Inspector', exact: true }).waitFor();
  await noTools(pane);
  assert.deepEqual(errors, []);
});

test('a 3MF is one mesh per object with its source colour; an uncoloured one takes the viewer\'s', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('pair.3mf');
  await ready(pane);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await noTools(pane);
  await pane.getByRole('button', { name: 'Inspector', exact: true }).click();
  await pane.locator('[data-file-sheet="3MF"]').waitFor();
  await pane.getByRole('button', { name: 'Inspector', exact: true }).click();
  await pane.locator('[data-file-sheet="3MF"]').waitFor({ state: 'detached' });
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy] > div > canvas').width >= 1190);
  await settle(page);

  await display(page, GUIDES_OFF);
  // Original: both authored colours, each on its own object. Flat shows them unlit, so exactly two.
  const shaded = await capture(page);
  assert.ok(dominantColors(shaded).some(isRed) && dominantColors(shaded).some(isBlue), `both colours, lit: ${JSON.stringify(dominantColors(shaded))}`);
  await display(page, { surfaces: { style: 'flat' } });
  const original = dominantColors(await capture(page));
  assert.equal(original.length, 2, `two objects, two flat colours: ${JSON.stringify(original)}`);
  assert.ok(original.some(isRed) && original.some(isBlue), JSON.stringify(original));
  // Color by part deals one palette colour per object; Single colour is one for both.
  await display(page, { surfaces: { style: 'flat', colorMode: 'by-part', colors: ['#c02080', '#00c040'] } });
  const palette = dominantColors(await capture(page));
  assert.equal(palette.length, 2, JSON.stringify(palette));
  assert.ok(!palette.some(isRed) && !palette.some(isBlue), `the palette replaces the source colours: ${JSON.stringify(palette)}`);
  await display(page, { surfaces: { style: 'flat', colorMode: 'single', color: '#00c040' } });
  assert.equal(dominantColors(await capture(page)).length, 1);
  await display(page, { surfaces: { style: 'shaded', colorMode: 'original' } });
  assert.equal(differingPixels(shaded, await capture(page)), 0, 'the look is fully reversible');
  // Render keeps the colours and re-lights them.
  await page.evaluate(() => window.cadHarness.a.controller.setRenderMode(true));
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy="false"]'));
  const rendered = await capture(page);
  assert.ok(differingPixels(shaded, rendered) > 5000);
  assert.ok(dominantColors(rendered, { minShare: 0.002 }).some(([r, g, b]) => r > g + 60 && r > b + 60), 'the red object is still red under the studio');
  assert.deepEqual(errors, []);

  // No colour in the file: every object is the viewer's surface colour, the one an STL gets.
  const plain = await open('plain.3mf');
  await ready(plain.pane);
  await plain.page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await display(plain.page, { ...GUIDES_OFF, surfaces: { style: 'flat' } });
  const neutral = dominantColors(await capture(plain.page));
  assert.equal(neutral.length, 1, JSON.stringify(neutral));
  assert.ok(Math.max(...neutral[0]) - Math.min(...neutral[0]) < 60, JSON.stringify(neutral));
  assert.deepEqual(plain.errors, []);
});

test('a corrupt mesh raises the viewer\'s load alert and an empty one says there is no geometry', async (t) => {
  const { open } = await serveHarness(t);
  const broken = await open('broken.stl');
  const alert = broken.pane.getByRole('alert');
  await alert.waitFor();
  assert.match(await alert.innerText(), /Couldn’t load the model/);
  assert.match(await alert.innerText(), /broken\.stl/);
  await noTools(broken.pane);
  assert.equal(await alert.getByRole('button', { name: 'Try again', exact: true }).count(), 1);
  assert.equal(await alert.getByText('Details', { exact: true }).count(), 1);

  const empty = await open('empty.stl');
  await empty.pane.getByRole('alert').waitFor();
  assert.match(await empty.pane.getByRole('alert').innerText(), /No geometry to display/);
  assert.match(await empty.pane.getByRole('alert').innerText(), /empty\.stl/);
});
