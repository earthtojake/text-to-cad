import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// A non-modal sheet the page opens itself (Quick Edit's on a phone), over a page that must stay
// usable. vaul never passes `modal={false}` on to the Radix dialog under it, whose lock on the
// page's pointer events then stayed on in a real browser: the navbar was dead while the sheet was
// up. jsdom's timing lifts the lock on its own, so this is a browser's.
test('a non-modal drawer opened through `open` leaves the rest of the page pressable', async t => {
  const { outputFiles } = await build({ stdin: {
    resolveDir: fileURLToPath(new URL('.', import.meta.url)), loader: 'jsx', contents: `
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Drawer, DrawerContent, DrawerTitle } from '../../dist/primitives/drawer.js';
function App() {
  const [open, setOpen] = useState(false), [pressed, setPressed] = useState(0);
  return <>
    <button type="button" onClick={() => setOpen(true)}>Open</button>
    <button type="button" onClick={() => setPressed(count => count + 1)}>Outside {pressed}</button>
    <Drawer modal={false} open={open}><DrawerContent overlay={false}><DrawerTitle>Sheet</DrawerTitle></DrawerContent></Drawer>
  </>;
}
createRoot(document.getElementById('root')).render(<App/>);
` }, bundle: true, write: false, format: 'esm', platform: 'browser', jsx: 'automatic' });
  const server = createServer((request, response) => {
    if (request.url === '/app.js') { response.setHeader('content-type', 'text/javascript'); response.end(outputFiles[0].contents); }
    else { response.setHeader('content-type', 'text/html'); response.end('<!doctype html><div id="root"></div><script type="module" src="/app.js"></script>'); }
  });
  let browser;
  t.after(async () => { await browser?.close(); await new Promise(resolve => server.close(resolve)); });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 700 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.getByRole('button', { name: 'Open' }).click();
  await page.locator('[data-slot="drawer-content"]').waitFor();
  // The sheet's own open has settled: its content mounted and two frames drawn.
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.notEqual(await page.evaluate(() => getComputedStyle(document.body).pointerEvents), 'none', 'the page keeps its pointer events');
  // A press outside lands (by its text: the dialog under the sheet hides the rest of the page
  // from the accessibility tree, which is not what this asks).
  await page.locator('button', { hasText: 'Outside' }).click({ timeout: 2000 });
  await page.locator('button', { hasText: 'Outside 1' }).waitFor();
  assert.deepEqual(errors, []);
});
