import { createHash } from 'node:crypto';
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
// object digests the `.surf` bytes are fetched by — and, when it names a
// tessellation, into each component's stored mesh, which cadgen makes. The
// descriptor the real store route serves is NOT materialized, so that round
// trip is mandatory and this server implements it exactly as
// `client/surfaceResolution.js` validates it: the returned URL must be
// `/__cad/store` carrying the same `tree`, `surfaceInput` and a lowercase 64-hex
// `object`, and a requested mesh's row must be that mesh's probe row.

const FIXTURE = new URL('../step/__fixtures__/step/', import.meta.url);

const read = (name) => readFile(new URL(name, FIXTURE));

// The LOD levels the fixture stores a mesh at (`components/<cid>.l<level>.glb`).
const MESH_LEVELS = [0, 1, 2, 3];

/**
 * Everything the fixture is, loaded once: the view, the sidecar, the surf bytes by object digest,
 * and each component's stored meshes, decoded so the harness's store can serve them for any input.
 */
export async function loadStepFixture() {
  const { decodeComponentTessellation } = await import('@text-to-cad/core/lib/surf/tessellationCache.js');
  const assembly = await read('assembly.json');
  const sidecar = JSON.parse(await read('hinge_block.step.json'));
  const view = JSON.parse(assembly);
  // `surfaceObject` is the digest of the `.surf` payload itself — the pin a real
  // surface resolution hands back. Deriving it here keeps the fixture to the files
  // the client actually reads.
  const surfaces = new Map();
  for (const [cid, component] of Object.entries(view.components)) {
    const bytes = await read(`components/${cid}.surf`);
    const meshes = new Map();
    for (const level of MESH_LEVELS) {
      meshes.set(level, decodeComponentTessellation(new Uint8Array(await read(`components/${cid}.l${level}.glb`))));
    }
    surfaces.set(component.surfaceInput, { cid, bytes, object: createHash('sha256').update(bytes).digest('hex'), meshes });
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
  // The same package with no `bbox`, as a descriptor that declares none is served: the viewer
  // frames its first batch and again once it is whole (`declare(false)` serves this one).
  const undeclared = { ...view };
  delete undeclared.bbox;
  return { ...fixture, view, surfaces, heldInputs, assembly: Buffer.from(JSON.stringify(view)),
    undeclaredAssembly: Buffer.from(JSON.stringify(undeclared)) };
}

/**
 * The base alone, staged as the SINGLE-PART STEP cadgen writes: one component, one occurrence,
 * `entryKind: "part"`, and — as in every such file cadgen writes — the part under a root product
 * OCCT named by its label entry, `=>[0:1:1:2]`, which the reader hands back as the occurrence's,
 * the root's and the view's name. It carries no sidecar: kinematics need two parts.
 */
export function stageSinglePartFixture(fixture) {
  const original = fixture.view;
  const XCAF_ENTRY = '=>[0:1:1:2]';
  const base = original.occurrences.find(occurrence => occurrence.name === 'base');
  const view = {
    ...original,
    entryKind: 'part', label: XCAF_ENTRY,
    components: { [base.component]: original.components[base.component] },
    occurrences: [{ ...base, id: 'o1.1', name: XCAF_ENTRY }],
    bbox: { min: [-10, -10, -5], max: [10, 10, 5] },
    stats: { ...original.stats, occurrenceCount: 1, shapeCount: 1 },
    assembly: { root: { id: 'o1', name: XCAF_ENTRY, nodeType: 'assembly', leafPartIds: ['o1.1'],
      children: [{ ...leaf('o1.1', XCAF_ENTRY) }] } }
  };
  const surfaces = new Map([...fixture.surfaces].filter(([input]) => input === original.components[base.component].surfaceInput));
  return { ...fixture, view, surfaces, sidecar: null, file: 'hinge_base.step', assembly: Buffer.from(JSON.stringify(view)) };
}

/**
 * The fixture saved again, as cadgen lists a rebuilt file: new STEP bytes — so a new document hash,
 * and a new tree and view over them — holding the same components, and the sidecar written again,
 * bound to the new bytes, its mates, named pose and routine as they were. `revision` names it.
 */
export function reviseFixture(fixture, revision) {
  const digest = text => createHash('sha256').update(`${text}:${revision}`).digest('hex');
  const view = { ...fixture.view, tree: digest(fixture.view.tree), viewId: digest(fixture.view.viewId), documentHash: digest(fixture.view.documentHash) };
  const sidecar = fixture.sidecar ? { ...fixture.sidecar, documentHash: view.documentHash } : null;
  return { ...fixture, view, sidecar, assembly: Buffer.from(JSON.stringify(view)) };
}

/**
 * cadgen's mesh store as the harness serves it: every component of `fixture` has a mesh at each
 * fixture LOD level, keyed and encoded as the store keeps it, for whatever input names it (a staged
 * component shares its shape's mesh). `warm` holds every component at the standard tier already, as
 * an earlier open leaves it; otherwise a mesh is stored once a surface request asks for it
 * (`produce`), as cadgen meshes on request. Answers the routes the client reads it by: a probe, a
 * batch read and a single read.
 */
async function meshStore(fixture, { warm = false } = {}) {
  const [cache, { encodeMeshFixture }, { lodTessellationForLevel }, { installTestTessellationLadder }] = await Promise.all([
    import('@text-to-cad/core/lib/surf/tessellationCache.js'),
    import('@text-to-cad/core/lib/surf/testing.js'),
    import('@text-to-cad/core/lib/surf/lodPolicy.js'),
    import('@text-to-cad/core/lib/surf/testing.js'),
  ]);
  installTestTessellationLadder();
  const stored = new Map();
  const produce = (surfaceInput, tessellation = {}) => {
    const surface = fixture.surfaces.get(surfaceInput);
    if (!surface) return null;
    const key = cache.tessellationCacheKey(surfaceInput, tessellation);
    if (!stored.has(key)) {
      // The fixture level these tolerances name, else the standard tier's shape under their key.
      const level = MESH_LEVELS.find(candidate => cache.tessellationCacheKey(surfaceInput, lodTessellationForLevel(candidate)) === key) ?? 1;
      const { component, partColor } = surface.meshes.get(level);
      const bytes = encodeMeshFixture(component, { surfaceInput, surfaceObject: surface.object, tessellation, partColor });
      const row = cache.validateTessellationProbeRow({ schemaVersion: cache.MESH_INDEX_SCHEMA,
        object: createHash('sha256').update(bytes).digest('hex'), ...cache.tessellationPayloadFacts(bytes) });
      stored.set(key, { bytes: Buffer.from(bytes), row });
    }
    return stored.get(key).row;
  };
  if (warm) for (const component of Object.values(fixture.view.components)) produce(component.surfaceInput);
  const binary = (response, bytes) => {
    response.setHeader('Content-Type', 'application/octet-stream');
    response.setHeader('Content-Length', String(bytes.byteLength));
    response.end(bytes);
  };
  return {
    produce,
    probe: keys => ({ entries: Object.fromEntries(keys.filter(key => stored.has(key)).map(key => [key, stored.get(key).row])) }),
    batch: (response, requested) => binary(response, Buffer.from(cache.encodeTessellationCacheBatch(requested.map(({ tessellationInput, object }) => {
      const entry = stored.get(tessellationInput);
      return entry?.row.object === object ? entry.bytes : null;
    })))),
    read: (response, key) => { const entry = stored.get(key); if (entry) { binary(response, entry.bytes); return true; } return false; },
  };
}

/**
 * The catalog entry the real scanner writes for this document, with the sidecar inline: the file
 * by its absolute path, under the `/models` the harness opens a bare `?file=` name in.
 */
export function stepCatalogEntry({ view, sidecar, assembly, file }) {
  if (!sidecar) {
    return { file: `/models/${file}`, kind: 'part', url: `/__cad/store?file=${view.tree}&documentHash=${view.documentHash}`,
      hash: view.tree, documentHash: view.documentHash, bytes: assembly.length };
  }
  return {
    file: `/models/${file}`,
    kind: 'assembly',
    url: `/__cad/store?file=${view.tree}&documentHash=${view.documentHash}`,
    hash: view.tree,
    documentHash: view.documentHash,
    bytes: assembly.length,
    sourceUrl: `/${file}.json`,
    // Inline: the renderer loads kinematics and animation from the entry and
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
 * How the real scanner lists a STEP whose bytes have no build: a bare part with no hash and no mesh,
 * under bytes of its own, whatever the file held before. A rewritten file is listed so until its
 * build lands, and for good when the build fails.
 */
function unbuiltEntry(listed) {
  return { file: listed.file, kind: 'part', url: '/__cad/store?file=unbuilt-0f1e2d3c4b5a69788796a5b4', hash: '',
    documentHash: createHash('sha256').update(`unbuilt:${listed.documentHash}`).digest('hex'), bytes: 0 };
}

/**
 * The page a spec opens, and so the viewer: it fills the page. Small, because a software renderer
 * (CI's SwiftShader) pays for every pixel of every frame; but tall enough that a tree row's
 * context menu opens below the pointer rather than being pushed up under it.
 */
export const VIEWPORT = Object.freeze({ width: 800, height: 600 });

// The harness bundle, built once per process: every server a spec starts (a second fixture, a
// staged one) serves the same bytes, so none of them bundles the viewer again.
let bundled;
function harnessBundle() {
  bundled ??= (async () => {
    const temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-step-browser-'));
    try {
      await build({ entryPoints: [fileURLToPath(new URL('./index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.avif': 'dataurl', '.woff2': 'dataurl', '.svg': 'dataurl' } });
      // Two stylesheets: the package's compiled one, and the one esbuild extracts
      // from what the bundle imports (the drawing editor's). Without the second the
      // editor has no layout and sizes its canvas from an unconstrained container.
      return { bundle: await readFile(join(temporary, 'harness.js')), bundledCss: await readFile(join(temporary, 'harness.css')).catch(() => '') };
    } finally {
      await rm(temporary, { recursive: true, force: true });
    }
  })();
  return bundled;
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
 *   rather than a race; `declare(false)` then serves its descriptor without the `bbox` it
 *   declares. `singlePart` serves the base alone as a cadgen single-part STEP
 *   (`stageSinglePartFixture`), its part named by an XCAF label entry. `warmCache` serves a mesh
 *   store that already holds every component at the standard tier (`meshStore`); without it the
 *   store is cold, and a component's mesh is made when its surface request asks for it.
 */
export async function serveStepHarness(t, { onRequest, progressive = false, singlePart = false, warmCache = false } = {}) {
  const loaded = await loadStepFixture();
  const fixture = progressive ? stageProgressiveFixture(loaded) : singlePart ? stageSinglePartFixture(loaded) : loaded;
  const meshes = await meshStore(fixture, { warm: warmCache });
  const entry = stepCatalogEntry(fixture);
  // The file as the catalog lists it now (`revise`), and every revision a page may still ask
  // for, by its tree.
  let current = fixture, listed = entry, revisions = 0;
  const views = new Map([[fixture.view.tree, fixture]]);
  // Each gate is a latch a test can close again (`hold`), so one server can serve the same
  // package progressively more than once — an open, and then a REOPEN in a fresh page.
  const opened = {}, gates = {};
  const hold = name => { gates[name] = new Promise(resolve => { opened[name] = resolve; }); };
  for (const name of ['a', 'b']) hold(name);
  let declaring = true;
  // Set by `fail()`: the file was saved again and its build failed.
  let failing = false;
  let server, browser;
  const pages = new Set();
  t.after(async () => {
    await browser?.close();
    if (server) await new Promise(resolve => server.close(resolve));
  });
  const { bundle, bundledCss } = await harnessBundle();
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
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); return; }
    if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); return; }
    if (url.pathname === '/harness.css') { response.setHeader('Content-Type', 'text/css'); response.end(bundledCss); return; }
    if (url.pathname.endsWith('/__cad/catalog')) { json(response, { entries: [failing ? unbuiltEntry(listed) : listed] }); return; }
    if (url.pathname.endsWith('/__cad/server')) { json(response, { backend: 'cadgen' }); return; }
    if (url.pathname.endsWith('/__cad/artifact')) {
      json(response, failing ? { state: 'failed', reason: 'build_failed', error: 'failed to read STEP file: the CAD kernel could not parse it' }
        : { state: 'compiled' });
      return;
    }
    if (url.pathname.endsWith('/__cad/surfaces')) {
      const body = await readBody(request);
      const shown = views.get(body.tree) || fixture;
      json(response, {
        viewId: shown.view.viewId,
        components: Object.fromEntries((body.components || []).map(({ cid, surfaceInput }) => {
          const surface = fixture.surfaces.get(surfaceInput);
          if (!surface) return [cid, { surfaceInput, state: 'failed', error: `unknown surface input for ${cid}` }];
          return [cid, { surfaceInput, state: 'ready', surfaceObject: surface.object, byteLength: surface.bytes.length,
            url: `/__cad/store?tree=${shown.view.tree}&surfaceInput=${surfaceInput}&object=${surface.object}`,
            ...(body.tessellation ? { mesh: meshes.produce(surfaceInput, body.tessellation) } : {}) }];
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
        // one component's download that waits (selectors read it; display reads the mesh,
        // held where the mesh store answers).
        const gate = fixture.heldInputs?.get(url.searchParams.get('surfaceInput'));
        if (gate && request.method !== 'HEAD') await gates[gate];
        response.setHeader('Content-Type', 'application/octet-stream');
        response.setHeader('Content-Length', String(surface.bytes.length));
        response.end(request.method === 'HEAD' ? undefined : surface.bytes);
        return;
      }
      if (url.searchParams.get('file')?.endsWith('/assembly.json')) {
        const shown = views.get(url.searchParams.get('file').split('/')[0]) || fixture;
        response.setHeader('Content-Type', 'application/json');
        response.end(declaring || !shown.undeclaredAssembly ? shown.assembly : shown.undeclaredAssembly);
        return;
      }
      notFound(response); return;
    }
    if (url.pathname.endsWith('/__tess_cache/probe')) {
      json(response, meshes.probe((await readBody(request)).tessellationInputs || []));
      return;
    }
    if (url.pathname.endsWith('/__tess_cache/batch')) {
      const entries = (await readBody(request)).entries || [];
      // A warm reopen reads its meshes in batches: a batch carrying a held component waits too.
      for (const gate of new Set(entries.map(entry => fixture.heldInputs?.get(String(entry?.tessellationInput).slice(0, 64))).filter(Boolean))) {
        await gates[gate];
      }
      meshes.batch(response, entries);
      return;
    }
    if (request.method === 'GET' && url.pathname.endsWith('.glb')) {
      const key = decodeURIComponent(url.pathname.split('/__tess_cache/')[1].slice(0, -'.glb'.length));
      // A cold component's display waits on its mesh, so that is the body a staged batch holds:
      // by INPUT, as identical components share one mesh's geometry.
      const gate = fixture.heldInputs?.get(key.slice(0, 64));
      if (gate) await gates[gate];
      if (meshes.read(response, key)) return;
    }
    // A mesh the store does not hold: a clean 404, never the HTML shell, which a
    // reader would fail to parse.
    if (url.pathname.includes('/__tess_cache/')) { notFound(response); return; }
    if (url.pathname.endsWith(`/${fixture.file}.json`)) { if (current.sidecar) json(response, current.sidecar); else notFound(response); return; }
    if (/\.(woff2|ttf)$/.test(url.pathname)) { notFound(response); return; }
    response.setHeader('Content-Type', 'text/html');
    response.end('<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/harness.css"><style>body { margin: 0 } #root > div { width: 100vw !important; height: 100vh !important }</style></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>');
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: (process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1')
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });

  /**
   * One page over the fixture. `deviceScaleFactor: 1` keeps a screenshot's pixels the viewport's.
   * `record` opens the page as a previous session left its tab: the tab record a test read off
   * `window.cadHarness.tabStore.getSnapshot()` earlier, seeded before any of the app runs; `store:
   * 'session'` keeps the tab record in the page's own sessionStorage instead, so a reload of the
   * page is a reload of the tab and a new page is a new tab; `init` is a function run in the page
   * before the app, as `page.addInitScript` runs it. Every page is its own browser context: a new tab.
   * The viewer fills the page (`VIEWPORT`), whatever size the harness's own layout gives it. Its
   * `update()` saves the file again and settles once the page shows the new revision.
   */
  const open = async ({ timeout = 30000, record = null, store = null, hasTouch = false, init = null } = {}) => {
    const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1, hasTouch });
    pages.add(page);
    t.after(() => page.close().catch(() => {}));
    page.setDefaultTimeout(timeout);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // No Worker: mesh decoding falls back to the main thread, which is what
    // `renderAssetClient` does for a host without one.
    await page.addInitScript(() => { window.Worker = undefined; window.__cadPreviewChromeIdleMs = 5000; });
    if (record) await page.addInitScript(stored => { window.__cadTabRecord = stored; }, record);
    // A script of the test's own that must run before the app does (a render counter on
    // React's devtools hook, say).
    if (init) await page.addInitScript(init);
    await page.goto(`http://127.0.0.1:${server.address().port}/?file=${fixture.file}${store === 'session' ? '&store=session' : ''}`);
    // An update of the file on screen: saved again (`revise`), the catalog read, and the new
    // revision on screen and settled. The harness's client does not poll.
    const update = async () => {
      const revision = revise();
      await page.evaluate(() => window.cadHarness.a.client.refresh());
      await page.waitForFunction(wanted => {
        const state = window.cadHarness.a.controller?.readState();
        return state?.revision === wanted && state.loading === false;
      }, revision);
    };
    // The file saved again, broken: its build fails, and the catalog lists it as it lists any file
    // with no build (`unbuiltEntry`) until it is saved once more. Resolves once the page has read it.
    const fail = async () => {
      failing = true;
      await page.evaluate(() => window.cadHarness.a.client.refresh());
    };
    return { page, errors, pane: page.getByTestId('one'), update, fail };
  };
  /**
   * The file saved again (`reviseFixture`): the catalog lists the new revision from now on, and a
   * page hears of it the next time it reads the catalog. Answers the new document hash: the revision
   * a view reports (`readState().revision`) once the new one is on screen.
   */
  const revise = () => {
    revisions += 1;
    current = reviseFixture(fixture, revisions);
    views.set(current.view.tree, current);
    listed = stepCatalogEntry(current);
    return current.view.documentHash;
  };
  // A test's pages, closed when it ends: one left in preview, orbiting, would keep a software
  // renderer busy through every test after it. The file goes back to the revision it started at.
  const closePages = async () => {
    for (const page of pages) await page.close().catch(() => {});
    pages.clear();
    current = fixture;
    listed = entry;
    failing = false;
  };
  return { open, closePages, requests, fixture, entry, revise, port: () => server.address().port, release: gate => opened[gate]?.(), hold,
    declare: on => { declaring = on !== false; } };
}
