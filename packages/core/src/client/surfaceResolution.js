import { viewerOriginUrl } from "./origin.js";
import { tessellationCacheKey, tessellationQuality, validateTessellationProbeRow } from "../lib/surf/tessellationCache.js";
const DIGEST_RE = /^[0-9a-f]{64}$/;
const INITIAL_POLL_MS = 80;
const MAX_POLL_MS = 640;
// The longest a request whose derivation is still pending waits before asking again.
const MAX_PENDING_POLL_MS = 5000;
// The most components one POST /__cad/surfaces may name (cadgen/viewer/surfaces.py's
// MAX_COMPONENTS); a larger request is sent as several.
export const SURFACE_REQUEST_MAX_COMPONENTS = 64;

function abortError() {
  if (typeof DOMException === "function") {
    return new DOMException("The operation was aborted.", "AbortError");
  }
  const error = new Error("The operation was aborted.");
  error.name = "AbortError";
  return error;
}

function digest(value, label) {
  const text = String(value || "");
  if (!DIGEST_RE.test(text)) throw new TypeError(`${label} must be a full lowercase digest`);
  return text;
}

function waitForPoll(delay, signal) {
  if (signal?.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const aborted = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", aborted);
      resolve();
    }, delay);
    signal?.addEventListener("abort", aborted, { once: true });
  });
}

async function guardedPost(path, body, { signal, client }) {
  return path.endsWith("/cancel")
    ? client.cancelSurfaceRequest(body, { signal })
    : client.requestSurfaces(body, { signal });
}

function verifiedReadyRow(row, { tree, cid, surfaceInput, client, tessellation }) {
  if (!row || row.state !== "ready" || row.surfaceInput !== surfaceInput) {
    throw new Error(`Surface response changed the immutable input for ${cid}`);
  }
  const surfaceObject = digest(row.surfaceObject, `surface object for ${cid}`);
  const byteLength = Number(row.byteLength);
  if (!Number.isSafeInteger(byteLength) || byteLength <= 0) {
    throw new Error(`Surface response has an invalid byte length for ${cid}`);
  }
  const parsed = new URL(String(row.url || ""), "http://cad-viewer.local");
  if (parsed.origin !== "http://cad-viewer.local" || parsed.pathname !== "/__cad/store"
      || parsed.searchParams.get("tree") !== tree
      || parsed.searchParams.get("surfaceInput") !== surfaceInput
      || parsed.searchParams.get("object") !== surfaceObject) {
    throw new Error(`Surface response has an invalid immutable URL for ${cid}`);
  }
  // The component's selector table (cadgen's, derived with the surface): the same store route,
  // bound to the same input, naming the table's object.
  const selectors = row.selectors;
  const selectorsObject = digest(selectors?.object, `selector table object for ${cid}`);
  const selectorsByteLength = Number(selectors?.byteLength);
  if (!Number.isSafeInteger(selectorsByteLength) || selectorsByteLength <= 0) {
    throw new Error(`Surface response has an invalid selector table byte length for ${cid}`);
  }
  const selectorsParsed = new URL(String(selectors?.url || ""), "http://cad-viewer.local");
  if (selectorsParsed.origin !== "http://cad-viewer.local" || selectorsParsed.pathname !== "/__cad/store"
      || selectorsParsed.searchParams.get("tree") !== tree
      || selectorsParsed.searchParams.get("surfaceInput") !== surfaceInput
      || selectorsParsed.searchParams.get("object") !== selectorsObject) {
    throw new Error(`Surface response has an invalid selector table URL for ${cid}`);
  }
  // A request that named a tessellation is ready only with that mesh stored: its row is the
  // probe row a read of the mesh store would answer.
  let mesh = null;
  if (tessellation) {
    mesh = validateTessellationProbeRow(row.mesh, {
      tessellationInput: tessellationCacheKey(surfaceInput, tessellation), surfaceInput, surfaceObject,
    });
    if (!mesh) throw new Error(`Surface response has no valid mesh for ${cid}`);
  }
  const url = (location) => (client ? viewerOriginUrl(client.origin, `${location.pathname}${location.search}`) : `${location.pathname}${location.search}`);
  return Object.freeze({
    surfaceInput,
    surfaceObject,
    surfUrl: url(parsed),
    byteLength,
    selectorsObject,
    selectorsUrl: url(selectorsParsed),
    selectorsByteLength,
    ...(mesh ? { mesh } : {}),
  });
}

