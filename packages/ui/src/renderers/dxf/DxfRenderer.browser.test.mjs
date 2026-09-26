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

// The drawing under test is a COMMITTED payload: exactly what
// `GET /__cad/drawing` answered for `__fixtures__/sample.dxf`, so this test
// needs neither Python nor ezdxf and cannot drift from the route by accident.
// `__fixtures__/README.md` says how to regenerate the pair.
const SAMPLE = JSON.parse(await readFile(new URL('./__fixtures__/sample.drawing.json', import.meta.url), 'utf8'));
// A drawing whose modelspace is empty: `bounds: null`, and nothing to frame.
const EMPTY = { schemaVersion: 1, units: SAMPLE.units, bounds: null, layers: [], primitives: [] };
const BAD_DXF_MESSAGE = 'plate.dxf is not a readable DXF document: run `ezdxf audit` on it, or export it again.';

// The fixture's own measurements, so an assertion can say WHICH edge it is reading.
const MODEL = { width: 100, height: 60 };
const DRAWINGS = { 'sample.dxf': SAMPLE, 'empty.dxf': EMPTY };

async function serveHarness(t) {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-dxf-browser-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  const files = ['sample.dxf', 'empty.dxf', 'broken.dxf'];
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/__cad/drawing')) {
      const drawing = DRAWINGS[url.searchParams.get('file')];
      response.setHeader('Content-Type', 'application/json');
      if (!drawing) { response.statusCode = 400; response.end(JSON.stringify({ error: BAD_DXF_MESSAGE })); return; }
      response.end(JSON.stringify(drawing));
    } else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: files.map(file => (
        { kind: 'dxf', file, rootRelativeFile: file, url: `/${file}`, hash: `${root}-${file}`, bytes: 4096 })) }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true });
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

const canvasOf = pane => pane.locator('[data-drawing-surface] canvas').first();
const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
const drawn = async (pane) => {
  await canvasOf(pane).waitFor();
  await pane.locator('[aria-busy="false"]').first().waitFor();
  await settle(pane.page());
};
/** The frame ON SCREEN, not a re-render: what the person is actually looking at. */
async function frame(pane) {
  await settle(pane.page());
  return PNG.sync.read(await canvasOf(pane).screenshot());
}
const pixel = (image, x, y) => {
  const offset = (Math.round(y) * image.width + Math.round(x)) * 4;
  return [image.data[offset], image.data[offset + 1], image.data[offset + 2]];
};
const near = (left, right, tolerance = 12) =>
  Math.abs(left[0] - right[0]) + Math.abs(left[1] - right[1]) + Math.abs(left[2] - right[2]) <= tolerance;
