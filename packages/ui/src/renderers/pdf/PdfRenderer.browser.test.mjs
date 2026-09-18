import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createServer } from 'vite';
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import path from 'node:path';

test('PDF.js renders the same two-page document that live read, page, selection and capture use', async () => {
  const root = fileURLToPath(new URL('../../..', import.meta.url));
  const pdfRoot = path.dirname(createRequire(import.meta.url).resolve('pdfjs-dist/package.json'));
  const server = await createServer({ configFile: false, root, server: { host: '127.0.0.1', port: 0 },
    plugins: [{ name: 'pdf-harness', configureServer(server) { server.middlewares.use((request, response, next) => {
      if (/^\/pdfjs\/(cmaps|standard_fonts|wasm|iccs)\/[\w.-]+$/.test(request.url ?? '')) {
        response.end(readFileSync(path.join(pdfRoot, request.url.slice('/pdfjs/'.length)))); return;
      }
      if (request.url !== '/') return next();
      response.setHeader('Content-Type', 'text/html'); response.end('<div id="root"></div><script type="module" src="/tests/pdf/index.tsx"></script>');
    }); } }], esbuild: { jsx: 'automatic' } });
  let browser;
  try {
    await server.listen(); browser = await chromium.launch({ headless: true });
    const page = await browser.newPage(); const errors = []; const assetRequests = [];
    page.on('response', response => { if (response.url().includes('/pdfjs/')) assetRequests.push({ url: response.url(), status: response.status() }); });
    page.on('pageerror', error => { errors.push(error.message); console.error(error.message); });
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/`);
    await page.waitForFunction(() => window.pdfHarness?.live?.state().pageCount === 2);
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
    const invalid = await page.evaluate(async () => { try { await window.pdfHarness.live.read(0, 1); } catch (error) { return error.message; } });
    assert.match(invalid, /Page must be/);
    await page.evaluate(() => window.pdfHarness.unmount());
    assert.equal(await page.evaluate(() => window.pdfHarness.live), null);
    assert.deepEqual(errors, []);
  } finally { await browser?.close(); await server.close(); }
});
