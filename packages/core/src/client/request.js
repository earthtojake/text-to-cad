// Preserve request context across the artifact hook. A transport failure is not a
// compiler diagnosis; callers can explain it without guessing what the server did.
export class ViewerRequestError extends Error {
  constructor(failure, cause) {
    super(failure.detail, { cause });
    this.name = "ViewerRequestError";
    this.failure = failure;
  }
}

export function serverErrorMessage(payload) {
  const value = payload?.error || payload?.result?.error || payload?.result?.validation?.error;
  if (typeof value === "string") return value.trim();
  return String(value?.message || payload?.message || payload?.reason || "").trim();
}

/**
 * A response's JSON, with `onProgress` called as each part of its body arrives and once more,
 * with `true`, when the last has. A body the runtime cannot stream is read whole.
 */
function readJson(response, onProgress) {
  const body = response.body;
  if (!onProgress || typeof body?.pipeThrough !== "function" || typeof TransformStream !== "function" || typeof Response !== "function") {
    return response.json();
  }
  const watched = body.pipeThrough(new TransformStream({
    transform(chunk, controller) { onProgress(false); controller.enqueue(chunk); },
    flush() { onProgress(true); }
  }));
  return new Response(watched).json();
}

/**
 * One request to the viewer, answered as JSON. A GET given `timeoutMs` is bounded by how long the
 * server stays SILENT, never by how long the answer takes: the bound runs until the response's
 * headers arrive, and then again from each part of its body to the next, and stops when the body
 * is in (parsing it is this page's work, not the server's). A server that stopped answering still
 * fails, and an answer that is long, or long to arrive a part at a time, does not.
 */
export async function requestViewerJson(url, options, operation, { timeoutMs = 0, fetch: fetchImpl = globalThis.fetch } = {}) {
  const requestUrl = typeof window !== "undefined" && window.location?.href
    ? new URL(url, window.location.href).href : url;
  const context = { operation, url: requestUrl, method: options?.method || "GET" };
  const parentSignal = options?.signal;
  const timed = Number(timeoutMs) > 0 && context.method === "GET";
  const controller = timed ? new AbortController() : null;
  const seconds = Math.round(Number(timeoutMs) / 1000);
  // What a timeout says: the server never answered, or it stopped part way through its answer.
  let timedOut = "";
  let timer = 0;
  const arm = (detail) => {
    if (timer) globalThis.clearTimeout(timer);
    timer = globalThis.setTimeout(() => {
      timedOut = detail;
      controller.abort(new DOMException("Viewer request timed out", "TimeoutError"));
    }, Number(timeoutMs));
  };
  const disarm = () => {
    if (timer) globalThis.clearTimeout(timer);
    timer = 0;
  };
  const abortFromParent = () => controller?.abort(parentSignal?.reason);
  if (controller && parentSignal) {
    if (parentSignal.aborted) abortFromParent();
    else parentSignal.addEventListener("abort", abortFromParent, { once: true });
  }
  if (controller) arm(`The server did not respond within ${seconds} seconds.`);
  const requestOptions = controller ? { ...options, signal: controller.signal } : options;
  let response;
  try {
    parentSignal?.throwIfAborted();
    response = await fetchImpl(url, requestOptions);
    parentSignal?.throwIfAborted();
  } catch (cause) {
    disarm();
    parentSignal?.removeEventListener?.("abort", abortFromParent);
    if (parentSignal?.aborted) throw cause;
    if (timedOut) throw new ViewerRequestError({ ...context, kind: "timeout", detail: timedOut }, cause);
    if (cause?.name === "AbortError") throw cause;
    throw new ViewerRequestError({ ...context, kind: "network", detail: String(cause?.message || cause) }, cause);
  }
  let payload;
  try {
    const stalled = `The server stopped sending its answer for ${seconds} seconds.`;
    if (controller) arm(stalled);
    payload = await readJson(response, controller ? (finished) => (finished ? disarm() : arm(stalled)) : null);
    parentSignal?.throwIfAborted();
  } catch (cause) {
    if (parentSignal?.aborted) throw cause;
    if (timedOut) throw new ViewerRequestError({ ...context, kind: "timeout", detail: timedOut }, cause);
    if (cause?.name === "AbortError") throw cause;
    throw new ViewerRequestError({
      ...context, kind: response.ok ? "response" : "http", status: response.status,
      detail: response.ok ? "The server returned an unreadable JSON response." : `HTTP ${response.status} ${response.statusText}`.trim()
    }, cause);
  } finally {
    disarm();
    parentSignal?.removeEventListener?.("abort", abortFromParent);
  }
  if (!response.ok) {
    throw new ViewerRequestError({
      ...context, kind: payload?.state === "failed" ? "compile" : "http", status: response.status,
      detail: serverErrorMessage(payload) || `HTTP ${response.status} ${response.statusText}`.trim()
    });
  }
  return payload;
}
