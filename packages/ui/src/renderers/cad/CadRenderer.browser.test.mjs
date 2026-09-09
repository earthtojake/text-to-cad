import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// Inline fixture bytes are served in memory; no CAD artifact is written outside models/.
const mesh = 'solid triangle\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 20 0 0\nvertex 0 20 0\nendloop\nendfacet\nendsolid triangle\n';

test('the shared CAD renderer preserves baseline camera persistence, panels, capture and multiple-view isolation', async (t) => {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-cad-browser-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise((resolve) => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [new URL('./harness/index.tsx', import.meta.url).pathname], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', jsx: 'automatic', loader: { '.webp': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const compiledCss = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  const requests = [];
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    requests.push(url.pathname);
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(compiledCss); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: [{ kind: 'stl', file: 'part.stl', rootRelativeFile: 'part.stl', url: '/mesh.stl', hash: root, bytes: mesh.length }] }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else if (url.pathname.endsWith('/mesh.stl')) { response.end(mesh); }
    else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, args: ['--use-angle=metal'] });
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
  await first.getByRole('textbox', { name: 'Zoom level percent' }).waitFor().catch((error) => { throw new Error(`${error.message}; page errors: ${errors.join('; ')}`); });
  await page.waitForFunction(() => Object.keys(window.cadHarness.state.renderers || {}).length > 0);
  assert.deepEqual(errors, []);
  assert.equal(await page.title(), 'Host title');
  await first.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[aria-label="Zoom level percent"]')?.value !== '100%');
  await first.getByRole('button', { name: 'Inspector', exact: true }).click();
  await first.locator('[data-file-sheet="STL"]').waitFor();
  await first.getByRole('button', { name: 'Theme settings', exact: true }).click();
  await page.evaluate(() => window.cadHarness.capture());
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  const captured = await page.evaluate(() => window.cadHarness.captures[0]);
  assert.equal(captured.file, 'part.stl');
  assert.equal(captured.type, 'image/png');
  assert.ok(captured.size > 100);
  assert.deepEqual(captured.references, []);
  assert.equal(await first.locator('[data-file-sheet="STL"]').count(), 0);
  await first.getByRole('button', { name: 'Theme settings', exact: true }).click();
  await page.evaluate(() => window.cadHarness.second(true));
  await page.getByTestId('two').getByRole('textbox', { name: 'Zoom level percent' }).waitFor();
  assert.equal(await page.getByTestId('two').getByRole('textbox', { name: 'Zoom level percent' }).inputValue(), '100%');
  assert.ok(requests.includes('/one/mesh.stl'));
  assert.ok(requests.includes('/two/mesh.stl'));
  assert.equal(await first.getByRole('textbox', { name: 'Zoom level percent' }).inputValue(), '110%');
  const before = await page.evaluate(() => window.cadHarness.state);
  await page.evaluate(() => window.cadHarness.mounted(false));
  await first.locator('[data-slot="cad-file-view"]').waitFor({ state: 'detached' });
  await page.evaluate(() => window.cadHarness.mounted(true));
  await first.getByRole('textbox', { name: 'Zoom level percent' }).waitFor();
  // Baseline intentionally serializes camera vectors/zoom without viewport scope.
  // CadViewer requires that scope on restoration, so reopening retains the saved
  // record while initially reporting 100%. This refactor preserves that behavior.
  assert.equal(await first.getByRole('textbox', { name: 'Zoom level percent' }).inputValue(), '100%');
  assert.deepEqual((await page.evaluate(() => window.cadHarness.state)).renderers, before.renderers);
  assert.deepEqual(errors, []);
});
