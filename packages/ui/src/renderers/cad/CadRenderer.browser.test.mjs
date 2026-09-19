import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// Inline fixture bytes are served in memory with a private temporary harness.
const mesh = 'solid triangle\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 20 0 0\nvertex 0 20 0\nendloop\nendfacet\nendsolid triangle\n';

test('the shared CAD renderer resolves deferred files, reuses warm assets and restores isolated view state', async (t) => {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-cad-browser-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise((resolve) => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('./harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', jsx: 'automatic', loader: { '.webp': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const compiledCss = await readFile(new URL('../../../dist/styles.css', import.meta.url));
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
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.setDefaultTimeout(10000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(() => {
    window.Worker = undefined;
    for (const name of ['localStorage', 'sessionStorage']) {
      Object.defineProperty(window, name, { get() { throw new Error(`Renderer accessed ${name}`); } });
    }
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const first = page.getByTestId('one');
  await first.getByLabel('Zoom level percent', { exact: true }).waitFor().catch(async (error) => { throw new Error(`${error.message}; page errors: ${errors.join('; ')}; body: ${await page.locator("body").innerText()}; requests: ${requests.join(", ")}`); });
  await page.waitForFunction(() => Object.keys(window.cadHarness.state.renderers || {}).length > 0);
  assert.deepEqual(errors, []);
  assert.equal(await page.title(), 'Host title');
  await first.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[aria-label="Zoom level percent"]')?.textContent !== '100%');
  await first.getByRole('button', { name: 'Inspector', exact: true }).click();
  await first.locator('[data-file-sheet="STL"]').waitFor();
  assert.equal(await first.getByRole('button', { name: 'Theme settings', exact: true }).count(), 0);
  assert.equal(await first.locator('[data-file-sheet="Theme"]').count(), 0);
  await first.getByRole('button', { name: 'Inspector', exact: true }).click();
  await page.evaluate(() => window.cadHarness.capture());
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
  await page.evaluate(() => window.cadHarness.second(true));
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
  for (const saved of Object.values(before.renderers)) {
    assert.ok(saved.fileSession.slices.tab.camera, 'unmount flushes the outgoing tab camera');
    assert.ok(saved.fileSession.slices.render.cadCamera, 'unmount flushes the outgoing CAD camera');
  }
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
      savedCamera: state?.fileSession?.slices?.render?.cadCamera };
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
    const previousSlices = previousState[key].fileSession.slices;
    const restoredSlices = restoredState[key].fileSession.slices;
    for (const [previousCamera, restoredCamera] of [
      [previousSlices.tab.camera, restoredSlices.tab.camera],
      [previousSlices.render.cadCamera, restoredSlices.render.cadCamera],
    ]) {
      for (const field of ['position', 'target', 'up']) {
        assert.equal(restoredCamera[field].length, previousCamera[field].length);
        restoredCamera[field].forEach((value, index) => assert.ok(Math.abs(value - previousCamera[field][index]) < 1e-9, `${field}[${index}] was restored`));
      }
      assert.equal(restoredCamera.zoom, previousCamera.zoom);
      assert.equal(restoredCamera.projection, previousCamera.projection);
    }
    // Focal/frustum measurements are regenerated by the mounted viewport.
    // Pose, projection and user zoom are the durable camera contract; every
    // non-camera slice must remain byte-for-byte equivalent.
    assert.ok(restoredSlices.render.cadCamera.focalLength > 0);
    assert.ok(restoredSlices.render.cadCamera.orthographicHalfHeight > 0);
    delete previousSlices.tab.camera; delete restoredSlices.tab.camera;
    delete previousSlices.render.cadCamera; delete restoredSlices.render.cadCamera;
  }
  assert.deepEqual(restoredState, previousState);
  assert.equal(requests.filter((path) => path === '/one/mesh.stl').length, 1, 'reopening a file reuses its decoded mesh without another asset request');
  // Render is a display style: keep a non-default camera and all common
  // settings across both depth-buffer runtimes, without touching a sibling.
  await first.getByRole('button', { name: 'Inspector', exact: true }).click();
  await first.getByRole('tab', { name: 'View', exact: true }).click();
  await page.evaluate(async () => {
    await window.cadHarness.a.controller.setDisplaySettings({
      clip: { enabled: true, axis: 'x', offset: 0.6 },
      guides: { grid: { enabled: true } },
      partColor: { mode: 'single', color: '#336699' }
    });
  });
  await page.waitForFunction(() => !window.cadHarness.a.controller.readState().loading);
  let beforeStyle = await page.evaluate(() => window.cadHarness.a.controller.readState());
  let beforeZoom = await first.getByLabel('Zoom level percent', { exact: true }).innerText();
  const assertCommonState = async () => {
    const current = await page.evaluate(() => window.cadHarness.a.controller.readState());
    assert.equal(current.camera.projection, beforeStyle.camera.projection);
    for (const key of ['position', 'target', 'up']) {
      current.camera[key].forEach((v, i) => assert.ok(Math.abs(v - beforeStyle.camera[key][i]) < 1e-7, `${key}[${i}] unchanged across style switch`));
    }
    for (const key of ['zoom', 'orthographicHalfHeight']) {
      assert.ok(Math.abs(current.camera[key] - beforeStyle.camera[key]) < 1e-7, `${key} unchanged across style switch`);
    }
    for (const key of ['clip', 'guides', 'partColor', 'exploded']) assert.deepEqual(current.display[key], beforeStyle.display[key]);
    assert.equal(await first.getByLabel('Zoom level percent', { exact: true }).innerText(), beforeZoom);
    assert.equal(await page.evaluate(() => window.cadHarness.b.controller.readState().display.mode), 'shaded_edges');
  };
  await first.getByRole('combobox', { name: 'Mode', exact: true }).click();
  await page.getByRole('option', { name: 'Render', exact: true }).click();
  await page.waitForFunction(() => {
    const state = window.cadHarness.a.controller.readState();
    return state.display.mode === 'render' && !state.loading;
  });
  await assertCommonState();
  assert.equal(await first.getByText('Could not display that file', { exact: true }).count(), 0);
  assert.equal(await first.getByRole('button', { name: 'Theme settings', exact: true }).count(), 0);
  await first.getByRole('combobox', { name: 'Mode', exact: true }).click();
  await page.getByRole('option', { name: 'Shaded with edges', exact: true }).click();
  await page.waitForFunction(() => {
    const state = window.cadHarness.a.controller.readState();
    return state.display.mode === 'shaded_edges' && !state.loading;
  });
  await assertCommonState();
  await first.getByRole('combobox', { name: 'Projection', exact: true }).click();
  await page.getByRole('option', { name: 'Perspective', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().camera.projection === 'perspective');
  beforeStyle = await page.evaluate(() => window.cadHarness.a.controller.readState());
  beforeZoom = await first.getByLabel('Zoom level percent', { exact: true }).innerText();
  const lensReadout = parseFloat(await first.getByLabel('Lens value', { exact: true }).inputValue());
  assert.ok(Math.abs(lensReadout - beforeStyle.camera.focalLength) < 0.51, 'Lens shows the actual camera value');
  // The same unified display command drives agent integrations, including
  // Render-specific options, rather than a separate render-state envelope.
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({ mode: 'render', render: { quality: 'preview', exposure: 0.5 } }));
  await page.waitForFunction(() => !window.cadHarness.a.controller.readState().loading);
  await assertCommonState();
  assert.equal(await first.getByLabel('Exposure value', { exact: true }).inputValue(), '0.5 EV');
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({ mode: 'shaded_edges' }));
  await page.waitForFunction(() => !window.cadHarness.a.controller.readState().loading);
  await assertCommonState();
  assert.equal(await page.evaluate(() => window.cadHarness.captures.length), 1, 'an acknowledged capture does not replay after remount');
  assert.deepEqual(errors, []);
});
