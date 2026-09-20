import { afterViewPaint, viewPreparationKey, viewUpdateLabel } from './viewUpdatePlan.js';

// One active operation and one replaceable target. Owns no user settings, React,
// Three objects or DOM. Completion must never write back into desired state.
export function createViewUpdateCoordinator(initial, {
  prepare, apply, present, onStatus = () => {}, yieldPaint = afterViewPaint,
}) {
  let applied = initial, visible = initial, desired = initial;
  let revision = 0, running = false, disposed = false, active = null, failure = null;
  const waiters = new Set();
  function status(pending, error = null) {
    onStatus({ pending, error, label: pending ? viewUpdateLabel(visible, desired) : '', revision });
  }
  function settle(error) {
    for (const waiter of waiters) error ? waiter.reject(error) : waiter.resolve();
    waiters.clear();
  }
  async function drain() {
    if (running || disposed) return;
    running = true;
    try {
      while (!disposed && visible !== desired) {
        const target = desired, token = revision;
        const expensive = viewPreparationKey(applied) !== viewPreparationKey(target);
        const controller = active = new AbortController();
        status(true);
        await yieldPaint();
        if (disposed || token !== revision) continue;
        if (expensive) await prepare(target, controller.signal);
        if (disposed || token !== revision) continue;
        // Reconciliation is serial even when superseded. Keep track of the real
        // scene, but present it only if it still matches the latest request.
        await apply(target, { revision: token, expensive });
        applied = target;
        if (disposed || token !== revision) continue;
        await present(token);
        visible = target;
      }
    } catch (error) {
      if (!disposed && !active?.signal.aborted) {
        failure = error;
        status(false, String(error?.message || error));
        settle(error);
      }
    } finally {
      active = null;
      running = false;
      if (!disposed && !failure) {
        // Returning to the already-visible recipe can cancel all preparation.
        if (visible === desired && applied === desired) { status(false); settle(); }
        else {
          // A superseded reconciliation changed the hidden scene. It must be
          // restored even if the requested recipe is the old visible one.
          if (visible === desired) visible = null;
          void drain();
        }
      }
    }
  }
  return {
    request(next) {
      if (disposed || next === desired) return;
      desired = next; revision++; failure = null; active?.abort();
      void drain();
    },
    whenReady() {
      if (disposed) return Promise.reject(new Error('Viewer closed'));
      if (failure) return Promise.reject(failure);
      if (!running && visible === desired) return Promise.resolve();
      return new Promise((resolve, reject) => waiters.add({ resolve, reject }));
    },
    retry() { failure = null; revision++; void drain(); },
    dispose() { disposed = true; active?.abort(); settle(new Error('Viewer closed')); },
  };
}