/** The box around everything that is not the pane's own background. */
function inkBox(image) {
  const backdrop = pixel(image, 0, 0);
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, painted = 0;
  for (let y = 0; y < image.height; y += 1) {
    for (let x = 0; x < image.width; x += 1) {
      if (near(pixel(image, x, y), backdrop)) continue;
      painted += 1;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  assert.ok(painted > 0, 'nothing was drawn on this canvas');
  return { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY, painted,
    centreX: (minX + maxX) / 2, centreY: (minY + maxY) / 2, backdrop };
}
/** Contiguous runs of ink down one column: how thick the strokes crossing it are. */
function columnRuns(image, x) {
  const backdrop = pixel(image, 0, 0);
  const runs = [];
  let start = -1;
  for (let y = 0; y < image.height; y += 1) {
    const ink = !near(pixel(image, x, y), backdrop);
    if (ink && start < 0) start = y;
    if (!ink && start >= 0) { runs.push(y - start); start = -1; }
  }
  if (start >= 0) runs.push(image.height - start);
  return runs;
}
const countWhere = (image, predicate) => {
  let count = 0;
  for (let offset = 0; offset < image.data.length; offset += 4) {
    if (predicate(image.data[offset], image.data[offset + 1], image.data[offset + 2])) count += 1;
  }
  return count;
};
const reddish = (r, g, b) => r - g > 60 && r - b > 60;
/** The extreme luminance along one row: the middle of a hairline, not its antialiased skirt. */
function rowExtreme(image, y, pick) {
  let best = null;
  for (let x = 0; x < image.width; x += 1) {
    const value = pixel(image, x, y);
    const luminance = value[0] + value[1] + value[2];
    if (best === null || pick(luminance, best.luminance)) best = { value, luminance };
  }
  return best.value;
}
const darkestOnRow = (image, y) => rowExtreme(image, y, (next, best) => next < best);
const lightestOnRow = (image, y) => rowExtreme(image, y, (next, best) => next > best);
const wheelAt = (page, box, point, deltaY) => page.mouse.move(box.x + point.x, box.y + point.y)
  .then(() => page.mouse.wheel(0, deltaY));
/** The wheel delta this renderer reads as `factor`: it zooms by exp(-deltaY * 0.0015). */
const deltaForFactor = factor => -Math.log(factor) / 0.0015;
const state = page => page.evaluate(() => window.cadHarness.a.controller.readState());

test('a drawing opens fitted and centred, in the theme’s ink, and flips with the theme', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('sample.dxf');
  await drawn(pane);

  const light = await frame(pane);
  const box = inkBox(light);
  // Fitted: the drawing's own aspect, centred, filling the pane but for the gutter.
  assert.ok(Math.abs(box.centreX - light.width / 2) <= 2, `centred across: ${box.centreX} of ${light.width}`);
  assert.ok(Math.abs(box.centreY - light.height / 2) <= 2, `centred down: ${box.centreY} of ${light.height}`);
  const aspect = box.width / box.height;
  assert.ok(Math.abs(aspect - MODEL.width / MODEL.height) < 0.05, `the drawing's own aspect: ${aspect}`);
  // The pane is wider than the drawing, so height is the binding axis: the ink
  // reaches to the 16 px gutter and no further.
  assert.ok(Math.abs(box.height - (light.height - 32)) <= 3, `fitted to the gutter: ${box.height} in ${light.height}`);

  // Default pen: the theme's foreground, on the theme's background. The outline's
  // left edge is default-pen line-work.
  assert.ok(near(box.backdrop, [255, 255, 255], 12), `light background: ${box.backdrop}`);
  const edgeLight = darkestOnRow(light, Math.round(light.height / 2));
  assert.ok(edgeLight[0] < 110 && edgeLight[1] < 110 && edgeLight[2] < 110, `dark ink on light: ${edgeLight}`);

  // The red circle is red — its own pen, not the theme's.
  assert.ok(countWhere(light, reddish) > 200, `a red circle is drawn: ${countWhere(light, reddish)} px`);

  // One payload serves both themes: flipping the app's tokens repaints, it does not refetch.
  await page.evaluate(() => document.documentElement.classList.add('dark'));
  const dark = await frame(pane);
  const darkBox = inkBox(dark);
  assert.ok(darkBox.backdrop[0] < 110, `dark background: ${darkBox.backdrop}`);
  const edgeDark = lightestOnRow(dark, Math.round(dark.height / 2));
  assert.ok(edgeDark[0] > 200 && edgeDark[1] > 200 && edgeDark[2] > 200, `light ink on dark: ${edgeDark}`);
  assert.ok(countWhere(dark, reddish) > 200, 'and the red circle is still red');
  // The view did not move while the ink changed.
  assert.ok(Math.abs(darkBox.minX - box.minX) <= 1 && Math.abs(darkBox.maxY - box.maxY) <= 1, 'the theme is not a camera move');
  assert.deepEqual(errors, []);
});

test('a solid hatch’s island is a hole, not a filled square', async (t) => {
  const { open } = await serveHarness(t);
  const { pane, errors } = await open('sample.dxf');
  await drawn(pane);
  const image = await frame(pane);
  const box = inkBox(image);
  // Model -> screen, from the fitted ink box: the drawing's bounds ARE that box.
  const at = (x, y) => ({
    x: box.minX + (x / MODEL.width) * box.width,
    y: box.maxY - (y / MODEL.height) * box.height
  });
  // The hatch is (58,28)-(92,52) with an island at (68,34)-(82,46), in blue.
  const ring = at(62, 30);
  const hole = at(75, 40);
  const ringColor = pixel(image, ring.x, ring.y);
  assert.ok(ringColor[2] - ringColor[0] > 80, `the hatch is filled blue: ${ringColor}`);
  assert.ok(near(pixel(image, hole.x, hole.y), box.backdrop), `its island is unfilled: ${pixel(image, hole.x, hole.y)}`);
  assert.deepEqual(errors, []);
});

test('strokes stay hairlines when the drawing is zoomed in eight times', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('sample.dxf');
  await drawn(pane);
  const fitted = inkBox(await frame(pane));
  const canvas = await canvasOf(pane).boundingBox();
  // A column 90% of the way across crosses the bottom outline and nothing else
  // once the drawing is blown up, so its one run IS that stroke's thickness.
  const column = Math.round(fitted.minX + fitted.width * 0.9);
  const bottomAtFit = columnRuns(await frame(pane), column).at(-1);

  // Zoom about a point ON that bottom edge, so the edge stays under the column.
  await wheelAt(page, canvas, { x: column, y: fitted.maxY }, deltaForFactor(8));
  const zoomed = await frame(pane);
  const bottomAtZoom = columnRuns(zoomed, column).at(-1);

  assert.ok(bottomAtFit <= 4, `a hairline at 100%: ${bottomAtFit} px`);
  assert.ok(bottomAtZoom <= 4, `still a hairline at 800%: ${bottomAtZoom} px`);
  assert.ok(Math.abs(bottomAtZoom - bottomAtFit) <= 1.5,
    `model-space lineweights are not displayed: ${bottomAtFit} -> ${bottomAtZoom} px`);
  // And the drawing really is eight times bigger: at 800% that bottom edge is the
  // only thing left on the pane, running its whole width and still a hairline tall.
  const overrun = inkBox(zoomed);
  assert.ok(overrun.minX <= 1 && overrun.maxX >= zoomed.width - 2,
    `the bottom edge now spans the pane: ${JSON.stringify(overrun)}`);
  assert.ok(overrun.height <= 3, `and it is still a hairline: ${overrun.height} px tall`);
  assert.deepEqual(errors, []);
});

