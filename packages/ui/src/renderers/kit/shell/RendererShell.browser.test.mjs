import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import * as THREE from 'three';
import { interactiveCameraFrameForBounds } from '../../../../dist/renderers/kit/camera/viewportCameraFit.js';
import { DEFAULT_VIEW_DIRECTION, WORLD_UP } from '../../../../dist/renderers/kit/camera/viewportCameraKit.js';
import { CAD_DEFAULT_VERTICAL_FOV_DEGREES } from '../../../../dist/renderers/kit/camera/cameraLens.js';

// A software WebGL renderer (SwiftShader, llvmpipe: Linux CI) caps the pixel ratio at 1, idle and
// moving (`useViewerRuntime.js`), so the hardware-only ratio checks read the policy that applies.
const softwareWebGl = page => page.evaluate(() => {
  const gl = document.createElement('canvas').getContext('webgl');
  const info = gl?.getExtension('WEBGL_debug_renderer_info');
  const name = String(info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl?.getParameter(gl.RENDERER) || '');
  return /swiftshader|llvmpipe|softpipe|software rasterizer|lavapipe/i.test(name);
});

// The harness renders its panes at a fixed CSS size; the spec draws them smaller, so a software
// GL (CI's SwiftShader) has fewer pixels to fill and a screenshot fewer to read.
const HARNESS_SIZE = '<style>#root > div { width: 800px !important; height: 500px !important; }</style>';

// One harness bundle and one browser for the file; every test serves its own files and opens its
// own page. (A browser's first WebGL page pays for compiling the viewer's shaders; later pages
// reuse them.)
let temporary, bundle, compiledCss, browser;
before(async () => {
  temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-shell-browser-'));
  await build({ entryPoints: [fileURLToPath(new URL('../../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.avif': 'dataurl', '.woff2': 'dataurl', '.svg': 'dataurl' } });
  bundle = await readFile(join(temporary, 'harness.js'));
  compiledCss = await readFile(new URL('../../../../dist/styles.css', import.meta.url));
  browser = await chromium.launch({ headless: true, args: (process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1')
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
});
after(async () => {
  await browser?.close();
  if (temporary) await rm(temporary, { recursive: true, force: true });
});

/**
 * A server for one test: the harness page, and `route(url, root, response)` for the workspace
 * behind it (it answers `true` for what it served). A harness-only renderer's files are its own,
 * so an empty catalog serves it, and the fonts it asks for are not found.
 */
async function serve(t, route = () => false) {
  const server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(compiledCss); }
    else if (route(url, root, response)) return;
    else if (url.pathname.endsWith('/__cad/catalog')) { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, entries: [] })); }
    else if (url.pathname.endsWith('/__cad/server')) { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' })); }
    else if (/\.(woff2|ttf)$/.test(url.pathname)) { response.statusCode = 404; response.end(); }
    else { response.setHeader('Content-Type', 'text/html'); response.end(`<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  t.after(() => new Promise(resolve => server.close(resolve)));
  return `http://127.0.0.1:${server.address().port}`;
}

async function newPage(t, { deviceScaleFactor = 1, timeout = 15000 } = {}) {
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor });
  t.after(() => page.close());
  page.setDefaultTimeout(timeout);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  return { page, errors };
}
// Two frames on: what a change asked for has been drawn.
const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));

// The shell end to end, in a real browser, under the smallest renderer that mounts it: a
// one-triangle mesh file. Everything asserted here is the shell's (kit/shell), so it holds
// for every renderer built on it. Inline fixture bytes are served in memory with a private
// temporary harness.
const mesh = 'solid triangle\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 20 0 0\nvertex 0 20 0\nendloop\nendfacet\nendsolid triangle\n';

