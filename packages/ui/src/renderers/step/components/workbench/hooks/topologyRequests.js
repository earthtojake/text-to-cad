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
//
// A part whose topology could not be loaded is published as `failed`, never among the `ids`: it
// settles the request it failed in, so the loop does not ask for it again and again, and the next
// request (`request`) asks for it afresh.
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
    // Every `request` call: what a part's failure is current for.
    requests: 0,
  };
  // The parts that failed in the current request; none once a later request asks again.
  const failedNow = () => new Set(session.published?.requests === session.requests ? session.published.failed || [] : []);
  // What the loop asks for: every wanted part but those that failed in the current request.
  const asking = () => {
    const failed = failedNow();
    return session.desired.filter((id) => !failed.has(id));
  };
  const satisfied = () => {
    const published = session.published;
    if (!published) return false;
    if (published.whole) return true;
    if (published.failed?.length && published.requests !== session.requests) return false;
    return sameTopologyIds(published.ids, asking());
  };
  const priorityIds = () => {
    const done = new Set([...(session.published?.ids || []), ...failedNow()]);
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
        const batch = chooseTopologyBatch(asking(), session.published?.ids, { budget, requestOrder: session.requestOrder });
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
  session.publish = (ids, state, { whole = false, failed = [] } = {}) => {
    // A failure stands for the rest of its request, beside those of the request's earlier batches.
    const loaded = new Set(ids);
    const failures = new Set([...failedNow(), ...failed].filter((id) => !loaded.has(id)));
    session.published = { ids: [...ids], state, failed: [...failures], requests: session.requests,
      ...(whole ? { whole: true } : {}) };
    session.batches += 1;
  };
  session.satisfied = satisfied;
  session.request = (ids) => {
    session.requests += 1;
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
