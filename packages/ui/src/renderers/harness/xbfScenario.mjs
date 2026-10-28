import { readFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { createServer } from 'node:http';
import { harnessBundle } from './bundle.mjs';
import { chromium } from 'playwright';

// An engine document the harness can open: core's bracket (`lib/xbf/__fixtures__/bracket`, a
// served document's structure and its two part buffers, as `cadgen serve` answers them: a
// filleted plate and two instances of one peg), relayed as the viewer relays its engine
// (`cadgen/viewer/xbf.py`): `GET /__cad/xbf?file=` answers where the page reads the document, and
// `/__cad/xbf/api/...` answers the engine's reads -- the structure, a buffer per part, the version a
// page waits on, and the look (`look.json`) with an environment image of one texel.
const FIXTURES = join(dirname(createRequire(import.meta.url).resolve('@text-to-cad/core/lib/xbf/xbfDocument.js')), '__fixtures__');
const STRUCTURE = readFileSync(join(FIXTURES, 'bracket', 'structure.json'));
const VERSION = JSON.parse(STRUCTURE).version;
const LOOK = readFileSync(join(FIXTURES, 'look.json'));
// 1 x 1, radiance 1 (RGBE 255, 255, 255, e 128), as `xbf.test.js` serves it.
const ENVIRONMENT = Buffer.concat([Buffer.from('#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 1\n'), Buffer.from([255, 255, 255, 128])]);
const FILE = 'bracket.xbf';
const DOC = '/__cad/xbf/api/doc/bracket';

/**
 * The page a spec opens, and so the viewer: it fills the page. Small, because a software renderer
 * (CI's SwiftShader) pays for every pixel of every frame.
 */
export const VIEWPORT = Object.freeze({ width: 800, height: 600 });

/**
 * Serve the harness over the bracket and hand back an `open`.
 *
 * @param {{ after: (cleanup: () => unknown) => void }} lifetime — a test context, or any object
 *   with its `after`, so one server and one browser can span a whole file.
 */
export async function serveXbfHarness(t, { transmission = false } = {}) {
  let server, browser;
  t.after(async () => {
    await browser?.close();
    if (server) await new Promise(resolve => server.close(resolve));
  });
  const { bundle, css: bundledCss } = await harnessBundle();
  // The document as it is served now: its version moves with each `update` of an open page.
  const structure = JSON.parse(STRUCTURE);
  if (transmission) structure.prototypes[0].material = { pbr: { values: { transmission: 0.9, roughness: 0.1, ior: 1.5 }, textures: {} } };
  const initial = Buffer.from(JSON.stringify(structure));
  let served = { version: VERSION, structure: initial };
  let updates = 0;
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  const json = (response, body) => { response.setHeader('Content-Type', 'application/json'); response.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body)); };
  const binary = (response, bytes) => { response.setHeader('Content-Type', 'application/octet-stream'); response.end(bytes); };
  const notFound = (response) => { response.statusCode = 404; json(response, { error: 'not found' }); };

  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const path = url.pathname;
    if (path === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); return; }
    if (path === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); return; }
    if (path === '/harness.css') { response.setHeader('Content-Type', 'text/css'); response.end(bundledCss); return; }
    // The catalog's row for the file, by its absolute path under the `/models` the harness opens a bare `?file=` in.
    if (path.endsWith('/__cad/catalog')) { json(response, { entries: [{ file: `/models/${FILE}`, kind: 'xbf', hash: VERSION, bytes: STRUCTURE.length }], revision: VERSION }); return; }
    if (path.endsWith('/__cad/server')) { json(response, { backend: 'cadgen' }); return; }
    if (path.endsWith('/__cad/xbf')) {
      if (url.searchParams.get('file') !== `/models/${FILE}`) { notFound(response); return; }
      json(response, url.searchParams.get('held') ? { held: true } : { doc: 'bracket', url: DOC });
      return;
    }
    const relayed = path.indexOf('/__cad/xbf/api/');
    if (relayed >= 0) {
      const rest = path.slice(relayed);
      if (rest === '/__cad/xbf/api/look') { json(response, LOOK); return; }
      if (rest === '/__cad/xbf/api/look/environment') { binary(response, ENVIRONMENT); return; }
      if (rest === DOC) { json(response, served.structure); return; }
      // The engine answers a version wait at once with the version it holds: the page paces its next ask.
      if (rest === `${DOC}/version`) { json(response, { version: served.version, patch: null }); return; }
      const part = /^\/part\/([0-9a-f]+)$/.exec(rest.slice(DOC.length));
      if (part) {
        try { binary(response, readFileSync(join(FIXTURES, 'bracket', `${part[1]}.xbm`))); } catch { notFound(response); }
        return;
      }
      if (/^\/part\/[0-9a-f]+\/groups$/.test(rest.slice(DOC.length))) { json(response, { faces: {}, edges: {} }); return; }
      const fact = /^\/part\/[0-9a-f]+\/(face|edge|vertex)\/(\d+)$/.exec(rest.slice(DOC.length));
      if (fact) { json(response, { kind: fact[1], ordinal: Number(fact[2]) }); return; }
      notFound(response);
      return;
    }
    if (path.includes('/__cad/') || /\.(woff2|ttf)$/.test(path)) { notFound(response); return; }
    response.setHeader('Content-Type', 'text/html');
    response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/harness.css"><style>body { margin: 0 } #root > div { width: 100vw !important; height: 100vh !important }</style></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>');
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: (process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1')
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });

  /**
   * One page over the bracket. `deviceScaleFactor: 1` keeps a screenshot's pixels the viewport's.
   * Its `update()` serves a new version of the document, as a build that changed none of its parts
   * writes one, and settles once the page shows it.
   */
  const open = async ({ timeout = 30000 } = {}) => {
    const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1 });
    t.after(() => page.close().catch(() => {}));
    page.setDefaultTimeout(timeout);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // No Worker: what a worker would build is built on the main thread, as for a host without one.
    await page.addInitScript(() => { window.Worker = undefined; });
    await page.goto(`http://127.0.0.1:${server.address().port}/?file=${FILE}`);
    const update = async () => {
      const next = JSON.parse(initial);
      next.version = `${VERSION}-${(updates += 1)}`;
      served = { version: next.version, structure: Buffer.from(JSON.stringify(next)) };
      // The page hears it on its next wait (about a second), reads it and puts it on screen.
      await page.waitForFunction(version => window.__cadViewerLoad?.complete && window.__cadViewerLoad.modelKey.endsWith(`:${version}`), next.version);
    };
    return { page, errors, pane: page.getByTestId('one'), update };
  };
  return { open };
}
