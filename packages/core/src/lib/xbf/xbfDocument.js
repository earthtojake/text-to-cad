// A cadgen engine document -- an `.xbf`, or a STEP the engine read -- as a page reads it from the
// engine that serves it (`cadgen serve`, `cadgen/engine/serve.py`): its structure as JSON
// (prototypes with their names, geometry keys, colours and element names by ordinal; instances
// with world matrices; the tree; the version) and one XBM2 buffer per prototype, read as views
// over the fetched bytes (`xbm.js`). The viewer's xbf renderer and the snapshot's headless stage
// both load through here, so they draw the same bytes. The viewer's page reads the engine through
// its own server (`/__cad/api/...`, `cadgen/viewer/documents.py`), with the fetch its client
// sends every request with (the CAD app's goes over its tunnel); the snapshot's stage reads the
// engine's own port. Either is a document URL here, and every read is made beside it.
//
// A part is fetched once per geometry key: a new version of the document fetches the parts
// whose keys it has not held (an edit changes the keys of the parts it touched, and only those)
// and keeps the rest, buffers and the geometry built over them, as FreeCAD recomputes only the
// objects an edit touched. What the kernel measures of an element is asked of the engine when a
// person asks (`fetchXbfElementFacts`), never extracted ahead. Beside the document, the engine's
// look of the regular display modes (`GET /api/look`, `xbfLook.js`), read once per engine.

import { fetchXbfLook } from "./xbfLook.js";
import { readXbmPart, xbmUnmeshedFaces } from "./xbm.js";