test('the wheel zooms about the pointer, dragging pans, and a double-click fits again', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('sample.dxf');
  await drawn(pane);
  const fitted = inkBox(await frame(pane));
  const canvas = await canvasOf(pane).boundingBox();

  // The point under the pointer does not move: put it on the drawing's bottom-left
  // corner. Zooming OUT, so the whole drawing stays on the canvas and the ink box
  // measures the drawing rather than the pane's edges.
  const anchor = { x: fitted.minX, y: fitted.maxY };
  await wheelAt(page, canvas, anchor, deltaForFactor(0.5));
  const zoomed = inkBox(await frame(pane));
  assert.ok(Math.abs(zoomed.minX - anchor.x) <= 2 && Math.abs(zoomed.maxY - anchor.y) <= 2,
    `the corner under the pointer stayed put: (${zoomed.minX}, ${zoomed.maxY}) vs (${anchor.x}, ${anchor.y})`);
  assert.ok(Math.abs(zoomed.height / fitted.height - 0.5) < 0.03, `and it halved: ${zoomed.height / fitted.height}`);

  // Dragging moves the picture by exactly the pointer's travel. Up and to the
  // right, so the whole drawing stays on the canvas and the ink box measures it
  // rather than the pane's edges.
  await page.mouse.move(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2);
  await page.mouse.down();
  await page.mouse.move(canvas.x + canvas.width / 2 + 140, canvas.y + canvas.height / 2 - 45, { steps: 8 });
  await page.mouse.up();
  const panned = inkBox(await frame(pane));
  assert.ok(Math.abs((panned.minX - zoomed.minX) - 140) <= 2, `panned right 140: ${panned.minX - zoomed.minX}`);
  assert.ok(Math.abs((panned.maxY - zoomed.maxY) + 45) <= 2, `panned up 45: ${panned.maxY - zoomed.maxY}`);
  assert.ok(Math.abs(panned.height - zoomed.height) <= 2, 'panning is not zooming');

  // A double-click frames the whole drawing again.
  await page.mouse.dblclick(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2);
  const refitted = inkBox(await frame(pane));
  assert.ok(Math.abs(refitted.height - fitted.height) <= 2 && Math.abs(refitted.centreX - fitted.centreX) <= 2,
    `back to the fit: ${JSON.stringify(refitted)} vs ${JSON.stringify(fitted)}`);
  assert.deepEqual(errors, []);
});

test('the cursor says the drawing can be dragged, and says so louder while it is', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('sample.dxf');
  await drawn(pane);
  const canvas = canvasOf(pane);
  const cursor = () => canvas.evaluate(node => getComputedStyle(node).cursor);
  assert.equal(await cursor(), 'grab');
  const box = await canvas.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 30, box.y + box.height / 2, { steps: 3 });
  assert.equal(await cursor(), 'grabbing');
  await page.mouse.up();
  assert.equal(await cursor(), 'grab');
  assert.deepEqual(errors, []);
});

