import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// A STEP workspace the harness can open, served from the committed fixture under
// `renderers/step/__fixtures__/step` (its README says how those bytes were made).
//
// A STEP is the one format whose load is a conversation rather than a download:
// the catalog names a store view, the view names components by an immutable
// `surfaceInput`, and only `POST /__cad/surfaces` turns those inputs into the
// object digests the `.surf` bytes are fetched by. The descriptor the real store
// route serves is NOT materialized, so that round trip is mandatory and this
// server implements it exactly as `client/surfaceResolution.js` validates it:
// the returned URL must be `/__cad/store` carrying the same `tree`,
// `surfaceInput` and a lowercase 64-hex `object`.

const FIXTURE = new URL('../step/__fixtures__/step/', import.meta.url);

const read = (name) => readFile(new URL(name, FIXTURE));

/** Everything the fixture is, loaded once: the view, the sidecar and the surf bytes by object digest. */
export async function loadStepFixture() {
  const assembly = await read('assembly.json');
  const sidecar = JSON.parse(await read('hinge_block.step.json'));
  const view = JSON.parse(assembly);
  // `surfaceObject` is the digest of the `.surf` payload itself — the pin a real
  // surface resolution hands back. Deriving it here keeps the fixture to the two
  // files the client actually reads.
  const { createHash } = await import('node:crypto');
  const surfaces = new Map();
  for (const [cid, component] of Object.entries(view.components)) {
    const bytes = await read(`components/${cid}.surf`);
    surfaces.set(component.surfaceInput, { cid, bytes, object: createHash('sha256').update(bytes).digest('hex') });
  }
  return { assembly, view, sidecar, surfaces, file: 'hinge_block.step' };
}

/** The catalog entry the real scanner writes for this document, with the sidecar inline. */
export function stepCatalogEntry({ view, sidecar, assembly, file }) {
  return {
    file,
    rootRelativeFile: file,
    kind: 'assembly',
    url: `/__cad/store?file=${view.tree}&documentHash=${view.documentHash}`,
    hash: view.tree,
    documentHash: view.documentHash,
    bytes: assembly.length,
    sourceUrl: `/${file}.json`,
    // Inline: the renderer compiles kinematics and animation from the entry and
    // never fetches the sidecar. The scanner only supplies it when the sidecar
    // declares the current schema AND a `documentHash` equal to the digest of
    // the STEP's bytes; a fixture failing either gate silently has no Kinematics
    // tab and no Animate tool.
    sourceSidecar: sidecar,
    poseUrl: `/${file}.json`,
    animationHash: 'fixture-animation',
  };
}

/**
 * Serve the harness over the STEP fixture and hand back an `open`.
 *
 * @param {{ after: (cleanup: () => unknown) => void }} lifetime — a test context, or
 *   any object with its `after`, so one server and one browser can span a whole file.
 * @param {{ onRequest?: (url: URL, request: import('node:http').IncomingMessage) => void }} [options]
 */
export async function serveStepHarness(t, { onRequest } = {}) {
  const fixture = await loadStepFixture();
  const entry = stepCatalogEntry(fixture);
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-step-browser-'));
  let server, browser;
  t.after(async () => {
    await browser?.close();
    if (server) await new Promise(resolve => server.close(resolve));
    await rm(temporary, { recursive: true, force: true });
  });
  await build({ entryPoints: [fileURLToPath(new URL('./index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  // Two stylesheets: the package's compiled one, and the one esbuild extracts
  // from what the bundle imports (the drawing editor's). Without the second the
  // editor has no layout and sizes its canvas from an unconstrained container.
  const bundledCss = await readFile(join(temporary, 'harness.css')).catch(() => '');
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  const requests = [];

  const json = (response, body) => { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(body)); };
  const notFound = (response) => { response.statusCode = 404; response.end(); };
  const readBody = (request) => new Promise((resolve) => {
    const chunks = [];
    request.on('data', chunk => chunks.push(chunk));
    request.on('end', () => { try { resolve(JSON.parse(Buffer.concat(chunks).toString() || '{}')); } catch { resolve({}); } });
  });

  server = createServer(async (request, response) => {
    const url = new URL(request.url, 'http://test');
    requests.push(`${request.method} ${url.pathname}${url.search}`);
    onRequest?.(url, request);
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); return; }
    if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); return; }
    if (url.pathname === '/harness.css') { response.setHeader('Content-Type', 'text/css'); response.end(bundledCss); return; }
    if (url.pathname.endsWith('/__cad/catalog')) { json(response, { rootId: root, entries: [entry] }); return; }
    if (url.pathname.endsWith('/__cad/server')) { json(response, { rootId: root, rootPath: '/models', backend: 'cadgen' }); return; }
    if (url.pathname.endsWith('/__cad/artifact')) { json(response, { state: 'compiled' }); return; }
    if (url.pathname.endsWith('/__cad/surfaces')) {
      const body = await readBody(request);
      json(response, {
        viewId: fixture.view.viewId,
        components: Object.fromEntries((body.components || []).map(({ cid, surfaceInput }) => {
          const surface = fixture.surfaces.get(surfaceInput);
          if (!surface) return [cid, { surfaceInput, state: 'failed', error: `unknown surface input for ${cid}` }];
          return [cid, { surfaceInput, state: 'ready', surfaceObject: surface.object, byteLength: surface.bytes.length,
            url: `/__cad/store?tree=${fixture.view.tree}&surfaceInput=${surfaceInput}&object=${surface.object}` }];
        })),
      });
      return;
    }
    if (url.pathname.endsWith('/__cad/store')) {
      const object = url.searchParams.get('object');
      if (object) {
        const surface = [...fixture.surfaces.values()].find(entry => entry.object === object);
        if (!surface) { notFound(response); return; }
        response.setHeader('Content-Type', 'application/octet-stream');
        response.setHeader('Content-Length', String(surface.bytes.length));
        response.end(request.method === 'HEAD' ? undefined : surface.bytes);
        return;
      }
      if (url.searchParams.get('file')?.endsWith('/assembly.json')) {
        response.setHeader('Content-Type', 'application/json'); response.end(fixture.assembly); return;
      }
      notFound(response); return;
    }
    // A cold cache: the tessellation cache probes and writes back, and a clean
    // 404 is what "nothing warm here" looks like. Falling through to the HTML
    // shell instead makes the probe throw on a page that is not JSON.
    if (url.pathname.includes('/__tess_cache/')) { notFound(response); return; }
    if (url.pathname.endsWith(`/${fixture.file}.json`)) { json(response, fixture.sidecar); return; }
    if (/\.(woff2|ttf)$/.test(url.pathname)) { notFound(response); return; }
    response.setHeader('Content-Type', 'text/html');
    response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/harness.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>');
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: process.platform === 'darwin'
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });

  /** One page over the fixture. `deviceScaleFactor: 1` keeps a screenshot's pixels the viewport's. */
  const open = async ({ timeout = 30000 } = {}) => {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
    t.after(() => page.close().catch(() => {}));
    page.setDefaultTimeout(timeout);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // No Worker: the surf tessellator falls back to the main thread, which is
    // what `renderAssetClient` does for a host without one.
    await page.addInitScript(() => { window.Worker = undefined; });
    await page.goto(`http://127.0.0.1:${server.address().port}/?file=${fixture.file}`);
    return { page, errors, pane: page.getByTestId('one') };
  };
  return { open, requests, fixture, entry, port: () => server.address().port };
}