test('a shell renderer restores isolated view state on a remount', async (t) => {
  const requests = [];
  const catalogFiles = [];
  const origin = await serve(t, (url, root, response) => {
    requests.push(url.pathname);
    if (url.pathname.endsWith('/__cad/catalog')) {
      // The workspace listing defers the file; asked for it by name, the catalog resolves it.
      response.setHeader('Content-Type', 'application/json');
      catalogFiles.push({ root, file: url.searchParams.get('file') });
      const entry = url.searchParams.get('file') === 'part.stl'
        ? { kind: 'stl', file: 'part.stl', rootRelativeFile: 'part.stl', url: '/mesh.stl', hash: root, bytes: mesh.length }
        : { file: 'part.stl', rootRelativeFile: 'part.stl', catalogPending: true };
      response.end(JSON.stringify({ rootId: root, entries: [entry] }));
      return true;
    }
    if (url.pathname.endsWith('/mesh.stl')) { response.end(mesh); return true; }
    return false;
  });
  // A Retina page: the drawing buffer is device pixels, and a quality switch resizes it.
  const { page, errors } = await newPage(t, { deviceScaleFactor: 2, timeout: 10000 });
  await page.addInitScript(() => {
    window.Worker = undefined;
    // A Retina quality switch resizes the drawing buffer. Every such clear
    // must be followed by its replacement draw in the SAME task, even while
    // shader preparation is asynchronous. Canvas identity alone cannot catch it.
    const draws = new WeakMap();
    window.cadBufferClears = [];
    for (const name of ['drawElements', 'drawArrays', 'drawElementsInstanced', 'drawArraysInstanced']) {
      const original = WebGL2RenderingContext.prototype[name];
      WebGL2RenderingContext.prototype[name] = function (...args) {
        draws.set(this.canvas, (draws.get(this.canvas) || 0) + 1);
        return original.apply(this, args);
      };
    }
    for (const name of ['width', 'height']) {
      const property = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, name);
      Object.defineProperty(HTMLCanvasElement.prototype, name, { ...property, set(value) {
        property.set.call(this, value);
        if (this !== window.cadHarnessView?.canvas) return;
        const before = draws.get(this) || 0;
        queueMicrotask(() => window.cadBufferClears.push({ name, redrawn: (draws.get(this) || 0) > before }));
      } });
    }

    for (const name of ['localStorage', 'sessionStorage']) {
      Object.defineProperty(window, name, { get() { throw new Error(`Renderer accessed ${name}`); } });
    }
  });
  await page.goto(`${origin}/`);
  const first = page.getByTestId('one');
  // Display's settings are a panel at the foot of the tool stack, opened by the strip's last button:
  // a file never opens with it, and it is not a tool.
  const displayButton = pane => pane.locator('[data-cad-toolbar]').getByRole('button', { name: 'Display', exact: true });
  const display = first.locator('[data-tool-panel-id="display"]');
  const cameraZoom = id => page.evaluate(pane => window.cadHarness[pane].controller?.readState().camera?.zoom ?? null, id);
  await displayButton(first).waitFor().catch(async (error) => { throw new Error(`${error.message}; page errors: ${errors.join('; ')}; body: ${await page.locator("body").innerText()}; requests: ${requests.join(", ")}`); });
  await page.waitForFunction(() => Object.keys(window.cadHarness.state.renderers || {}).length > 0);
  assert.ok(catalogFiles.some(({ root, file }) => root === 'one' && file === 'part.stl'), 'the deferred file was resolved by name');

  // The camera is moved through the live controller: there is no zoom control in the viewer to press.
  // A view refuses commands until it has drawn its file (`liveBinding.ts`), which a software GL
  // takes longer to do than the stored record above takes to be written: wait for it, as for pane b.
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    await controller.setCamera({ ...controller.readState().camera, zoom: 1.1 });
  });
  await page.waitForFunction(() => Math.abs((window.cadHarness.a.controller.readState().camera?.zoom ?? 0) - 1.1) < 1e-6);

  // ISOLATED: a sibling renderer over the same file opens at its own framing, and the first
  // pane keeps the camera it was given.
  await page.evaluate(() => window.cadHarness.second(true));
  await displayButton(page.getByTestId('two')).waitFor();
  await page.waitForFunction(() => window.cadHarness.b.controller?.readState().loading === false);
  assert.equal(await cameraZoom('b'), 1, 'a sibling renderer opens at its own framing');
  assert.ok(requests.includes('/two/mesh.stl'));
  assert.ok(Math.abs(await cameraZoom('a') - 1.1) < 1e-6, 'the first pane kept the camera it was given');
  // A second pane changes the first viewport's dimensions. Let its resize
  // observer and camera event publish before taking the saved snapshot.
  await settle(page);

  // The file goes with its Display settings open.
  await displayButton(first).click();
  await display.waitFor();
  await page.evaluate(() => window.cadHarness.mounted(false));
  await display.waitFor({ state: 'detached' });
  await first.locator('[data-slot="cad-file-view"]').waitFor({ state: 'detached' });
  // Unmount persists the display settings and the camera, under the file and the renderer.
  const before = await page.evaluate(() => window.cadHarness.state);
  assert.deepEqual(Object.keys(before.renderers), [JSON.stringify(['part.stl', 'mesh'])], 'one record per file, keyed [path, renderer id]');
  for (const saved of Object.values(before.renderers)) assert.ok(Math.abs(saved.camera.zoom - 1.1) < 1e-6, `the camera is persisted: ${JSON.stringify(saved.camera)}`);
  await page.evaluate(() => window.cadHarness.mounted(true));
  // Whether the panel is open is transient, not file state.
  await displayButton(first).waitFor();
  assert.equal(await display.count(), 0, 'the remounted file opens with its Display settings shut');
  assert.equal(await displayButton(first).getAttribute('aria-pressed'), 'false');
  // The pane remounts before the viewport adopts the mesh and publishes its restored
  // camera. Wait for the actual presented frame, not an arbitrary settling delay.
  await page.waitForFunction(() => {
    const pane = document.querySelector('[data-testid="one"]');
    return pane?.querySelector('[aria-busy="false"] canvas') &&
      !pane.querySelector('[data-viewer-transition], [data-viewer-loading]');
  });
  // The remount opens at the camera it was left at, not a fresh fit, and the record is unchanged.
  await page.waitForFunction(() => Math.abs((window.cadHarness.a.controller.readState().camera?.zoom ?? 0) - 1.1) < 1e-6);
  const after = await page.evaluate(() => window.cadHarness.state);
  assert.deepEqual(structuredClone(after.renderers), structuredClone(before.renderers));
  assert.equal(requests.filter((path) => path === '/one/mesh.stl').length, 1, 'reopening a file reuses its decoded mesh without another asset request');

  // The live canvas at Retina: a drag drops the drawing buffer to the interaction pixel ratio
  // and its end restores it. Every buffer that clears is drawn again in the same task.
  const canvas = first.locator('[aria-busy] > div > canvas').first();
  await canvas.evaluate(node => { window.cadHarnessView = { canvas: node }; });
  const box = await canvas.boundingBox();
  const idleWidth = await canvas.evaluate(node => node.width);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 20, { steps: 4 });
  await page.mouse.up();
  // Back at the idle ratio, whatever the drag did to it.
  await page.waitForFunction(width => document.querySelector('[data-testid="one"] [aria-busy] > div > canvas').width === width, idleWidth);
  await settle(page);
  const clears = await page.evaluate(() => window.cadBufferClears);
  // A software renderer never changes its pixel ratio, so there is no Retina resize to exercise.
  if (!(await softwareWebGl(page))) assert.ok(clears.length > 0, 'exercise actual Retina buffer resizes');
  assert.ok(clears.every(clear => clear.redrawn), 'no cleared framebuffer is left waiting for a later draw');
  assert.deepEqual(errors, []);
});

