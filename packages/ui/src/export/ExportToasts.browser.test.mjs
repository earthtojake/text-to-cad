import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// The export toasts' size and place are layout, which jsdom has none of: a real browser measures
// them. Each stands under the viewer's navbar at its top right, by the 16px gutter, and is as small
// as a menu item: one line of the menu's text, under 32px tall, as wide as that line.
test('an export toast is a small line at the top right under the navbar', async t => {
  const { outputFiles } = await build({ stdin: {
    resolveDir: fileURLToPath(new URL('.', import.meta.url)), loader: 'jsx', contents: `
import React, { useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { ExportControls } from '../../dist/export/ExportControls.js';
import { useExportView } from '../../dist/export/context.js';
import { I18nProvider } from '../../dist/i18n/index.js';
import { ViewerElementContext, ViewerHostContext } from '../../dist/host/context.js';
const view = { doc: 'doc', revision: 'v1', file: '/probe_couple.xbf', name: 'probe_couple.xbf' };
function Document() { useExportView(view); return null; }
const finish = [];
window.finish = () => finish.splice(0).forEach(done => done());
const service = {
  epoch: async () => 'epoch',
  create: async request => ({ ...request, id: request.requestId, filename: 'probe_couple.step', state: 'queued', stage: '', sequence: 0 }),
  status: (id, sequence) => new Promise(resolve => finish.push(() => resolve({ id, filename: 'probe_couple.step', state: 'ready', stage: '', sequence: sequence + 1 }))),
  fileUrl: id => '/file/' + id,
};
const downloads = { save() {} };
function App() {
  const viewer = useRef(null);
  return <I18nProvider locale="en"><ExportControls service={service} downloads={downloads} file={view.file}>{({ navbar, overlay }) =>
    <ViewerHostContext.Provider value={{ environment: { colorScheme: 'light' } }}><ViewerElementContext.Provider value={viewer}>
      <div ref={viewer} className="text-ui" style={{ height: '100vh' }}>
        <header data-viewer-navbar="" style={{ height: 40, display: 'flex', justifyContent: 'flex-end' }}>{navbar}</header>
        <Document />{overlay}
      </div>
    </ViewerElementContext.Provider></ViewerHostContext.Provider>}</ExportControls></I18nProvider>;
}
createRoot(document.getElementById('root')).render(<App/>);
` }, bundle: true, write: false, format: 'esm', platform: 'browser', jsx: 'automatic' });
  const styles = await readFile(new URL('../../dist/styles.css', import.meta.url));
  const server = createServer((request, response) => {
    if (request.url === '/app.js') { response.setHeader('content-type', 'text/javascript'); response.end(outputFiles[0].contents); }
    else if (request.url === '/styles.css') { response.setHeader('content-type', 'text/css'); response.end(styles); }
    else { response.setHeader('content-type', 'text/html'); response.end('<!doctype html><link rel="stylesheet" href="/styles.css"><body style="margin:0"><div id="root"></div><script type="module" src="/app.js"></script>'); }
  });
  let browser;
  t.after(async () => { await browser?.close(); await new Promise(resolve => server.close(resolve)); });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true });
  for (const width of [1024, 390]) {
    // Sonner's motion off, so a toast's box is where it rests.
    const page = await browser.newPage({ viewport: { width, height: 700 }, reducedMotion: 'reduce' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.getByRole('button', { name: 'Export', exact: true }).click();
    const menuFont = await page.getByRole('menuitem', { name: 'STEP' }).evaluate(item => getComputedStyle(item).fontSize);
    await page.getByRole('menuitem', { name: 'STEP' }).click();
    for (const [type, title] of [['loading', 'Preparing probe_couple.step…']]) {
      const toast = page.locator(`[data-sonner-toast][data-type="${type}"][data-mounted="true"]`);
      await toast.waitFor();
      const box = await toast.evaluate(item => {
        // The spinner turns, so an icon is its own box, not its bounds.
        const title = item.querySelector('[data-title]');
        const range = document.createRange(); range.selectNodeContents(title);
        const list = item.closest('[data-sonner-toaster]').getBoundingClientRect(), own = item.getBoundingClientRect();
        return { title: title.textContent, font: getComputedStyle(title).fontSize, weight: getComputedStyle(title).fontWeight,
          icon: getComputedStyle(item.querySelector('[data-icon] svg')).width, text: range.getBoundingClientRect().width,
          top: own.top, right: own.right, width: own.width, height: own.height, listTop: list.top, description: Boolean(item.querySelector('[data-description]')) };
      });
      const label = `${width}px ${type}`;
      assert.equal(box.title, title, label);
      // Under the navbar (40px) by the gutter, at the right gutter.
      assert.equal(box.top, 56, label);
      assert.equal(box.listTop, 56, label);
      assert.equal(box.right, width - 16, label);
      // A menu item's text, regular weight, with a 14px icon; one line under 32px.
      assert.deepEqual([box.font, box.weight, box.icon, box.description], [menuFont, '400', '14px', false], label);
      assert.ok(box.height < 32, `${label}: ${box.height}px tall`);
      // As wide as its line (icon, gap and padding beside it) above Sonner's narrow layout.
      if (width > 600) assert.ok(box.width <= box.text + 50, `${label}: ${box.width}px wide for ${box.text}px of text`);
      console.log(`${label}: ${box.width.toFixed(1)}x${box.height.toFixed(1)}px, text ${box.text.toFixed(1)}px at ${box.font}`);
    }
    // Handed to the browser, the file needs no toast of its own: the one there goes.
    await page.evaluate(() => window.finish());
    await page.locator('[data-sonner-toast]').waitFor({ state: 'detached' });
    assert.deepEqual(errors, []);
    await page.close();
  }
});
