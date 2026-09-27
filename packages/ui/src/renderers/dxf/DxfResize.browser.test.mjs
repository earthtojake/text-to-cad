import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// A drawing pane that changes size in ONE layout step (the file tree opening, a window
// snap) must paint the drawing at its new size in the very frame that layout lands in.
// Setting a canvas's width or height wipes it, so a pane that resizes its canvas as it
// is observed and paints on the NEXT animation frame shows an empty pane for a frame.
//
// A ResizeObserver callback runs after layout and before paint, and observers are called
// in the order they were created: a probe created after the pane's own observer sees, in
// the same pass, exactly what the next paint will show. A 2D canvas keeps its pixels, so
// the probe can read them there and compare them with the picture once it has settled.

// The committed `/__cad/drawing` payload the DXF spec uses (see `__fixtures__/README.md`).
const SAMPLE = JSON.parse(await readFile(new URL('./__fixtures__/sample.drawing.json', import.meta.url), 'utf8'));

// The harness renders its pane at a fixed CSS size; the spec draws it smaller (a Retina buffer
// of fewer pixels to paint and digest) and resizes it through these variables. It stays wider
// than the viewer's mobile breakpoint (720px) throughout, so a resize is only ever a resize.
const HARNESS_SIZE = '<style>#root > div { width: var(--harness-width, 800px) !important; height: var(--harness-height, 500px) !important; }</style>';