test('a viewport that goes loses its WebGL context and leaves no listener on the page, and a context recovery hands over to a fresh one', async (t) => {
  const origin = await serve(t, (url, root, response) => {
    if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: [{ kind: 'stl', file: 'part.stl', rootRelativeFile: 'part.stl', url: '/mesh.stl', hash: root, bytes: mesh.length }] }));
      return true;
    }
    if (url.pathname.endsWith('/mesh.stl')) { response.end(mesh); return true; }
    return false;
  });
  const { page, errors } = await newPage(t);
  await page.addInitScript(() => {
    window.Worker = undefined;
    // Every WebGL context the page makes, held weakly, and the keydown listeners on the window and
    // the document, counted as the DOM keeps them (one per listener and capture flag).
    const contexts = [];
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
      const context = getContext.call(this, type, ...rest);
      if (context && /webgl/.test(type) && !contexts.some(ref => ref.deref() === context)) contexts.push(new WeakRef(context));
      return context;
    };
    // Oldest first: lost, or collected (true); live (false).
    window.cadContextsLost = () => contexts.map(ref => ref.deref()?.isContextLost() ?? true);
    const keydown = new Set(), ids = new WeakMap();
    let next = 0;
    const key = (target, listener, options) => {
      if (!ids.has(listener)) ids.set(listener, next += 1);
      return `${target === window ? 'window' : 'document'}:${ids.get(listener)}:${typeof options === 'boolean' ? options : options?.capture === true}`;
    };
    const { addEventListener, removeEventListener } = EventTarget.prototype;
    EventTarget.prototype.addEventListener = function (type, listener, options) {
      if (type === 'keydown' && listener && (this === window || this === document)) keydown.add(key(this, listener, options));
      return addEventListener.call(this, type, listener, options);
    };
    EventTarget.prototype.removeEventListener = function (type, listener, options) {
      if (type === 'keydown' && listener && (this === window || this === document)) keydown.delete(key(this, listener, options));
      return removeEventListener.call(this, type, listener, options);
    };
    window.cadKeydownListeners = () => keydown.size;
  });
  await page.goto(`${origin}/`);
  const shown = () => page.waitForFunction(() => window.cadHarness?.a?.controller?.readState().loading === false
    && !!document.querySelector('[data-testid="one"] [aria-busy="false"] canvas'));
  const gone = () => page.waitForFunction(() => !document.querySelector('[data-testid="one"] canvas'));
  // A teardown finishes after React has taken the view off the page, so the expected contexts are
  // awaited before the state is read.
  const state = async (expected) => {
    await page.waitForFunction(lost => JSON.stringify(window.cadContextsLost()) === JSON.stringify(lost), expected).catch(() => {});
    return page.evaluate(() => ({ contexts: window.cadContextsLost(), keydown: window.cadKeydownListeners() }));
  };
  await shown();
  const keydown = await page.evaluate(() => window.cadKeydownListeners());
  assert.deepEqual(await state([false]), { contexts: [false], keydown });

  // A file switch, or a library card pictured: the view goes and another comes. Every one that went
  // has lost its context, the GPU memory with it, and the page keeps no listener of its controls.
  for (let remount = 1; remount <= 3; remount += 1) {
    await page.evaluate(() => window.cadHarness.mounted(false));
    await gone();
    await page.evaluate(() => window.cadHarness.mounted(true));
    await shown();
    const contexts = [...Array(remount).fill(true), false];
    assert.deepEqual(await state(contexts), { contexts, keydown },
      `after remount ${remount}: the views that went have lost their contexts, and the page holds one view's listeners`);
  }

  // A context RECOVERY replaces the runtime under a view that stays: the next one draws in a
  // context of its own, and the one it replaced goes as any other does, its listeners with it.
  const recovered = page.evaluate(() => new Promise(resolve => {
    const canvas = document.querySelector('[data-testid="one"] [aria-busy="false"] canvas');
    const extension = canvas.getContext('webgl2').getExtension('WEBGL_lose_context');
    canvas.addEventListener('webglcontextlost', () => setTimeout(() => { extension.restoreContext(); resolve(); }), { once: true });
    extension.loseContext();
  }));
  await recovered;
  await page.waitForFunction(() => window.cadContextsLost().length === 5);
  await shown();
  assert.deepEqual(await state([true, true, true, true, false]), { contexts: [true, true, true, true, false], keydown },
    'the recovered view draws in a fresh context, and the one it replaced is lost');
  // And the fresh one is a viewer: the camera orbits under a drag.
  const before = await page.evaluate(() => window.__cadCamera().position);
  const box = await page.getByTestId('one').locator('[aria-busy="false"] > div > canvas').first().boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 20, { steps: 4 });
  await page.mouse.up();
  await page.waitForFunction(start => window.__cadCamera().position.some((value, index) => Math.abs(value - start[index]) > 1e-3), before);

  // The last view goes: every context is lost, and no test seam keeps a runtime on the window.
  await page.evaluate(() => window.cadHarness.mounted(false));
  await gone();
  assert.deepEqual((await state([true, true, true, true, true])).contexts, [true, true, true, true, true]);
  assert.deepEqual(await page.evaluate(() => [typeof window.__cadCamera, typeof window.__cadStage]), ['undefined', 'undefined']);
  assert.deepEqual(errors, []);
});