const DOC_PATH = /^(.*\/api\/doc\/[^/?#]+)\/?$/;
// How many part requests are in flight at once: a browser holds about six connections per host.
const PART_CONCURRENCY = 6;
// How long a version request waits on the engine for a new version, in seconds (the engine caps it at 60).
export const XBF_VERSION_WAIT_SECONDS = 25;

/**
 * Where a served document is read: its API URL -- the engine's own,
 * `http://127.0.0.1:<port>/api/doc/<id>`, or the viewer's relay of it, `/__cad/api/doc/<id>`
 * (resolved against the page) -- and the base every other read of that engine is made under
 * (`base`: the URL before `/api/doc/<id>`, its look at `<base>/api/look`).
 * @param {string | { url: string }} value
 * @returns {{ url: string, origin: string, base: string, doc: string }}
 */
export function xbfDocumentSource(value) {
  const text = String(typeof value === "string" ? value : value?.url || "").trim();
  const match = DOC_PATH.exec(text.split(/[?#]/)[0]);
  let parsed = null;
  try { parsed = match ? new URL(match[1], globalThis.location?.href) : null; } catch { /* not a URL here */ }
  if (!parsed) throw new Error(`an engine document is read from its API URL (…/api/doc/<id>), not ${JSON.stringify(text)}`);
  const url = parsed.href.replace(/\/$/, "");
  return { url, origin: parsed.origin, base: url.slice(0, url.lastIndexOf("/api/doc/")), doc: decodeURIComponent(url.split("/").pop()) };
}

async function failure(response, what) {
  let detail = "";
  try { detail = (await response.json())?.error || ""; } catch { /* not JSON */ }
  return new Error(`${what}: the engine answered ${response.status}${detail ? ` (${detail})` : ""}`);
}

async function getJson(fetchImpl, url, what, signal) {
  const response = await fetchImpl(url, { signal, cache: "no-store" });
  if (!response.ok) throw await failure(response, what);
  return response.json();
}

/**
 * One part's buffer and its views, shared by every version of a document that holds its key,
 * and by every scene drawn of them. What a scene builds over it (its geometry) is kept on it
 * (`hold`) and released with it: the last document that holds it releases it.
 */
function createPart(key, buffer) {
  const mesh = readXbmPart(buffer);
  const held = new Map();
  let refs = 0;
  const part = {
    key,
    mesh,
    unmeshed: xbmUnmeshedFaces(mesh),
    get bytes() { return buffer.byteLength; },
    /** What `make()` builds over this part, once; `dispose(value)` when the part is released. */
    hold(name, make, dispose) {
      let found = held.get(name);
      if (!found) held.set(name, found = { value: make(), dispose });
      return found.value;
    },
    retain() { refs += 1; return part; },
    release() {
      refs -= 1;
      if (refs > 0) return;
      for (const { value, dispose } of held.values()) dispose?.(value);
      held.clear();
    }
  };
  return part;
}

async function inBatches(items, limit, run) {
  let next = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const item = items[next++];
      await run(item);
    }
  });
  await Promise.all(workers);
}

/**
 * @typedef {object} XbfDocument
 * @property {{ url: string, origin: string, base: string, doc: string }} source
 * @property {object} structure  The engine's structure JSON, as it answered.
 * @property {string} version
 * @property {Map<string, ReturnType<typeof createPart>>} parts  By geometry key.
 * @property {object} look  The engine's look of the regular display modes (`parseXbfLook`).
 * @property {typeof fetch} fetch  What it was read with: every later read of its engine (an element's
 *   facts, a part's groups) is made with it.
 * @property {{ fetched: string[], kept: string[], structureMs: number, partsMs: number, bytes: number }} load
 * @property {() => void} release  Let go of its parts (the last holder disposes their geometry).
 */

/**
 * Read a served document: its structure, then every part it holds that `previous` (an earlier
 * version of the same document, or of any document from the same engine) does not; and the
 * engine's look, unless `previous` came from the same engine and holds it.
 *
 * @param {string | { url: string }} source  The document's API URL (`xbfDocumentSource`).
 * @param {{ previous?: XbfDocument | null, fetch?: typeof fetch, signal?: AbortSignal,
 *   onProgress?: (progress: { done: number, total: number }) => void }} [options]
 * @returns {Promise<XbfDocument>}
 */
export async function loadXbfDocument(source, { previous = null, fetch: fetchImpl = globalThis.fetch, signal, onProgress } = {}) {
  const where = xbfDocumentSource(source);
  const started = performance.now();
  const looked = previous?.look && previous.source?.base === where.base ? Promise.resolve(previous.look)
    : fetchXbfLook(where.base, { fetch: fetchImpl, signal });
  // Read beside the structure; a failure of it is reported once the structure is in.
  looked.catch(() => {});
  const structure = await getJson(fetchImpl, where.url, "the document's structure", signal);
  if (!Array.isArray(structure?.prototypes) || !Array.isArray(structure?.instances)) {
    throw new Error("the engine's structure has no prototypes and instances");
  }
  const structureMs = performance.now() - started;
  const parts = new Map();
  const fetched = [];
  const kept = [];
  const wanted = [...new Set(structure.prototypes.map(prototype => String(prototype.key)))];
  const missing = [];
  for (const key of wanted) {
    const held = previous?.parts?.get(key);
    if (held) { parts.set(key, held.retain()); kept.push(key); } else missing.push(key);
  }
  let done = kept.length;
  let bytes = 0;
  onProgress?.({ done, total: wanted.length });
  const partsStarted = performance.now();
  try {
    await inBatches(missing, PART_CONCURRENCY, async (key) => {
      const response = await fetchImpl(`${where.url}/part/${encodeURIComponent(key)}`, { signal });
      if (!response.ok) throw await failure(response, `part ${key}`);
      const buffer = await response.arrayBuffer();
      parts.set(key, createPart(key, buffer).retain());
      fetched.push(key);
      bytes += buffer.byteLength;
      done += 1;
      onProgress?.({ done, total: wanted.length });
    });
  } catch (error) {
    for (const part of parts.values()) part.release();
    throw error;
  }
  let look;
  try {
    look = await looked;
  } catch (error) {
    for (const part of parts.values()) part.release();
    throw error;
  }
  let released = false;
  return {
    source: where,
    structure,
    version: String(structure.version || ""),
    parts,
    look,
    fetch: fetchImpl,
    load: { fetched, kept, structureMs: Math.round(structureMs), partsMs: Math.round(performance.now() - partsStarted), bytes },
    release() {
      if (released) return;
      released = true;
      for (const part of parts.values()) part.release();
    }
  };
}

/**
 * Wait on the engine for a version of the document other than `after`: the engine answers at
 * once when it has one, else when a build's patch lands, else after `wait` seconds with the
 * same version. Given `progress` (the count of the document's build last heard), it answers too
 * when that count moves: a build writing the document reports its stage, or fails.
 * @returns {Promise<{ version: string, patch: object | null, building: object | null,
 *   failed: { model?: string, error?: string, progress?: object | null } | null, progress: number | null }>}
 *   `building`: the last progress frame of the build writing the document now (`progress.py`'s);
 *   `failed`: the last build of it that failed, until one succeeds or another begins; `progress`:
 *   the count to wait past next.
 */
export async function waitForXbfVersion(source, after, { wait = XBF_VERSION_WAIT_SECONDS, progress = null, fetch: fetchImpl = globalThis.fetch, signal } = {}) {
  const where = xbfDocumentSource(source);
  const counted = Number.isInteger(progress) && progress >= 0 ? `&progress=${progress}` : "";
  const query = `after=${encodeURIComponent(after || "")}&wait=${encodeURIComponent(wait)}${counted}`;
  const answer = await getJson(fetchImpl, `${where.url}/version?${query}`, "the document's version", signal);
  const record = value => (value && typeof value === "object" && !Array.isArray(value) ? value : null);
  return { version: String(answer?.version || ""), patch: answer?.patch || null, building: record(answer?.building),
    failed: record(answer?.failed), progress: Number.isInteger(answer?.progress) ? answer.progress : null };
}

const placePoint = (m, p) => [0, 1, 2].map(row => m[row] * p[0] + m[4 + row] * p[1] + m[8 + row] * p[2] + m[12 + row]);

/**
 * An element's facts (`fetchXbfElementFacts`, measured on the part's shape in its own frame) where
 * the instance places them: its points (a centroid, an edge's ends, a vertex's position) through the
 * instance's world matrix (column-major, the structure's), and a face's exact box as the box of its
 * placed corners. Lengths and areas a placement does not change.
 * @param {object} facts
 * @param {number[]} matrix  The instance's 4x4 world matrix, column-major.
 */
export function placeXbfFacts(facts, matrix) {
  if (!facts || !Array.isArray(matrix) || matrix.length !== 16) return facts;
  const placed = { ...facts };
  if (Array.isArray(facts.centroid)) placed.centroid = placePoint(matrix, facts.centroid);
  if (Array.isArray(facts.position)) placed.position = placePoint(matrix, facts.position);
  if (Array.isArray(facts.endpoints)) placed.endpoints = facts.endpoints.map(point => placePoint(matrix, point));
  if (facts.box?.min && facts.box?.max) {
    const corners = [];
    for (const x of [facts.box.min[0], facts.box.max[0]]) for (const y of [facts.box.min[1], facts.box.max[1]]) {
      for (const z of [facts.box.min[2], facts.box.max[2]]) corners.push(placePoint(matrix, [x, y, z]));
    }
    placed.box = { min: [0, 1, 2].map(axis => Math.min(...corners.map(c => c[axis]))), max: [0, 1, 2].map(axis => Math.max(...corners.map(c => c[axis]))) };
  }
  return placed;
}

/**
 * What the kernel measures of one element of a part, now: a face's area, centroid, surface type,
 * exact box and check; an edge's length, curve type, class, faces and endpoints; a vertex's
 * position. Measured on the exact shape, never on the mesh.
 * @param {"face" | "edge" | "vertex"} kind
 */
export function fetchXbfElementFacts(source, key, kind, ordinal, { fetch: fetchImpl = globalThis.fetch, signal } = {}) {
  if (!["face", "edge", "vertex"].includes(kind)) return Promise.reject(new Error(`no ${kind} facts: an element is a face, an edge or a vertex`));
  const where = xbfDocumentSource(source);
  return getJson(fetchImpl, `${where.url}/part/${encodeURIComponent(key)}/${kind}/${Number(ordinal)}`, `${kind} ${ordinal}`, signal);
}

/**
 * How a pick of one face or edge of a part grows, as the engine reads it from the part's shape
 * (`Topology.groups`): each face's tangent group and each edge's chain, by ordinal, a group named
 * by its smallest member. Asked for when Group faces or Group edges first needs it.
 * @returns {Promise<{ faces: Record<string, number>, edges: Record<string, number> }>}
 */
export function fetchXbfPartGroups(source, key, { fetch: fetchImpl = globalThis.fetch, signal } = {}) {
  const where = xbfDocumentSource(source);
  return getJson(fetchImpl, `${where.url}/part/${encodeURIComponent(key)}/groups`, `part ${key}'s groups`, signal);
}
