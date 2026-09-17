import { viewerOriginUrl } from "@hardcore/core/client";
const DIGEST_RE = /^[0-9a-f]{64}$/;
const INITIAL_POLL_MS = 80;
const MAX_POLL_MS = 640;

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

async function guardedPost(path, body, { signal, client } = {}) {
  if (client) {
    const payload = await (path.endsWith("/cancel") ? client.cancelSurfaceRequest(body, { signal }) : client.requestSurfaces(body, { signal }));
    return { json: async () => payload };
  }
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json", "x-cadgen-viewer": "1" },
    body: JSON.stringify(body),
    signal,
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = "";
    try { detail = String((await response.json())?.error || ""); } catch { /* response is not JSON */ }
    throw new Error(detail || `Surface request failed (${response.status})`);
  }
  return response;
}

function verifiedReadyRow(row, { tree, cid, surfaceInput, client }) {
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
  return Object.freeze({
    surfaceInput,
    surfaceObject,
    surfUrl: client ? viewerOriginUrl(client.origin, `${parsed.pathname}${parsed.search}`) : `${parsed.pathname}${parsed.search}`,
    byteLength,
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
 * Resolve exact SURF objects for one frozen runtime view. A fully warm TESS
 * path does not call this function. The request never computes D or producer
 * identity in JavaScript; it forwards the backend-prepared opaque pins.
 */
export async function resolveSurfaceComponents(descriptor, requested, { signal, client } = {}) {
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

  const base = { tree, viewId, producer, components };
  let job = "";
  let cancelled = false;
  const cancel = () => {
    if (cancelled || !job) return;
    cancelled = true;
    void guardedPost("/__cad/surfaces/cancel", { job }, { client }).catch(() => {});
  };
  signal?.addEventListener("abort", cancel);
  let delay = INITIAL_POLL_MS;
  try {
    for (;;) {
      if (signal?.aborted) throw abortError();
      const response = await guardedPost("/__cad/surfaces", { ...base, ...(job ? { job } : {}) }, { signal, client });
      const payload = await response.json();
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
        if (signal?.aborted) {
          cancel();
          throw abortError();
        }
      }
      const ready = new Map();
      let pending = false;
      for (const request of components) {
        const row = payload.components[request.cid];
        if (!row || row.surfaceInput !== request.surfaceInput) {
          throw new Error(`Surface response omitted ${request.cid}`);
        }
        if (row.state === "failed") {
          throw new SurfaceResolutionError(String(row.error || `Surface derivation failed for ${request.cid}`), {
            code: String(row.code || ""), cid: request.cid,
          });
        }
        if (row.state === "pending") {
          const rowJob = String(row.job || job || "");
          if (!rowJob || (job && rowJob !== job)) throw new Error("Surface response has an invalid subscriber token");
          job = rowJob;
          pending = true;
          continue;
        }
        const ticket = verifiedReadyRow(row, { tree, ...request, client });
        if (request.expectedSurfaceObject && ticket.surfaceObject !== request.expectedSurfaceObject) {
          throw new Error(`Surface response changed the pinned object for ${request.cid}`);
        }
        ready.set(request.cid, ticket);
      }
      if (!pending) return ready;
      await waitForPoll(delay, signal);
      delay = Math.min(MAX_POLL_MS, delay * 2);
    }
  } finally {
    signal?.removeEventListener("abort", cancel);
    if (signal?.aborted) cancel();
  }
}