// A wide, flat box: the shape whose fit is decided by its WIDTH against the viewport's
// aspect, so a fit taken under the wrong lens or the wrong canvas shows up immediately.
// (A tall or cubic model is fitted by its height and hides the difference entirely.)
const WIDE_CORNERS = [[0, 0, 0], [140, 0, 0], [140, 80, 0], [0, 80, 0], [0, 0, 2], [140, 0, 2], [140, 80, 2], [0, 80, 2]];
const WIDE_TRIANGLES = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]];
const widePlate = `solid plate\n${WIDE_TRIANGLES.map(triangle =>
  `facet normal 0 0 0\nouter loop\n${triangle.map(index => `vertex ${WIDE_CORNERS[index].join(' ')}`).join('\n')}\nendloop\nendfacet`
).join('\n')}\nendsolid plate\n`;

test('a file opens framed at 100% of its own ruler: the open fit is the fit, whatever lens it was taken under', async (t) => {
  const origin = await serve(t, (url, root, response) => {
    if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: [
        { kind: 'stl', file: 'plate.stl', rootRelativeFile: 'plate.stl', url: '/plate.stl', hash: root, bytes: widePlate.length }] }));
      return true;
    }
    if (url.pathname.endsWith('/plate.stl')) { response.end(widePlate); return true; }
    return false;
  });
  const { page, errors } = await newPage(t);
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`${origin}/?file=plate.stl`);
  const pane = page.getByTestId('one');
  await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await settle(page);

  const opened = await page.evaluate(() => {
    const camera = window.__cadCamera();
    const canvas = document.querySelector('[data-testid="one"] [aria-busy] > div > canvas');
    return { projection: camera.projection, halfHeight: camera.halfHeight, zoomPercent: camera.zoomPercent,
      bounds: camera.originalBounds, aspect: canvas.clientWidth / canvas.clientHeight };
  });
  assert.equal(opened.projection, 'orthographic');
  // 100% means "framed as the file opens". It is a ruler the viewport computes independently
  // of the fit, so the two agreeing is the whole claim: a fit taken under the opening
  // PERSPECTIVE lens and then converted to orthographic used to land near 89% of it.
  assert.equal(Math.round(opened.zoomPercent), 100, `opened at ${opened.zoomPercent}% of its own ruler`);
  // And it is the half-height the fit mathematics gives for this box at the REAL canvas aspect.
  const expected = interactiveCameraFrameForBounds(THREE, {
    camera: Object.assign(new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 1000), { fov: CAD_DEFAULT_VERTICAL_FOV_DEGREES }),
    controls: { target: new THREE.Vector3() }, bounds: opened.bounds, frameAspect: opened.aspect,
    minRadius: 0, viewDirection: DEFAULT_VIEW_DIRECTION, viewUp: WORLD_UP,
  }).halfHeight;
  assert.ok(Math.abs(opened.halfHeight - expected) / expected < 0.01,
    `framed at the fit for this aspect: ${opened.halfHeight} vs ${expected}`);

  // Home resets the complete view; cube faces keep the current zoom and target.
  const canvas = pane.locator('[aria-busy] > div > canvas').first();
  // The share of the drawn frame that is the model: read the middle/upper canvas region,
  // clear of the bottom prompt action and the viewport controls at the right edge.
  const inkFraction = async () => {
    const png = PNG.sync.read(await canvas.screenshot());
    const background = [png.data[0], png.data[1], png.data[2]];
    const columns = Math.floor(png.width * 0.8);
    const rows = Math.floor(png.height * 0.8);
    let drawn = 0;
    for (let y = 0; y < rows; y += 1) for (let x = 0; x < columns; x += 1) {
      const offset = (y * png.width + x) * 4;
      const delta = Math.abs(png.data[offset] - background[0]) + Math.abs(png.data[offset + 1] - background[1])
        + Math.abs(png.data[offset + 2] - background[2]);
      if (delta > 32) drawn += 1;
    }
    return drawn / (columns * rows);
  };
  const settleInk = async (reached, what) => {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const ink = await inkFraction();
      if (reached(ink)) return ink;
      await settle(page);
    }
    throw new Error(`the drawn frame never ${what}`);
  };
  assert.ok(await settleInk(ink => ink > 0.05, 'showed the plate') > 0.05);
  // Zoomed right in and dragged far off it: the model is no longer on screen.
  await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    const camera = controller.readState().camera;
    await controller.setCamera({ ...camera, target: [camera.target[0] + 4000, camera.target[1] + 4000, camera.target[2]],
      position: [camera.position[0] + 4000, camera.position[1] + 4000, camera.position[2]], zoom: 9 });
  });
  const lost = await settleInk(ink => ink < 0.01, 'emptied when the camera was driven off the model');

  const beforeSnap = await page.evaluate(() => window.__cadCamera());
  await pane.getByRole('button', { name: 'Jump to top view', exact: true }).click();
  await page.waitForFunction(() => { const c = window.__cadCamera(); return Math.hypot(c.position[0] - c.target[0], c.position[1] - c.target[1]) / Math.abs(c.position[2] - c.target[2]) < 0.001; });
  const snapped = await page.evaluate(() => window.__cadCamera());
  snapped.target.forEach((value, index) => assert.ok(Math.abs(value - beforeSnap.target[index]) < 1e-8));
  assert.equal(snapped.zoom, beforeSnap.zoom);
  assert.equal(await pane.getByRole('button', { name: 'Home', exact: true }).count(), 0);
  await page.evaluate(() => window.cadHarness.a.controller.resetCamera());
  const recovered = await settleInk(ink => ink > 0.05, 'Zoom to Fit frames the plate after panning away');
  assert.ok(recovered > lost * 5);
  const fitted = await page.evaluate(() => window.__cadCamera());
  assert.ok(Math.hypot(fitted.position[0] - fitted.target[0], fitted.position[1] - fitted.target[1]) / Math.abs(fitted.position[2] - fitted.target[2]) < 0.001,
    'Zoom to fit retains the top-view orientation');
  assert.deepEqual(errors, []);
});

