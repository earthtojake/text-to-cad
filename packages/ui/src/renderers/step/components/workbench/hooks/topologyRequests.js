// The part ids a viewer's topology requests name, as sets: pure helpers for the request
// session in useCadAssets (loadReferencesForEntry), split out so they unit-test in Node.

function idList(ids) {
  return (Array.isArray(ids) ? ids : [])
    .map((id) => String(id || "").trim())
    .filter(Boolean);
}

export function sameTopologyIds(a, b) {
  const left = new Set(idList(a));
  const right = new Set(idList(b));
  return left.size === right.size && [...left].every((id) => right.has(id));
}

// Whether every id of `ids` is one of `within`.
export function topologyIdsWithin(ids, within) {
  const allowed = new Set(idList(within));
  return idList(ids).every((id) => allowed.has(id));
}

// What one batch composes: every requested part already loaded (a part no longer requested drops
// out), and up to `budget` requested parts that are not, the most recently requested first
// (`requestOrder`: id -> a number that grows with each new request).
export function chooseTopologyBatch(requestedIds, loadedIds, { budget = Infinity, requestOrder = null } = {}) {
  const loaded = new Set(idList(loadedIds));
  const kept = [];
  let missing = [];
  for (const id of new Set(idList(requestedIds))) {
    (loaded.has(id) ? kept : missing).push(id);
  }
  if (missing.length > budget) {
    missing = missing
      .map((id, index) => ({ id, index, order: Number(requestOrder?.get(id)) || 0 }))
      .sort((a, b) => (b.order - a.order) || (a.index - b.index))
      .slice(0, Math.max(0, budget))
      .map(({ id }) => id);
  }
  return [...kept, ...missing];
}

// One file revision's topology requests (useCadAssets' loadReferencesForEntry drives it).
// `request(ids)` names the parts wanted now; requests union into this session and never abort its
// work. A bulk loop runs batches — what is published and still wanted, plus up to `budget` new
// parts, newest first — at most every `intervalMs` (the first at once), until what is published
// is what is wanted. Parts wanted after a bulk batch started and not in it load beside it in a
// small priority batch (`priorityBudget`), so a single new part is not held behind a big batch.
//
// `loadBatch(ids)` loads and composes a batch, then — synchronously with its own publication —
// asks `accepts(ids)` and, when accepted, calls `publish(ids, state)`. It resolves "published",
// "skipped" or "stale" (the session was cancelled). A batch is accepted when everything in it is
// still wanted and it keeps every wanted part already published: publication only ever adds what
// is wanted and drops what is not.
export function createTopologyRequestSession({
  loadBatch,
  isCurrent,
  onLoading = () => {},
  onSettled = () => {},
  onFailed = async () => {},
  published = null,
  intervalMs = 150,
  budget = 64,
  priorityBudget = 8,
  now = () => Date.now(),
  wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
}) {
  const session = {
    desired: [],
    published,
    requestOrder: new Map(),
    requestCount: 0,
    active: false,
    running: null,
    bulkBatch: null,
    priorityActive: false,
    lastStart: -Infinity,
    failed: false,
    batches: 0,
  };
  const satisfied = () => Boolean(session.published && (session.published.whole || sameTopologyIds(session.published.ids, session.desired)));
  const priorityIds = () => {
    const done = new Set(session.published?.ids || []);
    const waiting = session.desired.filter((id) => !done.has(id) && !session.bulkBatch?.has(id));
    return chooseTopologyBatch(waiting, [], { budget: priorityBudget, requestOrder: session.requestOrder });
  };

  async function runBulk() {
    session.active = true;
    try {
      while (isCurrent()) {
        if (satisfied()) break;
        const remaining = session.lastStart + intervalMs - now();
        if (remaining > 0) {
          await wait(remaining);
          continue;
        }
        session.lastStart = now();
        const batch = chooseTopologyBatch(session.desired, session.published?.ids, { budget, requestOrder: session.requestOrder });
        session.bulkBatch = new Set(batch);
        const outcome = await loadBatch(batch);
        session.bulkBatch = null;
        if (outcome === "stale") return;
      }
      if (isCurrent()) onSettled(session.published?.state || null);
    } catch (error) {
      session.failed = true;
      await onFailed(error);
    } finally {
      session.bulkBatch = null;
      session.active = false;
    }
  }

  async function runPriority() {
    session.priorityActive = true;
    try {
      while (isCurrent() && session.bulkBatch) {
        const picked = priorityIds();
        if (!picked.length) break;
        const done = new Set(session.published?.ids || []);
        if ((await loadBatch([...session.desired.filter((id) => done.has(id)), ...picked])) === "stale") return;
      }
    } catch (error) {
      session.failed = true;
      await onFailed(error);
    } finally {
      session.priorityActive = false;
    }
  }

  session.accepts = (ids) => {
    const wanted = new Set(session.desired);
    if (!topologyIdsWithin(ids, session.desired)) return false;
    return !session.published || topologyIdsWithin(session.published.ids.filter((id) => wanted.has(id)), ids);
  };
  session.publish = (ids, state, { whole = false } = {}) => {
    session.published = { ids: [...ids], state, ...(whole ? { whole: true } : {}) };
    session.batches += 1;
  };
  session.satisfied = satisfied;
  session.request = (ids) => {
    const desired = new Set();
    for (const rawId of Array.isArray(ids) ? ids : []) {
      const id = String(rawId || "").trim();
      if (!id || desired.has(id)) continue;
      desired.add(id);
      if (!session.requestOrder.has(id)) session.requestOrder.set(id, ++session.requestCount);
    }
    session.desired = [...desired];
    if (session.active) {
      if (!session.priorityActive && session.bulkBatch && priorityIds().length) runPriority();
      return { started: false, settled: false, promise: session.running };
    }
    if (satisfied()) return { started: false, settled: true, promise: Promise.resolve() };
    onLoading();
    session.running = runBulk();
    return { started: true, settled: false, promise: session.running };
  };
  return session;
}
