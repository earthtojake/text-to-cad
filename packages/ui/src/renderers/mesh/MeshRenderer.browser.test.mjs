import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { harnessBundle } from '../harness/bundle.mjs';
import { pressInPreview } from '../harness/preview.mjs';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import { strToU8, zipSync } from 'three/examples/jsm/libs/fflate.module.js';

// Inline fixtures, served from memory: an ASCII STL box (its solid named), a binary STL of one box and one of two
// bodies (a box, then a smaller tetrahedron before it in the file), a 3MF package with two boxes of two base-material
// colours, a 3MF whose objects carry no colour, a 3MF of one object, a well formed STL with no triangles, bytes
// that are no STL at all, and a slicer's print file (a 3MF of G-code and an empty build).
const CORNERS = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]];
const TRIANGLES = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]];
const boxCorners = ([x, y, z], size) => CORNERS.map(corner => [x + corner[0] * size, y + corner[1] * size, z + corner[2] * size]);
function stlBox(origin, size) {
  const corners = boxCorners(origin, size);
  const facets = TRIANGLES.map(triangle => `facet normal 0 0 0\nouter loop\n${triangle.map(index => `vertex ${corners[index].join(' ')}`).join('\n')}\nendloop\nendfacet`);
  return `solid box\n${facets.join('\n')}\nendsolid box\n`;
}
// A binary STL of these triangles (each three corners), its facets' normals left at zero.
function binaryStl(triangles) {
  const bytes = Buffer.alloc(84 + triangles.length * 50);
  bytes.writeUInt32LE(triangles.length, 80);
  triangles.forEach((triangle, index) => triangle.flat().forEach((value, at) => bytes.writeFloatLE(value, 84 + index * 50 + 12 + at * 4)));
  return bytes;
}
const boxFacets = (origin, size) => { const corners = boxCorners(origin, size); return TRIANGLES.map(triangle => triangle.map(index => corners[index])); };
const tetraFacets = ([x, y, z], size) => [[[0, 0, 0], [0, 1, 0], [1, 0, 0]], [[0, 0, 0], [1, 0, 0], [0, 0, 1]], [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [[0, 0, 0], [0, 0, 1], [0, 1, 0]]]
  .map(triangle => triangle.map(([a, b, c]) => [x + a * size, y + b * size, z + c * size]));
function threeMf(objects, entries = {}) {
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
    ...entries,
  }));
}
const FILES = {
  'part.stl': Buffer.from(stlBox([0, 0, 0], 20)),
  'pair.3mf': threeMf([{ name: 'base', origin: [0, 0, 0], size: 20, color: '#D02020' }, { name: 'rider', origin: [30, 0, 0], size: 10, color: '#2040D0' }]),
  'plain.3mf': threeMf([{ name: 'base', origin: [0, 0, 0], size: 20 }, { name: 'rider', origin: [30, 0, 0], size: 10 }]),
  'single.3mf': threeMf([{ name: 'bracket', origin: [0, 0, 0], size: 20 }]),
  'cube.stl': binaryStl(boxFacets([0, 0, 0], 20)),
  'bodies.stl': binaryStl([...tetraFacets([30, 0, 0], 10), ...boxFacets([0, 0, 0], 20)]),
  // A binary STL that is well formed and holds no triangles: an 80 byte header and a zero count.
  'empty.stl': Buffer.alloc(84),
  'broken.stl': Buffer.from('solid this is prose and not a mesh\nfacet normal but never a vertex\n'),
  'plate.gcode.3mf': threeMf([], { 'Metadata/plate_1.gcode': strToU8('G28\nG1 X10 Y10 E1.2 F1500\n') }),
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
const requests = [];
before(async () => {
  const { bundle } = await harnessBundle();
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    requests.push(url.pathname);
    const root = url.pathname.split('/')[1];
    const name = url.pathname.split('/').pop();
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/api/v1/documents') && request.method === 'GET') {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ documents: (Object.entries(FILES).map(([file, data]) => (
        { kind: file.split('.').pop(), file: `/models/${file}`, url: `/${file}`, hash: `${root}-${file}`, bytes: data.length }))).map(entry => ({ entry, revision: entry.hash })) }));
    } else if (url.pathname.endsWith('/api/v1/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ backend: 'cadgen' }));
    } else if (FILES[name]) {
      response.setHeader('Content-Type', 'application/octet-stream');
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

// `width`: the view's. `clock`: the page's timers Playwright's, to run forward (`page.clock`).
async function open(t, file, { width = 800, clock = false } = {}) {
  const page = await browser.newPage({ viewport: { width, height: 500 }, deviceScaleFactor: 1 });
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
// A mesh file's strip: an STL's Select (in hand, picking its bodies), Draw and Clip; a 3MF's Select (in hand),
// Draw, Measure and Clip. Clip is a tool as Draw is, pressed while in hand. View and Preview are the navbar's; the
// corner holds the cube alone.
const STL_TOOLS = ['Select:true', 'Draw:false', 'Clip:false'];
const THREE_MF_TOOLS = ['Select:true', 'Draw:false', 'Measure:false', 'Clip:false'];
const meshTools = async (pane, expected) => {
  assert.deepEqual(await pane.getByRole('group', { name: 'Interaction tools' }).getByRole('button')
    .evaluateAll(buttons => buttons.filter(button => button.hasAttribute('aria-pressed') && !button.closest('[data-view-controls]')).map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
  expected);
  const strip = pane.getByRole('group', { name: 'Interaction tools' });
  // The strip is the tools alone, Clip last, no rule; the view's settings are the navbar's, Display left of Preview, and
  // the corner is the cube alone.
  assert.equal(await strip.locator('[data-view-controls]').count(), 0, 'nothing of the view on the strip');
  assert.equal(await strip.locator('[data-strip-rule]').count(), 0, 'no rule');
  assert.deepEqual(await pane.locator('[data-viewer-navbar] [data-navbar-view-controls] button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label').split(':')[0])),
    ['Display', 'Preview'], 'the navbar\'s: Display, then Preview');
  assert.equal(await pane.locator('[data-view-corner] *').count(), 0, 'nothing beside the cube in its corner');
  // Nothing else of the view on screen.
  for (const name of ['Orbit', 'Pencil', 'Shapes', 'Explode', 'Joints', 'Animation']) assert.equal(await pane.getByRole('button', { name, exact: true }).count(), 0, name);
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
// Render is Preview's: in by Preview at the strip's end and out by Exit preview in Preview's bar, each once the view has
// come together under its cover.
async function togglePreview(page, pane, enter) {
  const press = pane.getByRole('button', { name: enter ? 'Preview' : 'Exit preview', exact: true });
  if (enter) await press.click(); else await pressInPreview(page, pane, press);
  await pane.getByRole('button', { name: enter ? 'Exit preview' : 'Preview', exact: true }).waitFor();
  await page.waitForFunction(() => !document.querySelector('[data-testid="one"] [data-preview-cover]')
    && document.querySelector('[data-testid="one"] [aria-busy="false"]'));
}
const display = (page, patch) => page.evaluate(next => window.cadHarness.a.controller.setDisplaySettings(next), patch);
// Grid lines are a share of the picture too; with the grid off (as a file opens), only the
// model's own colours are counted.
const GUIDES_OFF = { grid: false };
// A colour with no hue to speak of: the viewer's neutral surface, lit or not, or the backdrop.
const isNeutral = color => Math.max(...color) - Math.min(...color) < 60;
const isRed = ([r, g, b]) => r > 150 && g < 90 && b < 90;
const isBlue = ([r, g, b]) => b > 150 && r < 90 && g < 130;

test('an STL opens in Select, its one body the file: display settings, orbit, host commands and state all work', async (t) => {
  const requested = requests.length;
  const { page, pane, errors } = await open(t, 'part.stl');
  await ready(pane);
  assert.deepEqual(errors, []);
  await exported(page, 'part.stl');

  // An STL is in no unit: Select picks its bodies, nothing to measure; it is drawn on and cut.
  await meshTools(pane, STL_TOOLS);
  assert.deepEqual([await pane.locator('[data-quick-edit-box]').count(), await pane.locator('[data-quick-edit-context]').count()], [1, 0], 'Quick Edit is there, one row: nothing attached until a mark');
  assert.equal(await pane.locator('[data-navbar-view-controls]').getByRole('button', { name: 'Preview', exact: true }).count(), 1,
    'an STL is 3D: Preview is the navbar\'s, after Display');

  // One mesh: Solid alone (Shaded would be Solid again, and Parts has one part to colour), then the Grid switch and
  // the Background, in every view, and no settings a mode would bring.
  assert.deepEqual(await displayMenu(pane), { modes: ['solid'], grid: true, backgrounds: ['light', 'dark'] });
  assert.equal(await pane.locator('[data-cad-tool-stack] [data-tool-panel]').count(), 0, 'nothing joins the tool stack');
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy] > div > canvas').width >= 790);
  await settle(page);

  // Preview draws the model in Render, on the studio's floor; leaving it takes the studio down.
  await togglePreview(page, pane, true);
  await page.waitForFunction(() => window.__cadStage()?.studioGround);
  await togglePreview(page, pane, false);
  await page.waitForFunction(() => !window.__cadStage()?.studioGround);
  await display(page, GUIDES_OFF);

  // Surfaces. An STL authors no colour, so Solid is the viewer's neutral surface colour, shaded.
  const shaded = await capture(page);
  assert.ok(dominantColors(shaded).length >= 3, 'shaded faces differ');
  assert.ok(dominantColors(shaded).every(isNeutral), `the viewer's neutral surface colour: ${JSON.stringify(dominantColors(shaded))}`);
  // The grid, switched on, draws under the model; switched off, the look is as it was.
  await display(page, { grid: true });
  assert.ok(differingPixels(shaded, await capture(page)) > 0, 'the grid draws');
  await display(page, { grid: false });
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

  // A secondary tap on the model opens the view's menu, its body's reference and Select, then the framing, and the
  // browser's own stays off the canvas.
  await page.evaluate(() => {
    window.nativeMenu = [];
    document.addEventListener('contextmenu', event => window.nativeMenu.push(event.defaultPrevented));
  });
  await page.mouse.click(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2, { button: 'right' });
  // The press has reached the page, and a menu it opened would be up two frames on.
  await page.waitForFunction(() => window.nativeMenu.length > 0);
  await settle(page);
  assert.deepEqual(await page.getByRole('menuitem').allTextContents(), ['Copy Reference', 'Select', 'Zoom to fit', 'Zoom to selection']);
  assert.deepEqual(await page.evaluate(() => window.nativeMenu), [true], 'the native menu is still prevented');
  await page.keyboard.press('Escape');
  await page.getByRole('menu').waitFor({ state: 'detached' });

  // Host commands drive the mounted view, and one that makes no sense here fails loudly.
  const camera = await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    const current = controller.readState().camera;
    return (await controller.setCamera({ ...current, position: [90, -70, 60], target: [10, 5, 5], zoom: 1.3 })).camera;
  });
  assert.deepEqual(camera.position.map(Math.round), [90, -70, 60]);
  const state = await page.evaluate(() => window.cadHarness.a.controller.readState());
  assert.deepEqual([state.resource.path, state.revision, state.loading, state.selection], ['/models/part.stl', 'one-part.stl', false, []]);
  const declined = await page.evaluate(() => window.cadHarness.a.controller.select({ selectors: ['f:part.make_box1.1'] }).then(() => '', error => error.message));
  assert.match(declined, /A mesh file's objects and bodies are picked by a person in the viewport under Select/);
  assert.equal(await page.evaluate(() => window.cadHarness.a.controller.clearSelection().then(() => '', error => error.message)), '', 'a selection clears, an empty one too');
  // A host's request to select a reference is consumed without a notification.
  await page.evaluate(() => window.cadHarness.selectReference('f:part.make_box1.1'));
  await page.waitForFunction(() => !window.cadHarness.a.commands.getSnapshot().selectReference);
  assert.equal(await page.evaluate(() => window.cadHarness.a.commands.getSnapshot().selectReference ?? null), null, 'the declined request is acknowledged');

  // A host's capture request goes through the prompt port: the view, of the whole file.
  await page.evaluate(() => window.cadHarness.capture());
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  const captured = await page.evaluate(() => window.cadHarness.captures[0]);
  assert.deepEqual([captured.file, captured.type, captured.references.length], ['/models/part.stl', 'image/png', 1]);
  assert.deepEqual(captured.references[0].target, { kind: 'whole-resource' });

  // Camera and Display settings belong to this file under this renderer's id, and survive a remount.
  await display(page, { grid: true });
  await page.waitForFunction(() => window.cadHarness.state.renderers?.[JSON.stringify(['/models/part.stl', 'mesh'])]?.display?.grid === true);
  const stored = await page.evaluate(() => window.cadHarness.state.renderers);
  assert.deepEqual(Object.keys(stored), [JSON.stringify(['/models/part.stl', 'mesh'])], 'keyed by [absolute path, renderer id]');
  const left = await page.evaluate(() => window.cadHarness.a.controller.readState());
  await page.evaluate(() => window.cadHarness.mounted(false));
  await pane.locator('canvas').first().waitFor({ state: 'detached' });
  await page.evaluate(() => window.cadHarness.mounted(true));
  await ready(pane);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  const reopened = await page.evaluate(() => window.cadHarness.a.controller.readState());
  // Within a thousandth: the camera read when leaving can still be coasting its last hundredth.
  assert.ok(reopened.camera.position.every((value, axis) => Math.abs(value - left.camera.position[axis]) <= 1e-3 * Math.max(1, Math.abs(left.camera.position[axis]))),
    "reopening restores the camera the file was left at");
  assert.ok(Math.abs(reopened.camera.zoom - left.camera.zoom) < 1e-6);
  assert.deepEqual([reopened.display.mode, reopened.display.grid], ['solid', true]);
  assert.equal(requests.slice(requested).filter(path => path === '/one/part.stl').length, 1, 'reopening a file reuses its decoded mesh without another asset request');

  assert.deepEqual(errors, []);
});

test('a 3MF is one mesh per object with its source colour; an uncoloured one takes the viewer\'s', async (t) => {
  const { page, pane, errors } = await open(t, 'pair.3mf');
  await ready(pane);
  await exported(page, 'pair.3mf');
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await meshTools(pane, THREE_MF_TOOLS);
  // Display shut as it opens, the same dropdown an STL has, with Parts: a 3MF of two objects has two to colour.
  assert.deepEqual(await displayModes(pane), ['solid', 'parts']);
  // The panel put away from its navbar toggle, so the picture has the whole view (an open panel pushes it aside).
  const opened = pane.locator(`[data-navbar-panel][aria-expanded="true"]`);
  while (await opened.count()) await opened.first().click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-busy] > div > canvas').width >= 790);
  await settle(page);

  await display(page, GUIDES_OFF);
  // Solid: both authored colours, each on its own object.
  const shaded = await capture(page);
  assert.ok(dominantColors(shaded).some(isRed) && dominantColors(shaded).some(isBlue), `both colours, lit: ${JSON.stringify(dominantColors(shaded))}`);
  // Parts deals one palette colour per object, in place of the source colours.
  await display(page, { mode: 'parts' });
  const palette = dominantColors(await capture(page));
  assert.ok(!palette.some(isRed) && !palette.some(isBlue), `the palette replaces the source colours: ${JSON.stringify(palette)}`);
  assert.ok(differingPixels(shaded, await capture(page)) > 0, 'Parts recolours the objects');
  await display(page, { mode: 'solid' });
  assert.equal(differingPixels(shaded, await capture(page)), 0, 'the look is fully reversible');
  // Preview's Render keeps the colours and re-lights them.
  await togglePreview(page, pane, true);
  const rendered = await capture(page);
  assert.ok(dominantColors(rendered, { minShare: 0.002 }).some(([r, g, b]) => r > g + 60 && r > b + 60), 'the red object is still red under the studio');
  assert.deepEqual(errors, []);

  // No colour in the file: every object is the viewer's surface colour, the one an STL gets.
  const plain = await open(t, 'plain.3mf');
  await ready(plain.pane);
  await plain.page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await display(plain.page, GUIDES_OFF);
  const neutral = dominantColors(await capture(plain.page));
  assert.ok(neutral.length >= 1 && neutral.every(isNeutral), JSON.stringify(neutral));
  assert.deepEqual(plain.errors, []);
});

