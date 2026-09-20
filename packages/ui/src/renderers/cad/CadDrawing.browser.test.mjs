import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// The Draw tool end to end in a real browser: the real drawing editor over the
// real viewport. Unit tests cover the camera mathematics, the editor controller
// and the fill algorithm; this is the flow a person actually uses.
const mesh = 'solid triangle\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 20 0 0\nvertex 0 20 0\nendloop\nendfacet\nendsolid triangle\n';

test('Draw locks the view, pans model and ink together, keeps tools, colors and fills, and discards the sketch when left', async (t) => {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-cad-drawing-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise((resolve) => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('./harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const bundledCss = await readFile(join(temporary, 'harness.css')).catch(() => '');
  const compiledCss = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(compiledCss); }
    else if (url.pathname === '/harness.css') { response.setHeader('Content-Type', 'text/css'); response.end(bundledCss); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: [{ kind: 'stl', file: 'part.stl', rootRelativeFile: 'part.stl', url: '/mesh.stl', hash: root, bytes: mesh.length }] }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else if (url.pathname.endsWith('/mesh.stl')) { response.end(mesh); }
    else if (/\.(woff2|ttf)$/.test(url.pathname)) { response.statusCode = 404; response.end(); }
    else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host</title><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/harness.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: process.platform === 'darwin' ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const pane = page.getByTestId('one');
  const tool = name => pane.getByRole('group', { name: 'Drawing tools' }).getByRole('button', { name, exact: true });
  const camera = () => page.evaluate(() => window.cadHarness.a.controller.readState().camera);
  // What the static ink canvas holds: pixel counts by kind, and the ink's left edge in CSS pixels.
  const ink = () => page.evaluate(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    if (!canvas) return null;
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    const counts = { opaque: 0, translucent: 0, green: 0, red: 0 }; let left = Infinity;
    for (let index = 0; index < data.length; index += 4) {
      const [r, g, b, a] = [data[index], data[index + 1], data[index + 2], data[index + 3]];
      if (a > 200) { counts.opaque += 1; left = Math.min(left, (index / 4) % canvas.width); if (g > 200 && r < 120) counts.green += 1; if (r > 200 && g < 100) counts.red += 1; }
      else if (a > 30) counts.translucent += 1;
    }
    return { ...counts, left: left * canvas.getBoundingClientRect().width / canvas.width };
  });
  const drag = async (from, to) => { await page.mouse.move(...from); await page.mouse.down(); await page.mouse.move(...to, { steps: 8 }); await page.mouse.up(); };

  const draw = pane.getByRole('button', { name: 'Draw', exact: true });
  await page.waitForFunction(() => Object.keys(window.cadHarness.state.renderers || {}).length > 0);

  assert.equal(await pane.getByRole('button', { name: 'Animate', exact: true }).count(), 0, 'no routines, no Animate tool');
  await draw.click();
  await pane.locator('[data-cad-drawing-overlay] canvas.excalidraw__canvas.interactive').waitFor();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  assert.equal(await tool('Pen').getAttribute('aria-pressed'), 'true', 'Draw opens on the pen');
  assert.equal(await pane.locator('.layer-ui__wrapper').isVisible(), false, 'the SDK has no controls of its own here');
  const box = await pane.locator('[data-cad-drawing-overlay]').boundingBox();
  const at = (x, y) => [box.x + x, box.y + y];

  // Locked: a drag that would have orbited the model draws instead.
  const locked = await camera();
  await drag(at(120, 120), at(260, 150));
  assert.deepEqual(await camera(), locked, 'drawing never moves the camera');
  const stroke = await ink();
  assert.ok(stroke.red > 50, `neon red ink: ${JSON.stringify(stroke)}`);

  // Pan belongs to the editor; the camera follows along its own plane.
  await page.mouse.move(...at(200, 300));
  await page.mouse.wheel(-90, 0);
  await page.waitForFunction(left => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    for (let x = 0; x < canvas.width; x += 1) for (let y = 0; y < canvas.height; y += 1) if (data[(y * canvas.width + x) * 4 + 3] > 200) return x * canvas.getBoundingClientRect().width / canvas.width > left + 60;
    return false;
  }, stroke.left);
  const panned = await camera();
  const direction = state => state.position.map((value, index) => value - state.target[index]);
  assert.ok(Math.hypot(...panned.target.map((value, index) => value - locked.target[index])) > 1e-3, 'the model moved with the ink');
  direction(panned).forEach((value, index) => assert.ok(Math.abs(value - direction(locked)[index]) < 1e-6, 'the view direction did not change'));
  assert.equal(panned.zoom, locked.zoom);

  // The Pan view tool drags the same picture.
  await tool('Pan view').click();
  await drag(at(300, 300), at(340, 330));
  const dragged = await camera();
  assert.ok(Math.hypot(...dragged.target.map((value, index) => value - panned.target[index])) > 1e-3);
  assert.equal((await ink()).opaque > 0, true, 'panning draws nothing');

  // Sticky tools: a rectangle is followed by a rectangle.
  await tool('Rectangle').click();
  await drag(at(120, 220), at(300, 360));
  assert.equal(await tool('Rectangle').getAttribute('aria-pressed'), 'true');
  // Color is for what comes next; the red ink stays red.
  await tool('Color').click();
  await pane.getByRole('radio', { name: 'Neon green', exact: true }).click();
  await drag(at(330, 220), at(400, 300));
  const colored = await ink();
  assert.ok(colored.green > 50 && colored.red >= stroke.red, JSON.stringify(colored));

  // Fill: a translucent area inside the first rectangle, and nothing opaque added.
  await tool('Fill area').click();
  await page.mouse.click(...at(210, 290));
  await page.waitForFunction(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    let translucent = 0; for (let index = 3; index < data.length; index += 4) if (data[index] > 30 && data[index] <= 200) translucent += 1;
    return translucent > 5000;
  });
  assert.equal(await tool('Fill area').getAttribute('aria-pressed'), 'true');
  // One Undo, one fill.
  await tool('Undo').click();
  await page.waitForFunction(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    let translucent = 0; for (let index = 3; index < data.length; index += 4) if (data[index] > 30 && data[index] <= 200) translucent += 1;
    return translucent < 5000;
  });

  // The capture carries the ink, registered to the viewport.
  // "Copy Drawing" for a clipboard host, "Add to Prompt" where the host has a composer.
  await pane.getByRole('button', { name: /^(Copy Drawing|Add to Prompt)$/ }).click();
  await page.waitForFunction(() => window.cadHarness.captures.length > 0);

  // Pressing Draw again ends the session and the sketch with it.
  await draw.click();
  await pane.locator('[data-cad-drawing-overlay]').waitFor({ state: 'detached' });
  assert.equal(await pane.getByRole('group', { name: 'Drawing tools' }).count(), 0);
  const left = await camera();
  for (const key of ['position', 'target']) left[key].forEach((value, index) => assert.ok(Math.abs(value - dragged[key][index]) < 1e-6, `the camera keeps the pose the sketch left it in: ${key}`));
  await draw.click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  assert.equal((await ink()).opaque, 0, 'a new session starts empty');
  assert.deepEqual(errors, []);
});
