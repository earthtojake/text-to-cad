import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from '@playwright/test';
import { createServer } from 'vite';
import { test } from 'vitest';

/**
 * The PDF renderer in real Chromium, with PDF.js's real worker: a FileViewer on an
 * effect-free host (`pdf/index.tsx`), served by Vite from this app's root. The
 * renderer is this app's source; FileViewer is `@text-to-cad/ui`'s built export.
 */
test('PDF.js renders the same two-page document that live read, page, selection and capture use', { timeout: 120_000 }, async () => {
  const root = fileURLToPath(new URL('../..', import.meta.url));
  const pdfRoot = path.dirname(createRequire(import.meta.url).resolve('pdfjs-dist/package.json'));
  // A fresh dependency cache every run: what Vite optimises is then the same here
  // and in CI, and a late discovery (a reload mid-test) shows up every time.
  const cacheDir = mkdtempSync(path.join(tmpdir(), 'pdf-harness-vite-'));
  const server = await createServer({ configFile: false, root, cacheDir, server: { host: '127.0.0.1', port: 0 },
    plugins: [{ name: 'pdf-harness', configureServer(server) { server.middlewares.use((request, response, next) => {
      if (/^\/pdfjs\/(cmaps|standard_fonts|wasm|iccs)\/[\w.-]+$/.test(request.url ?? '')) {
        response.end(readFileSync(path.join(pdfRoot, request.url.slice('/pdfjs/'.length)))); return;
      }
      if (request.url !== '/') return next();
      response.setHeader('Content-Type', 'text/html'); response.end('<div id="root"></div><script type="module" src="/tests/browser/pdf/index.tsx"></script>');
    }); } }], esbuild: { jsx: 'automatic' },
    // Scan the harness, not the app: the default entry is every index.html under
    // the root, which here is the renderer's — a scan that fails on its aliases
    // and leaves discovery to the page, whose late finds re-optimise and reload
    // it mid-test.
    // `include` names what the scan cannot see: the automatic JSX runtime esbuild
    // injects is `react/jsx-dev-runtime` here, and Vite finding it from the page
    // re-optimises and reloads mid-test.
    optimizeDeps: { entries: ['tests/browser/pdf/index.tsx'], include: ['react/jsx-dev-runtime'] } });
  let browser;
  try {
    await server.listen(); browser = await chromium.launch({ headless: true });
    const page = await browser.newPage(); const errors = []; const assetRequests = [];
    page.on('response', response => { if (response.url().includes('/pdfjs/')) assetRequests.push({ url: response.url(), status: response.status() }); });
    page.on('pageerror', error => { errors.push(error.message); console.error(error.message); });
    let loads = 0; page.on('load', () => { loads += 1; });
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/`);
    await page.waitForFunction(() => window.pdfHarness?.live?.state().pageCount === 2);
    // Vite reloads the page when it finds a dependency its scan missed; a reload
    // mid-load restarts the harness and the wait above can miss its window.
    assert.equal(loads, 1, 'the harness loaded once: no Vite re-optimise reload mid-test');
    await page.getByText('First PDF page', { exact: true }).waitFor();
    const text = await page.evaluate(() => window.pdfHarness.live.read(1, 2));
    assert.equal(text[1].text.trim(), 'Second PDF page');
    assert.match(text[0].text, /日本/);
    assert.ok(assetRequests.some(request => request.url.endsWith('/cmaps/UniJIS-UTF16-H.bcmap') && request.status === 200));
    assert.ok(assetRequests.every(request => request.status === 200));
    await page.evaluate(() => window.pdfHarness.live.setPage(2));
    await page.getByText('Second PDF page', { exact: true }).waitFor();
    assert.equal(await page.getByRole('spinbutton', { name: 'PDF page' }).inputValue(), '2');
    await page.getByText('Second PDF page', { exact: true }).evaluate(element => {
      const range = document.createRange(); range.selectNodeContents(element);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    });
    await page.getByText('Second PDF page', { exact: true }).dispatchEvent('mouseup');
    assert.equal(await page.evaluate(() => window.pdfHarness.live.state().selection), 'Second PDF page');
    const png = await page.evaluate(async () => { const blob = await window.pdfHarness.live.capture(1); return { size: blob.size, type: blob.type, page: window.pdfHarness.live.state().page }; });
    assert.ok(png.size > 1000); assert.equal(png.type, 'image/png'); assert.equal(png.page, 2);
    // A delivery that worked says nothing: no "Copied" or "Added to prompt" beside the action.
    await page.getByRole('button', { name: 'Copy for prompt' }).click();
    await page.waitForFunction(() => window.pdfHarness.deliveries.length === 1);
    await page.getByRole('button', { name: 'Copy for prompt' }).and(page.locator(':enabled')).waitFor();
    assert.equal(await page.getByRole('status').innerText(), '');
    const invalid = await page.evaluate(async () => { try { await window.pdfHarness.live.read(0, 1); } catch (error) { return error.message; } });
    assert.match(invalid, /Page must be/);
    await page.evaluate(() => window.pdfHarness.unmount());
    assert.equal(await page.evaluate(() => window.pdfHarness.live), null);
    assert.deepEqual(errors, []);
  } finally { await browser?.close(); await server.close(); rmSync(cacheDir, { recursive: true, force: true }); }
});
