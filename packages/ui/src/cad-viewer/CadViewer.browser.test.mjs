import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// The viewer a host composes (`CadViewer`, `harness/index.tsx`) over the engine's API as this server answers it: a
// project of one folder of STL files, each a document a page opens by its path, and what a page records of it (the
// time it was opened, which the home's default order, Last activity, reads).
const ROOT = '/work/proj';
const PROJECT = { id: 'p1', name: 'proj', root: ROOT, created: 1, opened: 1, missing: false };
// A tetrahedron, binary STL: four triangles.
function stl(size) {
  const corners = [[[0, 0, 0], [size, 0, 0], [0, size, 0]], [[0, 0, 0], [0, size, 0], [0, 0, size]], [[0, 0, 0], [0, 0, size], [size, 0, 0]], [[size, 0, 0], [0, 0, size], [0, size, 0]]];
  const bytes = Buffer.alloc(84 + corners.length * 50);
  bytes.writeUInt32LE(corners.length, 80);
  corners.forEach((triangle, index) => triangle.flat().forEach((value, at) => bytes.writeFloatLE(value, 84 + index * 50 + 12 + at * 4)));
  return bytes;
}

let server, browser, temporary, bundle, css;
// When the folder was last read (ms), and each open the page recorded: a step after the folder was read again.
let folderRead = 0;
// The folder's files, by name: when each was last opened (null: never) and last changed, in seconds.
let files;
const fresh = () => {
  files = new Map(['alpha', 'bravo', 'charlie', 'delta'].map((name, index) => [`${name}.stl`, { opened: null, updated: 1000 - index * 10, bytes: stl(10 + index) }]));
};
const pathOf = name => `${ROOT}/${name}`;
const idOf = name => `00000000-0000-5000-8000-00000000000${[...files.keys()].indexOf(name) + 1}`;
const row = name => {
  const file = files.get(name);
  return { id: idOf(name), kind: 'stl', record: 'file', api: `/api/v1/documents/stl/${idOf(name)}`, path: pathOf(name), name, folder: ROOT,
    opened: file.opened, updated: file.updated, created: 1, pinned: false, missing: false, thumbnail: null, pictured: null, size: file.bytes.length,
    parts: null, project: PROJECT.id };
};
const envelope = name => ({ id: idOf(name), kind: 'stl', name, version: `v-${name}`, state: 'live', source: { type: 'file', path: pathOf(name), present: true },
  producers: [], api: `/api/v1/documents/stl/${idOf(name)}`, exports: [], revision: `r-${name}`,
  entry: { id: idOf(name), file: pathOf(name), kind: 'stl', url: `/api/v1/local/files?path=${encodeURIComponent(pathOf(name))}`, hash: `h-${name}`,
    bytes: files.get(name).bytes.length, project: { id: PROJECT.id, name: PROJECT.name, root: ROOT, folder: '' } } });
const named = path => [...files.keys()].find(name => pathOf(name) === path) ?? null;

before(async () => {
  temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-cad-viewer-browser-'));
  await build({ entryPoints: [fileURLToPath(new URL('./harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true,
    format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', target: 'es2022',
    loader: { '.webp': 'dataurl', '.avif': 'dataurl', '.woff2': 'dataurl', '.svg': 'dataurl' } });
  bundle = await readFile(join(temporary, 'harness.js'));
  css = Buffer.concat([await readFile(fileURLToPath(new URL('../../dist/styles.css', import.meta.url))),
    await readFile(join(temporary, 'harness.css')).catch(() => Buffer.alloc(0))]);
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const json = (body, status = 200) => { response.statusCode = status; response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(body)); };
    const body = () => new Promise(resolve => { let text = ''; request.on('data', chunk => { text += chunk; }); request.on('end', () => resolve(JSON.parse(text || '{}'))); });
    const route = url.pathname;
    if (route === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); return; }
    if (route === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); return; }
    if (!route.startsWith('/api/v1/')) {
      response.setHeader('Content-Type', 'text/html');
      response.end('<!doctype html><html><head><link rel="stylesheet" href="/styles.css"><style>body { margin: 0 }</style></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>');
      return;
    }
    if (route === '/api/v1/documents' && request.method === 'GET') {
      const asked = url.searchParams.get('path');
      if (asked !== null) { const name = named(asked); json({ documents: name ? [envelope(name)] : [] }); return; }
      json({ documents: [...files.keys()].filter(name => files.get(name).opened).map(row) });
      return;
    }
    if (route === '/api/v1/documents' && request.method === 'POST') {
      void body().then(({ path }) => { const name = named(path); if (name) json({ id: idOf(name), kind: 'stl', api: envelope(name).api }, 201); else json({ error: 'not found' }, 404); });
      return;
    }
    if (route === '/api/v1/documents' && request.method === 'PATCH') {
      void body().then(({ action, path }) => {
        const name = named(path);
        if (name && action === 'open') files.get(name).opened = Date.now() / 1000;
        if (name && action === 'open') files.get(name).recorded = Date.now();
        json({ documents: [...files.keys()].filter(item => files.get(item).opened).map(row) });
      });
      return;
    }
    if (route === '/api/v1/projects') { json({ projects: [PROJECT] }); return; }
    if (route === `/api/v1/projects/${PROJECT.id}`) {
      folderRead = Date.now();
      const words = (url.searchParams.get('q') || '').trim();
      json({ project: PROJECT, path: '', folders: [], truncated: false, documents: [...files.keys()].filter(name => !words || name.includes(words)).map(row) });
      return;
    }
    if (route === '/api/v1/local/files') {
      const name = named(url.searchParams.get('path'));
      if (!name) { json({ error: 'not found' }, 404); return; }
      response.setHeader('Content-Type', 'application/octet-stream');
      response.end(files.get(name).bytes);
      return;
    }
    if (route === '/api/v1/server') { json({ app: 'cad-viewer' }); return; }
    json({ error: 'not found' }, 404);
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
  if (temporary) await rm(temporary, { recursive: true, force: true });
});