// A scene a renderer publishes in pieces, under the harness-only renderer over one triangle
// (`renderers/shell-harness`): the viewport draws what has arrived, and frames it once whole.
test('a scene that arrives in place is framed when whole', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`${origin}/?file=one.harness`);
  const pane = page.getByTestId('one');
  const canvasElement = pane.locator('[aria-busy="false"] > div > canvas').first();
  await canvasElement.waitFor();
  // The drawn frame: how much of it is the triangle, and whether it runs off the edge.
  const drawn = async () => {
    const png = PNG.sync.read(await canvasElement.screenshot());
    const { width, height, data } = png;
    const background = [data[8 * 4 * width + 32], data[8 * 4 * width + 33], data[8 * 4 * width + 34]];
    let painted = 0, atEdge = 0;
    for (let y = 0; y < height; y += 2) for (let x = 0; x < width; x += 2) {
      const at = (y * width + x) * 4;
      // The triangle is a flat blue-grey; the grid lines and the axes are thin and sampled away by the solid test.
      const solid = Math.abs(data[at] - background[0]) + Math.abs(data[at + 1] - background[1]) + Math.abs(data[at + 2] - background[2]) > 60
        && data[at + 2] > data[at] + 8;
      if (!solid) continue;
      painted += 1;
      if (x < 6 || y < 6 || x > width - 8 || y > height - 8) atEdge += 1;
    }
    return { painted, atEdge };
  };
  const waitForFrame = async (accept, what) => {
    let last;
    for (let attempt = 0; attempt < 80; attempt += 1) {
      last = await drawn();
      if (accept(last)) return last;
      await settle(page);
    }
    assert.fail(`the drawn frame never ${what}: ${JSON.stringify(last)}`);
  };

  // A SCENE THAT ARRIVES IN PLACE. The same scene identity grows fourfold and says it is not
  // whole yet: the viewport adopts what arrived (it is drawn, larger) but does NOT re-frame,
  // so the triangle runs off the canvas. When the scene says it is whole, it is framed again.
  const opened = await waitForFrame(frame => frame.painted > 500 && frame.atEdge === 0, 'showed the framed triangle');
  const pose = () => page.evaluate(() => { const c = window.__cadCamera(); return [c.position, c.target, c.zoom]; });
  // The opened camera once it is at rest: the same over several frames running.
  await page.waitForFunction(() => new Promise(resolve => {
    let still = 0, last = null;
    const step = () => {
      const c = window.__cadCamera();
      const now = JSON.stringify([c.position, c.target, c.zoom]);
      still = now === last ? still + 1 : 0;
      last = now;
      if (still >= 5) resolve(true); else requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }));
  const openedPose = await pose();
  await pane.locator('[data-harness-arrive="partial"]').click();
  const partial = await waitForFrame(frame => frame.painted > opened.painted * 3 && frame.atEdge > 0,
    'drew the grown scene, unframed, while it was still arriving');
  // Not reframed: the pose is the opened one, to within the float noise of a settled camera
  // (a reframe moves it by the scene's own size, four orders of magnitude more).
  const partialPose = (await pose()).flat();
  openedPose.flat().forEach((value, index) => assert.ok(Math.abs(value - partialPose[index]) < 1e-4,
    `the camera did not move for a partial arrival (${index}: ${value} → ${partialPose[index]})`));
  await pane.locator('[data-harness-arrive="whole"]').click();
  const whole = await waitForFrame(frame => frame.atEdge === 0 && frame.painted > 500 && frame.painted < partial.painted,
    'framed the scene once it was whole');
  assert.ok(Math.abs(whole.painted - opened.painted) < opened.painted * 0.2,
    `the whole scene fills the frame as the first one did: ${JSON.stringify({ opened, whole })}`);
  assert.deepEqual(errors, []);
});

