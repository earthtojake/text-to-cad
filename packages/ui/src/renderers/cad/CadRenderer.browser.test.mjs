import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// What is this renderer's own, in its own frame, until it moves onto the shell
// (the shared behaviour is tested there: kit/shell/RendererShell.browser.test.mjs).
// The fixture is the smallest file it opens without a backend: a plate with one hole.
const dxf = [
  '0', 'SECTION', '2', 'HEADER', '0', 'ENDSEC', '0', 'SECTION', '2', 'ENTITIES',
  '0', 'LWPOLYLINE', '8', 'CUT', '90', '4', '70', '1', '10', '0', '20', '0', '10', '40', '20', '0', '10', '40', '20', '20', '10', '0', '20', '20',
  '0', 'CIRCLE', '8', 'CUT', '10', '20', '20', '10', '40', '4',
  '0', 'ENDSEC', '0', 'EOF', ''
].join('\n');

test('a file that is not a STEP keeps STEP-only view tools off, saves them as written, and records its session under [path, "cad"]', async (t) => {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-cad-browser-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise((resolve) => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const compiledCss = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(compiledCss); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: [{ kind: 'dxf', file: 'plate.dxf', rootRelativeFile: 'plate.dxf', url: '/plate.dxf', hash: `${root}-dxf`, bytes: dxf.length }] }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else if (url.pathname.endsWith('/plate.dxf')) { response.end(dxf); }
    else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: process.platform === 'darwin'
    ? ['--use-angle=metal']
    : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(() => {
    window.Worker = undefined;
    for (const name of ['localStorage', 'sessionStorage']) {
      Object.defineProperty(window, name, { get() { throw new Error(`Renderer accessed ${name}`); } });
    }
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=plate.dxf`);
  const first = page.getByTestId('one');
  await first.locator('[aria-busy="false"] canvas').first().waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  // The session record is debounced; it lands under this renderer's own key.
  await page.waitForFunction(() => Object.keys(window.cadHarness.state.renderers || {}).length > 0);
  assert.deepEqual(await page.evaluate(() => Object.keys(window.cadHarness.state.renderers)), [JSON.stringify(['plate.dxf', 'cad'])]);

  // A command's tools are saved as written (the same settings still section the
  // next STEP file), but this file resolves them off: nothing is cut, no section appears.
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({
    clip: { enabled: true, axis: 'x', offsets: { x: 0.6 } }, exploded: { enabled: true, amount: 0.3 }
  }));
  await page.waitForFunction(() => !window.cadHarness.a.controller.readState().loading);
  const display = await page.evaluate(() => window.cadHarness.a.controller.readState().display);
  assert.deepEqual([display.clip.enabled, display.clip.axis, display.clip.offsets.x], [true, 'x', 0.6]);
  assert.deepEqual(display.exploded, { enabled: true, amount: 0.3 });
  await page.waitForFunction(() => Object.values(window.cadHarness.state.renderers || {}).some(saved => {
    const slice = saved.fileSession?.slices?.display;
    return slice?.clip?.enabled === true && slice.clip.offsets?.x === 0.6 && slice.exploded?.amount === 0.3;
  }));
  if (!await first.locator('[data-file-sheet-header]').isVisible()) await first.getByRole('button', { name: 'Inspector', exact: true }).click();
  await first.getByRole('tab', { name: 'Display', exact: true }).click();
  assert.equal((await page.evaluate(() => window.__cadClip())).enabled, false, 'the viewport applies no clip to a file that is not a STEP');
  assert.equal(await first.getByRole('region', { name: /^(?:Clip|Explode|Edges)$/ }).count(), 0);
  assert.equal(await first.getByRole('button', { name: /^(?:Enable|Disable) (?:Clip|Explode)$/ }).count(), 0);
  await first.getByRole('combobox', { name: 'Mode', exact: true }).click();
  assert.deepEqual(await page.getByRole('option').allTextContents(), ['Solid', 'Render'], 'the presets made of CAD edges are a STEP\'s');
  await page.keyboard.press('Escape');
  assert.deepEqual(errors, []);
});
