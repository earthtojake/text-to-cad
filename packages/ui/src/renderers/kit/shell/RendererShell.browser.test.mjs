import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';
import * as THREE from 'three';
import { interactiveCameraFrameForBounds } from '../../../../dist/renderers/kit/camera/viewportCameraFit.js';
import { DEFAULT_VIEW_DIRECTION, WORLD_UP } from '../../../../dist/renderers/kit/camera/viewportCameraKit.js';
import { CAD_DEFAULT_VERTICAL_FOV_DEGREES } from '../../../../dist/renderers/kit/camera/cameraLens.js';

// The shell end to end, in a real browser, under the smallest renderer that mounts it: a
// one-triangle mesh file. Everything asserted here is the shell's (kit/shell), so it holds
// for every renderer built on it. Inline fixture bytes are served in memory with a private
// temporary harness.
const mesh = 'solid triangle\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 20 0 0\nvertex 0 20 0\nendloop\nendfacet\nendsolid triangle\n';

test('a shell renderer resolves deferred files, reuses warm assets, restores isolated view state and edits settings on the live canvas', async (t) => {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-cad-browser-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise((resolve) => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('../../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const compiledCss = await readFile(new URL('../../../../dist/styles.css', import.meta.url));
  const requests = [];
  const catalogFiles = [];
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    requests.push(url.pathname);
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(compiledCss); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      catalogFiles.push({ root, file: url.searchParams.get('file') });
      const entry = url.searchParams.get('file') === 'part.stl'
        ? { kind: 'stl', file: 'part.stl', rootRelativeFile: 'part.stl', url: '/mesh.stl', hash: root, bytes: mesh.length }
        : { file: 'part.stl', rootRelativeFile: 'part.stl', catalogPending: true };
      response.end(JSON.stringify({ rootId: root, entries: [entry] }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else if (url.pathname.endsWith('/mesh.stl')) { response.end(mesh); }
    else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: process.platform === 'darwin'
    ? ['--use-angle=metal']
    : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });
  page.setDefaultTimeout(10000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
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
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const first = page.getByTestId('one');
  const ensureInspector = async pane => {
    if (!await pane.locator('[data-file-sheet-header]').isVisible()) {
      await pane.getByRole('button', { name: 'Inspector', exact: true }).click();
    }
  };
  const zoomAction = async name => {
    await ensureInspector(first);
    await first.getByRole('button', { name: 'Zoom controls', exact: true }).click();
    await page.getByRole('menuitem', { name, exact: true }).click();
    await page.getByRole('menu').waitFor({ state: 'detached' });
  };
  await ensureInspector(first);

  await first.getByLabel('Zoom level percent', { exact: true }).waitFor().catch(async (error) => { throw new Error(`${error.message}; page errors: ${errors.join('; ')}; body: ${await page.locator("body").innerText()}; requests: ${requests.join(", ")}`); });
  await page.waitForFunction(() => Object.keys(window.cadHarness.state.renderers || {}).length > 0);
  assert.deepEqual(errors, []);
  assert.equal(await page.title(), 'Host title');
  await zoomAction('Zoom in');
  await page.waitForFunction(() => document.querySelector('[aria-label="Zoom level percent"]')?.textContent !== '100%');
  await ensureInspector(first);
  await first.locator('[data-file-sheet="STL"]').waitFor();
  assert.equal(await first.getByRole('button', { name: 'Theme settings', exact: true }).count(), 0);
  assert.equal(await first.locator('[data-file-sheet="Theme"]').count(), 0);
  await first.getByRole('button', { name: 'Inspector', exact: true }).click();
  await first.getByRole('button', { name: 'Take snapshot', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  const captured = await page.evaluate(() => window.cadHarness.captures[0]);
  assert.equal(captured.file, 'part.stl');
  assert.equal(captured.type, 'image/png');
  assert.ok(captured.size > 100);
  assert.equal(captured.references.length, 1);
  assert.deepEqual(captured.references[0].target, { kind: 'whole-resource' });
  assert.equal(captured.references[0].resource.workspaceId, 'one');
  assert.equal(captured.references[0].resource.path, 'part.stl');
  assert.equal(await first.locator('[data-file-sheet="STL"]').count(), 0);
  // A mesh hands the shell no tools, so there is no strip over its viewport at
  // all: orbit, pan and zoom, and nothing to take up.
  assert.equal(await first.getByRole('group', { name: 'Interaction tools' }).count(), 0, 'no tools, no strip');
  for (const name of ['Orbit', 'Draw', 'Select', 'Measure', 'Pose', 'Animate']) {
    assert.equal(await first.getByRole('button', { name, exact: true }).count(), 0, name);
  }
  // Nor a menu of its own on a secondary press — and the browser's own is still
  // kept off the canvas, so the press is the camera's and nothing else.
  const canvasBox = await first.locator('[aria-busy] > div > canvas').first().boundingBox();
  await page.evaluate(() => {
    window.nativeMenu = [];
    window.addEventListener('contextmenu', event => window.nativeMenu.push(event.defaultPrevented), true);
    document.addEventListener('contextmenu', event => window.nativeMenu.push(event.defaultPrevented));
  });
  await page.mouse.click(canvasBox.x + canvasBox.width / 2, canvasBox.y + canvasBox.height / 2, { button: 'right' });
  await page.waitForTimeout(200);
  assert.equal(await page.getByRole('menu').count(), 0, 'a mesh viewport opens no menu');
  assert.deepEqual(await page.evaluate(() => window.nativeMenu), [false, true],
    'the event reaches the canvas and leaves it prevented: no native menu either');
  await first.getByRole('button', { name: 'Inspector', exact: true }).click();
  await zoomAction('Reset Zoom');
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-label="Zoom level percent"]')?.textContent === '100%');
  await zoomAction('Zoom in');
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [aria-label="Zoom level percent"]')?.textContent === '110%');
  await page.evaluate(() => window.cadHarness.second(true));
  await ensureInspector(page.getByTestId('two'));
  await page.getByTestId('two').getByLabel('Zoom level percent', { exact: true }).waitFor();
  assert.equal(await page.getByTestId('two').getByLabel('Zoom level percent', { exact: true }).innerText(), '100%');
  assert.ok(requests.includes('/one/mesh.stl'));
  assert.ok(requests.includes('/two/mesh.stl'));
  assert.ok(catalogFiles.some(({ root, file }) => root === 'one' && file === 'part.stl'));
  assert.ok(catalogFiles.some(({ root, file }) => root === 'two' && file === 'part.stl'));
  assert.equal(await first.getByLabel('Zoom level percent', { exact: true }).innerText(), '110%');
  // A second pane changes the first viewport's dimensions. Let its resize
  // observer and camera event publish before taking the saved snapshot.
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.evaluate(() => window.cadHarness.mounted(false));
  await first.locator('[data-slot="cad-file-view"]').waitFor({ state: 'detached' });
  // Camera persistence is debounced during interaction and synchronously
  // flushed on unmount. Compare the outgoing flush, not an earlier snapshot
  // that can still contain null cameras while the rendered zoom is already 110%.
  const before = await page.evaluate(() => window.cadHarness.state);
  assert.deepEqual(Object.keys(before.renderers), [JSON.stringify(['part.stl', 'mesh'])], 'one record per file, keyed [path, renderer id]');
  for (const saved of Object.values(before.renderers)) assert.ok(saved.camera, 'unmount flushes the outgoing camera');
  await page.evaluate(() => window.cadHarness.mounted(true));
  await first.getByLabel('Zoom level percent', { exact: true }).waitFor();
  // The toolbar mounts with its default 100% before the viewport adopts the mesh
  // and publishes its restored camera. Wait for the actual presented frame,
  // not for the expected zoom value or an arbitrary settling delay.
  const restoreDiagnostic = await page.evaluate(() => {
    const pane = document.querySelector('[data-testid="one"]');
    const state = Object.values(window.cadHarness.state.renderers || {})[0];
    return { zoom: pane.querySelector('[aria-label="Zoom level percent"]')?.textContent,
      busy: pane.querySelector('[aria-busy]')?.getAttribute('aria-busy'),
      savedCamera: state?.camera };
  });
  await page.waitForFunction(() => {
    const pane = document.querySelector('[data-testid="one"]');
    return pane?.querySelector('[aria-busy="false"] canvas') &&
      !pane.querySelector('[data-viewer-transition], [data-file-status] .animate-spin');
  });
  t.diagnostic(`Remount camera readiness: ${JSON.stringify({ ...restoreDiagnostic,
    presentedZoom: await first.getByLabel('Zoom level percent', { exact: true }).innerText() })}`);
  // Serialized camera state restores in its file session; a sibling renderer
  // still opens at its own default zoom. Runtime-only scope is not persisted.
  assert.equal(await first.getByLabel('Zoom level percent', { exact: true }).innerText(), '110%');
  const after = await page.evaluate(() => window.cadHarness.state);
  const previousState = structuredClone(before.renderers);
  const restoredState = structuredClone(after.renderers);
  for (const key of Object.keys(previousState)) {
    const previousCamera = previousState[key].camera;
    const restoredCamera = restoredState[key].camera;
    for (const field of ['position', 'target', 'up']) {
      assert.equal(restoredCamera[field].length, previousCamera[field].length);
      restoredCamera[field].forEach((value, index) => assert.ok(Math.abs(value - previousCamera[field][index]) < 1e-9, `${field}[${index}] was restored`));
    }
    assert.equal(restoredCamera.zoom, previousCamera.zoom);
    assert.equal(restoredCamera.projection, previousCamera.projection);
    // Focal/frustum measurements are regenerated by the mounted viewport.
    // Pose, projection and user zoom are the durable camera contract; everything
    // else in the record must remain byte-for-byte equivalent.
    assert.ok(restoredCamera.focalLength > 0);
    assert.ok(restoredCamera.orthographicHalfHeight > 0);
    delete previousState[key].camera; delete restoredState[key].camera;
  }
  assert.deepEqual(restoredState, previousState);
  assert.equal(requests.filter((path) => path === '/one/mesh.stl').length, 1, 'reopening a file reuses its decoded mesh without another asset request');
  // Presets and settings edit the live renderer; no replacement canvas, hidden
  // canvas or opening overlay may appear, even transiently between assertions.
  await page.evaluate(() => {
    const pane = document.querySelector('[data-testid="one"]');
    const canvas = pane.querySelector('[aria-busy] > div > canvas');
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error('Missing live WebGL canvas');
    window.cadHarnessView = { canvas, interruptions: [] };
    const observer = new MutationObserver(records => {
      for (const record of records) {
        if (record.type === 'childList') {
          for (const node of record.removedNodes) {
            if (node === canvas || node.contains?.(canvas)) window.cadHarnessView.interruptions.push('canvas removed');
          }
          for (const node of record.addedNodes) {
            if (node.matches?.('[data-viewer-transition]') || node.querySelector?.('[data-viewer-transition]')) window.cadHarnessView.interruptions.push('opening overlay');
          }
        }
        if (record.target === canvas && (canvas.style.visibility === 'hidden' || /visibility:\s*hidden/.test(record.oldValue || ''))) {
          window.cadHarnessView.interruptions.push('canvas hidden');
        }
      }
    });
    observer.observe(pane, { subtree: true, childList: true, attributes: true, attributeFilter: ['style'], attributeOldValue: true });
  });
  await ensureInspector(first);
  // A mesh Inspector is Display alone, drawn as the one selected tab every Inspector has.
  assert.deepEqual(await first.getByRole('tab').evaluateAll(tabs => tabs.map(tab => [tab.textContent, tab.getAttribute('aria-selected')])), [['Display', 'true']]);
  const modeRegion = first.getByRole('region', { name: 'Mode', exact: true });
  assert.equal(await modeRegion.getByRole('slider').count(), 0);
  // The fixture is a mesh: no parts to explode, no solid to section and no CAD edges, so
  // the View tab offers none of those sections, by heading, gate or title button.
  for (const title of ['Explode', 'Clip', 'Edges']) {
    assert.equal(await first.getByRole('region', { name: title, exact: true }).count(), 0, `a mesh has no ${title} section`);
    assert.equal(await first.getByRole('heading', { name: title, exact: true }).count(), 0, `a mesh has no ${title} heading`);
    assert.equal(await first.getByRole('button', { name: new RegExp(`^(?:(?:Enable|Disable) )?${title}$`) }).count(), 0, `a mesh has no ${title} button`);
  }
  // The same queries do find a gate the mesh has (its title button and its plus), so the zeros above mean absence.
  assert.equal(await first.getByRole('heading', { name: 'Floor', exact: true }).count(), 1);
  assert.equal(await first.getByRole('button', { name: /^(?:(?:Enable|Disable) )?Floor$/ }).count(), 2);
  assert.equal(await first.getByLabel('Explode value', { exact: true }).count(), 0);
  assert.equal(await first.getByLabel(/^Clip [XYZ] position$/).count(), 0);
  // A gate opens its section at the defaults; its controls do not exist while it is off.
  assert.equal(await first.getByLabel('Exposure value', { exact: true }).count(), 0);
  await first.getByRole('button', { name: 'Enable Lighting', exact: true }).click();
  assert.equal(await first.getByLabel('Exposure value', { exact: true }).inputValue(), '0.0 EV');
  await first.getByRole('button', { name: 'Disable Lighting', exact: true }).click();
  assert.equal(await first.getByLabel('Exposure value', { exact: true }).count(), 0);
  assert.equal(await first.getByRole('button', { name: /(?:Enable|Disable) Surfaces/ }).count(), 0);
  assert.equal(await first.getByRole('region', { name: 'Camera', exact: true }).count(), 0);
  assert.ok((await modeRegion.boundingBox()).height <= 69);
  const modeWidth = (await modeRegion.getByRole('combobox', { name: 'Mode', exact: true }).boundingBox()).width;
  const projectionWidth = (await modeRegion.getByRole('combobox', { name: 'Projection', exact: true }).boundingBox()).width;
  assert.ok(Math.abs(modeWidth - projectionWidth) < 1, 'Mode and Projection have equal widths');
  // The fixture is a mesh: no CAD edges, so no Edges section and no presets made of edges.
  assert.equal(await first.getByRole('combobox', { name: 'Edge visibility', exact: true }).count(), 0);
  assert.equal(await first.getByRole('region', { name: 'Edges', exact: true }).count(), 0);
  for (const [left, right] of [['Surface style', 'Parts']]) {
    const a = await first.getByRole('combobox', { name: left, exact: true }).boundingBox();
    const b = await first.getByLabel(right, { exact: true }).boundingBox();
    assert.ok(Math.abs(a.y - b.y) <= 1 && b.x > a.x, `${left} and ${right} share one compact row`);
  }
  // Human-paced pointing/clicking: the old toggle turned from plus to minus
  // during the hover dwell and immediately closed the section on mouse-up.
  // Floor is the gate a mesh still has that Solid leaves off, as Clip was.
  const floorPlus = first.getByRole('button', { name: 'Enable Floor', exact: true });
  await floorPlus.hover();
  await page.waitForTimeout(200);
  assert.equal(await floorPlus.count(), 1, 'hovering the action cannot change what its click means');
  await floorPlus.click({ delay: 200 });
  await page.waitForFunction(() => Object.values(window.cadHarness.state.renderers || {}).some(saved => saved.display?.floor?.enabled));
  await first.getByRole('button', { name: 'Disable Floor', exact: true }).click();
  await page.waitForTimeout(200);
  assert.equal(await first.getByRole('button', { name: 'Enable Floor', exact: true }).count(), 1, 'collapse does not immediately re-enable under the pointer');
  await first.getByRole('button', { name: 'Floor', exact: true }).hover();
  await page.waitForTimeout(250);
  assert.equal(await floorPlus.count(), 1, 'resting on the section title cannot enable Floor');
  await first.getByRole('button', { name: 'Floor', exact: true }).click();
  assert.ok((await first.getByRole('region', { name: 'Floor', exact: true }).boundingBox()).height <= 69);
  assert.equal(await first.getByRole('combobox', { name: 'Floor position', exact: true }).innerText(), 'Model origin');
  await first.getByRole('button', { name: 'Disable Floor', exact: true }).click();
  assert.deepEqual(await page.evaluate(() => window.cadHarness.a.controller.readState().display.floor), { enabled: false });
  // A guide's paint is a settings-only edit: it reaches the saved state without a scene sync.
  // The floor is scene content, so its gate above does sync; let that land first.
  const settledSceneSyncs = () => page.evaluate(async () => {
    for (let count = -1; count !== window.__viewerSurfaceLooks.count;) {
      count = window.__viewerSurfaceLooks.count;
      await new Promise(resolve => setTimeout(resolve, 300));
    }
    return window.__viewerSurfaceLooks.count;
  });
  const syncsBeforeGrid = await settledSceneSyncs();
  await first.getByRole('button', { name: 'Grid color', exact: true }).click();
  await page.getByRole('spinbutton', { name: 'Color opacity' }).fill('40');
  await page.getByRole('spinbutton', { name: 'Color opacity' }).press('Tab');
  await page.waitForFunction(() => Object.values(window.cadHarness.state.renderers || {}).some(saved => saved.display?.grid?.opacity === 0.4));
  await page.keyboard.press('Escape');
  assert.equal(await settledSceneSyncs(), syncsBeforeGrid, 'Grid paint only changes the guide: the scene is not dressed again');
  await first.getByRole('button', { name: 'Lighting', exact: true }).click();
  assert.ok((await first.getByRole('region', { name: 'Lighting', exact: true }).boundingBox()).height <= 170);
  await first.getByLabel('Exposure value', { exact: true }).fill('0.8');
  await first.getByLabel('Exposure value', { exact: true }).press('Enter');
  await first.getByLabel('Rotation value', { exact: true }).fill('45');
  await first.getByLabel('Rotation value', { exact: true }).press('Enter');
  await page.waitForFunction(() => Object.values(window.cadHarness.state.renderers || {}).some(saved => {
    const lighting = saved.display?.lighting;
    return lighting?.exposure === 0.8 && lighting.rotation === 45;
  }));
  await first.getByRole('button', { name: 'Disable Lighting', exact: true }).click();
  assert.deepEqual(await page.evaluate(() => window.cadHarness.a.controller.readState().display.lighting), { enabled: false });
  // Reopening a gate starts from its defaults, never its previous values.
  await first.getByRole('button', { name: 'Enable Lighting', exact: true }).click();
  assert.equal(await first.getByLabel('Exposure value', { exact: true }).inputValue(), '0.0 EV');
  assert.equal(await first.getByLabel('Rotation value', { exact: true }).inputValue(), '0°');
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({
    clip: { enabled: true, axis: 'x', offsets: { x: 0.6 } },
    exploded: { enabled: true, amount: 0.3 },
    surfaces: { colorMode: 'single', color: '#336699' }
  }));
  await page.waitForFunction(() => !window.cadHarness.a.controller.readState().loading);
  const beforeStyle = await page.evaluate(() => window.cadHarness.a.controller.readState());
  // A command's tools are saved as written, never rewritten to fit the file; a view whose
  // features leave those sections out resolves them off, and no section appears.
  const assertMeshToolsStayOff = async () => {
    assert.equal(await first.getByRole('region', { name: /^(?:Clip|Explode)$/ }).count(), 0);
    assert.equal(await first.getByRole('button', { name: /^(?:Enable|Disable) (?:Clip|Explode)$/ }).count(), 0);
  };
  assert.equal(beforeStyle.display.clip.enabled, true);
  assert.equal(beforeStyle.display.clip.axis, 'x');
  assert.equal(beforeStyle.display.clip.offsets.x, 0.6);
  assert.deepEqual(beforeStyle.display.exploded, { enabled: true, amount: 0.3 });
  await page.waitForFunction(() => Object.values(window.cadHarness.state.renderers || {}).some(saved => {
    const display = saved.display;
    return display?.clip?.enabled === true && display.clip.offsets?.x === 0.6 && display.exploded?.amount === 0.3;
  }));
  await assertMeshToolsStayOff();
  const assertPreservedState = async (preserveTools = true) => {
    const current = await page.evaluate(() => window.cadHarness.a.controller.readState());
    for (const key of ['target', 'up']) {
      current.camera[key].forEach((v, i) => assert.ok(Math.abs(v - beforeStyle.camera[key][i]) < 1e-6, `${key}[${i}] preserved`));
    }
    assert.ok(Math.abs(current.camera.zoom - beforeStyle.camera.zoom) < 1e-6, 'zoom preserved');
    for (const key of ['clip', 'exploded']) {
      if (preserveTools) assert.deepEqual(current.display[key], beforeStyle.display[key]);
      else assert.notEqual(current.display[key]?.enabled, true);
    }
    assert.equal(await page.evaluate(() => window.cadHarness.b.controller.readState().display.mode), 'solid');
  };
  for (const [mode, projection, label] of [
    ['render', 'perspective', 'Render'], ['solid', 'orthographic', 'Solid'],
    ['render', 'perspective', 'Render'], ['solid', 'orthographic', 'Solid']
  ]) {
    await first.getByRole('combobox', { name: 'Mode', exact: true }).click();
    // The fixture is a mesh: the presets made of CAD edges (X-ray, Hidden line, Wireframe) are not offered.
    assert.deepEqual(await page.getByRole('option').allTextContents(), ['Solid', 'Render']);
    await page.getByRole('option', { name: label, exact: true }).click();
    await page.waitForFunction(({ mode, projection }) => {
      const state = window.cadHarness.a.controller.readState();
      return state.display.mode === mode && state.camera.projection === projection && !state.loading;
    }, { mode, projection });
    await assertPreservedState();
    // A real pointer may land over a different section when the menu closes or
    // preset groups change height. Dwell long enough to catch delayed writes.
    const presetState = await page.evaluate(() => window.cadHarness.a.controller.readState().display);
    for (const title of ['Floor', 'Lighting', 'Background', 'Grid', 'Axes']) {
      await first.getByRole('heading', { name: title, exact: true }).hover();
      await page.waitForTimeout(220);
      assert.deepEqual(await page.evaluate(() => window.cadHarness.a.controller.readState().display), presetState, `${label}: hover over ${title} must not change settings`);
    }
    assert.equal(await first.getByRole('combobox', { name: 'Mode', exact: true }).innerText(), label);
  }
  await first.getByRole('combobox', { name: 'Projection', exact: true }).click();
  await page.getByRole('option', { name: 'Perspective', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().camera.projection === 'perspective');
  assert.equal(await first.getByRole('combobox', { name: 'Mode', exact: true }).innerText(), 'Custom');
  // Custom is a muted placeholder, never an option or a selected base preset.
  assert.equal(await first.getByRole('combobox', { name: 'Mode', exact: true }).getAttribute('data-placeholder'), '');
  await first.getByRole('combobox', { name: 'Mode', exact: true }).click();
  assert.equal(await page.getByRole('option', { name: 'Solid', exact: true }).getAttribute('data-state'), 'unchecked');
  assert.equal(await page.getByRole('option', { name: 'Custom', exact: true }).count(), 0);
  await page.getByRole('option', { name: 'Solid', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().camera.projection === 'orthographic');
  assert.equal(await first.getByRole('combobox', { name: 'Mode', exact: true }).innerText(), 'Solid');
  await assertPreservedState();

  // Actual control edits must survive subsequent edits and the debounced host
  // save, rather than only being visible in an intermediate React render.
  await first.getByLabel('Surface opacity value', { exact: true }).fill('65');
  await first.getByLabel('Surface opacity value', { exact: true }).press('Enter');
  await first.getByRole('combobox', { name: 'Surface style', exact: true }).click();
  await page.getByRole('option', { name: 'Flat', exact: true }).click();
  await first.getByRole('combobox', { name: 'Parts', exact: true }).click();
  await page.getByRole('option', { name: 'Single color', exact: true }).click();
  await page.waitForFunction(() => Object.values(window.cadHarness.state.renderers || {}).some(saved => {
    const surfaces = saved.display?.surfaces;
    return surfaces?.opacity === 0.65 && surfaces.style === 'flat' && surfaces.colorMode === 'single';
  }));
  assert.deepEqual(await page.evaluate(() => window.cadHarness.a.controller.readState().display.surfaces), {
    enabled: true, opacity: 0.65, style: 'flat', colorMode: 'single'
  });
  await page.evaluate(() => {
    window.cadHarness.a.controller.setDisplaySettings({ surfaces: { opacity: 0.7 } });
    window.cadHarness.a.controller.setDisplaySettings({ grid: { color: '#123456' } });
    window.cadHarness.a.controller.setDisplaySettings({ axes: { color: '#654321' } });
  });
  await page.waitForFunction(() => Object.values(window.cadHarness.state.renderers || {}).some(saved => {
    const display = saved.display;
    return display?.surfaces?.opacity === 0.7 && display.grid?.color === '#123456' && display.axes?.color === '#654321';
  }));

  // Lighting is independent of the preset and backgrounds carry real alpha.
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({
    mode: 'solid', lighting: { quality: 'preview', exposure: 0.5 }, background: { opacity: 0.4 }
  }));
  await page.waitForFunction(() => !window.cadHarness.a.controller.readState().loading);
  assert.equal(await first.getByLabel('Exposure value', { exact: true }).inputValue(), '0.5 EV');
  assert.equal(await first.getByRole('combobox', { name: 'Mode', exact: true }).innerText(), 'Custom');
  assert.equal(await first.getByRole('checkbox', { name: 'Transparent', exact: true }).count(), 0);
  await first.getByRole('button', { name: 'Background color', exact: true }).click();
  await page.getByRole('spinbutton', { name: 'Color opacity' }).fill('0');
  await page.getByRole('spinbutton', { name: 'Color opacity' }).press('Tab');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.background.opacity === 0);
  await page.keyboard.press('Escape');
  await first.getByRole('button', { name: 'Disable Lighting' }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.lighting.enabled === false);
  assert.equal(await first.getByLabel('Exposure value', { exact: true }).count(), 0);
  await first.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.waitForFunction(() => !window.cadHarness.a.controller.readState().loading);
  await assertPreservedState(false);
  assert.equal(await first.getByRole('combobox', { name: 'Mode', exact: true }).innerText(), 'Solid');

  await first.getByRole('combobox', { name: 'Mode', exact: true }).click();
  await page.getByRole('option', { name: 'Render', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.mode === 'render' && !window.cadHarness.a.controller.readState().loading);
  await first.getByLabel('Exposure value', { exact: true }).fill('1.5');
  await first.getByLabel('Exposure value', { exact: true }).press('Enter');
  await first.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.mode === 'render' && !window.cadHarness.a.controller.readState().loading);
  assert.equal(await first.getByRole('combobox', { name: 'Mode', exact: true }).innerText(), 'Render');
  assert.equal(await first.getByLabel('Exposure value', { exact: true }).inputValue(), '0.0 EV');
  await assertPreservedState(false);
  // Several commands in one turn must leave controls at the final request,
  // and capture must await that recipe rather than the last React render.
  const finalCapture = await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    const commands = [
      controller.setDisplaySettings({ mode: 'solid' }),
      controller.setDisplaySettings({ mode: 'render' }),
      controller.setDisplaySettings({ lighting: { exposure: 1.25 } }),
      controller.setDisplaySettings({ clip: { enabled: true, offset: 0.3 } }),
    ];
    // Superseded command acknowledgements may reject their old target; handle
    // all of them while the renderer itself coalesces to the latest recipe.
    void Promise.allSettled(commands);
    const capture = await controller.capture();
    return { size: capture.size, display: controller.readState().display,
      error: document.querySelector('[data-view-update-status][role="alert"]')?.textContent };
  });
  assert.ok(finalCapture.size > 100);
  assert.equal(finalCapture.display.mode, 'render');
  assert.equal(finalCapture.display.lighting.exposure, 1.25);
  // The clip command is saved as written; the mesh it was sent to is still not cut.
  assert.equal(finalCapture.display.clip.enabled, true);
  assert.equal(finalCapture.display.clip.offset, 0.3);
  await assertMeshToolsStayOff();
  assert.equal(finalCapture.error, undefined);
  assert.equal(await page.evaluate(() => window.cadHarness.captures.length), 1, 'an acknowledged capture does not replay after remount');
  assert.equal(await page.evaluate(() => window.cadHarnessView.canvas === document.querySelector('[data-testid="one"] [aria-busy] > div > canvas')), true);
  assert.deepEqual(await page.evaluate(() => window.cadHarnessView.interruptions), [], 'settings never replace or cover the live canvas');
  assert.equal(requests.filter(path => path === '/one/mesh.stl').length, 1, 'view edits never reload geometry');
  const clears = await page.evaluate(() => window.cadBufferClears);
  assert.ok(clears.length > 0, 'exercise actual Retina buffer resizes');
  assert.ok(clears.every(clear => clear.redrawn), 'no cleared framebuffer is left waiting for a later draw');
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
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-shell-fit-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('../../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const compiledCss = await readFile(new URL('../../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(compiledCss); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: [
        { kind: 'stl', file: 'plate.stl', rootRelativeFile: 'plate.stl', url: '/plate.stl', hash: root, bytes: widePlate.length }] }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else if (url.pathname.endsWith('/plate.stl')) { response.end(widePlate); }
    else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: process.platform === 'darwin'
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=plate.stl`);
  const pane = page.getByTestId('one');
  await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));

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
  assert.deepEqual(errors, []);
});

// Draw is the one tool the shell itself owns. The only format that has it is
// STEP, which is still the pre-shell renderer, so shell-level Draw behaviour is
// driven here through a harness-only renderer over one triangle
// (`renderers/shell-harness`). It goes when STEP moves onto the shell.
test('the shell keeps its Draw session across fullscreen, and fullscreen drags are the camera\'s', async (t) => {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-shell-draw-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('../../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  // The drawing editor's own stylesheet, extracted from what the bundle imports:
  // without it the editor has no layout and sizes its canvas from an unconstrained container.
  const bundledCss = await readFile(join(temporary, 'harness.css')).catch(() => '');
  const compiledCss = await readFile(new URL('../../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(compiledCss); }
    else if (url.pathname === '/harness.css') { response.setHeader('Content-Type', 'text/css'); response.end(bundledCss); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: [] }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else if (/\.(woff2|ttf)$/.test(url.pathname)) { response.statusCode = 404; response.end(); }
    else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/harness.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: process.platform === 'darwin'
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=one.harness`);
  const pane = page.getByTestId('one');
  await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
  const camera = () => page.evaluate(() => window.cadHarness.a.controller.readState().camera);

  await page.evaluate(async () => {
    window.cadHarness.preferences.update({ orbit: { speed: 0 } });
    const controller = window.cadHarness.a.controller;
    await controller.setCamera({ ...controller.readState().camera, position: [40, -25, 30], target: [2, 3, 0], zoom: 1.4 });
  });
  await pane.getByRole('button', { name: 'Draw', exact: true }).click();
  await pane.locator('[data-drawing-ready]').waitFor();
  await page.waitForTimeout(250);
  const regularCamera = await camera();

  // Fullscreen hides the host frame without remounting the scene or losing the tool.
  await page.evaluate(() => { window.beforeFullscreenCanvas = document.querySelector('[data-testid="one"] [aria-busy] > div > canvas'); window.cadHarness.fullscreen(true); });
  await pane.getByRole('button', { name: 'Inspector', exact: true }).waitFor({ state: 'detached' });
  assert.equal(await pane.getByRole('group', { name: 'Interaction tools' }).count(), 0);
  assert.equal(await pane.getByRole('button', { name: 'Zoom controls' }).count(), 0);
  const defaultFullscreenCamera = await camera();
  assert.notDeepEqual(defaultFullscreenCamera.position, regularCamera.position, 'fullscreen starts from the default camera');
  assert.equal(defaultFullscreenCamera.zoom, 1);
  await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    await controller.setCamera({ ...controller.readState().camera, position: [80, 30, 35], target: [4, 6, 1], zoom: 1.8, projection: 'perspective' });
  });
  const beforeDrag = await camera();
  const viewport = await pane.locator('[aria-busy] > div > canvas').first().boundingBox();
  await page.mouse.move(viewport.x + viewport.width / 2, viewport.y + viewport.height / 2);
  await page.mouse.down(); await page.mouse.move(viewport.x + viewport.width / 2 + 80, viewport.y + viewport.height / 2 + 30, { steps: 5 }); await page.mouse.up();
  assert.notDeepEqual((await camera()).position, beforeDrag.position, 'Draw cannot capture fullscreen camera drags');
  assert.equal(await page.evaluate(() => window.beforeFullscreenCanvas === document.querySelector('[data-testid="one"] [aria-busy] > div > canvas')), true);
  // Exercise actual hit testing above the pointer-transparent viewport overlay,
  // and the exit callback across FileViewer -> renderer -> toolbar.
  assert.equal(await pane.getByRole('toolbar', { name: 'Animation playback' }).count(), 0);
  await pane.getByRole('button', { name: 'Orbit settings', exact: true }).click();
  await page.getByRole('slider', { name: 'Orbit speed', exact: true }).press('Home');
  assert.equal(await page.getByRole('textbox', { name: 'Orbit speed value', exact: true }).inputValue(), '0×');
  await page.keyboard.press('Escape');
  await pane.getByRole('button', { name: 'Exit fullscreen', exact: true }).click();
  await pane.getByRole('button', { name: 'Draw', exact: true }).waitFor();
  const restoredCamera = await camera();
  for (const key of ['position', 'target', 'up']) {
    regularCamera[key].forEach((value, index) => assert.ok(Math.abs(value - restoredCamera[key][index]) < 1e-6, `restore ${key}[${index}]`));
  }
  assert.equal(restoredCamera.projection, regularCamera.projection);
  assert.equal(restoredCamera.zoom, regularCamera.zoom);
  // Presentation state is discarded each time, never resumed from the last orbit.
  await page.evaluate(() => window.cadHarness.fullscreen(true));
  await pane.getByRole('button', { name: 'Exit fullscreen', exact: true }).waitFor();
  const secondFullscreenCamera = await camera();
  for (const key of ['position', 'target', 'up']) {
    defaultFullscreenCamera[key].forEach((value, index) => assert.ok(Math.abs(value - secondFullscreenCamera[key][index]) < 1e-6, `fresh fullscreen ${key}[${index}]`));
  }
  await pane.getByRole('button', { name: 'Exit fullscreen', exact: true }).click();
  await pane.getByRole('button', { name: 'Draw', exact: true }).waitFor();
  assert.equal(await pane.getByRole('button', { name: 'Draw', exact: true }).getAttribute('aria-pressed'), 'true',
    'the session the sketch is in survives a trip through fullscreen');
  // Pressing it again ends the session, and the strip is left with no tool taken up.
  await pane.getByRole('button', { name: 'Draw', exact: true }).click();
  await pane.locator('[data-drawing-ready]').waitFor({ state: 'detached' });
  assert.equal(await pane.getByRole('button', { name: 'Draw', exact: true }).getAttribute('aria-pressed'), 'false');
  assert.deepEqual(errors, []);
});