async function serveHarness(t) {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-dxf-resize-browser-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/__cad/drawing')) { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(SAMPLE)); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: [{ kind: 'dxf', file: 'sample.dxf', rootRelativeFile: 'sample.dxf', url: '/sample.dxf', hash: `${root}-sample.dxf`, bytes: 4096 }] }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else { response.setHeader('Content-Type', 'text/html'); response.end(`<!doctype html><html><head><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true });
  // A Retina page: the canvas is device pixels, the pane CSS pixels.
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 2 });
  page.setDefaultTimeout(20000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    window.Worker = undefined;
    // The pane's size, in one layout step.
    window.resize = (width, height) => {
      const root = document.querySelector('#root > div');
      root.style.setProperty('--harness-width', width);
      if (height) root.style.setProperty('--harness-height', height);
    };
    // Every paint starts by setting the canvas transform: counting those counts paints.
    const original = CanvasRenderingContext2D.prototype.setTransform;
    CanvasRenderingContext2D.prototype.setTransform = function (...args) {
      window.__canvasPaints = (window.__canvasPaints || 0) + 1;
      return original.apply(this, args);
    };
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=sample.dxf`);
  const pane = page.getByTestId('one');
  await pane.locator('[data-drawing-surface] canvas').first().waitFor();
  await pane.locator('[data-drawing-surface] [aria-busy="false"]').first().waitFor();
  return { page, pane, errors };
}

const frames = (page, count = 2) => page.evaluate(n => new Promise(resolve => {
  const step = left => (left ? requestAnimationFrame(() => step(left - 1)) : resolve());
  step(n);
}), count);

// The probe: a ResizeObserver on the pane's canvas box, created after the pane's own,
// recording at each resize what the paint about to happen will show.
async function installProbe(page) {
  await page.evaluate(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-drawing-surface] canvas');
    const box = canvas.parentElement;
    // Painted pixels (any alpha) and a digest of the whole picture.
    const picture = () => {
      const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      let painted = 0, digest = 0;
      for (let offset = 0; offset < data.length; offset += 4) {
        if (data[offset + 3] > 0) painted += 1;
        digest = (Math.imul(digest, 31) + data[offset] + (data[offset + 1] << 8) + (data[offset + 2] << 16) + (data[offset + 3] << 24)) | 0;
      }
      return { painted, digest, pixels: canvas.width * canvas.height };
    };
    const probe = { records: [], picture, canvas, box };
    probe.mark = () => { probe.records.length = 0; };
    new ResizeObserver(() => {
      probe.records.push({
        cssWidth: box.clientWidth, cssHeight: box.clientHeight,
        canvasWidth: canvas.width, canvasHeight: canvas.height, ...picture()
      });
    }).observe(box);
    window.__dxfProbe = probe;
  });
  await frames(page, 3);
}

// The picture once it has come to rest: the same over two frames running, not whatever a
// fixed count of frames after the resize happened to show.
const settledPicture = async (page) => {
  let last = null;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await frames(page, 2);
    const picture = await page.evaluate(() => window.__dxfProbe.picture());
    if (last && picture.digest === last.digest && picture.pixels === last.pixels) return picture;
    last = picture;
  }
  throw new Error('the drawing never came to rest at its new size');
};

function assertPaintedAtNewSize(record, ratio, settled, label) {
  assert.equal(record.canvasWidth, Math.max(1, Math.round(record.cssWidth * ratio)),
    `${label}: the canvas is ${record.canvasWidth}px wide for a ${record.cssWidth}px pane at ${ratio}x, in the frame the pane changed`);
  assert.equal(record.canvasHeight, Math.max(1, Math.round(record.cssHeight * ratio)), `${label}: canvas height`);
  assert.ok(record.painted > 0, `${label}: the canvas is painted, not wiped, in the frame the pane changed (${record.painted} of ${record.pixels} pixels painted)`);
  assert.equal(record.digest, settled.digest, `${label}: what that frame shows is the settled picture at the new size`);
}

test('a drawing pane resized in one step paints the drawing at its new size in that same frame', async (t) => {
  const { page, pane, errors } = await serveHarness(t);
  await frames(page, 4);
  await installProbe(page);
  const ratio = await page.evaluate(() => window.__dxfProbe.canvas.width / window.__dxfProbe.box.clientWidth);
  assert.ok(ratio >= 1, `resting pixel ratio ${ratio}`);

  // 1. The pane narrows and shortens in one step, as a window snap or a sibling column does.
  await page.evaluate(() => window.__dxfProbe.mark());
  await page.evaluate(() => resize('730px', '400px'));
  await page.waitForFunction(() => window.__dxfProbe.records.length > 0);
  const [narrowed] = await page.evaluate(() => window.__dxfProbe.records);
  assert.ok(narrowed.cssWidth < 760, `the pane narrowed (${narrowed.cssWidth}px)`);
  assertPaintedAtNewSize(narrowed, ratio, await settledPicture(page), 'one-step narrowing');

  // 2. And grows back in one step.
  await page.evaluate(() => window.__dxfProbe.mark());
  await page.evaluate(() => resize('800px', '500px'));
  await page.waitForFunction(() => window.__dxfProbe.records.length > 0);
  const [widened] = await page.evaluate(() => window.__dxfProbe.records);
  assertPaintedAtNewSize(widened, ratio, await settledPicture(page), 'one-step widening');

  // 3. The person's own one-step resize: the file tree opening beside the drawing.
  await page.evaluate(() => window.__dxfProbe.mark());
  await pane.locator('[data-file-panel][aria-label="Show files"]').click();
  await page.waitForFunction(() => window.__dxfProbe.records.length > 0);
  const [treeOpened] = await page.evaluate(() => window.__dxfProbe.records);
  assert.ok(treeOpened.cssWidth < 780, `the file tree took room from the drawing (${treeOpened.cssWidth}px)`);
  assertPaintedAtNewSize(treeOpened, ratio, await settledPicture(page), 'file tree opening');

  // 4. A drag resizes once per frame: every frame is painted at its own size, once.
  await page.evaluate(() => window.__dxfProbe.mark());
  const paintsPerFrame = await page.evaluate(() => new Promise(resolve => {
    const perFrame = [];
    let last = window.__canvasPaints || 0;
    let step = 0;
    const tick = () => {
      const now = window.__canvasPaints || 0;
      if (step > 0) perFrame.push(now - last);
      last = now;
      if (step === 10) { resolve(perFrame); return; }
      resize(`${800 - (step + 1) * 7}px`);
      step += 1;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }));
  const dragged = await page.evaluate(() => window.__dxfProbe.records);
  assert.ok(dragged.length >= 8, `the drag resized the pane every frame (${dragged.length} resizes)`);
  for (const [index, record] of dragged.entries()) {
    assert.equal(record.canvasWidth, Math.max(1, Math.round(record.cssWidth * ratio)), `drag step ${index}: canvas width follows the pane`);
    assert.ok(record.painted > 0, `drag step ${index}: the canvas is painted in the frame it was resized`);
  }
  // Every frame of the drag costs the same one paint: no frame paints twice.
  assert.ok(paintsPerFrame.every(count => count > 0 && count === paintsPerFrame[0]),
    `a drag paints once each frame (canvas transforms per frame: ${paintsPerFrame.join(',')})`);

  // 5. At rest, nothing is painted.
  await frames(page, 4);
  const idleBefore = await page.evaluate(() => window.__canvasPaints || 0);
  await frames(page, 10);
  assert.equal(await page.evaluate(() => window.__canvasPaints || 0), idleBefore, 'an idle drawing paints nothing');
  assert.deepEqual(errors, []);
});