test('a 3MF\'s tools: Select picks an object by its place in the build, Measure reads its declared millimetres approximately, and Clip cuts it as it cuts an STL', async (t) => {
  const { page, pane, errors } = await open(t, 'pair.3mf');
  await ready(pane);
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await display(page, GUIDES_OFF);
  await settle(page);
  const box = await pane.locator('[data-cad-surface] canvas').first().boundingBox();
  const at = projector(await page.evaluate(() => window.__cadCamera()), box);
  const chips = () => pane.locator('[data-quick-edit-refs] [data-quick-edit-ref] > button:first-child')
    .evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label')));
  // The base: the first build item, a 20 mm cube at the origin.
  await page.mouse.click(...at([10, 10, 20]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedObjects?.join() === 'o1');
  assert.deepEqual(await chips(), ['base'], 'the object, by its name: pair.3mf#o1');

  await pane.getByRole('button', { name: 'Measure', exact: true }).click();
  assert.equal(await pane.locator('[data-measurements]').count(), 0, 'no row under the strip until something is measured');
  for (const corner of [[2, 10, 20], [18, 10, 20]]) { await page.mouse.click(...at(corner)); await settle(page); }
  // Its chip is Measure's row's, under the strip; Quick Edit carries the pick alone.
  const measured = pane.locator('[data-measurements] [data-quick-edit-ref]');
  await measured.waitFor();
  assert.deepEqual(await measured.locator('> button:first-child').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    ['Measurement 1: ≈ 16.0 mm (approximate)']);
  assert.deepEqual(await pane.locator('[data-quick-edit-box] [data-quick-edit-ref]').count(), 1);

  await display(page, { clip: { enabled: true, axis: 'x' } });
  await page.waitForFunction(() => window.__cadStage().cut === 1);
  const stl = await open(t, 'part.stl');
  await ready(stl.pane);
  await display(stl.page, { clip: { enabled: true, axis: 'z' } });
  await stl.page.waitForFunction(() => window.__cadStage().cut === 1);
  assert.deepEqual([...errors, ...stl.errors], []);
});

// The view's panel: its Model tab, its rows (`[data-scene-node]`), and the navbar's toggle, which says whether it is open.
const modelRows = pane => pane.locator('aside[data-flat-panel] [data-scene-node]');
const panelOpen = pane => pane.locator('[data-viewer-navbar] [data-navbar-panel]').getAttribute('aria-expanded');

// While the file loads, a structure tab with no row shows the panel's placeholder rows, its tabpanel busy.
const loadingRows = scope => scope.locator('aside[data-flat-panel] [role="tabpanel"][aria-busy="true"] [data-tree-row-placeholder]');

test('every mesh file has its Model tab from the first frame, open as it stays once the file is in, a row for its one object or body', async (t) => {
  // Wide enough that the panel starts open beside the model (it keeps 640px).
  for (const [file, rows] of [['cube.stl', ['cube.stl']], ['part.stl', ['box']], ['single.3mf', ['bracket']]]) {
    const release = hold(file);
    const { page, pane, errors } = await open(t, file, { width: 1000, clock: true });
    await pane.locator('aside[data-flat-panel] [data-flat-panel-heading]').filter({ hasText: 'Model' }).waitFor();
    const first = await panelOpen(pane);
    // Past the update status's delay: a first load is the loading cover's to say, never "Updating view…".
    await page.clock.runFor(1000);
    assert.deepEqual([first, await pane.locator('[aria-busy="true"]').count() > 0, await modelRows(pane).count(), await loadingRows(pane).count(),
      await pane.locator('[data-view-update-status]').count()], ['true', true, 0, 6, 0], `${file}: open, the file still loading, its placeholder rows, no update status`);
    release();
    await ready(pane);
    await modelRows(pane).first().waitFor();
    assert.deepEqual([await modelRows(pane).allInnerTexts(), await loadingRows(pane).count()], [rows, 0], `${file}: one row, named for the file, its solid or its object, in the placeholders' place`);
    assert.equal(await panelOpen(pane), first, `${file}: the panel as it was at the first frame`);
    assert.deepEqual(errors, []);
  }
});

test('an STL of several bodies lists them largest first once split, and Select picks the body under the pointer', async (t) => {
  const { page, pane, errors } = await open(t, 'bodies.stl', { width: 1000 });
  await ready(pane);
  // The model shows as one body first; its bodies follow, the box (12 triangles) before the tetrahedron (4).
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] aside[data-flat-panel] [data-scene-node]').length === 2);
  assert.deepEqual(await modelRows(pane).allInnerTexts(), ['Body 1', 'Body 2']);
  await display(page, GUIDES_OFF);
  await settle(page);
  const at = projector(await page.evaluate(() => window.__cadCamera()), await pane.locator('[data-cad-surface] canvas').first().boundingBox());
  await page.mouse.click(...at([10, 10, 20]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedObjects?.join() === 'b1');
  // The middle of the tetrahedron's slanted face.
  await page.mouse.click(...at([10 / 3 + 30, 10 / 3, 10 / 3]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedObjects?.join() === 'b2');
  assert.equal(await modelRows(pane).nth(1).locator('button[aria-pressed]').getAttribute('aria-pressed'), 'true', 'its row lit');
  assert.deepEqual(errors, []);
});

test('a corrupt mesh raises the viewer\'s load alert, an empty one says there is no geometry and a print file says what it is', async (t) => {
  const broken = await open(t, 'broken.stl');
  const alert = broken.pane.getByRole('alert');
  await alert.waitFor();
  assert.match(await alert.innerText(), /Couldn’t load the model/);
  assert.match(await alert.innerText(), /broken\.stl/);
  // Nothing on screen is the file's to work on: the card alone, with no tools or view actions.
  for (const name of ['Display', 'Preview']) {
    assert.equal(await broken.pane.getByRole('button', { name, exact: true }).count(), 0, `no ${name} over a failed load`);
  }
  assert.equal(await alert.getByRole('button', { name: 'Retry', exact: true }).count(), 1);
  assert.equal(await alert.getByText('Details', { exact: true }).count(), 1);

  const empty = await open(t, 'empty.stl');
  await empty.pane.getByRole('alert').waitFor();
  assert.match(await empty.pane.getByRole('alert').innerText(), /No geometry to display/);
  assert.match(await empty.pane.getByRole('alert').innerText(), /empty\.stl/);

  // A slicer's print file is no broken model: it says what it is, with nothing to retry.
  const sliced = await open(t, 'plate.gcode.3mf');
  await sliced.pane.getByRole('alert').waitFor();
  assert.match(await sliced.pane.getByRole('alert').innerText(), /A print file, not a model[\s\S]*plate\.gcode\.3mf[\s\S]*G-code/);
  assert.equal(await sliced.pane.getByRole('alert').getByRole('button', { name: 'Retry', exact: true }).count(), 0);
});