// Three shell surfaces a renderer opts into, driven under the same harness-only
// renderer over one triangle: a viewport menu whose items are its own, a bottom
// action whose long label falls back to a count, and the camera-settled report.
// They go with this renderer when STEP arrives on the shell and uses them for real.
test('a renderer supplies the viewport menu, a bottom action that falls back to a count, and is told when the camera settles', async (t) => {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-shell-surfaces-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('../../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const compiledCss = await readFile(new URL('../../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(compiledCss); }
    else if (url.pathname.endsWith('/__cad/catalog')) { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, entries: [] })); }
    else if (url.pathname.endsWith('/__cad/server')) { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' })); }
    else if (/\.(woff2|ttf)$/.test(url.pathname)) { response.statusCode = 404; response.end(); }
    else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: process.platform === 'darwin'
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=one.harness`);
  const pane = page.getByTestId('one');
  const canvas = await pane.locator('[aria-busy="false"] > div > canvas').first().boundingBox();
  const middle = { x: canvas.x + canvas.width / 2, y: canvas.y + canvas.height / 2 };

  // THE VIEWPORT MENU. A secondary tap over the canvas opens what the renderer
  // offered, where it was pressed, and the browser's own menu never appears.
  await page.evaluate(() => {
    window.nativeMenu = [];
    document.addEventListener('contextmenu', event => window.nativeMenu.push(event.defaultPrevented));
  });
  await page.mouse.click(middle.x, middle.y, { button: 'right' });
  const menu = page.getByRole('menu');
  await menu.waitFor();
  assert.deepEqual(await page.getByRole('menuitem').allInnerTexts(), ['Note the press', 'Clear the note']);
  assert.deepEqual(await page.evaluate(() => window.nativeMenu), [true], 'the native menu stays off the canvas');
  const menuBox = await menu.boundingBox();
  // It opens AT the press, not at a corner: a second press elsewhere moves it by
  // the same amount the press moved.
  await page.keyboard.press('Escape');
  await menu.waitFor({ state: 'detached' });
  const elsewhere = { x: middle.x + 220, y: middle.y - 140 };
  await page.mouse.click(elsewhere.x, elsewhere.y, { button: 'right' });
  await menu.waitFor();
  const movedBox = await menu.boundingBox();
  assert.ok(Math.abs((movedBox.x - menuBox.x) - 220) < 6 && Math.abs((movedBox.y - menuBox.y) + 140) < 6,
    `the menu follows the press (${JSON.stringify(menuBox)} -> ${JSON.stringify(movedBox)})`);
  assert.ok(Math.abs(movedBox.x - elsewhere.x) < 24 && Math.abs(movedBox.y - elsewhere.y) < 24,
    `and opens on it (${JSON.stringify(movedBox)} for ${JSON.stringify(elsewhere)})`);
  await page.keyboard.press('Escape');
  await menu.waitFor({ state: 'detached' });
  await page.mouse.click(middle.x, middle.y, { button: 'right' });
  await menu.waitFor();
  // The second item is disabled until the first has been taken, which is the
  // renderer's own state reaching the shell's menu.
  assert.equal(await page.getByRole('menuitem', { name: 'Clear the note', exact: true }).getAttribute('data-disabled'), '');
  await page.getByRole('menuitem', { name: 'Note the press', exact: true }).click();
  await menu.waitFor({ state: 'detached' });
  assert.equal(await pane.locator('[data-harness-menu-note]').innerText(),
    `${Math.round(middle.x)},${Math.round(middle.y)}`, 'the item acted on the press the renderer was given');

  // A press the renderer has nothing to say about opens nothing — and still no native menu.
  await page.evaluate(() => { window.nativeMenu = []; });
  await page.keyboard.down('Shift');
  await page.mouse.click(middle.x, middle.y, { button: 'right' });
  await page.keyboard.up('Shift');
  await page.waitForTimeout(200);
  assert.equal(await page.getByRole('menu').count(), 0, 'no items, no menu');
  assert.deepEqual(await page.evaluate(() => window.nativeMenu), [true]);

  // A secondary DRAG is the camera's: it pans and opens nothing.
  const settles = () => pane.locator('[data-harness-camera-settles]').innerText();
  const beforeDrag = await page.evaluate(() => window.cadHarness.a.controller.readState().camera.target);
  await page.mouse.move(middle.x, middle.y);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(middle.x + 90, middle.y + 40, { steps: 6 });
  await page.mouse.up({ button: 'right' });
  await page.waitForTimeout(250);
  assert.equal(await page.getByRole('menu').count(), 0, 'a secondary drag opens no menu');
  assert.notDeepEqual(await page.evaluate(() => window.cadHarness.a.controller.readState().camera.target), beforeDrag,
    'and still pans the camera');

  // THE CAMERA SETTLED. The pan above was reported; so is a presentation camera
  // that moves in fullscreen (which records no perspective at all), and so is a
  // viewport RESIZE, which can change what is on screen without moving the camera.
  const afterPan = Number(await settles());
  assert.ok(afterPan > 0, `a camera that moved was reported (${afterPan})`);
  // A viewport whose size changed is a settle too. (This one is over-covered: every
  // resize the harness can make also moves the stored camera, so the perspective path
  // reports it as well. The viewport reports it unconditionally because an aspect
  // change CAN expose part of a scene while every stored field stays equal, which is
  // the case `resampleLodAfterViewportResize` exists for.)
  const beforeWidthChange = Number(await settles());
  await page.setViewportSize({ width: 900, height: 800 });
  await page.waitForFunction(count => Number(document.querySelector('[data-harness-camera-settles]').textContent) > count, beforeWidthChange);
  const afterResize = Number(await settles());
  await page.evaluate(() => { window.cadHarness.preferences.update({ orbit: { speed: 0 } }); window.cadHarness.fullscreen(true); });
  await pane.getByRole('button', { name: 'Exit fullscreen', exact: true }).waitFor();
  const fullscreenCanvas = await pane.locator('[aria-busy] > div > canvas').first().boundingBox();
  await page.mouse.move(fullscreenCanvas.x + fullscreenCanvas.width / 2, fullscreenCanvas.y + fullscreenCanvas.height / 2);
  await page.mouse.down();
  await page.mouse.move(fullscreenCanvas.x + fullscreenCanvas.width / 2 + 80, fullscreenCanvas.y + fullscreenCanvas.height / 2 + 30, { steps: 5 });
  await page.mouse.up();
  await page.waitForFunction(count => Number(document.querySelector('[data-harness-camera-settles]').textContent) > count, afterResize);
  await pane.getByRole('button', { name: 'Exit fullscreen', exact: true }).click();
  await pane.getByRole('button', { name: 'Draw', exact: true }).waitFor();

  // THE BOTTOM ACTION. What it SAYS is measured, not guessed from the string: a
  // reference too wide for the button is replaced by the count the renderer
  // supplied, while the full reference stays the title; a reference that fits is
  // shown whole. `render` is what actually drew the control both times.
  const action = pane.locator('[data-harness-bottom-action]');
  await action.waitFor();
  const long = await page.evaluate(() => document.querySelector('[data-harness-bottom-action]').title);
  assert.ok(long.length > 240 && long.startsWith('#harness_document/'), `the renderer's own long reference: ${long.length} chars`);
  assert.equal(await action.innerText(), 'Copy 1 reference', 'a reference that does not fit becomes the count');
  assert.equal(await action.getAttribute('title'), long, 'and the full reference is still the title');
  // What is on screen is one line of the count, not a cut-off reference.
  assert.ok((await action.boundingBox()).width < 200, 'the button is the count\'s width');
  await action.click();
  await page.waitForFunction(() => document.querySelector('[data-harness-bottom-action]')?.textContent?.startsWith('#'));
  const short = await action.innerText();
  assert.equal(short, '#harness_document/triangle_face_0001', 'a reference that fits is shown whole');
  assert.equal(await action.getAttribute('title'), short);
  assert.deepEqual(errors, []);
});