// That second framing is for a camera NOBODY set. A view the person turned with the arrow keys
// while the scene was still arriving is theirs, as a dragged one is, and the whole scene keeps it.
test('a view turned with the arrow keys while a scene arrives is kept when it is whole', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`${origin}/?file=one.harness`);
  const pane = page.getByTestId('one');
  const canvas = pane.locator('[aria-busy="false"] > div > canvas').first();
  await canvas.waitFor();
  const pose = () => page.evaluate(() => { const c = window.__cadCamera(); return [...c.position, ...c.target, c.zoom]; });
  // The camera at rest: the same over several frames running.
  const atRest = () => page.waitForFunction(() => new Promise(resolve => {
    let still = 0, last = null;
    const step = () => {
      const c = window.__cadCamera();
      const now = JSON.stringify([c.position, c.target, c.zoom]);
      still = now === last ? still + 1 : 0;
      last = now;
      if (still >= 5) resolve(true); else requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }));
  await atRest();
  const opened = await pose();
  // Over the viewer, with nothing focused: its arrow keys orbit it. No press, which would be a drag.
  const box = await canvas.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.keyboard.press('ArrowLeft');
  await atRest();
  const turned = await pose();
  assert.ok(turned.some((value, index) => Math.abs(value - opened[index]) > 1e-3), 'the arrow key turned the view');
  await pane.locator('[data-harness-arrive="whole"]').click();
  await page.waitForFunction(() => window.__cadCamera().originalBounds?.max?.[0] === 80);
  await atRest();
  (await pose()).forEach((value, index) => assert.ok(Math.abs(value - turned[index]) < 1e-6,
    `the whole scene kept the turned view (${index}: ${turned[index]} → ${value})`));
  assert.deepEqual(errors, []);
});