function verifiedReplacementView(value, tree) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || value.tree !== tree || !value.surfaceProducer
      || typeof value.surfaceProducer !== "object" || Array.isArray(value.surfaceProducer)
      || !value.components || typeof value.components !== "object" || Array.isArray(value.components)) {
    throw new Error("Surface response has an invalid replacement view");
  }
  digest(value.viewId, "replacement surface viewId");
  for (const [cid, component] of Object.entries(value.components)) {
    digest(component?.surfaceInput, `replacement surface input for ${cid}`);
  }
  return value;
}

export class SurfaceResolutionError extends Error {
  constructor(message, { code = "", cid = "", replacementView = null } = {}) {
    super(message);
    this.name = "SurfaceResolutionError";
    this.code = code;
    this.cid = cid;
    this.replacementView = replacementView;
  }
}

/**
 * Resolve exact SURF objects for one frozen runtime view. A fully warm mesh
 * path does not call this function. The request never computes D or producer
 * identity in JavaScript; it forwards the backend-prepared opaque pins.
 *
 * `tessellation`, when given, also asks for every component's mesh at those
 * tolerances (`{}` is the default pair): cadgen meshes what its store lacks,
 * and each ticket carries the mesh's probe row (`mesh`), so its body is read
 * next without another probe.
 *
 * `onReady(cid, ticket)`, when given, hears each component the moment its row is
 * ready, once, while the request goes on waiting for the rest of its components:
 * a caller that asked for many need not hold the first behind the last.
 *
 * `onFailed(cid, error)`, when given, hears each component cadgen could not derive
 * or mesh, once, with its own error, and the request goes on for the rest: it
 * resolves with the ready ones. Without it, a failed component fails the request,
 * once every ready row of the response that names it has been announced.
 *
 * `onPending(cid)`, when given, hears a component cadgen is still deriving (its
 * surface or mesh was not in the store), on every answer that says so: what a
 * loading screen needs to say it is meshing rather than reading.
 */
export async function resolveSurfaceComponents(descriptor, requested, { signal, client, onReady = null, onFailed = null, onPending = null, tessellation = undefined } = {}) {
  if (!client) throw new TypeError("Surface resolution requires a CAD workspace service");
  const list = Array.isArray(requested) ? requested : [];
  if (list.length <= SURFACE_REQUEST_MAX_COMPONENTS) {
    return resolveSurfaceRequest(descriptor, list, { signal, client, onReady, onFailed, onPending, tessellation });
  }
  // Every chunk is its own request (and subscriber job); one failing stops the others.
  const controller = new AbortController();
  const forward = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", forward);
  try {
    const chunks = [];
    for (let start = 0; start < list.length; start += SURFACE_REQUEST_MAX_COMPONENTS) {
      chunks.push(list.slice(start, start + SURFACE_REQUEST_MAX_COMPONENTS));
    }
    const results = await Promise.all(chunks.map((chunk) => (
      resolveSurfaceRequest(descriptor, chunk, { signal: controller.signal, client, onReady, onFailed, onPending, tessellation }).catch((error) => {
        controller.abort();
        throw error;
      })
    )));
    const ready = new Map();
    for (const result of results) for (const [cid, ticket] of result) ready.set(cid, ticket);
    return ready;
  } catch (error) {
    // A sibling aborted by another chunk's failure reports that failure, not its abort.
    throw signal?.aborted ? abortError() : error;
  } finally {
    signal?.removeEventListener("abort", forward);
  }
}

/** The subscriber token a surface response names, on the response or on a pending row. */
function subscriberToken(payload) {
  if (payload?.job) return String(payload.job);
  const rows = payload?.components && typeof payload.components === "object" ? Object.values(payload.components) : [];
  return String(rows.find((row) => row?.job)?.job || "");
}