test('a pane that is resized re-fits only while the view is still the one it opened with', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('sample.dxf');
  await drawn(pane);
  const shrink = height => page.evaluate(next => {
    document.querySelector('[data-testid="one"]').parentElement.style.height = next;
  }, height);

  // Untouched: the drawing is re-framed for the pane it now has.
  const fitted = inkBox(await frame(pane));
  await shrink('420px');
  await settle(page);
  const refitted = inkBox(await frame(pane));
  assert.ok(refitted.height < fitted.height * 0.8, `re-fitted smaller: ${fitted.height} -> ${refitted.height}`);
  const resized = await frame(pane);
  assert.ok(Math.abs(refitted.height - (resized.height - 32)) <= 3, `fitted to the new pane: ${refitted.height} in ${resized.height}`);

  // Touched: the person's framing is theirs and a resize does not take it back — but it is
  // kept in the terms it was chosen in, not in pixels. The view holds the same zoom
  // RELATIVE to the fit, still centred on what it was centred on, so a pane that grows
  // shows the same view bigger, as the 3D viewports do. Holding an absolute pixel scale
  // would instead crop the drawing where it stood when the pane narrowed.
  const canvas = await canvasOf(pane).boundingBox();
  await wheelAt(page, canvas, { x: canvas.width / 2, y: canvas.height / 2 }, deltaForFactor(0.5));
  const chosenShot = await frame(pane);
  const chosen = inkBox(chosenShot);
  await shrink('640px');
  await settle(page);
  const grownShot = await frame(pane);
  const kept = inkBox(grownShot);
  // The canvas is the pane less its navbar; the share of it the drawing covers is the
  // person's zoom, and that is what survives.
  const share = (ink, shot) => ink.height / (shot.height - 32);
  assert.ok(Math.abs(share(kept, grownShot) - share(chosen, chosenShot)) < 0.02,
    `half the fit, before and after: ${share(chosen, chosenShot)} -> ${share(kept, grownShot)}`);
  assert.ok(kept.height > chosen.height * 1.3,
    `a bigger pane shows the same view bigger: ${chosen.height} -> ${kept.height}`);
  assert.ok(share(kept, grownShot) < 0.7, 'and it is still the zoom they chose, not the fit');
  assert.deepEqual(errors, []);
});