test('a renderer says more about its load than a download: finding the file, edit states, a failed update the model survives, the revision on screen, its own snapshot and its own frame', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`${origin}/?file=one.harness`);
  const pane = page.getByTestId('one');
  const canvasElement = pane.locator('[aria-busy="false"] > div > canvas').first();
  const canvas = await canvasElement.boundingBox();
  const middle = { x: canvas.x + canvas.width / 2, y: canvas.y + canvas.height / 2 };
  const stage = name => pane.locator(`[data-harness-stage="${name}"]`).click();
  // What the shell draws over the viewport about a load: the overlay that covers a model
  // still opening, and the card for an alert. Nothing is drawn beside the filename any more.
  const overlay = pane.locator('[data-viewer-loading]');
  const card = pane.getByRole('alert');
  // The DRAWN frame, and how much of it is the triangle: its lit blue-grey, counted below the
  // harness's own controls along the top, and outside `hole` (a box in canvas pixels).
  const shot = async () => PNG.sync.read(await canvasElement.screenshot());
  // The frame once it shows what `accept` asks of it: never the one frame after a change.
  const shotWhere = async (accept, what) => {
    let last;
    for (let attempt = 0; attempt < 60; attempt += 1) {
      last = await shot();
      if (accept(last)) return last;
      await settle(page);
    }
    assert.fail(`the drawn frame never ${what}`);
  };
  // The frame at rest: the same picture twice running.
  const stillShot = async () => {
    let last = await canvasElement.screenshot();
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await settle(page);
      const next = await canvasElement.screenshot();
      if (next.equals(last)) return PNG.sync.read(next);
      last = next;
    }
    assert.fail('the drawn frame never came to rest');
  };
  const triangle = ({ width, height, data }, hole = null) => {
    let count = 0;
    for (let y = 48; y < height; y += 2) for (let x = 0; x < width; x += 2) {
      if (hole && x >= hole.x0 && x <= hole.x1 && y >= hole.y0 && y <= hole.y1) continue;
      const at = (y * width + x) * 4;
      if (data[at] + data[at + 1] + data[at + 2] > 250 && data[at + 2] > data[at] + 8) count += 1;
    }
    return count;
  };

  // THE FRAME IS THE RENDERER'S TO WRAP. Its own context reaches the frame — and
  // it is above the frame, so it is there before anything the renderer draws in it.
  assert.equal(await pane.locator('[data-harness-frame-context]').innerText(), 'frame:idle');

  // A LOAD THAT IS ONLY A DOWNLOAD SAYS NOTHING. Nothing of the load's extras is
  // passed, and nothing covers the model or stands over it.
  assert.equal(await overlay.count(), 0, 'a plain load covers nothing');
  assert.equal(await card.count(), 0, 'and raises nothing');

  // THE CUBE IS THE BOTTOM-LEFT CORNER'S, far enough off the bottom that its axes stay inside the
  // view, and the tool stack stops above it. Display is the strip's; the view's control, Preview,
  // is the navbar's. The right of the view is Quick Edit's, and the bottom middle the host's (a
  // composer, on some) and preview's playbar.
  const frameBox = await canvasElement.boundingBox();
  const cubeBox = await pane.getByLabel('View cube', { exact: true }).boundingBox();
  const stackBox = await pane.locator('[data-cad-tool-groups]').boundingBox();
  const offBottom = frameBox.y + frameBox.height - cubeBox.y - cubeBox.height;
  assert.ok(offBottom >= 6 && offBottom < 16, `the view cube sits just off the bottom-left corner: ${offBottom}px`);
  assert.ok(cubeBox.x < frameBox.x + 20, 'the view cube stays against the left edge');
  assert.ok(stackBox.y + stackBox.height <= cubeBox.y, 'the tool stack stops above the cube');
  assert.equal(await pane.locator('[data-viewer-navbar]').getByRole('button', { name: 'Preview', exact: true }).count(), 1, 'Preview is in the navbar');
  assert.equal(await pane.locator('[data-cad-toolbar]').getByRole('button', { name: 'Display', exact: true }).count(), 1, 'Display is on the strip');

  // FINDING: the wait before the file is even located covers the viewport, and says
  // so as such rather than as a phase of reading it.
  await stage('finding');
  await overlay.waitFor();
  assert.match(await overlay.innerText(), /Finding file/);
  assert.equal(await pane.locator('[data-harness-frame-context]').innerText(), 'frame:finding');

  // AN EDIT OF THE PERSON'S OWN is a wait with nothing downloading, and the model it
  // edits stays on screen: nothing covers it. The corner says the model is catching up.
  const updating = pane.locator('[data-view-update-status]');
  await stage('editing');
  await overlay.waitFor({ state: 'detached' });
  assert.equal(await card.count(), 0);
  await updating.waitFor();
  assert.match(await updating.innerText(), /Updating model/);
  const updateBox = await updating.boundingBox();
  const toolsBox = await pane.getByRole('group', { name: 'Interaction tools' }).boundingBox();
  const middleY = box => box.y + box.height / 2;
  assert.ok(Math.abs(middleY(updateBox) - middleY(toolsBox)) < 1,
    `model update status is vertically centred with the tool strip: ${JSON.stringify({ updateBox, toolsBox })}`);

  // THE BUILD ENDING ENDS IT: the saved file is on screen, so the wait is over.
  await stage('idle');
  await updating.waitFor({ state: 'detached' });
  const settled = await stillShot();
  assert.deepEqual([await overlay.count(), await card.count()], [0, 0]);
  const whole = triangle(settled);
  assert.ok(whole > 500, `the triangle is drawn: ${whole} samples of it`);

  // A FAILED UPDATE THE MODEL SURVIVES is an error, and the viewport is where it is said:
  // a card over the model — which is still drawn around it, neither blanked nor covered.
  await stage('failed');
  await card.waitFor();
  const said = await card.innerText();
  assert.match(said, /Harness update failed/);
  assert.match(said, /The existing model remains visible/);
  assert.equal(await overlay.count(), 0, 'it is not a load: nothing covers the model');
  const [canvasBox, cardBox] = [await canvasElement.boundingBox(), await card.boundingBox()];
  const hole = { x0: cardBox.x - canvasBox.x - 4, y0: cardBox.y - canvasBox.y - 4,
    x1: cardBox.x - canvasBox.x + cardBox.width + 4, y1: cardBox.y - canvasBox.y + cardBox.height + 4 };
  const around = triangle(settled, hole);
  assert.ok(around > 200, `there is triangle to see around the card: ${around}`);
  const survived = triangle(await shot(), hole);
  assert.ok(Math.abs(survived - around) <= around * 0.05, `and it is still drawn there: ${survived} of ${around}`);
  // DISMISS puts the card away, since the previous version is there to use: the card goes
  // and the whole model is on screen again.
  await card.getByRole('button', { name: 'Dismiss', exact: true }).click();
  await card.waitFor({ state: 'detached' });
  await shotWhere(frame => Math.abs(triangle(frame) - whole) <= whole * 0.05, 'showed the whole triangle under where the card was');
  // It stays put away while that alert stands; once the alert clears, the same failure
  // raised again (a retry that failed the same way) is shown again.
  await settle(page);
  assert.equal(await card.count(), 0, 'dismissed while the same alert stands');
  await stage('idle');
  await settle(page);
  assert.equal(await card.count(), 0);
  await stage('failed');
  await card.waitFor();
  assert.match(await card.innerText(), /Harness update failed/);
  await stage('idle');
  await card.waitFor({ state: 'detached' });

  // THE REVISION ON SCREEN. Live state reports what is being SHOWN, which a renderer
  // holding a predecessor over a rebuild knows and the shell does not.
  const shown = () => page.evaluate(() => { const s = window.cadHarness.a.controller.readState(); return [s.revision, s.resource.revision]; });
  assert.deepEqual(await shown(), ['harness', 'harness']);
  await pane.locator('[data-harness-shown-revision]').click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().revision === 'shown-revision');
  assert.deepEqual(await shown(), ['shown-revision', 'shown-revision'], 'both halves name the revision on screen');

  // THE SNAPSHOT IS THE RENDERER'S TO ASSEMBLE. Its own reference vocabulary goes
  // through its own builder — and the resource it names is the one on screen.
  const before = await page.evaluate(() => window.cadHarness.captures.length);
  await page.evaluate(() => window.cadHarness.capture());
  await page.waitForFunction(count => window.cadHarness.captures.length > count, before);
  assert.deepEqual(await page.evaluate(() => {
    const context = window.cadHarness.captures.at(-1);
    return [context.type, context.references.map(reference => reference.resource.revision)];
  }), ['image/png', ['shown-revision']]);
  await pane.locator('[data-harness-shown-revision]').click();

  // A PRESS ON THE MODEL is the renderer's to hear: it puts down what it was
  // showing about something else before the viewport sees the press at all.
  assert.equal(await pane.locator('[data-harness-put-down]').innerText(), '');
  await page.mouse.click(middle.x, middle.y);
  await page.waitForFunction(() => document.querySelector('[data-harness-put-down]')?.textContent === 'put down @idle');
  // And the frame still takes focus on that same press, as it always did.
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.slot), 'cad-file-view');

  // Quick Edit is nowhere until something is picked; then it takes the top-right corner, 15rem
  // wide, and its own corner sizes it: wider to the left, and its note taller than the 10rem it
  // grows to with what is written. The box keeps up with the corner, a frame after each move.
  const quickEdit = pane.getByRole('region', { name: 'Quick Edit', exact: true });
  assert.equal(await pane.locator('[data-quick-edit-box]').count(), 0, 'nothing picked: no Quick Edit, not even a button');
  await canvasElement.click({ button: 'right', position: { x: 300, y: 200 } });
  await page.getByRole('menuitem', { name: 'Note the press', exact: true }).click();
  await quickEdit.waitFor();
  await quickEdit.evaluate(node => Promise.all(node.getAnimations().map(animation => animation.finished)));
  const opened = await quickEdit.boundingBox();
  assert.ok(opened.x + opened.width > frameBox.x + frameBox.width - 20 && opened.y < frameBox.y + 20,
    `Quick Edit takes the top-right corner: ${JSON.stringify([opened, frameBox])}`);
  assert.equal(Math.round(opened.width), 240);
  const note = quickEdit.getByRole('textbox', { name: 'Describe your changes', exact: true });
  const noteHeight = (await note.boundingBox()).height;
  const corner = await quickEdit.locator('[data-quick-edit-resize]').boundingBox();
  const grip = { x: corner.x + corner.width / 2, y: corner.y + corner.height / 2 };
  await page.mouse.move(grip.x, grip.y);
  await page.mouse.down();
  await page.mouse.move(grip.x - 30, grip.y + 60, { steps: 2 });
  await settle(page);
  const midway = (await quickEdit.boundingBox()).width;
  assert.ok(Math.abs(midway - opened.width - 30) <= 1, `mid-drag, the box is where its corner is: ${opened.width} -> ${midway}`);
  await page.mouse.move(grip.x - 60, grip.y + 120, { steps: 2 });
  await page.mouse.up();
  const resized = await quickEdit.boundingBox();
  assert.ok(Math.abs(resized.width - opened.width - 60) <= 1, `dragged out 60px: ${opened.width} -> ${resized.width}`);
  const noteResized = (await note.boundingBox()).height;
  assert.ok(noteResized > 160 && Math.abs(noteResized - noteHeight - 120) <= 1, `and its note 120px down: ${noteHeight} -> ${noteResized}`);
  assert.ok(Math.abs(resized.x + resized.width - opened.x - opened.width) < 1, 'still hanging from the same corner');
  await quickEdit.getByRole('button', { name: 'Close Quick Edit', exact: true }).click();
  await quickEdit.waitFor({ state: 'detached' });
  assert.deepEqual(errors, []);
});
