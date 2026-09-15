// One held request per editing tab. The server wakes it on a ledger change;
// the heartbeat still revalidates missing objects and actual saved bytes.
export function observeEditingPreview(file, onUpdate, onError, {
  fetchImpl = globalThis.fetch,
  schedule = globalThis.setTimeout,
  cancel = globalThis.clearTimeout,
} = {}) {
  const controller = new AbortController();
  let timer;
  let cursor = null;
  const poll = async () => {
    let delay = 500;
    try {
      const query = new URLSearchParams({ file });
      if (cursor) query.set("after", cursor);
      const response = await fetchImpl(`/__cad/preview?${query}`, {
        signal: controller.signal, cache: "no-store",
      });
      if (!response.ok) throw new Error("Editing preview is unavailable");
      const next = await response.json();
      if (controller.signal.aborted) return;
      cursor = typeof next.feedCursor === "string" ? next.feedCursor : null;
      // Coalesce bursty progress to at most one response per frame. A missing
      // daemon uses the slower retry without starting work or spinning.
      delay = cursor && !next.feedLimited ? 16 : 500;
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
