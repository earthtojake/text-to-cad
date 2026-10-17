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
// the catalog names a store view, the view names each component's part (its key),
// and the part store answers a part's record -- its display mesh and its selector
// table (`components/<cid>.selectors.json`, cadgen's), each read by the part's key and
// the object the record names -- for a part the store holds; `POST /__cad/parts`
// answers the same record for one cadgen has to derive first, as this server does
// for a cold store (`client/partResolution.js` validates it). `POST /__cad/measure`
// answers a face's exact area and centroid, as cadgen measured them for the fixture
// (`components/<cid>.measures.json`).

const FIXTURE = new URL('../step/__fixtures__/step/', import.meta.url);

const read = (name) => readFile(new URL(name, FIXTURE));

/**
 * Everything the fixture is, loaded once: the view, the sidecar and cadgen's articulation of its
 * kinematics, each part by its key: its stored display mesh (`components/<cid>.glb`), decoded
 * so the harness's store can serve it for any part, and its selector table; and `ids`, the
 * occurrence tokens the tree mints for its root, its base and its arm, read off the view so no
 * test writes an id down (a token names a place in the tree, not a position).
 */
export async function loadStepFixture() {
  const { decodeComponentTessellation } = await import('@text-to-cad/core/lib/parts/tessellationCache.js');
  const assembly = await read('assembly.json');
  const sidecar = JSON.parse(await read('hinge_block.step.json'));
  const articulation = JSON.parse(await read('hinge_block.articulation.json'));
  const view = JSON.parse(assembly);
  const partData = new Map();
  for (const [cid, component] of Object.entries(view.components)) {
    const mesh = decodeComponentTessellation(new Uint8Array(await read(`components/${cid}.glb`)));
    const table = await read(`components/${cid}.selectors.json`);
    const measures = JSON.parse(await read(`components/${cid}.measures.json`));
    partData.set(component.part, { cid, mesh, measures,
      selectors: { bytes: table, object: createHash('sha256').update(table).digest('hex') } });
  }
  const occurrence = name => view.occurrences.find(entry => entry.name === name).id;
  const ids = { root: view.assembly.root.id, base: occurrence('base'), arm: occurrence('arm') };
  return { assembly, view, sidecar, articulation, partData, ids, file: 'hinge_block.step' };
}

/**
 * A token-shaped id for a staged occurrence the fixture's tree never minted: `o:` and twelve
 * hex digits, as every occurrence id is, distinct from the fixture's own.
 */
const stagedId = index => `o:f${index.toString(16).padStart(11, '0')}`;

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
 * Two parts may hold identical geometry -- that is what a content-addressed store does
 * with two inputs that produce it -- so the twenty-four arms are twenty-four parts served
 * from one arm's mesh. They are HELD by part, one gate per batch, so each publish is a
 * test's to place rather than a race -- held the way cadgen holds a part it is still
 * meshing: the store does not list it, and its part row answers `pending` until the
 * gate opens, so the page asks again. No response is ever held
 * open. A browser keeps six connections to a host and the loader runs up to eight lanes
 * (`navigator.hardwareConcurrency`), so a held body could fill every connection and starve
 * an unheld component's request queued behind it: the first batch would never land.
 */
