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

const leaf = (id, name) => ({ children: [], id, leafPartIds: [id], name, nodeType: 'part' });
// Where the base goes in the descriptor, and so which batch it lands in: after the
// first eight and inside the second sixteen.
const ARM_COUNT = 24, BASE_AT = 19;

/**
 * The same two shapes, staged as a package that really ARRIVES IN PIECES — and,
 * crucially, in THREE publishes rather than two.
 *
 * The loader's ceilings double: it publishes when 8 components are pending, then 16,
 * then 32 (`PROGRESSIVE_PUBLISH_FIRST_COMPONENTS`). A two-component package therefore
 * publishes exactly once, and even a nine-component one publishes its second batch as
 * the FINAL one — which ends the load, which changes what the viewport is mounted with,
 * which makes it re-adopt the scene for reasons of its own. Neither can show what
 * `viewport.commitScene()` is for.
 *
 * Twenty-five components publish at 8, at 24 and at 25, so the middle publish is an
 * in-place change with NOTHING else moving: same scene object, same loading state, same
 * camera request. Twenty-four are the arm, all at the origin, so which eight of them
 * arrive first cannot change the model's box. The twenty-fifth is the base, listed
 * nineteenth so it lands in the MIDDLE batch — and on its own it is far larger than the
 * arms (20 × 20 × 10 against 10 × 8 × 8), so the box, the ground sized from it, the
 * depth range and the framing all change on that publish and on no other.
 *
 * Two surface inputs may name one surface object — that is what a content-addressed
 * store does with two inputs that produce identical geometry — so the twenty-four arms
 * are twenty-four components served from one `.surf`. They are HELD by input, one gate
 * per batch, so each publish is a test's to place rather than a race.
 */
export function stageProgressiveFixture(fixture) {
  const original = fixture.view;
  const occurrenceNamed = name => original.occurrences.find(occurrence => occurrence.name === name);
  const armOccurrence = occurrenceNamed('arm'), baseOccurrence = occurrenceNamed('base');
  const arm = original.components[armOccurrence.component], base = original.components[baseOccurrence.component];
  const armSurface = fixture.surfaces.get(arm.surfaceInput);
  const surfaces = new Map(fixture.surfaces);
  const components = {};
  const occurrences = [];
  const children = [];
  const inputs = [];
  const addArm = (index) => {
    const suffix = String(index).padStart(2, '0');
    const cid = `${arm.contentHash.slice(0, 14)}${suffix}`;
    const surfaceInput = `${arm.surfaceInput.slice(0, 62)}${suffix}`;
    components[cid] = { ...arm, contentHash: `${cid}${arm.contentHash.slice(16)}`, surfaceInput, brep: `components/${cid}.brep` };
    surfaces.set(surfaceInput, { ...armSurface, cid });
    const id = `o1.${index + 2}`;
    // Every arm at the origin: the box the first batch spans is one arm's, whichever
    // eight of them get there first.
    occurrences.push({ ...armOccurrence, id, name: `arm_${index + 1}`, component: cid, transform: baseOccurrence.transform });
    children.push(leaf(id, `arm_${index + 1}`));
    inputs.push(surfaceInput);
  };
  for (let index = 0; index < ARM_COUNT; index += 1) {
    if (index === BASE_AT) {
      components[baseOccurrence.component] = base;
      occurrences.push({ ...baseOccurrence, id: 'o1.1' });
      children.push(leaf('o1.1', 'base'));
      inputs.push(base.surfaceInput);
    }
    addArm(index);
  }
  const view = {
    ...original, components, occurrences,
    bbox: { min: [-10, -10, -5], max: [10, 10, 5] },
    stats: { ...original.stats, occurrenceCount: occurrences.length, shapeCount: occurrences.length },
    assembly: { root: { ...original.assembly.root, children, leafPartIds: children.map(child => child.id) } }
  };
  // Gate `a` is the second batch, gate `b` the one component that completes the load.
  const heldInputs = new Map([
    ...inputs.slice(8, 24).map(input => [input, 'a']),
    ...inputs.slice(24).map(input => [input, 'b'])
  ]);
  return { ...fixture, view, surfaces, heldInputs, assembly: Buffer.from(JSON.stringify(view)) };
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
    // the STEP's bytes; a fixture failing either gate silently has no Position
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
 * @param {{ onRequest?: (url: URL, request: import('node:http').IncomingMessage) => void,
 *   progressive?: boolean }} [options]  `progressive` serves the twenty-five-component
 *   staging (`stageProgressiveFixture`) and HOLDS each batch after the first until
 *   `release(gate)` is called, so the package's three publishes are a test's to place
 *   rather than a race.
 */
export async function serveStepHarness(t, { onRequest, progressive = false } = {}) {
  const loaded = await loadStepFixture();
  const fixture = progressive ? stageProgressiveFixture(loaded) : loaded;
  const entry = stepCatalogEntry(fixture);
  // Each gate is a latch a test can close again (`hold`), so one server can serve the same
  // package progressively more than once — an open, and then a REOPEN in a fresh page.
  const opened = {}, gates = {};
  const hold = name => { gates[name] = new Promise(resolve => { opened[name] = resolve; }); };
  for (const name of ['a', 'b']) hold(name);
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
        // Held by INPUT, not by object: identical components share one object, and it is
        // one component's download that waits. Only the BODY waits, so a metadata probe
        // still answers and the component is slow rather than unsizeable.
        const gate = fixture.heldInputs?.get(url.searchParams.get('surfaceInput'));
        if (gate && request.method !== 'HEAD') await gates[gate];
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

  /**
   * One page over the fixture. `deviceScaleFactor: 1` keeps a screenshot's pixels the viewport's.
   * `state` opens the page as a previous session left this file: the viewer state a test read
   * off `window.cadHarness.state` earlier, seeded before any of the app runs.
   */
  const open = async ({ timeout = 30000, state = null, hasTouch = false } = {}) => {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1, hasTouch });
    t.after(() => page.close().catch(() => {}));
    page.setDefaultTimeout(timeout);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // No Worker: the surf tessellator falls back to the main thread, which is
    // what `renderAssetClient` does for a host without one.
    await page.addInitScript(() => { window.Worker = undefined; });
    if (state) await page.addInitScript(stored => { window.__cadViewerState = stored; }, state);
    await page.goto(`http://127.0.0.1:${server.address().port}/?file=${fixture.file}`);
    return { page, errors, pane: page.getByTestId('one') };
  };
  return { open, requests, fixture, entry, port: () => server.address().port, release: gate => opened[gate]?.(), hold };
}