test('a DXF has no panels of its own, no tools and no fullscreen', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('sample.dxf');
  await drawn(pane);

  // The nav row's only panel is the host's file tree: a drawing declares none, not even
  // Display, and opened directly it opens with nothing (the tree is not where a file opens).
  const panels = () => pane.locator('[data-file-panel]')
    .evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`));
  assert.deepEqual(await panels(), ['Show files:false'], 'the file tree, one press away, and nothing else');
  assert.equal(await pane.locator('[data-tool-panel]').count(), 0, 'and no tool panel: a drawing has no tools');
  assert.equal(await pane.getByRole('group', { name: 'Interaction tools' }).count(), 0, 'no tool strip');
  for (const name of ['Orbit', 'Draw', 'Select', 'Measure', 'Position', 'Animate', 'Fullscreen']) {
    assert.equal(await pane.getByRole('button', { name, exact: true }).count(), 0, name);
  }
  for (const name of ['Switch to 2D view', 'Switch to 3D view']) {
    assert.equal(await pane.getByRole('button', { name, exact: true }).count(), 0, name);
  }
  assert.equal(await pane.getByRole('tab').count(), 0, 'no Material, Bends, Layers or Display tabs');
  // What a drawing offers: a snapshot, and nothing else. Zooming is the pointer's —
  // wheel or pinch about it, drag to pan, double-click to fit — so the navbar carries
  // no zoom buttons, and there is no zoom control anywhere else in the viewer either.
  assert.equal(await pane.getByRole('button', { name: 'Take snapshot', exact: true }).count(), 1);
  for (const name of ['Zoom in', 'Zoom out', 'Reset Zoom', 'Zoom to fit', 'Zoom controls']) {
    assert.equal(await pane.getByRole('button', { name, exact: true }).count(), 0, name);
  }

  // The snapshot is the drawing WITH its background, delivered through the host.
  await pane.getByRole('button', { name: 'Take snapshot', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  assert.deepEqual(await page.evaluate(() => [window.cadHarness.captures[0].file, window.cadHarness.captures[0].type]),
    ['sample.dxf', 'image/png']);
  assert.deepEqual(errors, []);
});

test('an unreadable drawing shows the server’s own sentence, and an empty one says it is empty', async (t) => {
  const { open } = await serveHarness(t);
  const broken = await open('broken.dxf');
  const alert = broken.pane.getByRole('alert');
  await alert.waitFor();
  const text = await alert.innerText();
  assert.match(text, /The viewer couldn’t complete the request/);
  assert.match(text, /HTTP 400/);
  assert.match(text, /not a readable DXF document/);
  assert.match(text, /Try again/);
  assert.equal(await broken.pane.locator('[data-viewer-loading]').count(), 0, 'and not a spinner forever');

  const empty = await open('empty.dxf');
  await drawn(empty.pane);
  await empty.pane.locator('[data-drawing-empty]').waitFor();
  assert.match(await empty.pane.locator('[data-drawing-empty]').innerText(), /no geometry in its modelspace/);
  assert.equal(await empty.pane.getByRole('alert').count(), 0, 'an empty drawing is not an error');
  assert.deepEqual(empty.errors, []);
});

test('the view a person chose comes back when the tab is reopened', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('sample.dxf');
  await drawn(pane);
  const canvas = await canvasOf(pane).boundingBox();
  await wheelAt(page, canvas, { x: canvas.width * 0.35, y: canvas.height * 0.6 }, deltaForFactor(3));
  const chosen = inkBox(await frame(pane));

  const key = JSON.stringify(['sample.dxf', 'dxf']);
  await page.waitForFunction(stateKey => window.cadHarness.state.renderers?.[stateKey]?.kind === 'dxf-view', key);
  const record = await page.evaluate(stateKey => window.cadHarness.state.renderers[stateKey], key);
  assert.equal(record.version, 1);
  assert.deepEqual(Object.keys(record.transform).sort(), ['offsetX', 'offsetY', 'scale']);

  await page.evaluate(() => window.cadHarness.mounted(false));
  await canvasOf(pane).waitFor({ state: 'detached' });
  await page.evaluate(() => window.cadHarness.mounted(true));
  await drawn(pane);
  const reopened = inkBox(await frame(pane));
  assert.ok(Math.abs(reopened.minX - chosen.minX) <= 2 && Math.abs(reopened.height - chosen.height) <= 2,
    `reopened where it was left: ${JSON.stringify(reopened)} vs ${JSON.stringify(chosen)}`);
  assert.deepEqual(errors, []);
});

test('host commands a flat drawing cannot answer are declined in words', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('sample.dxf');
  await drawn(pane);

  const refuse = (call) => page.evaluate(async (source) => {
    const controller = window.cadHarness.a.controller;
    // eslint-disable-next-line no-new-func
    return new Function('controller', `return (${source})(controller)`)(controller).then(() => '', error => error.message);
  }, call);

  assert.match(await refuse('c => c.select({ selectors: ["o1.f1"] })'), /A DXF is a 2D drawing without CAD references/);
  assert.match(await refuse('c => c.clearSelection()'), /never has a selection to clear/);
  assert.match(await refuse('c => c.setCamera({ position: [0, 0, 1], target: [0, 0, 0], up: [0, 1, 0] })'), /no camera to pose/);
  assert.match(await refuse('c => c.setRenderMode(true)'), /no Display settings/);

  // What it CAN do: report itself, fit again, and hand over a PNG. There is no zoom
  // command and no zoom readout: no host ever sent one, and nothing read the percentage.
  const snapshot = await state(page);
  assert.equal(snapshot.loading, false);
  assert.equal(snapshot.camera, null);
  assert.deepEqual(snapshot.selection, []);
  assert.equal('zoomPercent' in snapshot, false, 'the live state carries no zoom percentage');
  // setZoom is gone with the UI that was its only caller: no host ever sent it.
  assert.equal(await page.evaluate(() => typeof window.cadHarness.a.controller.setZoom), 'undefined');

  const fitted = inkBox(await frame(pane));
  const canvas = await canvasOf(pane).boundingBox();
  await wheelAt(page, canvas, { x: fitted.minX, y: fitted.maxY }, deltaForFactor(0.5));
  assert.ok(Math.abs(inkBox(await frame(pane)).height / fitted.height - 0.5) < 0.03, 'the wheel still zooms the drawing');
  await page.evaluate(() => window.cadHarness.a.controller.resetCamera());
  assert.ok(Math.abs(inkBox(await frame(pane)).height - fitted.height) <= 2, 'resetCamera fits the drawing again');

  const captured = await page.evaluate(async () => {
    const blob = await window.cadHarness.a.controller.capture();
    return { type: blob.type, size: blob.size };
  });
  assert.equal(captured.type, 'image/png');
  assert.ok(captured.size > 1000, `a real picture: ${captured.size} bytes`);
  assert.deepEqual(errors, []);
});

// A host asking a drawing to select something is answered, not ignored.
test('a select-reference request is consumed without a notification', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open('sample.dxf');
  await drawn(pane);
  await page.evaluate(() => window.cadHarness.selectReference('o1.f1'));
  await page.waitForFunction(() => !window.cadHarness.a.commands.getSnapshot().selectReference);
  assert.equal(await page.evaluate(() => window.cadHarness.a.commands.getSnapshot().selectReference ?? null), null,
    'the declined request is acknowledged');
  assert.deepEqual(errors, []);
});
