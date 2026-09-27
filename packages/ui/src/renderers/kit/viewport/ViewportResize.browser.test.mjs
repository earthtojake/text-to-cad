import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// A viewer whose box changes size in ONE layout step (the file tree opening, the tool
// stack widened, a window snap) must paint the model at the new size in the very frame
// that layout lands in. The canvas is sized 100% by CSS, so a drawing buffer or a render
// left for a later frame shows the old picture stretched over the new box for a frame.
//
// A ResizeObserver callback runs after layout and before paint, and observers are called
// in the order they were created: a probe created after the viewport's own observer sees,
// in the same pass, exactly what the next paint will show.

// One ASCII STL box, served from memory: tall enough that a stretched frame reads wrong.
const CORNERS = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]];
const TRIANGLES = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]];
function stlBox([sx, sy, sz]) {
  const corners = CORNERS.map(([x, y, z]) => [x * sx, y * sy, z * sz]);
  const facets = TRIANGLES.map(triangle => `facet normal 0 0 0\nouter loop\n${triangle.map(index => `vertex ${corners[index].join(' ')}`).join('\n')}\nendloop\nendfacet`);
  return `solid box\n${facets.join('\n')}\nendsolid box\n`;
}
const FILES = { 'part.stl': Buffer.from(stlBox([20, 12, 30])) };

// The harness renders its viewer at a fixed CSS size; the spec draws it smaller (a Retina
// drawing buffer of fewer pixels for a software GL to fill) and resizes it through these
// variables. It stays wider than the viewer's mobile breakpoint (720px) throughout, so a
// resize is only ever a resize.
const HARNESS_SIZE = '<style>#root > div { width: var(--harness-width, 800px) !important; height: var(--harness-height, 500px) !important; }</style>';

