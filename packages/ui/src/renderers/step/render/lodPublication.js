export function publishedLodContext(context) {
  return context?.lodPending && context.lodPending.phase !== "restoring"
    ? { ...context, ...context.lodPending.maps, meshData: context.lodPending.source } : context;
}

// React may evaluate an updater more than once, or abandon its render. The
// receipt travels in state and is acknowledged only by the committed layout
// effect. Retired commands cannot publish again when React replays the queue.
export function updateLodMeshState(previous, update, command = null) {
  if (command?.retired) return previous;
  const value = typeof update === "function" ? update(previous.value) : update;
  if (!command) return value === previous.value ? previous : {
    ...previous, value, receipt: previous.receipt?.command.receipted ? null : previous.receipt,
  };
  const accepted = value?.meshData === command.source;
  return { ...previous, value,
    reference: accepted && command.reference !== undefined ? command.reference : previous.reference,
    receipt: { command, accepted } };
}

export function updateLodReferenceState(previous, update) {
  const reference = typeof update === "function" ? update(previous.reference) : update;
  return reference === previous.reference ? previous : {
    ...previous, reference, receipt: previous.receipt?.command.receipted ? null : previous.receipt,
  };
}

function retireCommand(command) {
  if (!command) return;
  command.retired = true;
  command.source = null;
  command.reference = null;
}

// Abort is a cleanup request, not proof that a published source stopped being
// owned. One size-one publication keeps its old/new data until the renderer
// confirms adoption, restoration, or full disposal.
export function createLodPublication({ currentContext, now = () => performance.now() }) {
  let pending = null;
  const stats = { requested: 0, adopted: 0, restored: 0, rejected: 0, lastWaitMs: 0, maxWaitMs: 0 };
  const isCurrent = request => currentContext() === request.context && request.context?.meshHash === request.revision &&
    (!request.context?.descriptor || request.context.descriptor === request.descriptor);
  function settle(request, status) {
    if (pending !== request) return false;
    pending = null;
    retireCommand(request.command);
    request.signal?.removeEventListener("abort", request.abort);
    stats.lastWaitMs = Math.max(0, now() - request.startedAt);
    stats.maxWaitMs = Math.max(stats.maxWaitMs, stats.lastWaitMs);
    stats[status === "adopted" ? "adopted" : status === "restored" ? "restored" : "rejected"]++;
    try { request.onSettled?.(status); }
    finally { request.resolve({ status }); }
    return true;
  }
  function cancel() {
    const request = pending;
    if (!request) return;
    request.cancelled = true;
    if (!request.published) settle(request, "cancelled");
  }
  return {
    expect(spec) {
      if (pending) throw new Error("LOD publication still owns an unsettled scene");
      stats.requested++;
      return new Promise(resolve => {
        const request = { ...spec, revision: spec.context?.meshHash, resolve,
          phase: "candidate", published: false, cancelled: false, startedAt: now(), abort: cancel };
        pending = request;
        if (spec.signal?.aborted || !isCurrent(request)) cancel();
        else spec.signal?.addEventListener("abort", request.abort, { once: true });
      });
    },
    published(source) {
      if (pending && pending.source === source) pending.published = true;
    },
    committed(receipt) {
      if (receipt) receipt.command.receipted = true;
      if (receipt && pending?.command === receipt.command && !receipt.accepted && !pending.sceneOwned && !pending.cleanupFailed) {
        settle(pending, pending.phase === "restoring" && !pending.cancelled && isCurrent(pending)
          ? "disposed-failed" : "cancelled");
      }
    },
    adopted(source) {
      const request = pending;
      if (!request) return true;
      if (request.cleanupFailed) return false;
      if (request.phase === "restoring" && request.matchesBase?.(source)) {
        settle(request, request.cancelled || !isCurrent(request) ? "cancelled" : "restored");
        return true;
      }
      // A previously queued layout effect can still report the old scene
      // before the candidate commits. This is neither rollback nor disposal.
      if (request.matchesBase?.(source) || request.recognizesBase?.(source)) return true;
      if (request.matchesCandidate(source)) {
        request.commit?.(source);
        settle(request, request.cancelled || !isCurrent(request) ? "cancelled" : "adopted");
        return true;
      }
      // A known earlier progressive publication does not replace this
      // request's latest queued source, even after cancellation. Its actual
      // disposal or the latest publication will finish that ownership.
      if (request.recognizesCandidate?.(source)) { request.sceneOwned = true; return true; }
      if (request.cancelled || !isCurrent(request)) {
        // Another source actually adopted by this renderer replaces the old
        // scene, even if the retiring request no longer has an active context.
        settle(request, "cancelled");
        return true;
      }
      return false;
    },
    disposed(source, { recover = false, terminal = false, handoff = false } = {}) {
      const request = pending;
      if (!request) return;
      // A no-op clear from a stale render proves nothing about a queued
      // candidate. Only the owning renderer's final teardown can certify an
      // empty scene without a source identity.
      if (!source && !terminal) return;
      if (source && source !== request.source && source !== request.baseSource &&
          !request.matchesCandidate(source) && !request.matchesBase?.(source) &&
          !request.recognizesCandidate?.(source) && !request.recognizesBase?.(source)) return;
      // Inspect/Render use different WebGL runtimes. Disposing the old
      // runtime is a handoff while this model context remains current: the
      // replacement runtime will acknowledge the already-queued candidate or
      // restoration. Treating that planned teardown as a scene failure stops
      // every remaining refinement before the replacement can adopt it.
      // A failed cleanup is never a handoff; it keeps the ordinary fatal
      // ownership path below.
      if (handoff && !request.cleanupFailed && !request.cancelled && isCurrent(request)) {
        request.sceneOwned = false;
        return;
      }
      request.cleanupFailed = false;
      request.sceneOwned = false;
      if (request.phase === "restoring") {
        if (request.cancelled || !isCurrent(request)) settle(request, "cancelled");
        else {
          try { request.failed?.(); }
          finally { settle(request, "disposed-failed"); }
        }
      } else if (!recover || request.cancelled || !isCurrent(request)) {
        if (request.cancelled || !isCurrent(request)) settle(request, "cancelled");
        else {
          try { request.failed?.(); }
          finally { settle(request, "disposed-failed"); }
        }
      } else {
        request.phase = "restoring";
        retireCommand(request.command);
        request.command = { retired: false, source: null };
        try {
          const base = request.restore?.(request.command);
          if (!base) throw new Error("Previous LOD source is unavailable");
          request.baseSource = base;
        } catch {
          try { request.failed?.(); }
          finally { settle(request, "disposed-failed"); }
        }
      }
    },
    failed(source, { cleanupFailed = false } = {}) {
      if (pending && (pending.matchesCandidate(source) || pending.recognizesCandidate?.(source) || pending.matchesBase?.(source))) {
        pending.sceneOwned = true;
        if (cleanupFailed) pending.cleanupFailed = true;
      }
      return false; // failure alone never releases ownership
    },
    checkContext() { if (pending && !isCurrent(pending)) cancel(); },
    cancel,
    snapshot: () => ({ ...stats, pending: Number(!!pending), phase: pending?.cleanupFailed ? "cleanup-failed" : pending?.phase || null,
      pendingMs: pending ? Math.max(0, now() - pending.startedAt) : 0 }),
  };
}