async function open(t, file) {
  fresh();
  const page = await browser.newPage({ viewport: { width: 1000, height: 640 }, deviceScaleFactor: 1 });
  t.after(() => page.close().catch(() => {}));
  page.setDefaultTimeout(20_000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`http://127.0.0.1:${server.address().port}/${file ? `?file=${encodeURIComponent(file)}` : ''}`);
  return { page, errors };
}
// The document on screen, by the navbar's name, once its view is up.
const onScreen = (page, name) => page.waitForFunction(expected => document.querySelector('[data-file-name]')?.textContent?.trim() === expected
  && Boolean(document.querySelector('canvas')), name);
// Until `condition` holds, asked again every 50ms.
async function until(condition) { while (!condition()) await new Promise(resolve => setTimeout(resolve, 50)); }
// The page has recorded `name` opened and read its folder since, so the folder's order now puts it first, and drawn that.
async function readAgain(page, name) {
  await until(() => files.get(name).recorded && folderRead > files.get(name).recorded);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
// A key pressed in the view, as a person presses it with the pointer over the model: the view has the keyboard.
async function press(page, key) {
  const box = await page.locator('canvas').first().boundingBox();
  await page.mouse.click(box.x + 12, box.y + box.height - 12);
  await page.keyboard.press(key);
}

// `[` and `]` step through the folder in the order its page listed it when the person came to its documents, held while
// they stay among them: opening a document moves it first under Last activity, the default order, so an order taken
// again at each step walked back and forth between two documents and left the one just opened with no previous.
test('[ and ] walk the whole folder once under the default order, which opening a document does not change', async (t) => {
  const { page, errors } = await open(t, pathOf('alpha.stl'));
  // Opened by its address: the folder as it is first read, the document just opened first (Last activity).
  await onScreen(page, 'alpha.stl');
  await readAgain(page, 'alpha.stl');
  for (const name of ['bravo.stl', 'charlie.stl', 'delta.stl']) {
    await press(page, ']');
    await onScreen(page, name);
    await readAgain(page, name);
  }
  assert.deepEqual(await page.evaluate(() => window.cadHarness.shows.slice()), ['bravo.stl', 'charlie.stl', 'delta.stl'].map(pathOf));
  // The last: no next. Back with [.
  await press(page, ']');
  await press(page, '[');
  await onScreen(page, 'charlie.stl');
  await readAgain(page, 'charlie.stl');
  await press(page, '[');
  await onScreen(page, 'bravo.stl');
  assert.deepEqual(await page.evaluate(() => window.cadHarness.shows.slice(3)), ['charlie.stl', 'bravo.stl'].map(pathOf));

  // From the folder's page: the order it lists, as the person saw it there, whatever the open does to it.
  await page.locator('[data-navbar-project]').getByRole('button').first().click();
  const cards = page.locator('main li a, main li button').filter({ hasText: '.stl' });
  await page.getByRole('heading', { level: 1, name: /proj/ }).waitFor();
  await page.waitForFunction(() => document.querySelectorAll('main li').length >= 4);
  const listed = await page.locator('main li').evaluateAll(items => items.map(item => item.textContent.match(/[a-z]+\.stl/)?.[0]).filter(Boolean));
  assert.equal(listed.length, 4, `the folder's four documents in ${listed}`);
  const third = listed[2];
  await cards.filter({ hasText: third }).first().click();
  await onScreen(page, third);
  await readAgain(page, third);
  await press(page, '[');
  await onScreen(page, listed[1]);
  await press(page, ']');
  await onScreen(page, third);
  await press(page, ']');
  await onScreen(page, listed[3]);
  assert.deepEqual(errors, []);
});