async function serveHarness(t) {
  const temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-resize-browser-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('../../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const css = await readFile(new URL('../../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
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
    else { response.setHeader('Content-Type', 'text/html'); response.end(`<!doctype html><html><head><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: (process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1')
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const open = async () => {
    // A Retina page: the drawing buffer is device pixels, the box CSS pixels.
    const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 2 });
    page.setDefaultTimeout(15000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      window.Worker = undefined;
      // The viewer's box, resized in one layout step.
      window.resize = (width, height) => {
        const root = document.querySelector('#root > div');
        root.style.setProperty('--harness-width', width);
        if (height) root.style.setProperty('--harness-height', height);
      };
      // Every draw call the page's WebGL makes, so a test can see a frame being drawn.
      for (const Context of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
        for (const name of ['drawArrays', 'drawElements', 'drawArraysInstanced', 'drawElementsInstanced']) {
          const original = Context?.prototype?.[name];
          if (!original) continue;
          Context.prototype[name] = function (...args) { window.__glDraws = (window.__glDraws || 0) + 1; return original.apply(this, args); };
        }
      }
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/?file=part.stl`);
    const pane = page.getByTestId('one');
    await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
    return { page, pane, errors };
  };
  return { open };
}

// Opening over: no draw call for longer than the viewport's open-fit window. Opening settles
// in steps (the open fit, the panel column, the projection), each a draw, and until it has been
// quiet for OPEN_FIT_SETTLE_MS (600 ms, `ShellViewport.jsx`) a resize re-fits instead of
// rescaling. Awaited as a quiet spell, however long a slow GL takes to reach it.
const idle = page => page.waitForFunction(() => new Promise(resolve => {
  let last = window.__glDraws || 0, since = performance.now();
  const step = () => {
    const now = window.__glDraws || 0;
    if (now !== last) { last = now; since = performance.now(); }
    if (performance.now() - since >= 700) resolve(true); else requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}));

const frames = (page, count = 2) => page.evaluate(n => new Promise(resolve => {
  const step = left => (left ? requestAnimationFrame(() => step(left - 1)) : resolve());
  step(n);
}), count);

// Install the probe: a ResizeObserver on the viewport's box, created after the viewport's
// own, that records at each resize what the paint about to happen will show — the box,
// the drawing buffer, the camera's aspect, whether anything was drawn since the resize
// began, and a row and a column of the picture.
async function installProbe(page) {
  await page.evaluate(() => {
    const canvas = document.querySelector('[data-testid="one"] [aria-busy="false"] > div > canvas');
    const box = canvas.parentElement;
    const scratch = document.createElement('canvas');
    const signature = () => {
      scratch.width = canvas.width; scratch.height = canvas.height;
      const context = scratch.getContext('2d', { willReadFrequently: true });
      context.clearRect(0, 0, scratch.width, scratch.height);
      context.drawImage(canvas, 0, 0);
      const row = context.getImageData(0, Math.floor(canvas.height / 2), canvas.width, 1).data;
      const column = context.getImageData(Math.floor(canvas.width / 2), 0, 1, canvas.height).data;
      return { row: Array.from(row), column: Array.from(column) };
    };
    const aspect = () => {
      const camera = window.__cadCamera?.();
      return camera ? camera.aspect : null;
    };
    const probe = { records: [], drawsAtMark: 0, signature, aspect, canvas, box };
    probe.mark = () => { probe.drawsAtMark = window.__glDraws || 0; probe.records.length = 0; };
    new ResizeObserver(() => {
      probe.records.push({
        cssWidth: box.clientWidth, cssHeight: box.clientHeight,
        bufferWidth: canvas.width, bufferHeight: canvas.height,
        styleWidth: canvas.clientWidth, styleHeight: canvas.clientHeight,
        aspect: aspect(), drawn: (window.__glDraws || 0) - probe.drawsAtMark,
        ...signature()
      });
    }).observe(box);
    window.__resizeProbe = probe;
  });
  // The probe's first callback is the observation of the box as it stands.
  await frames(page, 3);
}

// The drawing buffer's scale to the box, at rest: the device pixel ratio, capped.
const restingRatio = page => page.evaluate(() => {
  const { canvas, box } = window.__resizeProbe;
  return canvas.width / box.clientWidth;
});
// The picture at rest at the current size, as a frame draws it. A WebGL canvas's drawing
// buffer is only readable until the frame is composited, so the reference is read in the
// frame that draws it: a window resize event asks the viewport for a frame, and an animation
// callback queued after that one reads it before the frame is composited.
const settledSignature = async (page) => {
  await frames(page, 4);
  return page.evaluate(() => new Promise(resolve => {
    window.dispatchEvent(new Event('resize'));
    requestAnimationFrame(() => resolve(window.__resizeProbe.signature()));
  }));
};
// Pixels (RGBA quads) that differ by more than a rounding step.
function differing(left, right) {
  assert.equal(left.length, right.length, 'the two pictures are the same size');
  let count = 0;
  for (let offset = 0; offset < left.length; offset += 4) {
    if (Math.max(...[0, 1, 2, 3].map(channel => Math.abs(left[offset + channel] - right[offset + channel]))) > 8) count += 1;
  }
  return count;
}

// three sizes the drawing buffer to floor(css size x pixel ratio).
function assertPaintedAtNewSize(record, ratio, settled, label) {
  assert.equal(record.bufferWidth, Math.floor(record.cssWidth * ratio),
    `${label}: the drawing buffer is ${record.bufferWidth}px wide for a ${record.cssWidth}px box at ${ratio}x, in the frame the box changed`);
  assert.equal(record.bufferHeight, Math.floor(record.cssHeight * ratio), `${label}: drawing buffer height`);
  assert.ok(Math.abs(record.aspect - record.cssWidth / record.cssHeight) < 1e-6,
    `${label}: the camera's aspect ${record.aspect} matches the box ${record.cssWidth}x${record.cssHeight}`);
  assert.ok(record.drawn > 0, `${label}: the model was drawn at the new size before the frame was painted`);
  // What is painted in that frame is the picture at rest at the new size, not a blank
  // buffer and not the old picture stretched.
  const width = record.bufferWidth;
  assert.ok(differing(record.row, settled.row) <= width * 0.01,
    `${label}: the middle row painted in the resize frame is the settled picture (${differing(record.row, settled.row)} of ${width} pixels differ)`);
  assert.ok(differing(record.column, settled.column) <= record.bufferHeight * 0.01,
    `${label}: the middle column painted in the resize frame is the settled picture`);
}

test('a viewer resized in one step paints the model at its new size in that same frame', async (t) => {
  const { open } = await serveHarness(t);
  const { page, pane, errors } = await open();
  // Let opening settle (the open fit, the panel column, the projection) before resizing.
  await idle(page);
  await installProbe(page);
  const ratio = await restingRatio(page);
  assert.ok(ratio >= 1, `resting pixel ratio ${ratio}`);

  // 1. The viewer's own box narrows in one step, as a window snap or a sibling column does.
  await page.evaluate(() => window.__resizeProbe.mark());
  await page.evaluate(() => resize('730px', '400px'));
  await page.waitForFunction(() => window.__resizeProbe.records.length > 0);
  const [narrowed] = await page.evaluate(() => window.__resizeProbe.records);
  assert.ok(narrowed.cssWidth < 760, `the box narrowed (${narrowed.cssWidth}px)`);
  assertPaintedAtNewSize(narrowed, ratio, await settledSignature(page), 'one-step narrowing');

  // 2. And widens back in one step.
  await page.evaluate(() => window.__resizeProbe.mark());
  await page.evaluate(() => resize('800px', '500px'));
  await page.waitForFunction(() => window.__resizeProbe.records.length > 0);
  const [widened] = await page.evaluate(() => window.__resizeProbe.records);
  assertPaintedAtNewSize(widened, ratio, await settledSignature(page), 'one-step widening');

  // 3. The person's own one-step resize: the file tree opening beside the viewer.
  await page.evaluate(() => window.__resizeProbe.mark());
  await pane.locator('[data-file-panel][aria-label="Show files"]').click();
  await page.waitForFunction(() => window.__resizeProbe.records.length > 0);
  const [treeOpened] = await page.evaluate(() => window.__resizeProbe.records);
  assert.ok(treeOpened.cssWidth < 780, `the file tree took room from the viewer (${treeOpened.cssWidth}px)`);
  assertPaintedAtNewSize(treeOpened, ratio, await settledSignature(page), 'file tree opening');

  // 4. A drag resizes once per frame; every frame is painted at its own size, and the
  //    viewport draws no more than one picture per frame to do it.
  await page.evaluate(() => window.__resizeProbe.mark());
  const drawsPerFrame = await page.evaluate(() => new Promise(resolve => {
    const perFrame = [];
    let last = window.__glDraws || 0;
    let step = 0;
    const tick = () => {
      const now = window.__glDraws || 0;
      if (step > 0) perFrame.push(now - last);
      last = now;
      if (step === 12) { resolve(perFrame); return; }
      resize(`${800 - (step + 1) * 5}px`);
      step += 1;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }));
  const dragged = await page.evaluate(() => window.__resizeProbe.records.map(({ row, column, ...rest }) => rest));
  assert.ok(dragged.length >= 10, `the drag resized the box every frame (${dragged.length} resizes)`);
  for (const [index, record] of dragged.entries()) {
    assert.equal(record.bufferWidth, Math.floor(record.cssWidth * ratio), `drag step ${index}: drawing buffer width follows the box`);
    assert.ok(Math.abs(record.aspect - record.cssWidth / record.cssHeight) < 1e-6, `drag step ${index}: camera aspect follows the box`);
  }
  const drawsPerPicture = Math.max(1, narrowed.drawn);
  assert.ok(Math.max(...drawsPerFrame) <= drawsPerPicture,
    `a drag draws at most one picture a frame (draw calls per frame ${drawsPerFrame.join(',')}, one picture is ${drawsPerPicture})`);

  // 5. At rest again, nothing is drawn: render on demand holds.
  await frames(page, 4);
  const idleBefore = await page.evaluate(() => window.__glDraws || 0);
  await frames(page, 10);
  assert.equal(await page.evaluate(() => window.__glDraws || 0), idleBefore, 'an idle viewer draws nothing');
  assert.deepEqual(errors, []);
});