export function stageProgressiveFixture(fixture) {
  const original = fixture.view;
  const occurrenceNamed = name => original.occurrences.find(occurrence => occurrence.name === name);
  const armOccurrence = occurrenceNamed('arm'), baseOccurrence = occurrenceNamed('base');
  const arm = original.components[armOccurrence.component], base = original.components[baseOccurrence.component];
  const armData = fixture.partData.get(arm.part);
  const partData = new Map(fixture.partData);
  const components = {};
  const occurrences = [];
  const children = [];
  const parts = [];
  const addArm = (index) => {
    const suffix = String(index).padStart(2, '0');
    const cid = `${arm.contentHash.slice(0, 14)}${suffix}`;
    const part = `${arm.part.slice(0, 62)}${suffix}${arm.part.slice(64)}`;
    components[cid] = { ...arm, contentHash: `${cid}${arm.contentHash.slice(16)}`, part, brep: `components/${cid}.brep` };
    partData.set(part, { ...armData, cid });
    const id = stagedId(index);
    // Every arm at the origin: the box the first batch spans is one arm's, whichever
    // eight of them get there first.
    occurrences.push({ ...armOccurrence, id, name: `arm_${index + 1}`, component: cid, transform: baseOccurrence.transform });
    children.push(leaf(id, `arm_${index + 1}`));
    parts.push(part);
  };
  for (let index = 0; index < ARM_COUNT; index += 1) {
    if (index === BASE_AT) {
      components[baseOccurrence.component] = base;
      occurrences.push({ ...baseOccurrence });
      children.push(leaf(baseOccurrence.id, 'base'));
      parts.push(base.part);
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
  const heldParts = new Map([
    ...parts.slice(8, 24).map(part => [part, 'a']),
    ...parts.slice(24).map(part => [part, 'b'])
  ]);
  // The same package with no `bbox`, as a descriptor that declares none is served: the viewer
  // frames its first batch and again once it is whole (`declare(false)` serves this one).
  const undeclared = { ...view };
  delete undeclared.bbox;
  return { ...fixture, view, partData, heldParts, assembly: Buffer.from(JSON.stringify(view)),
    undeclaredAssembly: Buffer.from(JSON.stringify(undeclared)) };
}

/**
 * The base alone, staged as the SINGLE-PART STEP cadgen writes: one component, one occurrence,
 * `entryKind: "part"`, the part under a root product the STEP gives no name (so the view calls
 * the root `model`, as every unnamed root) and named as its own product names it, `base`. It
 * carries no sidecar: kinematics need two parts.
 */
export function stageSinglePartFixture(fixture) {
  const original = fixture.view;
  const base = original.occurrences.find(occurrence => occurrence.name === 'base');
  const view = {
    ...original,
    entryKind: 'part', label: 'model',
    components: { [base.component]: original.components[base.component] },
    occurrences: [{ ...base }],
    bbox: { min: [-10, -10, -5], max: [10, 10, 5] },
    stats: { ...original.stats, occurrenceCount: 1, shapeCount: 1 },
    assembly: { root: { id: original.assembly.root.id, name: 'model', nodeType: 'assembly', leafPartIds: [base.id],
      children: [{ ...leaf(base.id, 'base') }] } }
  };
  const partData = new Map([...fixture.partData].filter(([part]) => part === original.components[base.component].part));
  return { ...fixture, view, partData, sidecar: null, articulation: null, file: 'hinge_base.step', assembly: Buffer.from(JSON.stringify(view)) };
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
 * A build's preview revision of the fixture, as its feed names it before the STEP is written (cadgen's
 * STORE.md 9b): the model's result tree -- another tree, whose components are the result's own bodies
 * under ids of their own, each named by the same part key as the saved file's (a part is named by its
 * geometry) and placed by the same occurrence tokens -- read at its tree with the producer, and naming
 * no document. `preview` numbers it. `parts` is the feed's map, `{cid: part key}`, and `annotations`
 * the object the build resolves the model's declarations into against the tree: the fixture's
 * articulation and routine, as the saved file's row will carry them.
 */
export function stagePreviewFixture(fixture, preview) {
  const digest = text => createHash('sha256').update(`preview:${text}:${preview}`).digest('hex');
  const renamed = new Map(Object.keys(fixture.view.components).map(cid => [cid, digest(cid).slice(0, 16)]));
  const components = Object.fromEntries(Object.entries(fixture.view.components).map(([cid, component]) => {
    const id = renamed.get(cid);
    return [id, { ...component, contentHash: `${id}${digest(component.contentHash).slice(16)}`, brep: `components/${id}.brep` }];
  }));
  const occurrences = fixture.view.occurrences.map(occurrence => ({ ...occurrence, component: renamed.get(occurrence.component) }));
  const { documentHash: _saved, ...result } = fixture.view;
  const view = { ...result, tree: digest(fixture.view.tree), viewId: digest(fixture.view.viewId), components, occurrences };
  const annotations = { kind: 'preview-annotations', schemaVersion: 1, tree: view.tree,
    articulation: fixture.articulation, appearance: null, display: null, animation: fixture.sidecar?.animation ?? null };
  return { ...fixture, view, assembly: Buffer.from(JSON.stringify(view)),
    parts: Object.fromEntries(Object.entries(components).map(([cid, component]) => [cid, component.part])), annotations };
}

/**
 * cadgen's part store as the harness serves it: every component of `fixture` has its part -- its
 * display mesh, encoded as the store keeps it for whatever part names it (a staged component shares
 * its shape's mesh), and its selector table -- under the record that names both. `warm` holds every
 * part already, as a build leaves it; otherwise a part is stored once a part request names its
 * component (`derive`), as cadgen's one job derives what a cleared store lacks. Answers the routes
 * the client reads it by: a probe, a batch read and a single read of either object.
 */
async function meshStore(fixture, { warm = false } = {}) {
  const [cache, { encodeMeshFixture, partMeshFacts, partSelectorFacts }] = await Promise.all([
    import('@text-to-cad/core/lib/parts/tessellationCache.js'),
    import('@text-to-cad/core/lib/parts/testing.js'),
  ]);
  const stored = new Map();
  const digest = bytes => createHash('sha256').update(bytes).digest('hex');
  const derive = (part) => {
    const data = fixture.partData.get(part);
    if (!data) return null;
    if (!stored.has(part)) {
      const bytes = encodeMeshFixture(data.mesh.component, { part });
      const record = {
        glb: { object: digest(bytes), ...partMeshFacts(bytes) },
        selectors: { object: data.selectors.object, ...partSelectorFacts(data.selectors.bytes) },
      };
      stored.set(part, { bytes: Buffer.from(bytes), table: data.selectors.bytes, record });
    }
    return stored.get(part).record;
  };
  if (warm) {
    for (const component of Object.values(fixture.view.components)) derive(component.part);
  }
  const binary = (response, bytes) => {
    response.setHeader('Content-Type', 'application/octet-stream');
    response.setHeader('Content-Length', String(bytes.byteLength));
    response.end(bytes);
  };
  return {
    derive,
    probe: parts => ({ entries: Object.fromEntries(parts.filter(part => stored.has(part)).map(part => [part, stored.get(part).record])) }),
    batch: (response, requested) => binary(response, Buffer.from(cache.encodeTessellationCacheBatch(requested.map(({ part, object }) => {
      const entry = stored.get(part);
      return entry?.record.glb.object === object ? entry.bytes : null;
    })))),
    read: (response, part, role, object) => {
      const entry = stored.get(part);
      if (!entry || entry.record[role]?.object !== object) return false;
      binary(response, role === 'glb' ? entry.bytes : entry.table);
      return true;
    },
  };
}

/**
 * The catalog entry the real scanner writes for this document, with what its sidecar means
 * inline: the file by its absolute path, under the `/models` the harness opens a bare `?file=`
 * name in.
 */
export function stepCatalogEntry({ view, sidecar, articulation, assembly, file }) {
  // The kind is the tree's answer (`entryKind`), as the scanner relays it: a sidecar changes nothing of it.
  const kind = view.entryKind === 'assembly' ? 'assembly' : 'part';
  if (!sidecar) {
    return { file: `/models/${file}`, kind, url: `/__cad/store?file=${view.tree}&documentHash=${view.documentHash}`,
      hash: view.tree, documentHash: view.documentHash, bytes: assembly.length };
  }
  return {
    file: `/models/${file}`,
    kind,
    url: `/__cad/store?file=${view.tree}&documentHash=${view.documentHash}`,
    hash: view.tree,
    documentHash: view.documentHash,
    bytes: assembly.length,
    // Inline, as the scanner publishes them: cadgen's articulation of the kinematics and the
    // baked animation. The renderer reads both from the entry and never fetches the sidecar;
    // the scanner only supplies them when the sidecar declares the current schema AND a
    // `documentHash` equal to the digest of the STEP's bytes, so a fixture failing either gate
    // silently has no Position tab and no Animate tool.
    articulation,
    animation: sidecar.animation,
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
 * @param {{ progressive?: boolean, singlePart?: boolean, warmCache?: boolean, bare?: boolean }} [options]
 *   `progressive` serves the twenty-five-component staging (`stageProgressiveFixture`) and
 *   HOLDS each batch after the first until
 *   `release(gate)` is called, so the package's three publishes are a test's to place
 *   rather than a race; `declare(false)` then serves its descriptor without the `bbox` it
 *   declares. `singlePart` serves the base alone as a cadgen single-part STEP
 *   (`stageSinglePartFixture`), its part named `base` in `hinge_base.step`. `warmCache` serves a mesh
 *   store that already holds every component's display mesh (`meshStore`); without it the
 *   store is cold, and a component's mesh is made when its part request asks for it. `bare` lists
 *   the file at first without its sidecar -- no mates, no routine -- as a model whose declarations
 *   its next build is the first to resolve; a revision (`revise`) is listed with them.
 */
export async function serveStepHarness(t, { progressive = false, singlePart = false, warmCache = false, bare = false } = {}) {
  const loaded = await loadStepFixture();
  const fixture = progressive ? stageProgressiveFixture(loaded) : singlePart ? stageSinglePartFixture(loaded) : loaded;
  const meshes = await meshStore(fixture, { warm: warmCache });
  const entry = stepCatalogEntry(bare ? { ...fixture, sidecar: null, articulation: null } : fixture);
  // The file as the catalog lists it now (`revise`), and every revision a page may still ask
  // for, by its tree.
  let current = fixture, listed = entry, revisions = 0;
  const views = new Map([[fixture.view.tree, fixture]]);
  // The file's build feed (`GET /__cad/preview`), as a test announces it (`announce`): the newest
  // build's status and the preview revision it names, answered at once with a cursor that moves
  // with each announcement, which paces the client's feed. Until a test announces, no build is
  // listed. The annotations objects a preview names, by hash (`GET /__cad/store?annotations=`).
  let feed = { state: 'disconnected', revision: null }, feedSerial = 0, previews = 0;
  const annotationObjects = new Map();
  // Each gate is a latch a test can close again (`hold`), so one server can serve the same
  // package progressively more than once — an open, and then a REOPEN in a fresh page. A
  // component behind a closed gate is one cadgen is still meshing (`stageProgressiveFixture`).
  const closed = new Set();
  const hold = name => { closed.add(name); };
  const meshing = part => closed.has(fixture.heldParts?.get(part));
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
  // What the server is answering right now, and who waits for it to answer nothing (`idle`).
  const answering = new Map();
  let idlers = [];

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
    answering.set(response, `${request.method} ${url.pathname}`);
    response.once('close', () => {
      answering.delete(response);
      if (!answering.size) for (const done of idlers.splice(0)) done();
    });
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); return; }
    if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); return; }
    if (url.pathname === '/harness.css') { response.setHeader('Content-Type', 'text/css'); response.end(bundledCss); return; }
    if (url.pathname.endsWith('/__cad/catalog')) { json(response, { entries: [failing ? unbuiltEntry(listed) : listed] }); return; }
    if (url.pathname.endsWith('/__cad/preview')) {
      json(response, { output: `/models/${fixture.file}`, file: `/models/${fixture.file}`, ...feed, feedCursor: `harness:${feedSerial}` });
      return;
    }
    if (url.pathname.endsWith('/__cad/server')) { json(response, { backend: 'cadgen' }); return; }
    if (url.pathname.endsWith('/__cad/artifact')) {
      json(response, failing ? { state: 'failed', reason: 'build_failed', error: 'failed to read STEP file: the CAD kernel could not parse it' }
        : { state: 'compiled' });
      return;
    }
    if (url.pathname.endsWith('/__cad/parts/cancel')) { response.statusCode = 204; response.end(); return; }
    if (url.pathname.endsWith('/__cad/measure')) {
      const body = await readBody(request);
      const measured = fixture.partData.get(body.part)?.measures?.[body.face - 1];
      if (measured) json(response, measured);
      else { response.statusCode = 400; json(response, { error: `no face ${body.face} of part ${body.part}` }); }
      return;
    }
    if (url.pathname.endsWith('/__cad/parts')) {
      const body = await readBody(request);
      const shown = views.get(body.tree) || fixture;
      // A held component is still being meshed: its row is pending under the request's
      // subscriber token, as cadgen answers one, and the page asks again.
      const job = body.job || `job-${createHash('sha256').update(JSON.stringify(body.components || [])).digest('hex').slice(0, 16)}`;
      const waiting = (body.components || []).some(({ part }) => meshing(part));
      json(response, {
        viewId: shown.view.viewId,
        ...(waiting ? { job } : {}),
        components: Object.fromEntries((body.components || []).map(({ cid, part }) => {
          if (!fixture.partData.has(part)) return [cid, { part, state: 'failed', error: `unknown part for ${cid}` }];
          if (meshing(part)) return [cid, { part, state: 'pending', job }];
          return [cid, { part, state: 'ready', record: meshes.derive(part) }];
        })),
      });
      return;
    }
    if (url.pathname.endsWith('/__cad/store')) {
      const annotations = url.searchParams.get('annotations');
      if (annotations) {
        if (annotationObjects.has(annotations)) json(response, annotationObjects.get(annotations)); else notFound(response);
        return;
      }
      const file = url.searchParams.get('file') || '';
      if (file.endsWith('/assembly.json')) {
        const shown = views.get(file.split('/')[0]) || fixture;
        response.setHeader('Content-Type', 'application/json');
        response.end(declaring || !shown.undeclaredAssembly ? shown.assembly : shown.undeclaredAssembly);
        return;
      }
      notFound(response);
      return;
    }
    if (url.pathname.endsWith('/__tess_cache/probe')) {
      // A part cadgen is still making is not in the store yet, though an earlier open made it:
      // a reopen's held component is resolved, and waits, as a cold one does.
      const parts = (await readBody(request)).parts || [];
      json(response, meshes.probe(parts.filter(part => !meshing(part))));
      return;
    }
    if (url.pathname.endsWith('/__tess_cache/batch')) {
      meshes.batch(response, (await readBody(request)).entries || []);
      return;
    }
    const object = request.method === 'GET' && /\/__tess_cache\/([^/]+?)\.(glb|selectors\.json)$/.exec(url.pathname);
    if (object && meshes.read(response, decodeURIComponent(object[1]), object[2] === 'glb' ? 'glb' : 'selectors',
      url.searchParams.get('object'))) return;
    // A mesh the store does not hold: a clean 404, never the HTML shell, which a
    // reader would fail to parse.
    if (url.pathname.includes('/__tess_cache/')) { notFound(response); return; }
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
  /**
   * Settles once the server is answering nothing, as one that never holds a request open soon is
   * between a page's requests; fails naming what it still answers after `timeout` ms.
   */
  const idle = ({ timeout = 10000 } = {}) => new Promise((resolve, reject) => {
    if (!answering.size) { resolve(); return; }
    const done = () => { clearTimeout(timer); resolve(); };
    const timer = setTimeout(() => {
      idlers = idlers.filter(idler => idler !== done);
      reject(new Error(`the server still holds ${[...new Set(answering.values())].join(', ')} open`));
    }, timeout);
    idlers.push(done);
  });
  /**
   * A build of the file, as its feed reports it from now on: `status` is the feed's answer but its
   * cursor (`state`, `phase`, `error`, `superseded`, `preview`; one build, revision 1, unless named).
   */
  const announce = status => { feed = { epoch: 'harness', revision: 1, ...status }; feedSerial += 1; };
  /**
   * A build's preview revision of the file as it is listed now (`stagePreviewFixture`): its view is
   * served at its tree, its annotations object stored under its hash. Answers what the feed names
   * of it -- `tree`, `parts`, `annotations` (the hash) -- and `named(extra)`, the feed's `preview`
   * field for it, every part named and the annotations not, unless `extra` says otherwise.
   */
  const preview = () => {
    previews += 1;
    const staged = stagePreviewFixture(current, previews);
    views.set(staged.view.tree, staged);
    const annotations = createHash('sha256').update(JSON.stringify(staged.annotations)).digest('hex');
    annotationObjects.set(annotations, staged.annotations);
    const named = (extra = {}) => ({ tree: staged.view.tree, producer: staged.view.producer, parts: staged.parts, complete: true, annotations: null, ...extra });
    return { tree: staged.view.tree, parts: staged.parts, annotations, named };
  };
  return { open, closePages, requests, idle, fixture, release: gate => { closed.delete(gate); }, hold,
    declare: on => { declaring = on !== false; }, announce, preview, revise };
}
