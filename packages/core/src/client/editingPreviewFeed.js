// One request at a time per editing tab. A server that holds it until the build
// ledger changes (the CAD Viewer's, for up to a second) paces the feed itself; one
// that answers at once is paced here. That is a host relaying requests through a
// few slots all its views share, where a held request would take one. An answer
// with nothing new waits out the rest of a second; news is asked after again within
// a tenth of one.
// The heartbeat still revalidates missing objects and actual saved bytes.
const IDLE_MS = 1000;
const NEWS_MS = 100;

export function observeEditingPreview(file, onUpdate, onError, {
  client,
  schedule = globalThis.setTimeout,
  cancel = globalThis.clearTimeout,
  now = () => Date.now(),
} = {}) {
  if (!client) throw new TypeError("Editing preview requires a CAD workspace service");
  const controller = new AbortController();
  let timer;
  let cursor = null;
  const poll = async () => {
    const asked = now();
    let delay = 500;
    try {
      const next = await client.editingPreview(file, { after: cursor || "", signal: controller.signal });
      if (controller.signal.aborted) return;
      const previous = cursor;
      cursor = typeof next.feedCursor === "string" ? next.feedCursor : null;
      // Coalesce bursty progress (at most ten answers a second, and never at frame
      // rate). A missing daemon uses the slower retry without starting work or spinning.
      delay = cursor && !next.feedLimited
        ? Math.max(16, (cursor === previous ? IDLE_MS : NEWS_MS) - (now() - asked))
        : 500;
      onUpdate(next);
    } catch (error) {
      if (controller.signal.aborted) return;
      cursor = null;
      onError(error);
    }
    if (!controller.signal.aborted) timer = schedule(poll, delay);
  };
  poll();
  return () => { controller.abort(); cancel(timer); };
}