async function resolveSurfaceRequest(descriptor, requested, { signal, client, onReady = null, onFailed = null, onPending = null, tessellation = undefined }) {
  const tree = digest(descriptor?.tree, "surface tree");
  const viewId = digest(descriptor?.viewId, "surface viewId");
  const producer = descriptor?.surfaceProducer;
  if (!producer || typeof producer !== "object" || Array.isArray(producer)) {
    throw new TypeError("surface view is missing its attested producer");
  }
  const components = requested.map(({ cid, surfaceInput, surfaceObject }) => ({
    cid: String(cid || ""),
    surfaceInput: digest(surfaceInput, `surface input for ${cid}`),
    ...(surfaceObject ? { expectedSurfaceObject: digest(surfaceObject, `surface object for ${cid}`) } : {}),
  }));
  if (!components.length || components.some((entry) => !entry.cid)) {
    throw new TypeError("surface request must name at least one component");
  }

  // The pair the server keys the mesh by: both tolerances, as the request names them.
  const quality = tessellation == null ? null : tessellationQuality(tessellation);
  const meshTessellation = quality
    ? { chordTolerance: quality.chordTolerance, angleTolerance: quality.angleTolerance } : null;
  const base = { tree, viewId, producer, components, ...(meshTessellation ? { tessellation: meshTessellation } : {}) };
  let job = "";
  let cancelled = false;
  const cancel = () => {
    if (cancelled || !job) return;
    cancelled = true;
    void guardedPost("/__cad/surfaces/cancel", { job }, { client }).catch(() => {});
  };
  signal?.addEventListener("abort", cancel);
  let delay = INITIAL_POLL_MS;
  const startedAt = Date.now();
  const announced = new Set();
  // Each component settles on its own: one cadgen could not derive or mesh fails alone, with its
  // own error, and stays failed for the rest of the request.
  const failed = new Map();
  try {
    for (;;) {
      if (signal?.aborted) throw abortError();
      // A first post (no token yet) is not aborted in flight: its answer, which comes at once,
      // carries the token a cancel needs. Aborted there, the server would go on deriving for a
      // view nobody watches until its subscriber expired, its daemon job with it.
      const payload = await guardedPost("/__cad/surfaces", { ...base, ...(job ? { job } : {}) },
        { signal: job ? signal : undefined, client });
      if (signal?.aborted) {
        job ||= subscriberToken(payload);
        throw abortError(); // the finally cancels the job, its token now known
      }
      if (!payload || payload.viewId !== viewId || !payload.components
          || typeof payload.components !== "object" || Array.isArray(payload.components)) {
        throw new Error("Surface response does not belong to the requested view");
      }
      if (payload.replacementView) {
        throw new SurfaceResolutionError("The pinned surface producer is unavailable", {
          code: "replacement-view",
          replacementView: verifiedReplacementView(payload.replacementView, tree),
        });
      }
      const responseJob = String(payload.job || "");
      if (responseJob) {
        if (job && job !== responseJob) throw new Error("Surface request changed subscriber token");
        job = responseJob;
      }
      const ready = new Map();
      let pending = false;
      for (const request of components) {
        if (failed.has(request.cid)) continue;
        const row = payload.components[request.cid];
        if (!row || row.surfaceInput !== request.surfaceInput) {
          throw new Error(`Surface response omitted ${request.cid}`);
        }
        if (row.state === "failed") {
          const error = new SurfaceResolutionError(String(row.error || `Surface derivation failed for ${request.cid}`), {
            code: String(row.code || ""), cid: request.cid,
          });
          failed.set(request.cid, error);
          onFailed?.(request.cid, error);
          continue;
        }
        if (row.state === "pending") {
          const rowJob = String(row.job || job || "");
          if (!rowJob || (job && rowJob !== job)) throw new Error("Surface response has an invalid subscriber token");
          job = rowJob;
          pending = true;
          onPending?.(request.cid);
          continue;
        }
        const ticket = verifiedReadyRow(row, { tree, ...request, client, tessellation: meshTessellation });
        if (request.expectedSurfaceObject && ticket.surfaceObject !== request.expectedSurfaceObject) {
          throw new Error(`Surface response changed the pinned object for ${request.cid}`);
        }
        ready.set(request.cid, ticket);
        if (onReady && !announced.has(request.cid)) {
          announced.add(request.cid);
          onReady(request.cid, ticket);
        }
      }
      // A caller that hears no failures one by one is told of the first, as the request's.
      if (failed.size && !onFailed) throw failed.values().next().value;
      if (!pending) return ready;
      await waitForPoll(delay, signal);
      // Doubling to 640 ms hears an ordinary derivation soon after it lands. One still pending after
      // seconds is queued behind others or stuck -- a daemon that waits two minutes for a worker that
      // never announces itself -- and is asked at a tenth of the wait so far, at most every 5 s. At
      // 640 ms the first parts of a cold open asked 1,500 times in those two minutes, every ask a host
      // call in the CAD app, before the failure came back.
      delay = Math.min(MAX_PENDING_POLL_MS,
        Math.max(Math.min(MAX_POLL_MS, delay * 2), (Date.now() - startedAt) / 10));
    }
  } finally {
    signal?.removeEventListener("abort", cancel);
    if (signal?.aborted) cancel();
  }
}
