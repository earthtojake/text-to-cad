// Browser init script: worker-isolate ownership independent of the app ledger.
export function installWorkerProbe() {
  const OriginalWorker = window.Worker;
  if (typeof OriginalWorker !== 'function') return;
  const stats = { created: 0, terminated: 0, live: 0, peakLive: 0 };
  window.__cadWorkerProbe = stats;
  const terminated = new WeakSet();
  window.Worker = class extends OriginalWorker {
    constructor(...args) {
      super(...args);
      stats.created += 1;
      stats.live += 1;
      stats.peakLive = Math.max(stats.peakLive, stats.live);
    }
    terminate() {
      if (!terminated.has(this)) {
        terminated.add(this);
        stats.terminated += 1;
        stats.live -= 1;
      }
      return super.terminate();
    }
  };
}
